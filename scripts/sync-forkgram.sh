#!/usr/bin/env bash
# Keep MultiGram in step with Forkgram.
#
#   scripts/sync-forkgram.sh [sync] [--remote NAME [--push]] [--force | --use-next [--allow-drop]]
#                                   [--url URL] [--branch NAME] [--history-depth N]
#   scripts/sync-forkgram.sh promote --remote NAME --candidate SHA --previous SHA
#                                    --version VERSION [--shallow]
#
# sync (the default)
#   1. Reads the tip of Forkgram's dev branch. If it is the commit the latest "forkgram"
#      snapshot was made from, there is nothing to do (exit 0), unless --force.
#   2. Otherwise it makes a snapshot commit on "forkgram": the tip's tree without the
#      .github folder (.gitmodules and the submodule links stay), parented on the previous
#      snapshot, with the Forkgram-Commit, Forkgram-Version and Telegram-Base lines.
#   3. It replays the MultiGram stack (previous-snapshot..multigram) onto the snapshot with
#      "git rebase --onto", in a temporary worktree, as branch "multigram-next". rerere is on,
#      so conflicts already resolved in this clone are resolved the same way (a fresh CI clone
#      has no recorded resolutions). On a conflict it aborts and reports the stack commit and
#      the files (exit 2). The stack must be linear: a merge commit that carries changes of
#      its own stops the sync, because the replay flattens merges.
#   It never replaces a multigram-next that holds commits it did not make (a fix by hand):
#   it then stops with status next-edited and changes nothing. refs/multigram-sync/next
#   (pushed with multigram-next, and kept locally) records the last multigram-next it built.
#   --remote NAME  read forkgram and multigram from that remote (default: the local branches)
#   --push         push forkgram and multigram-next to NAME (one atomic push, with leases)
#   --force        no new Forkgram release: rebuild multigram-next on the current snapshot
#                  (tests the pipeline, or retries after a failed compile)
#   --use-next     take the multigram-next branch as it is (a stack fixed by hand) as the
#                  candidate; nothing is fetched from Forkgram and nothing is rebuilt. It
#                  must still carry every commit of multigram's stack (matched by author and
#                  subject, or by patch id); --allow-drop accepts one that leaves some out.
#   The results are left in the local branches "forkgram" and "multigram-next". The
#   checked-out worktree is never touched, a branch checked out anywhere is not moved, and
#   a local multigram-next whose commits are on no other branch or tag is not moved either.
#
# promote
#   Moves "multigram" to a candidate that passed the compile check: tags the old tip
#   multigram-before-VERSION, moves multigram with --force-with-lease and deletes
#   multigram-next, in one atomic push. --shallow fetches only the two tips.
#
# Environment: FORKGRAM_URL (default https://github.com/forkgram/TelegramAndroid),
#   FORKGRAM_BRANCH (default dev), FORKGRAM_HISTORY_DEPTH (default 600: how many Forkgram
#   commits to search for Telegram's "update to X" commit; 0 = do not search).
#   When GITHUB_OUTPUT / GITHUB_STEP_SUMMARY are set, the outputs and a summary go there.
#
# Outputs (key=value, printed at the end and appended to $GITHUB_OUTPUT):
#   status          up-to-date | behind | next-edited | candidate | conflict | error   (sync)
#                   promoted | unchanged | error                                     (promote)
#   message         one line for people
#   new_snapshot    yes | no
#   forkgram_commit, forkgram_version, telegram_base, snapshot
#                   the Forkgram commit, its version, its Telegram base and the forkgram
#                   snapshot the candidate is built on (new or current)
#   previous_snapshot, previous_forkgram_commit, previous_version
#                   the forkgram tip before this run
#   multigram       the multigram tip the candidate was built from
#   multigram_base  the snapshot multigram is based on (differs from previous_snapshot
#                   when multigram is behind)
#   stack_count     MultiGram commits on multigram; candidate_count: on multigram-next
#   candidate       multigram-next's commit, empty when there is none
#   existing_next   the multigram-next this run found (next-edited: the one it left alone)
#   tag_version     the version, safe for a tag name
#   dropped         MultiGram commits the candidate leaves out ("sha subject" lines with
#                   --allow-drop, else git's lines about commits Forkgram already has)
#   missing         --use-next without --allow-drop: the commits multigram-next lacks
#   rerere_resolved conflicts resolved from recorded resolutions ("commit path" lines)
#   conflict_commit, conflict_subject, conflict_position,
#   conflict_files (paths), conflict_details ("what happened: path" lines)
#   forkgram_tip    the tip of Forkgram's branch this run saw
#   pushed          the branches pushed; tag (promote): the tag made for the old multigram
#   error           what went wrong
# Exit codes: 0 done (see status), 1 error, 2 conflict.
set -euo pipefail

FORKGRAM_URL=${FORKGRAM_URL:-https://github.com/forkgram/TelegramAndroid}
FORKGRAM_BRANCH=${FORKGRAM_BRANCH:-dev}
FORKGRAM_HISTORY_DEPTH=${FORKGRAM_HISTORY_DEPTH:-600}

FG=forkgram
MG=multigram
NEXT=multigram-next
TIP_REF=refs/multigram-sync/forkgram-tip
REC_REF=refs/multigram-sync/next # the last multigram-next this script built by replaying
export GIT_TERMINAL_PROMPT=0

NL=$'\n'
WORK=
WT=
ERROR_MSG=
OUT_KEYS=()
GITID=()

# ---------------------------------------------------------------- output and logging

log() { printf 'sync: %s\n' "$*" >&2; }

annotate() { # level message
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    local m=$2
    m=${m//'%'/'%25'}; m=${m//$'\r'/'%0D'}; m=${m//$'\n'/'%0A'}
    printf '::%s::%s\n' "$1" "$m"
  else
    printf 'sync: %s: %s\n' "$1" "$2" >&2
  fi
}

warn() { annotate warning "$*"; }

die() {
  ERROR_MSG=$*
  out status error
  out error "$ERROR_MSG"
  out message "$ERROR_MSG"
  exit 1
}

out() { # key value...
  local k=$1 have
  shift
  printf -v "o_$k" '%s' "$*"
  have=" ${OUT_KEYS[*]-} "
  case $have in *" $k "*) ;; *) OUT_KEYS+=("$k") ;; esac
}

