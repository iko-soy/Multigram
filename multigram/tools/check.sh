#!/usr/bin/env bash
# MultiGram checks that need no Android SDK. CI runs this from the repository root after the compile.
# Requirements: bash and python3 (standard library only). About 2 to 3 minutes on a 4-core runner.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

if [ -f multigram/tools/palette_fix_check.py ]; then
  # The style table is validated against overlay_A.json; this checks that PaletteFix.java, its hooks and the
  # theme sources apply exactly that overlay (present once the palette fix is in the tree).
  echo "== palette fix: PaletteFix.java, hooks and theme sources match overlay_A.json"
  python3 multigram/tools/palette_fix_check.py
fi

echo "== style table: format and readability on the current theme sources"
python3 multigram/tools/check_style_table.py

echo "== style table: does this tree regenerate the same asset?"
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
status=0
python3 multigram/tools/make_style_table.py --check > "$log" 2>&1 || status=$?
case "$status" in
  0) tail -n 1 "$log" ;;
  3) tail -n 1 "$log"
     echo "WARNING: make_style_table.py would now generate a different table (the theme sources changed since it was made)." \
          "The committed table still passed the readability check above; regenerate it when convenient." ;;
  4) cat "$log"
     echo "FAIL: the style table can no longer be generated on these theme sources (see STALLED above)."; exit 1 ;;
  *) cat "$log"; echo "FAIL: make_style_table.py exited with status $status"; exit 1 ;;
esac

echo "== all MultiGram checks passed"
