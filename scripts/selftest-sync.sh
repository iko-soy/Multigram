#!/usr/bin/env bash
# Self-test for sync-forkgram.sh and export-patches.sh. Builds a fake Forkgram remote and a
# fake MultiGram remote in a temporary folder (nothing touches GitHub or your clone) and
# runs the sync through its cases: no new release, --force, a release that applies, a
# release that conflicts, the hand fix (rerere, a multigram-next the sync must not replace,
# --use-next and the check that it carries all of multigram), promote, the .github guard,
# a missing multigram branch, local branches that must not move, merge commits, a full
# clone that must stay full, and the patch export.
#
#   bash scripts/selftest-sync.sh [--keep]     (--keep leaves the folder for a look)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SYNC=$HERE/sync-forkgram.sh
EXPORT=$HERE/export-patches.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/multigram-selftest.XXXXXX")
KEEP=no
[ "${1:-}" != --keep ] || KEEP=yes
trap '[ $KEEP = yes ] && echo "left in $T" || rm -rf "$T"' EXIT

# A clean git setup, whatever the user's own config says.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=$T/gitconfig
git config --global user.name "Self Test"
git config --global user.email selftest@example.invalid
git config --global init.defaultBranch main
git config --global advice.detachedHead false
unset GITHUB_ACTIONS GITHUB_OUTPUT GITHUB_STEP_SUMMARY RUNNER_TEMP FORKGRAM_URL FORKGRAM_BRANCH || true
export FORKGRAM_URL=file://$T/forkgram.git FORKGRAM_BRANCH=dev