get() { local n="o_$1"; printf '%s' "${!n-}"; }

random_hex() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }

# Prints text that may hold other people's words (commit subjects, file names) so that the
# Actions runner does not read it as workflow commands.
print_untrusted() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    local token
    token=$(random_hex)
    printf '::stop-commands::%s\n%s\n::%s::\n' "$token" "$1" "$token"
  else
    printf '%s\n' "$1"
  fi
}

emit_outputs() {
  [ ${#OUT_KEYS[@]} -gt 0 ] || return 0
  local k v delim text=
  delim=ghadelimiter_$(random_hex)
  for k in "${OUT_KEYS[@]}"; do
    v=$(get "$k")
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
      printf '%s<<%s\n%s\n%s\n' "$k" "$delim" "$v" "$delim" >>"$GITHUB_OUTPUT"
    fi
    case $v in
      *$'\n'*) text+="$k:"$'\n'"$(printf '%s\n' "$v" | sed 's/^/    /')"$'\n' ;;
      *) text+="$k=$v"$'\n' ;;
    esac
  done
  print_untrusted "---- outputs ----"$'\n'"${text%$'\n'}"
}

md() { printf '%s' "$1" | tr '`' "'"; } # untrusted text for a Markdown code span or block

write_summary() {
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] && [ ${#OUT_KEYS[@]} -gt 0 ] || return 0
  local k v
  {
    printf '### Forkgram sync: %s\n\n' "$(get status)"
    printf '```text\n%s\n```\n\n' "$(md "$(get message)")"
    printf '| | |\n|---|---|\n'
    for k in forkgram_version forkgram_commit telegram_base new_snapshot snapshot previous_version \
      previous_snapshot forkgram_tip multigram multigram_base stack_count existing_next candidate \
      candidate_count pushed tag; do
      v=$(get "$k")
      [ -z "$v" ] || printf '| %s | `%s` |\n' "$k" "$(md "$v" | tr '|' '/')"
    done
    for k in conflict_commit conflict_subject conflict_position conflict_details dropped missing rerere_resolved error; do
      v=$(get "$k")
      [ -z "$v" ] || printf '\n**%s**\n```text\n%s\n```\n' "$k" "$(md "$v")"
    done
  } >>"$GITHUB_STEP_SUMMARY"
}

cleanup() {
  local rc=$?
  set +e
  if [ -n "$WT" ] && [ -e "$WT" ]; then
    git -C "$WT" rebase --abort >/dev/null 2>&1
    git worktree remove --force "$WT" >/dev/null 2>&1 || { rm -rf "$WT"; git worktree prune; }
  fi
  git update-ref -d "$TIP_REF" >/dev/null 2>&1
  [ -z "$WORK" ] || rm -rf "$WORK"
  if [ $rc -ne 0 ] && [ -z "$(get status)" ]; then
    out status error
    out error "${ERROR_MSG:-the script stopped unexpectedly (exit $rc); see the log above}"
  fi
  if [ "$(get status)" = error ]; then annotate error "$(get error)"; fi
  emit_outputs
  write_summary
  exit $rc
}
trap cleanup EXIT

# ---------------------------------------------------------------- git helpers

short() { git rev-parse --short "$1" 2>/dev/null || printf '%s' "${1:0:10}"; }

enter_repo() {
  local top
  top=$(git rev-parse --show-toplevel 2>/dev/null) || die "Run this inside a clone of the MultiGram repository."
  cd "$top"
  WORK=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/multigram-sync.XXXXXX")
  # Commits made here (the snapshot, the replayed stack) need a committer identity.
  if ! git config user.email >/dev/null 2>&1; then
    GITID=(-c "user.name=MultiGram sync" -c "user.email=multigram-sync@users.noreply.github.com")
  fi
}

# git for the commits this script makes: the fallback identity, and no signing (a local
# signing setup could prompt, or fail, in the middle of the replay).
g() { git -c commit.gpgSign=false ${GITID[@]+"${GITID[@]}"} "$@"; }

remote_ref() { # "ls-remote output" refname -> sha or empty
  printf '%s\n' "$1" | awk -v r="$2" '$2 == r { print $1; exit }'
}

check_free_branches() { # branch... : this script moves these branches
  local list b
  list=$(git worktree list --porcelain)
  for b; do
    if grep -qxF "branch refs/heads/$b" <<<"$list"; then
      die "The branch $b is checked out in a worktree. Switch that worktree to another branch first; this script moves $b."
    fi
  done
}

set_branch() { # branch sha why
  local old
  old=$(git rev-parse -q --verify "refs/heads/$1" || true)
  [ "$old" != "$2" ] || return 0
  git update-ref -m "sync-forkgram: $3" "refs/heads/$1" "$2"
  if [ -n "$old" ]; then
    log "local branch $1: $(short "$old") -> $(short "$2")"
  else
    log "local branch $1: created at $(short "$2")"
  fi
}

# True when replacing multigram-next loses nothing a person made: there is none, it is the
# one this script built last (the record), or multigram already has all of it.
next_is_ours() { # next record multigram
  [ -z "$1" ] || [ "$1" = "$2" ] || git merge-base --is-ancestor "$1" "$3" 2>/dev/null
}

# Stops before the local multigram-next moves away from commits that are on no other
# branch, tag or record (say a fix by hand that was not pushed yet).
check_local_next() { # [the sha it would move to]
  local cur others
  cur=$(git rev-parse -q --verify "refs/heads/$NEXT" || true)
  [ -n "$cur" ] && [ "$cur" != "${1:-}" ] || return 0
  others=$(git for-each-ref --format='%(refname)' --contains "$cur" | grep -vxF "refs/heads/$NEXT" || true)
  [ -n "$others" ] ||
    die "Your local $NEXT ($(short "$cur")) has commits that are on no other branch or tag, so this script does not move it. Push it, or keep it under another name (git branch -m $NEXT <name>), then run again."
}

# Prints "sha subject" for each commit of multigram's stack (base..mg) that the hand-made
# multigram-next (old..next) does not carry. A commit counts as carried when next has one
# with the same author (e-mail and time) and subject, which a rebase, a conflict fix, a
# reword-free fixup or git am all keep, or one with the same patch id.
missing_commits() { # base mg old next
  local f=$WORK/missing
  {
    git log --no-merges --no-color --no-ext-diff --format='commit %H' -p "$3..$4" | git patch-id --stable | awk '{ print "P\t" $1 }'
    git log --no-merges --format='N%x09%ae %at%x09%s' "$3..$4"
    git log --no-merges --no-color --no-ext-diff --format='commit %H' -p "$1..$2" | git patch-id --stable | awk '{ print "Q\t" $2 "\t" $1 }'
    git log --no-merges --reverse --format='M%x09%H%x09%ae %at%x09%s' "$1..$2"
  } >"$f"
  awk -F'\t' '
    $1 == "P" { pid[$2] = 1; next }
    $1 == "N" { k = $0; sub(/^[^\t]*\t/, "", k); have[k] = 1; next }
    $1 == "Q" { mine[$2] = $3; next }
    $1 == "M" {
      k = $0; sub(/^[^\t]*\t[^\t]*\t/, "", k)
      if ((k in have) || (($2 in mine) && (mine[$2] in pid))) next
      s = k; sub(/^[^\t]*\t/, "", s)
      print $2 " " s
    }' "$f"
}

# The replay flattens merge commits (git rebase without --rebase-merges). That loses nothing
# when a merge only joins its parents, so those just get a warning; a merge with changes of
# its own (a conflict fix, glue code) would be lost, so it stops the sync.
check_merges() { # old mg
  local m parents tree bad= clean=0
  for m in $(git rev-list --merges "$1..$2"); do
    parents=$(git rev-list --parents -n 1 "$m" | cut -d' ' -f2-)
    if [ "$(printf '%s\n' $parents | grep -c .)" -eq 2 ] &&
      tree=$(git merge-tree --write-tree --no-messages $parents 2>/dev/null) &&
      [ "${tree%%"$NL"*}" = "$(git rev-parse "$m^{tree}")" ]; then
      clean=$((clean + 1))
      continue
    fi
    bad+="$(short "$m") $(git log -1 --format=%s "$m")$NL"
  done
  if [ -n "$bad" ]; then
    die "$MG has merge commits with changes of their own (the check needs git 2.38 or newer):$NL$bad""The sync replays the stack without merges, so those changes would be lost. Make $MG linear first and keep what the merges added as a commit of its own: git switch -C $MG origin/$MG && git rebase origin/$FG (fix any conflicts), then git restore --source=origin/$MG --staged --worktree :/ && git commit -m 'Keep the changes made in merges', and push it with git push --force-with-lease origin $MG."
  fi
  [ "$clean" -eq 0 ] || warn "$MG has $clean merge commit(s) on top of $FG that only join their parents; the replay flattens them into a linear stack."
}

safe_version() { # prints the version, or "unknown" when it holds odd characters
  if [[ $1 =~ ^[0-9A-Za-z][0-9A-Za-z._+-]{0,39}$ ]]; then printf '%s' "$1"; else printf unknown; fi
}

tag_version() { # version fallback -> a string that is safe in a tag name
  local v
  v=$(printf '%s' "$1" | tr -c '0-9A-Za-z._-' '-')
  if [ "$v" = unknown ] || ! git check-ref-format "refs/tags/multigram-before-$v"; then v=$2; fi
  printf '%s' "$v"
}

has_github() { [ -n "$(git ls-tree --name-only "$1" -- .github)" ]; }

check_no_github() { # from to what : every commit in from..to
  local c
  for c in $(git rev-list "$1..$2"); do
    if has_github "$c"; then
      die "Refusing to go on: $3 would contain a .github folder (commit $(short "$c")). The forkgram snapshots and the MultiGram stack must never carry .github (GITHUB_TOKEN cannot push workflow files, and the workflows live on main)."
    fi
  done
}

# ---------------------------------------------------------------- snapshot helpers

S_COMMIT= S_VERSION= S_BASE=
read_snapshot() { # commit : reads the Forkgram-* lines of a snapshot commit
  local body
  body=$(git log -1 --format=%B "$1")
  S_COMMIT=$(printf '%s\n' "$body" | sed -n 's/^Forkgram-Commit:[[:space:]]*\([0-9a-f]\{40\}\)[[:space:]]*$/\1/p' | tail -n 1)
  S_VERSION=$(printf '%s\n' "$body" | sed -n 's/^Forkgram-Version:[[:space:]]*//p' | tail -n 1 | tr -d '\r')
  S_BASE=$(printf '%s\n' "$body" | sed -n 's/^Telegram-Base:[[:space:]]*//p' | tail -n 1 | tr -d '\r')
  [ -n "$S_COMMIT" ] || return 1
  S_VERSION=$(safe_version "$S_VERSION")
}

forkgram_version() { # tree subject -> APP_VERSION_NAME from gradle.properties, else the "[Release] X." subject
  local v
  v=$(git cat-file -p "$1:gradle.properties" 2>/dev/null |
    sed -n 's/^[[:space:]]*APP_VERSION_NAME[[:space:]]*=[[:space:]]*//p' | tail -n 1 | tr -d '\r' || true)
  v=${v%%[[:space:]]*}
  if [ -z "$v" ]; then
    v=$(printf '%s\n' "$2" | sed -n 's/^\[Release\][[:space:]]*\([0-9][0-9A-Za-z._-]*[0-9A-Za-z]\)\.\{0,1\}[[:space:]]*$/\1/p')
  fi
  safe_version "$v"
}

TBASE=
find_telegram_base() { # tip : sets TBASE to "sha (update to X)" when Forkgram's history shows it
  local tip=$1 hist=$WORK/history.git lines line sha ver
  TBASE=
  [ "$FORKGRAM_HISTORY_DEPTH" -gt 0 ] || return 0
  # Commits only (no trees or files): cheap even a few hundred commits deep.
  if ! git clone --quiet --bare --filter=tree:0 --depth "$FORKGRAM_HISTORY_DEPTH" --single-branch \
    --branch "$FORKGRAM_BRANCH" --no-tags "$FORKGRAM_URL" "$hist" >"$WORK/history.log" 2>&1; then
    warn "Could not read Forkgram's history, so the snapshot has no Telegram-Base line."
    return 0
  fi
  if ! git -C "$hist" cat-file -e "$tip^{commit}" 2>/dev/null; then
    warn "Forkgram's $FORKGRAM_BRANCH moved during the sync, so the snapshot has no Telegram-Base line."
    return 0
  fi
  lines=$(git -C "$hist" log --first-parent --format='%H %s' "$tip")
  line=$(printf '%s\n' "$lines" | grep -m 1 -E '^[0-9a-f]{40} update to [0-9]' || true)
  if [ -z "$line" ]; then
    warn "No Telegram \"update to X\" commit in the last $FORKGRAM_HISTORY_DEPTH Forkgram commits, so the snapshot has no Telegram-Base line."
    return 0
  fi
  sha=${line%% *}
  ver=$(printf '%s\n' "${line#* }" | sed -n 's/^update to \([0-9][0-9A-Za-z._-]*\).*/\1/p')
  TBASE="$sha (update to $(safe_version "$ver"))"
}

source_link() { # commit
  local u=${FORKGRAM_URL%/}
  u=${u%.git}
  case $u in
    https://github.com/*/*) printf '%s/commit/%s' "$u" "$1" ;;
    *) printf '%s (%s) at %s' "$FORKGRAM_URL" "$FORKGRAM_BRANCH" "$1" ;;
  esac
}

