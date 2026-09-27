#!/usr/bin/env bash
# Write the MultiGram stack as numbered patches (git format-patch forkgram..multigram) into
# a folder, with APPLY.txt saying how to apply them onto a plain Forkgram checkout.
#
#   scripts/export-patches.sh [--base REF] [--head REF] [--force] [FOLDER]
#
#   --base REF   the snapshot branch (default: forkgram)
#   --head REF   the app branch (default: multigram)
#   --force      replace the patches of an earlier export in FOLDER
#   FOLDER       where to write them (default: multigram-patches)
#
# For branches you have not checked out locally, pass --base origin/forkgram
# --head origin/multigram after a git fetch.
set -euo pipefail

die() { printf 'export-patches: %s\n' "$*" >&2; exit 1; }

base=forkgram head=multigram force=no dir=multigram-patches
while [ $# -gt 0 ]; do
  case $1 in
    --base) base=${2:?--base needs a ref}; shift 2 ;;
    --head) head=${2:?--head needs a ref}; shift 2 ;;
    --force) force=yes; shift ;;
    -h | --help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option: $1 (see --help)" ;;
    *) dir=$1; shift ;;
  esac
done

git rev-parse --git-dir >/dev/null 2>&1 || die "run this inside a clone of the MultiGram repository"
base_c=$(git rev-parse -q --verify "$base^{commit}") || die "no such ref: $base"
head_c=$(git rev-parse -q --verify "$head^{commit}") || die "no such ref: $head"
count=$(git rev-list --count "$base_c..$head_c")
[ "$count" -gt 0 ] || die "$head has no commits on top of $base"
[ -z "$(git rev-list --merges "$base_c..$head_c")" ] ||
  die "$head has merge commits on top of $base; git format-patch cannot export them"

# The snapshot the stack sits on, and the Forkgram commit it was made from.
snap=$(git merge-base "$base_c" "$head_c") || die "$head shares no history with $base"
msg=$(git log -1 --format=%B "$snap")
fg_commit=$(printf '%s\n' "$msg" | sed -n 's/^Forkgram-Commit:[[:space:]]*\([0-9a-f]\{40\}\).*/\1/p' | tail -n 1)
fg_version=$(printf '%s\n' "$msg" | sed -n 's/^Forkgram-Version:[[:space:]]*\([0-9A-Za-z._+-]*\).*/\1/p' | tail -n 1)
[ -n "$fg_commit" ] || die "$(git rev-parse --short "$snap") (where $head meets $base) is not a Forkgram snapshot"
[ -n "$fg_version" ] || fg_version=unknown
if [ "$snap" != "$base_c" ]; then
  printf 'export-patches: note: %s is based on an older snapshot than %s; the patches are for Forkgram %s\n' \
    "$head" "$base" "$fg_version" >&2
fi

mkdir -p "$dir"
if [ -n "$(ls -A "$dir")" ]; then
  [ "$force" = yes ] || die "$dir is not empty (use --force to replace an earlier export)"
  find "$dir" -mindepth 1 -maxdepth 1 \( -name '[0-9][0-9][0-9][0-9]-*.patch' -o -name APPLY.txt \) -exec rm -f {} +
  [ -z "$(ls -A "$dir")" ] || die "$dir holds files this script did not write; pick another folder"
fi

git format-patch --quiet --full-index --binary -o "$dir" "$base_c..$head_c"
abs=$(cd "$dir" && pwd)

cat >"$dir/APPLY.txt" <<EOF
MultiGram patches
=================

$count patch(es): the MultiGram commits of $head ($(git rev-parse --short "$head_c")), made on the
forkgram snapshot $(git rev-parse --short "$snap"), which is Forkgram $fg_version with the .github folder removed:

  Forkgram commit $fg_commit

Apply them onto a plain Forkgram checkout of that commit. Forkgram tags its releases
<version>.0 (so $fg_version.0 here); if the tag is missing, fetch the commit instead.

  git clone --depth 1 --branch $fg_version.0 https://github.com/forkgram/TelegramAndroid.git
  cd TelegramAndroid
  git rev-parse HEAD        # should print $fg_commit
  git switch -c multigram
  git am -3 $abs/*.patch

-3 lets git fall back to a three-way merge when a patch does not apply as it is.
If git am still stops, it names the patch and the files: fix them, "git add" them and
run "git am --continue" (or "git am --skip" to leave that patch out, "git am --abort"
to go back). The same commands work on a newer Forkgram release (expect more stops);
clone without --depth 1 then, so -3 can find the older versions of the files.
EOF

printf '%s\n' "Wrote $count patch(es) and APPLY.txt to $abs"
sed -n '/^  git clone/,/^  git am/p' "$dir/APPLY.txt"