PASS=0
FAIL=0
ok() { PASS=$((PASS + 1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$1"; }
eq() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1: got [$2], want [$3]"; fi; }
has() { case $2 in *"$3"*) ok "$1" ;; *) bad "$1: [$3] not in [$2]" ;; esac; }
title() { printf '\n== %s\n' "$*"; }

# Runs the sync script; keeps its exit code in RC and its outputs in $T/out.
run() { # dir args...
  local d=$1
  shift
  : >"$T/out"
  RC=0
  (cd "$d" && GITHUB_OUTPUT=$T/out bash "$SYNC" "$@") >"$T/log" 2>&1 || RC=$?
  sed -e '/^---- outputs ----$/,$d' -e 's/^/    | /' "$T/log"
}
o() { # key -> value from the last run's outputs
  python3 - "$T/out" "$1" <<'PY'
import sys
path, key = sys.argv[1], sys.argv[2]
lines = open(path).read().split('\n')
vals, i = {}, 0
while i < len(lines):
    line = lines[i]
    if '<<' in line:
        k, d = line.split('<<', 1)
        j = lines.index(d, i + 1)
        vals[k] = '\n'.join(lines[i + 1:j])
        i = j + 1
    else:
        i += 1
print(vals.get(key, ''), end='')
PY
}
rref() { git --git-dir="$T/multigram.git" rev-parse -q --verify "$1" || true; }

# ------------------------------------------------------------------ fake Forkgram

git init -q --bare "$T/forkgram.git"
git --git-dir="$T/forkgram.git" config uploadpack.allowFilter true
git --git-dir="$T/forkgram.git" config uploadpack.allowAnySHA1InWant true
git init -q "$T/fg"
cd "$T/fg"

main_java() { # name line, tail line
  printf 'class Main {\n  String name = "%s";\n  int a = 1;\n  int b = 2;\n  int c = 3;\n  int d = 4;\n  // %s\n}\n' "$1" "$2"
}
props() { printf 'APP_VERSION_CODE=%s\nAPP_VERSION_NAME=%s\nAPP_PACKAGE=org.example\n' "$1" "$2"; }
gitlink() { git update-index --add --cacheinfo "160000,$1,$2"; }
subst() { sed "$1" "$2" >"$2.new" && mv "$2.new" "$2"; } # sed -i, on any sed
setver() { subst "s/^APP_VERSION_NAME=.*/APP_VERSION_NAME=$1/" gradle.properties; }
upstream() { # version code name tail sublink : a Telegram "update to" commit
  mkdir -p app
  props "$2" "$1" >gradle.properties
  main_java "$3" "$4" >app/Main.java
  printf 'class Util {}\n' >app/Util.java
  printf '[submodule "lib/sub"]\n\tpath = lib/sub\n\turl = https://example.invalid/sub.git\n[submodule "topsub"]\n\tpath = topsub\n\turl = https://example.invalid/top.git\n' >.gitmodules
  git add -A
  gitlink "$5" lib/sub
  gitlink 2222222222222222222222222222222222222222 topsub
  git commit -q -m "update to $1 ($2)"
}
fork_commits() { # version : Forkgram's own commits, then the release commit
  mkdir -p .github/workflows
  printf 'on: push\n' >.github/workflows/ci.yml
  printf 'class Fork {}\n' >app/Fork.java
  git add -A
  git commit -q -m "Added fork settings."
  setver "$1"
  printf '// release %s\n' "$1" >>app/Fork.java
  git commit -q -am "[Release] $1."
}

upstream 1.0.0 100 Fork "end" 1111111111111111111111111111111111111111
fork_commits 1.0.1
git push -q "$T/forkgram.git" HEAD:refs/heads/dev
R1=$(git rev-parse HEAD)
U1=$(git rev-parse HEAD~2)

# ------------------------------------------------------------------ fake MultiGram

git init -q --bare "$T/multigram.git"
git --git-dir="$T/multigram.git" config uploadpack.allowFilter true
git --git-dir="$T/multigram.git" config uploadpack.allowAnySHA1InWant true
git init -q "$T/mgsetup"
cd "$T/mgsetup"
git fetch -q "$T/forkgram.git" dev
tree=$(git ls-tree FETCH_HEAD | grep -v "	.github$" | git mktree)
S1=$(printf 'Forkgram 1.0.1 snapshot\n\nSource: https://github.com/forkgram/TelegramAndroid/commit/%s\nForkgram-Commit: %s\nForkgram-Version: 1.0.1\nTelegram-Base: %s (update to 1.0.0)\n\nTree is Forkgram'"'"'s dev branch at that commit with the .github folder removed.\n' "$R1" "$R1" "$U1" | git commit-tree "$tree")
git switch -q -c multigram "$S1"
mkdir -p multigram
printf 'MultiGram notes\n' >multigram/README.md
git add -A && git commit -q -m "Add MultiGram notes"
subst 's/"Fork"/"MultiGram"/' app/Main.java
git commit -q -am "Rename the app"
printf 'class Util { /* MultiGram: hook */ }\n' >app/Util.java
git commit -q -am "Add a MultiGram hook"
git switch -q --orphan main
printf 'main\n' >README.md
git add README.md && git commit -q -m "Start main"
git push -q "$T/multigram.git" main "$S1:refs/heads/forkgram" multigram
MG0=$(rref multigram)

# "CI": a blobless, depth-1 clone of main, like actions/checkout with filter: blob:none.
ci_clone() {
  rm -rf "$T/ci"
  git clone -q --filter=blob:none --depth 1 --branch main "file://$T/multigram.git" "$T/ci"
  git -C "$T/ci" config user.name "github-actions[bot]"
  git -C "$T/ci" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
}

# ------------------------------------------------------------------ A: no new release
title "A. No new Forkgram release"
ci_clone
run "$T/ci" --remote origin --push
eq "exit code" "$RC" 0
eq "status" "$(o status)" up-to-date
eq "new_snapshot" "$(o new_snapshot)" no
eq "forkgram unchanged" "$(rref forkgram)" "$S1"
eq "no multigram-next" "$(rref multigram-next)" ""

# ------------------------------------------------------------------ B: --force
title "B. --force with no new release, then promote"
ci_clone
run "$T/ci" --remote origin --push --force
eq "exit code" "$RC" 0
eq "status" "$(o status)" candidate
eq "new_snapshot" "$(o new_snapshot)" no
eq "candidate is multigram (nothing to replay)" "$(o candidate)" "$MG0"
eq "multigram-next pushed" "$(rref multigram-next)" "$MG0"
eq "pushed" "$(o pushed)" multigram-next
cand=$(o candidate) prev=$(o multigram) tv=$(o tag_version)
ci_clone
run "$T/ci" promote --remote origin --candidate "$cand" --previous "$prev" --version "$tv" --shallow
eq "promote exit code" "$RC" 0
eq "promote status" "$(o status)" unchanged
eq "multigram unchanged" "$(rref multigram)" "$MG0"
eq "multigram-next deleted" "$(rref multigram-next)" ""

# ------------------------------------------------------------------ C: clean release
title "C. New Forkgram release 1.1.0 that applies cleanly"
cd "$T/fg"
git reset -q --hard "$U1"
printf 'class Other {}\n' >app/Other.java
git add -A
upstream 1.1.0 110 Fork "end, 1.1.0" 3333333333333333333333333333333333333333
U2=$(git rev-parse HEAD)
fork_commits 1.1.0
R2=$(git rev-parse HEAD)
git push -q -f "$T/forkgram.git" HEAD:refs/heads/dev
ci_clone
run "$T/ci" --remote origin --push
eq "exit code" "$RC" 0
eq "status" "$(o status)" candidate
eq "new_snapshot" "$(o new_snapshot)" yes
eq "forkgram_commit" "$(o forkgram_commit)" "$R2"
eq "forkgram_version" "$(o forkgram_version)" 1.1.0
eq "telegram_base" "$(o telegram_base)" "$U2 (update to 1.1.0)"
eq "previous_version" "$(o previous_version)" 1.0.1
S2=$(rref forkgram)
eq "forkgram pushed" "$S2" "$(o snapshot)"
eq "snapshot parent is the previous snapshot" "$(git --git-dir="$T/multigram.git" rev-parse "$S2^")" "$S1"
eq "snapshot has no .github" "$(git --git-dir="$T/multigram.git" ls-tree --name-only "$S2" .github)" ""
want=$(git -C "$T/fg" ls-tree "$R2" | grep -v "	.github$")
eq "snapshot tree = Forkgram tree minus .github" "$(git --git-dir="$T/multigram.git" ls-tree "$S2")" "$want"
eq "gitlink lib/sub kept" "$(git --git-dir="$T/multigram.git" ls-tree "$S2" lib/sub | cut -f1)" "160000 commit 3333333333333333333333333333333333333333"
eq "gitlink topsub kept" "$(git --git-dir="$T/multigram.git" ls-tree "$S2" topsub | cut -f1)" "160000 commit 2222222222222222222222222222222222222222"
msg=$(git --git-dir="$T/multigram.git" log -1 --format=%B "$S2")
has "message title" "$msg" "Forkgram 1.1.0 snapshot"
has "message Source" "$msg" "Source: file://$T/forkgram.git (dev) at $R2"
has "message Forkgram-Commit" "$msg" "Forkgram-Commit: $R2"
has "message Forkgram-Version" "$msg" "Forkgram-Version: 1.1.0"
has "message Telegram-Base" "$msg" "Telegram-Base: $U2 (update to 1.1.0)"
has "message tail" "$msg" "Tree is Forkgram's dev branch at that commit with the .github folder removed."
C1=$(rref multigram-next)
eq "multigram-next = candidate" "$C1" "$(o candidate)"
eq "candidate has 3 commits on the snapshot" "$(git --git-dir="$T/multigram.git" rev-list --count "$S2..$C1")" 3
eq "candidate subjects" "$(git --git-dir="$T/multigram.git" log --reverse --format=%s "$S2..$C1" | tr '\n' '|')" "Add MultiGram notes|Rename the app|Add a MultiGram hook|"
eq "candidate Main.java: stack change on the new upstream" "$(git --git-dir="$T/multigram.git" show "$C1:app/Main.java" | sed -n '2p;7p' | tr '\n' '|')" '  String name = "MultiGram";|  // end, 1.1.0|'
eq "candidate keeps upstream's new file" "$(git --git-dir="$T/multigram.git" show "$C1:app/Other.java")" "class Other {}"
eq "candidate tree = snapshot + stack diff" \
  "$(git --git-dir="$T/multigram.git" diff --stat "$S2" "$C1" | tail -n1)" \
  "$(git --git-dir="$T/multigram.git" diff --stat "$S1" "$MG0" | tail -n1)"
eq "multigram not moved yet" "$(rref multigram)" "$MG0"
eq "the sync recorded the multigram-next it built" "$(rref refs/multigram-sync/next)" "$C1"
cand=$(o candidate) prev=$(o multigram) tv=$(o tag_version)
ci_clone
run "$T/ci" promote --remote origin --candidate "$cand" --previous "$prev" --version "$tv" --shallow
eq "promote exit code" "$RC" 0
eq "promote status" "$(o status)" promoted
eq "multigram moved to the candidate" "$(rref multigram)" "$C1"
eq "old multigram tagged" "$(rref refs/tags/multigram-before-1.1.0)" "$MG0"
eq "multigram-next deleted" "$(rref multigram-next)" ""

# ------------------------------------------------------------------ D: conflicting release
title "D. New Forkgram release 1.2.0 that conflicts"
cd "$T/fg"
git reset -q --hard "$U2"
upstream 1.2.0 120 "Fork 2" "end, 1.1.0" 3333333333333333333333333333333333333333
fork_commits 1.2.0
R3=$(git rev-parse HEAD)
git push -q -f "$T/forkgram.git" HEAD:refs/heads/dev
MG1=$(rref multigram)
ci_clone
run "$T/ci" --remote origin --push
eq "exit code" "$RC" 2
eq "status" "$(o status)" conflict
S3=$(rref forkgram)
eq "snapshot pushed anyway" "$S3" "$(o snapshot)"
eq "forkgram_version" "$(o forkgram_version)" 1.2.0
eq "conflict commit is the rename" "$(o conflict_commit)" "$(git --git-dir="$T/multigram.git" rev-parse "$MG1~1")"
eq "conflict subject" "$(o conflict_subject)" "Rename the app"
eq "conflict position" "$(o conflict_position)" "2 of 3"
eq "conflict files" "$(o conflict_files)" app/Main.java
eq "conflict details" "$(o conflict_details)" "changed on both sides: app/Main.java"
eq "multigram untouched" "$(rref multigram)" "$MG1"
eq "no multigram-next" "$(rref multigram-next)" ""
eq "no candidate" "$(o candidate)" ""
eq "pushed" "$(o pushed)" forkgram

# ------------------------------------------------------------------ E: behind
title "E. Next run, no new release: multigram is behind"
ci_clone
run "$T/ci" --remote origin --push
eq "exit code" "$RC" 0
eq "status" "$(o status)" behind
eq "multigram_base is the old snapshot" "$(o multigram_base)" "$S2"
eq "nothing pushed" "$(o pushed)" ""

# ------------------------------------------------------------------ F: hand fix with rerere
title "F. Hand fix in a local clone; rerere replays it on the next local run"
git clone -q "file://$T/multigram.git" "$T/owner"
cd "$T/owner"
git config rerere.enabled true
git switch -q -C multigram-next origin/multigram
if git rebase -q --onto "$S3" "$S2" >/dev/null 2>&1; then bad "hand rebase should conflict"; fi
main_java "MultiGram 2" "end, 1.1.0" >app/Main.java
git add app/Main.java
GIT_EDITOR=true git rebase --continue >/dev/null 2>&1
FIX=$(git rev-parse HEAD)
eq "hand fix has 3 commits on the new snapshot" "$(git rev-list --count "$S3..$FIX")" 3
git switch -q --detach
git branch -q -D multigram-next
# The owner's own branches, with rebase.updateRefs on: the replay must not move them.
git config rebase.updateRefs true
git branch -q -f multigram origin/multigram
git branch -q -f wip origin/multigram~1
run "$T/owner" --remote origin --force
git config --unset rebase.updateRefs
eq "exit code" "$RC" 0
eq "status" "$(o status)" candidate
eq "local multigram not moved (rebase.updateRefs)" "$(git rev-parse multigram)" "$MG1"
eq "local wip not moved (rebase.updateRefs)" "$(git rev-parse wip)" "$(git rev-parse "$MG1~1")"
eq "local record = local multigram-next" "$(git rev-parse refs/multigram-sync/next)" "$(git rev-parse multigram-next)"
has "rerere_resolved names the file" "$(o rerere_resolved)" "app/Main.java"
eq "local multigram-next has the recorded resolution" "$(git show multigram-next:app/Main.java | sed -n 2p)" '  String name = "MultiGram 2";'
eq "same tree as the hand fix" "$(git rev-parse "multigram-next^{tree}")" "$(git rev-parse "$FIX^{tree}")"
eq "local forkgram = latest snapshot" "$(git rev-parse forkgram)" "$S3"
eq "nothing pushed without --push" "$(rref multigram-next)" ""

# ------------------------------------------------------------------ G: --use-next
title "G. The hand fix on multigram-next: never replaced; --use-next checks it, then promote"
git push -q -f origin "$FIX:refs/heads/multigram-next"
ci_clone
run "$T/ci" --remote origin --push --force
eq "--force: exit code" "$RC" 0
eq "--force: status" "$(o status)" next-edited
eq "--force: existing_next" "$(o existing_next)" "$FIX"
eq "--force: multigram-next kept" "$(rref multigram-next)" "$FIX"
eq "--force: nothing pushed" "$(o pushed)" ""
cd "$T/fg"
setver 1.2.1
git commit -q -am "[Release] 1.2.1."
git push -q -f "$T/forkgram.git" HEAD:refs/heads/dev
ci_clone
run "$T/ci" --remote origin --push
eq "new release: status" "$(o status)" next-edited
eq "new release: forkgram_tip is the new commit" "$(o forkgram_tip)" "$(git -C "$T/fg" rev-parse HEAD)"
eq "new release: no new snapshot" "$(rref forkgram)" "$S3"
eq "new release: multigram-next kept" "$(rref multigram-next)" "$FIX"
has "new release: message says why" "$(o message)" "has commits the sync did not make"
git reset -q --hard "$R3"
git push -q -f "$T/forkgram.git" HEAD:refs/heads/dev
cd "$T/owner"
git fetch -q origin
git switch -q -C late origin/multigram
printf 'late\n' >app/Late.java
git add -A && GIT_AUTHOR_DATE="2030-01-01T00:00:00Z" git commit -q -m "Late MultiGram commit"
LATE=$(git rev-parse HEAD)
git push -q origin late:multigram
git switch -q --detach
git branch -q -D late
ci_clone
run "$T/ci" --remote origin --push --use-next
eq "late commit: exit code" "$RC" 1
eq "late commit: status" "$(o status)" error
eq "late commit: missing" "$(o missing)" "$LATE Late MultiGram commit"
has "late commit: error names it" "$(o error)" "Late MultiGram commit"
has "late commit: error offers allow_drop" "$(o error)" "allow_drop"
ci_clone
run "$T/ci" --remote origin --push --use-next --allow-drop
eq "--allow-drop: status" "$(o status)" candidate
eq "--allow-drop: dropped" "$(o dropped)" "$LATE Late MultiGram commit"
ci_clone
run "$T/ci" --remote origin --push --allow-drop
eq "--allow-drop without --use-next: exit code" "$RC" 1
git -C "$T/owner" push -q -f origin "$MG1:refs/heads/multigram"
ci_clone
run "$T/ci" --remote origin --push --use-next
eq "exit code" "$RC" 0
eq "status" "$(o status)" candidate
eq "candidate is the hand fix" "$(o candidate)" "$FIX"
eq "the hand fix carries the whole stack" "$(o missing)$(o dropped)" ""
eq "forkgram_version" "$(o forkgram_version)" 1.2.0
cand=$(o candidate) prev=$(o multigram) tv=$(o tag_version)
ci_clone
run "$T/ci" promote --remote origin --candidate "$cand" --previous "$prev" --version "$tv" --shallow
eq "promote status" "$(o status)" promoted
eq "multigram = hand fix" "$(rref multigram)" "$FIX"
eq "tag" "$(rref refs/tags/multigram-before-1.2.0)" "$MG1"
ci_clone
run "$T/ci" --remote origin --push
eq "and now up to date" "$(o status)" up-to-date

# ------------------------------------------------------------------ H: dropped commit
title "H. Release 1.3.0 already has one MultiGram change: that commit is dropped"
cd "$T/fg"
git reset -q --hard "$R3"
mkdir -p multigram && printf 'MultiGram notes\n' >multigram/README.md
git add -A && git commit -q -m "Take the notes file"
setver 1.3.0
git commit -q -am "[Release] 1.3.0."
git push -q -f "$T/forkgram.git" HEAD:refs/heads/dev
ci_clone
run "$T/ci" --remote origin --push
eq "status" "$(o status)" candidate
eq "telegram_base still found" "$(o telegram_base)" "$(git -C "$T/fg" rev-parse "HEAD~4") (update to 1.2.0)"
eq "stack_count" "$(o stack_count)" 3
eq "candidate_count" "$(o candidate_count)" 2
if [ -n "$(o dropped)" ]; then ok "dropped is reported"; else bad "dropped is empty"; fi
cand=$(o candidate) prev=$(o multigram) tv=$(o tag_version)

# ------------------------------------------------------------------ I: promote lease
title "I. Promote refuses when multigram moved after the sync"
cd "$T/owner"
git fetch -q origin
git commit -q --allow-empty -m "Someone else's commit" && git push -q -f origin "HEAD:refs/heads/multigram"
ci_clone
run "$T/ci" promote --remote origin --candidate "$cand" --previous "$prev" --version "$tv" --shallow
eq "exit code" "$RC" 1
eq "status" "$(o status)" error
has "error says why" "$(o error)" "pushed to meanwhile"
eq "multigram-next kept" "$(rref multigram-next)" "$cand"
git push -q -f origin "$prev:refs/heads/multigram"
ci_clone
run "$T/ci" promote --remote origin --candidate "$cand" --previous "$prev" --version "$tv" --shallow
eq "promote after restoring multigram" "$(o status)" promoted

# ------------------------------------------------------------------ J: .github guard
title "J. A stack commit that adds .github is refused"
cd "$T/owner"
git fetch -q origin
git switch -q -C multigram origin/multigram
mkdir -p .github && printf 'x\n' >.github/extra.yml
git add -A && git commit -q -m "Add a workflow file"
git push -q -f origin multigram
BAD=$(git rev-parse HEAD)
F_BEFORE=$(rref forkgram)
ci_clone
run "$T/ci" --remote origin --push --force
eq "exit code" "$RC" 1
eq "status" "$(o status)" error
has "error names .github" "$(o error)" ".github"
eq "nothing pushed" "$(rref multigram-next)" ""
eq "forkgram unchanged" "$(rref forkgram)" "$F_BEFORE"
git push -q -f origin "$BAD~1:refs/heads/multigram"
git switch -q --detach

# ------------------------------------------------------------------ K: guards
title "K. Guards: branch checked out, no multigram branch"
git switch -q -C forkgram origin/forkgram
run "$T/owner" --force
eq "checked-out forkgram: exit code" "$RC" 1
has "checked-out forkgram: error" "$(o error)" "checked out in a worktree"
git switch -q --detach
git init -q --bare "$T/empty.git"
git -C "$T/owner" push -q "$T/empty.git" "origin/forkgram:refs/heads/forkgram"
git -C "$T/owner" remote add empty "$T/empty.git"
run "$T/owner" --remote empty --push
eq "no multigram: exit code" "$RC" 1
has "no multigram: error" "$(o error)" "has no multigram branch yet"
run "$T/owner" --remote empty --use-next --force
eq "--force with --use-next: exit code" "$RC" 1
git fetch -q origin
UNPUSHED=$(git commit-tree -p origin/multigram -m "Unpushed fix" "origin/multigram^{tree}")
git branch -q -f multigram-next "$UNPUSHED"
F_BEFORE=$(git rev-parse forkgram)
run "$T/owner" --remote origin --force
eq "unpushed local multigram-next: exit code" "$RC" 1
has "unpushed local multigram-next: error" "$(o error)" "on no other branch or tag"
eq "unpushed local multigram-next: not moved" "$(git rev-parse multigram-next)" "$UNPUSHED"
eq "unpushed local multigram-next: local forkgram not moved" "$(git rev-parse forkgram)" "$F_BEFORE"
git branch -q -D multigram-next

# ------------------------------------------------------------------ L: local mode
title "L. Local branches, no remote"
cd "$T/owner"
git fetch -q origin
git branch -q -f forkgram origin/forkgram
git branch -q -f multigram origin/multigram
run "$T/owner"
eq "status" "$(o status)" up-to-date
HAND=$(git commit-tree -p multigram -m "Hand fix" "multigram^{tree}")
git branch -q -f multigram-next "$HAND"
run "$T/owner" --force
eq "hand-made local multigram-next: exit code" "$RC" 0
eq "hand-made local multigram-next: status" "$(o status)" next-edited
eq "hand-made local multigram-next: kept" "$(git rev-parse multigram-next)" "$HAND"
git branch -q -D multigram-next

# ------------------------------------------------------------------ M: export-patches
title "M. export-patches.sh, applied onto a plain Forkgram checkout with git am -3"
cd "$T/owner"
EXP_RC=0
bash "$EXPORT" --base origin/forkgram --head origin/multigram "$T/patches" >"$T/log" 2>&1 || EXP_RC=$?
sed 's/^/    | /' "$T/log" | head -n 8
eq "export exit code" "$EXP_RC" 0
eq "patch files" "$(cd "$T/patches" && ls ./*.patch | wc -l | tr -d ' ')" 2
if [ -f "$T/patches/APPLY.txt" ]; then ok "APPLY.txt written"; else bad "APPLY.txt missing"; fi
has "APPLY.txt names the Forkgram commit" "$(cat "$T/patches/APPLY.txt")" "$(git -C "$T/fg" rev-parse HEAD)"
git clone -q -b dev "$T/forkgram.git" "$T/plain"
cd "$T/plain"
git switch -q -c multigram
if git am -q -3 "$T/patches"/*.patch >/dev/null 2>&1; then ok "git am -3 applies"; else bad "git am -3 failed"; fi
eq "result = multigram + Forkgram's .github" \
  "$(git ls-tree -r HEAD | grep -v '	.github/')" \
  "$(git -C "$T/owner" ls-tree -r origin/multigram)"
EXP_RC=0
bash "$EXPORT" --base origin/forkgram --head origin/multigram "$T/patches" >/dev/null 2>&1 || EXP_RC=$?
eq "refuses a non-empty folder without --force" "$EXP_RC" 1

# ------------------------------------------------------------------ N: Forkgram already fetched
title "N. Forkgram's tip already in the local clone; a history too short for Telegram-Base"
cd "$T/fg"
printf 'class Later {}\n' >app/Later.java
git add -A && git commit -q -m "Added a later feature."
setver 1.5.0
git commit -q -am "[Release] 1.5.0."
git push -q -f "$T/forkgram.git" HEAD:refs/heads/dev
R5=$(git rev-parse HEAD)
git clone -q "file://$T/multigram.git" "$T/full"
run "$T/full" --remote origin
eq "full clone: status" "$(o status)" candidate
has "full clone: fetched into a scratch repository" "$(cat "$T/log")" "into a scratch repository"
eq "full clone: still not shallow" "$(git -C "$T/full" rev-parse --is-shallow-repository)" false
eq "full clone: snapshot tree" "$(git -C "$T/full" ls-tree forkgram)" "$(git -C "$T/fg" ls-tree "$R5" | grep -v "	.github$")"
eq "full clone: version from gradle.properties" "$(o forkgram_version)" 1.5.0
if git -C "$T/full" fsck --no-progress >"$T/fsck" 2>&1; then ok "full clone: fsck is clean"; else bad "full clone: fsck: $(head -n 3 "$T/fsck")"; fi
cd "$T/owner"
git fetch -q "$T/forkgram.git" "+refs/heads/dev:refs/forkgram-full/dev"
git fetch -q origin
git branch -q -f forkgram origin/forkgram
git branch -q -f multigram origin/multigram
FORKGRAM_HISTORY_DEPTH=1 run "$T/owner" --remote origin
eq "status" "$(o status)" candidate
has "used the local copy" "$(cat "$T/log")" "already here"
eq "no Telegram-Base when the history is too short" "$(o telegram_base)" ""
if git log -1 --format=%B forkgram | grep -q '^Telegram-Base:'; then bad "Telegram-Base line written"; else ok "no Telegram-Base line"; fi
eq "snapshot tree" "$(git ls-tree forkgram)" "$(git ls-tree "$R5" | grep -v "	.github$")"
eq "local forkgram is the new snapshot, origin untouched" "$(git rev-parse forkgram^)" "$(rref forkgram)"
eq "not a shallow repository" "$(git rev-parse --is-shallow-repository)" false

# ------------------------------------------------------------------ O: tag already taken
title "O. A second promotion for the same Forkgram version gets its own tag"
cd "$T/owner"
git fetch -q origin
git switch -q -C multigram-next origin/multigram
printf 'more\n' >>multigram/README.md 2>/dev/null || { mkdir -p multigram; printf 'more\n' >multigram/README.md; }
git add -A && git commit -q -m "Another MultiGram change"
git push -q -f origin multigram-next
git switch -q --detach
ci_clone
run "$T/ci" --remote origin --push --use-next
cand=$(o candidate) prev=$(o multigram) tv=$(o tag_version)
eq "same version as the last promotion" "$tv" 1.3.0
ci_clone
run "$T/ci" promote --remote origin --candidate "$cand" --previous "$prev" --version "$tv" --shallow
eq "status" "$(o status)" promoted
eq "tag with a suffix" "$(o tag)" multigram-before-1.3.0-2
eq "tag points at the old multigram" "$(rref refs/tags/multigram-before-1.3.0-2)" "$prev"
eq "first tag untouched" "$(rref refs/tags/multigram-before-1.3.0)" "$FIX"

# ------------------------------------------------------------------ Q: merge commits
title "Q. Merge commits on multigram: a plain merge is flattened, one with its own changes stops the sync"
cd "$T/owner"
git fetch -q origin
MGQ=$(git rev-parse origin/multigram)
git switch -q -C side origin/forkgram
printf 'class Side {}\n' >app/Side.java
git add -A && git commit -q -m "Side feature"
git switch -q -C multigram "$MGQ"
git merge -q --no-ff --no-edit side
git push -q -f origin multigram
run "$T/owner" --remote origin --force
eq "plain merge: exit code" "$RC" 0
eq "plain merge: status" "$(o status)" candidate
has "plain merge: warned" "$(cat "$T/log")" "only join their parents"
eq "plain merge: candidate = snapshot + everything multigram changes" \
  "$(git diff "$(o snapshot)" multigram-next -- | grep -v '^index ')" "$(git diff origin/forkgram multigram -- | grep -v '^index ')"
eq "plain merge: candidate is linear" "$(git rev-list --merges "origin/forkgram..multigram-next")" ""
git reset -q --hard "$MGQ"
git merge -q --no-ff --no-commit side
printf 'class Glue {}\n' >app/Glue.java
git add -A && git commit -q -m "Merge side with glue"
git push -q -f origin multigram
run "$T/owner" --remote origin --force
eq "merge with changes: exit code" "$RC" 1
has "merge with changes: error names it" "$(o error)" "Merge side with glue"
git push -q -f origin "$MGQ:refs/heads/multigram"
git switch -q --detach
git branch -q -D side multigram

# ------------------------------------------------------------------ P: sync-report.py
title "P. sync-report.py against a fake gh"
mkdir -p "$T/bin"
cat >"$T/bin/gh" <<'PY'
#!/usr/bin/env python3
# A tiny stand-in for the gh CLI: keeps issues in a JSON file.
import json, os, sys
path = os.environ['FAKE_GH_STATE']
st = json.load(open(path)) if os.path.exists(path) else {'issues': [], 'labels': []}
a = sys.argv[1:]
def opt(name):
    return a[a.index(name) + 1] if name in a else None
def body():
    f = opt('--body-file')
    return open(f).read() if f else ''
def issue(n):
    return next(i for i in st['issues'] if i['number'] == int(n))
if a[:2] == ['label', 'create']:
    st['labels'].append(a[2])
elif a[:2] == ['issue', 'list']:
    print(json.dumps([{'number': i['number'], 'title': i['title']} for i in st['issues']
                      if i['state'] == 'open' and opt('--label') in i['labels']]))
elif a[:2] == ['issue', 'view']:
    i = issue(a[2])
    print(json.dumps({'body': i['body'], 'comments': [{'body': c} for c in i['comments']]}))
elif a[:2] == ['issue', 'create']:
    if opt('--label') not in st['labels']:
        sys.exit('label missing')
    n = len(st['issues']) + 1
    st['issues'].append({'number': n, 'title': opt('--title'), 'body': body(), 'labels': [opt('--label')],
                         'state': 'open', 'comments': []})
    print(f'https://example.invalid/issues/{n}')
elif a[:2] == ['issue', 'comment']:
    issue(a[2])['comments'].append(body())
elif a[:2] == ['issue', 'edit']:
    issue(a[2])['title'] = opt('--title')
elif a[:2] == ['issue', 'close']:
    i = issue(a[2]); i['state'] = 'closed'; i['comments'].append(opt('--comment'))
else:
    sys.exit('fake gh: unsupported ' + ' '.join(a))
json.dump(st, open(path, 'w'))
PY
chmod +x "$T/bin/gh"
export REPORT_GH=$T/bin/gh FAKE_GH_STATE=$T/gh.json RUN_URL=https://example.invalid/runs/1
report() { # VAR=value... : runs sync-report.py with only these job results and outputs
  env -i PATH="$PATH" REPORT_GH="$REPORT_GH" FAKE_GH_STATE="$FAKE_GH_STATE" RUN_URL="$RUN_URL" "$@" \
    python3 "$HERE/sync-report.py" 2>&1 | sed 's/^/    | /'
}
gh_state() { python3 -c "import json,sys; st=json.load(open('$T/gh.json')); print(eval(sys.argv[1]))" "$1"; }
A40=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa B40=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb C40=cccccccccccccccccccccccccccccccccccccccc
conflict=(SYNC_RESULT=failure COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=conflict
  SYNC_FORKGRAM_VERSION=1.2.0 SYNC_FORKGRAM_COMMIT=$A40 SYNC_SNAPSHOT=$B40 SYNC_PREVIOUS_SNAPSHOT=$C40
  SYNC_CONFLICT_COMMIT=$C40 "SYNC_CONFLICT_SUBJECT=Rename the \`app\`" "SYNC_CONFLICT_POSITION=2 of 3"
  SYNC_CONFLICT_FILES=app/Main.java "SYNC_CONFLICT_DETAILS=changed on both sides: app/Main.java")
report "${conflict[@]}"
eq "conflict opens an issue" "$(gh_state "len(st['issues'])")" 1
eq "issue title" "$(gh_state "st['issues'][0]['title']")" "Forkgram sync needs a hand (Forkgram 1.2.0)"
has "issue body has the rebase command" "$(gh_state "st['issues'][0]['body']")" "git rebase --onto $B40 $C40"
has "issue body has the file" "$(gh_state "st['issues'][0]['body']")" "changed on both sides: app/Main.java"
has "backticks in the subject are neutralised" "$(gh_state "st['issues'][0]['body']")" "Rename the 'app'"
report "${conflict[@]}"
eq "the same conflict is not reported twice" "$(gh_state "len(st['issues'][0]['comments'])")" 0
report SYNC_RESULT=success COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=behind SYNC_FORKGRAM_VERSION=1.2.0
eq "behind with an open issue adds nothing" "$(gh_state "len(st['issues'][0]['comments'])")" 0
report SYNC_RESULT=success COMPILE_RESULT=failure PROMOTE_RESULT=skipped SYNC_STATUS=candidate \
  SYNC_FORKGRAM_VERSION=1.2.0 SYNC_CANDIDATE=$A40 SYNC_SNAPSHOT=$B40
eq "compile failure comments on the open issue" "$(gh_state "len(st['issues'][0]['comments'])")" 1
has "comment has the autosquash fix" "$(gh_state "st['issues'][0]['comments'][0]")" "git rebase -i --autosquash $B40"
next_edited=(SYNC_RESULT=success COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=next-edited
  SYNC_FORKGRAM_VERSION=1.2.0 SYNC_FORKGRAM_COMMIT=$A40 SYNC_FORKGRAM_TIP=$B40 SYNC_EXISTING_NEXT=$C40)
report "${next_edited[@]}"
eq "next-edited comments on the open issue" "$(gh_state "len(st['issues'][0]['comments'])")" 2
has "next-edited comment says what to do" "$(gh_state "st['issues'][0]['comments'][1]")" "use_next"
has "next-edited comment names the new Forkgram commit" "$(gh_state "st['issues'][0]['comments'][1]")" "${B40:0:10}"
report "${next_edited[@]}"
eq "the same next-edited is not reported twice" "$(gh_state "len(st['issues'][0]['comments'])")" 2
report SYNC_RESULT=success COMPILE_RESULT=success PROMOTE_RESULT=success SYNC_STATUS=candidate \
  SYNC_FORKGRAM_VERSION=1.2.0 SYNC_CANDIDATE=$A40 PROMOTE_TAG=multigram-before-1.2.0 "SYNC_DROPPED=$C40 Late \`commit\`"
eq "promotion closes the issue" "$(gh_state "st['issues'][0]['state']")" closed
has "closing note names the tag" "$(gh_state "st['issues'][0]['comments'][-1]")" "multigram-before-1.2.0"
has "closing note lists the dropped commits" "$(gh_state "st['issues'][0]['comments'][-1]")" "$C40 Late 'commit'"
report SYNC_RESULT=success COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=up-to-date SYNC_FORKGRAM_VERSION=1.2.0
eq "up to date with no open issue: nothing" "$(gh_state "len(st['issues'])")" 1
report SYNC_RESULT=failure COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=error "SYNC_ERROR=origin has no multigram branch yet."
eq "a sync error opens a new issue" "$(gh_state "len(st['issues'])")" 2
has "error text in the issue" "$(gh_state "st['issues'][1]['body']")" "origin has no multigram branch yet."
report SYNC_RESULT=cancelled COMPILE_RESULT=skipped PROMOTE_RESULT=skipped
report SYNC_RESULT=success COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=up-to-date SYNC_FORKGRAM_VERSION=1.2.0
eq "in step again closes it" "$(gh_state "st['issues'][1]['state']")" closed
report SYNC_RESULT=success COMPILE_RESULT=skipped PROMOTE_RESULT=skipped SYNC_STATUS=behind SYNC_FORKGRAM_VERSION=1.3.0
eq "behind with no open issue opens one" "$(gh_state "[i['state'] for i in st['issues']]")" "['closed', 'closed', 'open']"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