snapshot_tree() { # tree -> the same tree without the top-level .github
  local entry
  while IFS= read -r -d '' entry; do
    [ "${entry#*$'\t'}" = .github ] && continue
    printf '%s\0' "$entry"
  done < <(git ls-tree -z "$1") | git mktree -z
}

NEW_SNAPSHOT=
make_snapshot() { # tip tip_tree parent version telegram_base : sets NEW_SNAPSHOT
  local tip=$1 tree msg=$WORK/snapshot-message
  tree=$(snapshot_tree "$2") || die "Could not build the snapshot tree of $tip."
  {
    printf 'Forkgram %s snapshot\n\n' "$4"
    printf 'Source: %s\n' "$(source_link "$tip")"
    printf 'Forkgram-Commit: %s\n' "$tip"
    printf 'Forkgram-Version: %s\n' "$4"
    if [ -n "$5" ]; then printf 'Telegram-Base: %s\n' "$5"; fi
    printf "\\nTree is Forkgram's %s branch at that commit with the .github folder removed.\\n" "$FORKGRAM_BRANCH"
  } >"$msg"
  NEW_SNAPSHOT=$(g commit-tree "$tree" -p "$3" -F "$msg") || die "Could not create the snapshot commit."
}

# Gets Forkgram's tip commit's files into this repository. Sets TIP (the commit, re-read
# from the fetch), TIP_TREE and TIP_SUBJECT.
TIP= TIP_TREE= TIP_SUBJECT=
fetch_tip() { # sha from ls-remote
  local tipgit=(git)
  TIP=$1
  if [ -z "$(git config extensions.partialClone || true)" ] && git cat-file -e "$TIP^{commit}" 2>/dev/null; then
    log "Forkgram ${TIP:0:10} is already here; not fetching it"
  elif [ "$(git rev-parse --is-shallow-repository)" = true ]; then
    # A shallow clone (as in CI) takes one more shallow commit in its stride.
    log "Fetching Forkgram ${TIP:0:10}"
    git fetch --no-tags --quiet --depth=1 "$FORKGRAM_URL" "+refs/heads/$FORKGRAM_BRANCH:$TIP_REF" ||
      die "Could not fetch Forkgram's $FORKGRAM_BRANCH from $FORKGRAM_URL."
    TIP=$(git rev-parse --verify "$TIP_REF^{commit}")
  else
    # A full clone: a shallow fetch would turn it into a shallow repository. Fetch into a
    # scratch repository instead and copy only the tip's tree (its files) into this one.
    log "Fetching Forkgram ${TIP:0:10} (into a scratch repository)"
    tipgit=(git -C "$WORK/tip.git")
    git init --quiet --bare "$WORK/tip.git"
    "${tipgit[@]}" fetch --no-tags --quiet --depth=1 "$FORKGRAM_URL" "+refs/heads/$FORKGRAM_BRANCH:refs/tip" ||
      die "Could not fetch Forkgram's $FORKGRAM_BRANCH from $FORKGRAM_URL."
    TIP=$("${tipgit[@]}" rev-parse --verify "refs/tip^{commit}")
    "${tipgit[@]}" rev-list --objects "$TIP^{tree}" | "${tipgit[@]}" pack-objects --quiet --stdout |
      git index-pack --stdin >/dev/null || die "Could not copy Forkgram's files into this repository."
  fi
  TIP_TREE=$("${tipgit[@]}" rev-parse --verify "$TIP^{tree}")
  TIP_SUBJECT=$("${tipgit[@]}" log -1 --format=%s "$TIP")
}

set_snapshot_outputs() { # snapshot new_snapshot(yes|no)
  read_snapshot "$1" || die "The snapshot $(short "$1") has no Forkgram-Commit line."
  out snapshot "$1"
  out new_snapshot "$2"
  out forkgram_commit "$S_COMMIT"
  out forkgram_version "$S_VERSION"
  out telegram_base "$S_BASE"
  out tag_version "$(tag_version "$S_VERSION" "$(git rev-parse --short=10 "$S_COMMIT" 2>/dev/null || printf '%s' "${S_COMMIT:0:10}")")"
}

# ---------------------------------------------------------------- the replay

rebase_in_progress() {
  local d
  for d in rebase-merge rebase-apply; do
    [ ! -d "$(git -C "$WT" rev-parse --path-format=absolute --git-path "$d")" ] || return 0
  done
  return 1
}

conflict_kinds() { # "stages<TAB>path" lines -> "what happened: path" lines
  awk -F'\t' '{
    k = $1
    if (k == "123") w = "changed on both sides"
    else if (k == "23") w = "added on both sides"
    else if (k == "13") w = "Forkgram deleted it, MultiGram changed it"
    else if (k == "12") w = "MultiGram deleted it, Forkgram changed it"
    else if (k == "2") w = "only on the Forkgram side (rename or delete conflict)"
    else if (k == "3") w = "only on the MultiGram side (rename or delete conflict)"
    else w = "conflict (stages " k ")"
    print w ": " $2
  }'
}

# Replays upstream..tip onto onto in a temporary worktree. Sets REPLAY to "ok" and
# CANDIDATE, or to "conflict" and the conflict_* outputs.
CANDIDATE=
REPLAY=
replay() { # onto upstream tip
  local onto=$1 upstream=$2 tip=$3 rc=0 rounds=0 from=0 stopped unmerged stages files stack pos total resolved
  local rlog=$WORK/rebase.log
  WT=$WORK/replay
  git worktree add --quiet --detach "$WT" "$tip" >"$WORK/worktree.log" 2>&1 ||
    { cat "$WORK/worktree.log" >&2; die "Could not create a temporary worktree for the rebase."; }
  # The caller's git config must not change the replay: no update-refs (it would move the
  # caller's own branches), no merge-preserving rebase, no autostash, no hooks, no signing.
  local rb=(git -C "$WT" -c rerere.enabled=true -c rerere.autoUpdate=true -c rebase.updateRefs=false
    -c rebase.rebaseMerges=false -c rebase.autoStash=false -c rebase.backend=merge
    -c core.hooksPath=/dev/null -c commit.gpgSign=false ${GITID[@]+"${GITID[@]}"})
  log "Replaying $(git rev-list --count "$upstream..$tip") MultiGram commit(s) onto $(short "$onto")"
  # LC_ALL=C: the messages below are read back (rerere and dropped commits).
  GIT_EDITOR=true LC_ALL=C "${rb[@]}" rebase --no-autosquash --empty=drop --onto "$onto" "$upstream" >"$rlog" 2>&1 || rc=$?
  while [ $rc -ne 0 ]; do
    if ! rebase_in_progress; then
      print_untrusted "$(tail -n 40 "$rlog" | tr '\r' '\n')"
      die "git rebase failed without a conflict; see the log above."
    fi
    unmerged=$(git -C "$WT" ls-files -u)
    [ -z "$unmerged" ] || break
    # rerere resolved every conflict of this commit from a recorded resolution: go on.
    stopped=$(git -C "$WT" rev-parse -q --verify REBASE_HEAD || echo unknown)
    resolved=$(tail -c +$((from + 1)) "$rlog" | tr '\r' '\n' |
      sed -n -E "s/^(Resolved|Staged) '(.*)' using previous resolution\.\$/$(short "$stopped") \2/p")
    [ -n "$resolved" ] || resolved="$(short "$stopped") (files not named by git)"
    out rerere_resolved "$(get rerere_resolved)${o_rerere_resolved:+$NL}$resolved"
    rounds=$((rounds + 1))
    [ $rounds -le 1000 ] || die "git rebase keeps stopping; giving up."
    log "rerere resolved the conflicts in $(short "$stopped") from a recorded resolution; continuing"
    rc=0
    from=$(wc -c <"$rlog")
    GIT_EDITOR=true LC_ALL=C "${rb[@]}" rebase --continue >>"$rlog" 2>&1 || rc=$?
  done

  local dropped
  dropped=$(tr '\r' '\n' <"$rlog" | grep -E '^(dropping |warning: skipped previously applied commit)' || true)
  [ -z "$dropped" ] || out dropped "$dropped"

  if [ $rc -eq 0 ]; then
    CANDIDATE=$(git -C "$WT" rev-parse HEAD)
    REPLAY=ok
    return 0
  fi

  stopped=$(git -C "$WT" rev-parse -q --verify REBASE_HEAD || true)
  stages=$(printf '%s\n' "$unmerged" | awk -F'\t' '{ split($1, a, " "); s[$2] = s[$2] a[3] } END { for (p in s) print s[p] "\t" p }' | sort -t "$(printf '\t')" -k 2)
  files=$(printf '%s\n' "$stages" | cut -f 2-)
  stack=$(git rev-list --reverse "$upstream..$tip")
  total=$(printf '%s\n' "$stack" | grep -c . || true)
  pos=$(printf '%s\n' "$stack" | grep -n -x -F "${stopped:-none}" | cut -d: -f1 || true)
  out conflict_commit "$stopped"
  out conflict_subject "$( [ -z "$stopped" ] || git log -1 --format=%s "$stopped")"
  out conflict_position "${pos:-?} of $total"
  out conflict_files "$files"
  out conflict_details "$(printf '%s\n' "$stages" | conflict_kinds)"
  print_untrusted "$(tr '\r' '\n' <"$rlog" | grep -v '^Rebasing (' | tail -n 40)"
  git -C "$WT" rebase --abort >/dev/null 2>&1 || true
  REPLAY=conflict
}

# ---------------------------------------------------------------- sync

sync_main() {
  local remote= push=no force=no use_next=no allow_drop=no
  while [ $# -gt 0 ]; do
    case $1 in
      --remote) remote=${2:?--remote needs a name}; shift 2 ;;
      --remote=*) remote=${1#*=}; shift ;;
      --push) push=yes; shift ;;
      --force) force=yes; shift ;;
      --use-next) use_next=yes; shift ;;
      --allow-drop) allow_drop=yes; shift ;;
      --url) FORKGRAM_URL=${2:?--url needs a URL}; shift 2 ;;
      --url=*) FORKGRAM_URL=${1#*=}; shift ;;
      --branch) FORKGRAM_BRANCH=${2:?--branch needs a name}; shift 2 ;;
      --branch=*) FORKGRAM_BRANCH=${1#*=}; shift ;;
      --history-depth) FORKGRAM_HISTORY_DEPTH=${2:?--history-depth needs a number}; shift 2 ;;
      --history-depth=*) FORKGRAM_HISTORY_DEPTH=${1#*=}; shift ;;
      -h | --help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
      *) die "Unknown option: $1 (see --help)" ;;
    esac
  done
  [ "$push" = no ] || [ -n "$remote" ] || die "--push needs --remote."
  [ "$force" = no ] || [ "$use_next" = no ] || die "--force and --use-next do not go together."
  [ "$allow_drop" = no ] || [ "$use_next" = yes ] || die "--allow-drop only goes with --use-next."
  [[ $FORKGRAM_HISTORY_DEPTH =~ ^[0-9]+$ ]] || die "--history-depth must be a number."
  enter_repo
  check_free_branches "$FG" "$NEXT"

  # 1. Where forkgram, multigram and multigram-next are now, and the multigram-next this
  #    script built last (rec_prev).
  local old mg next_prev= rec_prev=
  if [ -n "$remote" ]; then
    local heads specs what
    heads=$(git ls-remote "$remote" "refs/heads/$FG" "refs/heads/$MG" "refs/heads/$NEXT" "$REC_REF") ||
      die "Could not read the branches of $remote."
    [ -n "$(remote_ref "$heads" "refs/heads/$FG")" ] ||
      die "$remote has no $FG branch. It holds the Forkgram snapshots; create it first (see README.md)."
    [ -n "$(remote_ref "$heads" "refs/heads/$MG")" ] ||
      die "$remote has no $MG branch yet. Create it (the latest $FG snapshot plus the MultiGram commits) and push it; the sync replays that stack and cannot start without it."
    next_prev=$(remote_ref "$heads" "refs/heads/$NEXT")
    rec_prev=$(remote_ref "$heads" "$REC_REF")
    specs=("+refs/heads/$FG:refs/remotes/$remote/$FG" "+refs/heads/$MG:refs/remotes/$remote/$MG")
    what="$FG and $MG"
    if [ -n "$next_prev" ]; then
      specs+=("+refs/heads/$NEXT:refs/remotes/$remote/$NEXT")
      what="$FG, $MG and $NEXT"
    fi
    log "Fetching $what from $remote"
    git fetch --no-tags --quiet "$remote" "${specs[@]}" || die "Could not fetch $what from $remote."
    old=$(git rev-parse --verify "refs/remotes/$remote/$FG^{commit}")
    mg=$(git rev-parse --verify "refs/remotes/$remote/$MG^{commit}")
    [ -z "$next_prev" ] || next_prev=$(git rev-parse --verify "refs/remotes/$remote/$NEXT^{commit}")
  else
    old=$(git rev-parse -q --verify "refs/heads/$FG^{commit}") ||
      die "There is no $FG branch here. It holds the Forkgram snapshots; fetch it or pass --remote."
    mg=$(git rev-parse -q --verify "refs/heads/$MG^{commit}") ||
      die "There is no $MG branch yet. Create it (the latest $FG snapshot plus the MultiGram commits); the sync replays that stack and cannot start without it."
    next_prev=$(git rev-parse -q --verify "refs/heads/$NEXT^{commit}" || true)
    rec_prev=$(git rev-parse -q --verify "$REC_REF^{commit}" || true)
  fi
  out existing_next "$next_prev"

  # 2. The latest snapshot and the stack on top of it.
  read_snapshot "$old" ||
    die "The tip of $FG ($(short "$old")) has no Forkgram-Commit line, so it is not a Forkgram snapshot."
  local old_commit=$S_COMMIT old_version=$S_VERSION base behind stack_count
  out previous_snapshot "$old"
  out previous_forkgram_commit "$old_commit"
  out previous_version "$old_version"
  out multigram "$mg"
  base=$(git merge-base "$old" "$mg") || die "$MG shares no history with $FG."
  out multigram_base "$base"
  if [ "$base" = "$old" ]; then behind=no; else behind=yes; fi
  if [ "$behind" = yes ] && ! read_snapshot "$base"; then
    warn "$MG is based on $(short "$base"), which is not a $FG snapshot."
  fi
  stack_count=$(git rev-list --count "$old..$mg")
  out stack_count "$stack_count"
  [ "$stack_count" -gt 0 ] || warn "$MG has no commits on top of $FG."

  # 3a. A stack fixed by hand, already pushed to multigram-next.
  if [ "$use_next" = yes ]; then
    local missing n
    [ -n "$next_prev" ] || die "There is no $NEXT branch. Push the fixed stack to $NEXT first (see README.md)."
    git merge-base --is-ancestor "$old" "$next_prev" ||
      die "$NEXT is not based on the latest $FG snapshot ($(short "$old"), Forkgram $old_version). Rebase it onto $FG first."
    [ "$next_prev" != "$old" ] || die "$NEXT has no commits on top of $FG."
    set_snapshot_outputs "$old" no
    check_no_github "$old" "$next_prev" "$NEXT"
    # Everything on multigram must still be there: commits pushed to multigram after the fix
    # was started would otherwise leave the app branch at the promotion.
    missing=$(missing_commits "$base" "$mg" "$old" "$next_prev")
    if [ -n "$missing" ]; then
      n=$(printf '%s\n' "$missing" | grep -c .)
      if [ "$allow_drop" = yes ]; then
        out dropped "$missing"
        warn "$NEXT leaves out $n of $MG's commit(s); --allow-drop accepts that (see the dropped output)."
      else
        out missing "$missing"
        die "$NEXT does not carry $n of $MG's commit(s):$NL$missing${NL}They were probably pushed to $MG after the fix on $NEXT was started. Add them to $NEXT (git switch $NEXT && git cherry-pick <commit>...), push it and run with use_next again. If $NEXT leaves them out on purpose (Forkgram has them now, or you folded or dropped them), run use_next with allow_drop (--allow-drop)."
      fi
    fi
    CANDIDATE=$next_prev
    out candidate "$CANDIDATE"
    out candidate_count "$(git rev-list --count "$old..$CANDIDATE")"
    check_local_next "$CANDIDATE"
    set_branch "$FG" "$old" "Forkgram $old_version snapshot"
    set_branch "$NEXT" "$CANDIDATE" "use multigram-next as the candidate"
    out pushed ""
    out status candidate
    out message "Using $NEXT ($(short "$CANDIDATE")) as it is: $(get candidate_count) commit(s) on the Forkgram $old_version snapshot."
    log "$(get message)"
    return 0
  fi

  # 3b. Forkgram's tip.
  local tip new new_snapshot tbase version
  log "Reading $FORKGRAM_URL ($FORKGRAM_BRANCH)"
  tip=$(git ls-remote "$FORKGRAM_URL" "refs/heads/$FORKGRAM_BRANCH") || die "Could not reach Forkgram at $FORKGRAM_URL."
  tip=$(remote_ref "$tip" "refs/heads/$FORKGRAM_BRANCH")
  [ -n "$tip" ] || die "Forkgram has no $FORKGRAM_BRANCH branch at $FORKGRAM_URL."
  out forkgram_tip "$tip"

  if [ "$tip" = "$old_commit" ] && [ "$force" = no ]; then
    set_snapshot_outputs "$old" no
    out candidate ""
    out pushed ""
    if [ "$behind" = no ]; then
      out status up-to-date
      out message "Nothing to do: Forkgram's $FORKGRAM_BRANCH is still $(short "$tip") (Forkgram $old_version), the latest $FG snapshot, and $MG is based on it."
      log "$(get message)"
    else
      out status behind
      out message "No new Forkgram release, but $MG is still based on $(short "$base"), not on the Forkgram $old_version snapshot ($(short "$old")): the last sync could not move it. Fix the stack on $NEXT and run with --use-next, or retry with --force."
      warn "$(get message)"
    fi
    return 0
  fi

  # From here on the run builds a new multigram-next. It never replaces one that holds
  # commits it did not make (a fix by hand): that one waits for --use-next, or for someone
  # to delete it. Nothing is snapshotted meanwhile, so the fix stays based on the latest
  # snapshot and --use-next can take it.
  if ! next_is_ours "$next_prev" "$rec_prev" "$mg"; then
    set_snapshot_outputs "$old" no
    out candidate ""
    out pushed ""
    out status next-edited
    if [ "$tip" = "$old_commit" ]; then
      out message "$NEXT ($(short "$next_prev")) has commits the sync did not make (a fix by hand?), so --force does not replace it. Run with --use-next to compile and promote it, or delete $NEXT to let the sync rebuild it from $MG."
    else
      out message "Forkgram's $FORKGRAM_BRANCH has moved to $(short "$tip"), but $NEXT ($(short "$next_prev")) has commits the sync did not make (a fix by hand?), so the sync changes nothing: no new snapshot, no new $NEXT. Run with --use-next to compile and promote $NEXT, or delete it to let the sync rebuild it from $MG; the next run then takes the new Forkgram commit."
    fi
    warn "$(get message)"
    return 0
  fi
  check_local_next
  check_merges "$old" "$mg"

  if [ "$tip" = "$old_commit" ]; then
    log "No new Forkgram release; --force: rebuilding $NEXT on the current snapshot"
    new=$old
    new_snapshot=no
  else
    fetch_tip "$tip"
    [ "$TIP" != "$old_commit" ] ||
      die "Forkgram's $FORKGRAM_BRANCH moved back to the latest snapshot's commit during the sync; run it again."
    tip=$TIP
    out forkgram_tip "$tip"
    version=$(forkgram_version "$TIP_TREE" "$TIP_SUBJECT")
    [ "$version" != unknown ] || warn "Could not read the Forkgram version (APP_VERSION_NAME in gradle.properties)."
    find_telegram_base "$tip"
    tbase=$TBASE
    make_snapshot "$tip" "$TIP_TREE" "$old" "$version" "$tbase"
    new=$NEW_SNAPSHOT
    new_snapshot=yes
    log "New snapshot $(short "$new"): Forkgram $version ($(short "$tip")), Telegram base: ${tbase:-not found}"
    if [ "$version" = "$old_version" ]; then
      warn "Forkgram's $FORKGRAM_BRANCH moved but its version is still $version."
    fi
  fi
  set_snapshot_outputs "$new" "$new_snapshot"
  version=$(get forkgram_version)
  check_no_github "$old" "$new" "$FG"

  # 4. The replay.
  replay "$new" "$old" "$mg"
  if [ "$REPLAY" = ok ]; then
    check_no_github "$new" "$CANDIDATE" "$NEXT"
    check_local_next "$CANDIDATE"
  fi
  set_branch "$FG" "$new" "Forkgram $version snapshot"
  if [ "$REPLAY" = ok ]; then
    set_branch "$NEXT" "$CANDIDATE" "replay of $MG onto Forkgram $version"
    git update-ref -m "sync-forkgram: the $NEXT it built" "$REC_REF" "$CANDIDATE"
    out candidate "$CANDIDATE"
    out candidate_count "$(git rev-list --count "$new..$CANDIDATE")"
  else
    out candidate ""
  fi

  # 5. The push. refs/multigram-sync/next records the multigram-next the sync built, so a
  #    later run can tell it from one changed by hand.
  local refspecs=() leases=() pushed=()
  if [ "$new_snapshot" = yes ]; then
    refspecs+=("$new:refs/heads/$FG")
    leases+=("--force-with-lease=refs/heads/$FG:$old")
    pushed+=("$FG")
  fi
  if [ -n "$CANDIDATE" ]; then
    refspecs+=("$CANDIDATE:refs/heads/$NEXT" "$CANDIDATE:$REC_REF")
    leases+=("--force-with-lease=refs/heads/$NEXT:$next_prev" "--force-with-lease=$REC_REF:$rec_prev")
    pushed+=("$NEXT")
  fi
  if [ "$push" = yes ] && [ ${#refspecs[@]} -gt 0 ]; then
    log "Pushing ${pushed[*]} to $remote"
    git push --atomic --quiet "${leases[@]}" "$remote" "${refspecs[@]}" || die "The push of ${pushed[*]} to $remote failed."
    out pushed "${pushed[*]}"
  else
    out pushed ""
  fi

  if [ "$REPLAY" = ok ]; then
    out status candidate
    out message "$NEXT ($(short "$CANDIDATE")) is $MG's $(get stack_count) commit(s) replayed onto Forkgram $version ($(short "$(get forkgram_commit)")); $(get candidate_count) commit(s) on top of the snapshot."
    log "$(get message)"
    [ -z "$(get dropped)" ] || warn "Some MultiGram commits were left out because Forkgram already has them; see the dropped output."
    return 0
  fi
  out status conflict
  out message "The MultiGram stack does not apply to Forkgram $version: commit $(short "$(get conflict_commit)") ($(get conflict_position)) conflicts in $(printf '%s\n' "$(get conflict_files)" | grep -c .) file(s). $MG is unchanged."
  annotate error "$(get message)"
  return 2
}

# ---------------------------------------------------------------- promote

promote_main() {
  local remote= cand= prev= version= shallow=no
  while [ $# -gt 0 ]; do
    case $1 in
      --remote) remote=${2:?}; shift 2 ;;
      --candidate) cand=${2:?}; shift 2 ;;
      --previous) prev=${2:?}; shift 2 ;;
      --version) version=${2:?}; shift 2 ;;
      --shallow) shallow=yes; shift ;;
      -h | --help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
      *) die "Unknown option: $1 (see --help)" ;;
    esac
  done
  [ -n "$remote" ] || die "promote needs --remote."
  [[ $cand =~ ^[0-9a-f]{40}$ ]] || die "promote needs --candidate with a full commit id."
  [[ $prev =~ ^[0-9a-f]{40}$ ]] || die "promote needs --previous with a full commit id."
  [[ $version =~ ^[0-9A-Za-z._-]+$ ]] || die "promote needs --version (letters, digits, dot, dash)."
  enter_repo

  local heads now_mg now_next depth=() tag base n existing
  heads=$(git ls-remote "$remote" "refs/heads/$MG" "refs/heads/$NEXT") || die "Could not read the branches of $remote."
  now_mg=$(remote_ref "$heads" "refs/heads/$MG")
  now_next=$(remote_ref "$heads" "refs/heads/$NEXT")
  [ "$now_mg" = "$prev" ] ||
    die "$MG on $remote is ${now_mg:-missing}, not $prev that the candidate was built from: it was pushed to meanwhile. Not promoting."
  [ "$now_next" = "$cand" ] ||
    die "$NEXT on $remote is ${now_next:-missing}, not the compiled candidate $cand. Not promoting."
  [ "$shallow" = no ] || depth=(--depth=1)
  git fetch --no-tags --quiet ${depth[@]+"${depth[@]}"} "$remote" \
    "+refs/heads/$MG:refs/remotes/$remote/$MG" "+refs/heads/$NEXT:refs/remotes/$remote/$NEXT" ||
    die "Could not fetch $MG and $NEXT from $remote."
  ! has_github "$cand" || die "Refusing to promote: the candidate contains a .github folder."
  out candidate "$cand"
  out previous_multigram "$prev"

  if [ "$cand" = "$prev" ]; then
    git push --atomic --quiet "--force-with-lease=refs/heads/$NEXT:$cand" "$remote" ":refs/heads/$NEXT" ||
      die "Could not delete $NEXT on $remote."
    out status unchanged
    out tag ""
    out message "$MG already is the candidate ($(short "$cand")); deleted $NEXT."
    log "$(get message)"
    return 0
  fi

  base=multigram-before-$version
  existing=$(git ls-remote --tags "$remote" "refs/tags/$base*" | awk '{ print $2 }') ||
    die "Could not read the tags of $remote."
  tag=$base
  n=1
  while grep -qxF "refs/tags/$tag" <<<"$existing"; do
    n=$((n + 1))
    tag=$base-$n
  done
  log "Tagging $(short "$prev") as $tag, moving $MG to $(short "$cand"), deleting $NEXT"
  git push --atomic --quiet \
    "--force-with-lease=refs/heads/$MG:$prev" "--force-with-lease=refs/heads/$NEXT:$cand" \
    "$remote" "$cand:refs/heads/$MG" "$prev:refs/tags/$tag" ":refs/heads/$NEXT" ||
    die "The push that moves $MG failed; $MG is unchanged."
  out status promoted
  out tag "$tag"
  out message "$MG moved from $(short "$prev") (tagged $tag) to $(short "$cand"); $NEXT deleted."
  log "$(get message)"
}

cmd=sync
case ${1:-} in
  sync | promote) cmd=$1; shift ;;
esac
# A conflict makes sync_main return 2, which (set -e) ends the script with exit code 2.
"${cmd}_main" "$@"
