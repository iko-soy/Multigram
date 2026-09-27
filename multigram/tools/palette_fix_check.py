#!/usr/bin/env python3
"""Check that the MultiGram palette fix (overlay A) is fully applied to this source tree.

Run from the repository root:

    python3 multigram/tools/palette_fix_check.py              # values, key tables and hooks
    python3 multigram/tools/palette_fix_check.py --base REV   # also: nothing else changed vs REV

What it checks, against multigram/palette-fix/overlay_A.json:
  * ThemeColors.createDefaultColors(): the overlay's defaults, except the 12 on-accent content keys,
    which keep their stock value (the on-accent rule sets them at run time for runtime accents).
  * The five bundled .attheme files: the overlay's values.
  * PaletteFix.java: accent exclusions, on-accent pairs (the overlay's 12 plus EXTRA_PAIRS), muted
    pins and muted fill table.
  * The one-line hooks in upstream files.
  * With --base: the diff of ThemeColors.java and the .attheme files against REV touches only the
    lines above.

Standard library only. Exit status 0 when everything matches, 1 otherwise.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SPEC = os.path.join(ROOT, "multigram", "palette-fix", "overlay_A.json")
JAVA = "TMessagesProj/src/main/java/org/telegram"
THEME = JAVA + "/ui/ActionBar/Theme.java"
THEME_COLORS = JAVA + "/ui/ActionBar/ThemeColors.java"
PALETTE_FIX = JAVA + "/messenger/multigram/PaletteFix.java"
ASSETS = "TMessagesProj/src/main/assets/"

# On-accent pairs MultiGram adds after the overlay's 12 (content drawn on the voice-record fill).
EXTRA_PAIRS = [["key_chat_messagePanelVoicePressed", "key_chat_messagePanelVoiceBackground"]]

# (file, regex that must match exactly once)
HOOKS = [
    (THEME, r"if \(!isMyMessagesGradientColorsNear \|\| org\.telegram\.messenger\.multigram\.PaletteFix\.isRuntimeAccent\(this\)\) \{ // MultiGram:"),
    (THEME, r"file\.length\(\) != size \|\| org\.telegram\.messenger\.multigram\.PaletteFix\.isStaleAssetCopy\(file\)\) \{ // MultiGram:"),
    (THEME, r"PaletteFix\.addAccentExclusions\(themeAccentExclusionKeys\); // MultiGram:"),
    (THEME, r"PaletteFix\.applyToCurrentColors\(currentTheme, accent, currentColors\); // MultiGram:"),
    (THEME, r"PaletteFix\.applyToColorMap\(parentTheme, this, currentColors\); // MultiGram:"),
    (JAVA + "/ui/ActionBar/EmojiThemes.java", r"PaletteFix\.applyToColorMap\(themeInfo, accent, currentColors\); // MultiGram:"),
    (JAVA + "/ui/PeerColorActivity.java", r"PaletteFix\.applyToColorMap\(themeInfo, accent, currentColors\); // MultiGram:"),
    (JAVA + "/ui/ChannelColorActivity.java", r"PaletteFix\.applyToColorMap\(themeInfo, accent, currentColors\); // MultiGram:"),
    (JAVA + "/ui/Components/Paint/Views/MessageEntityView.java", r"PaletteFix\.applyToColorMap\(themeInfo, accent, currentColors\); // MultiGram:"),
    (JAVA + "/ui/Stories/DarkThemeResourceProvider.java", r"PaletteFix\.getOverrideFallbackColor\(sparseIntArray, key\); // MultiGram:"),
    (JAVA + "/ui/Components/ChatActivityEnterView.java", r"int glyph = org\.telegram\.messenger\.multigram\.PaletteFix\.getGlyphColorOnFill\(.*\); // MultiGram:"),
    (JAVA + "/ui/Components/ChatActivityEnterView.java", r"new PorterDuffColorFilter\(glyph != 0 \? glyph : Theme\.getColor\(Theme\.key_chat_messagePanelVoicePressed, resourcesProvider\), PorterDuff\.Mode\.SRC_IN\)\); // MultiGram:"),
]

errors = []


def fail(msg):
    errors.append(msg)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def u32(v):
    return v & 0xFFFFFFFF


def s32(v):
    v = u32(v)
    return v - (1 << 32) if v & 0x80000000 else v


def java_int(tok):
    tok = tok.strip().rstrip("Ll")
    return u32(int(tok, 16) if tok.lower().startswith("0x") else int(tok))


def themecolors_defaults(src):
    out = {}
    for m in re.finditer(r"defaultColors\[(key_\w+)\]\s*=\s*(0x[0-9a-fA-F]+|-?\d+)\s*;", src):
        out.setdefault(m.group(1), []).append(java_int(m.group(2)))
    return out


def attheme_values(text):
    out = {}
    for line in text.split("\n"):
        if line.startswith("WPS"):
            break
        k, sep, v = line.partition("=")
        if sep and re.fullmatch(r"-?\d+", v.strip()):
            out.setdefault("key_" + k, []).append(u32(int(v)))
    return out


def check_values(spec):
    content_keys = {a for a, _ in spec["hook"]["pairs"]}
    tc = themecolors_defaults(read(THEME_COLORS))
    for key, val in sorted(spec["defaults"].items()):
        got = tc.get(key, [])
        want = 0xFFFFFFFF if key in content_keys else u32(val)   # on-accent defaults stay stock white
        if got != [want]:
            fail("ThemeColors %s = %s, expected 0x%08x" % (key, ["0x%08x" % g for g in got], want))
    for asset, kv in sorted(spec["attheme"].items()):
        vals = attheme_values(read(ASSETS + asset))
        for key, val in sorted(kv.items()):
            got = vals.get(key, [])
            if got != [u32(val)]:
                fail("%s %s = %s, expected %d" % (asset, key[4:], [s32(g) for g in got], s32(val)))


def check_palette_fix(spec):
    src = read(PALETTE_FIX)
    m = re.search(r"addAccentExclusions\([^)]*\)\s*\{(.*?)\n    \}", src, re.S)
    excl = re.findall(r"exclusions\.add\(Theme\.(key_\w+)\)", m.group(1)) if m else []
    if sorted(excl) != sorted(spec["exclusions"]) or len(excl) != len(set(excl)):
        fail("PaletteFix exclusions %s != overlay %s" % (sorted(excl), sorted(spec["exclusions"])))
    m = re.search(r"ON_ACCENT\s*=\s*\{(.*?)\};", src, re.S)
    keys = re.findall(r"Theme\.(key_\w+)", m.group(1)) if m else []
    pairs = [list(p) for p in zip(keys[0::2], keys[1::2])]
    if pairs != spec["hook"]["pairs"] + EXTRA_PAIRS:
        fail("PaletteFix ON_ACCENT pairs differ from the overlay's plus EXTRA_PAIRS")
    m = re.search(r"MUTED_PINS\s*=\s*\{(.*?)\};", src, re.S)
    pins = re.findall(r"Theme\.(key_\w+)", m.group(1)) if m else []
    if pins != spec["hook"]["muted"]["pins"]:
        fail("PaletteFix MUTED_PINS %s != overlay %s" % (pins, spec["hook"]["muted"]["pins"]))
    m = re.search(r"ON_ACCENT_DARK\s*=\s*(0x[0-9a-fA-F]+)", src)
    if not m or java_int(m.group(1)) != u32(spec["hook"]["near_black"]):
        fail("PaletteFix ON_ACCENT_DARK != overlay near_black")
    arrays = {n: [java_int(x) for x in re.findall(r"0x[0-9a-fA-F]+", body)]
              for n, body in re.findall(r"int\[\]\s+(\w+)\s*=\s*\{([^}]*)\}", src)}
    table = {}
    for theme, expr in re.findall(r'MUTED_FILL\.put\("([^"]+)",\s*([^;]+)\);', src):
        vals = [java_int(x) for x in re.findall(r"0x[0-9a-fA-F]+", expr)] or arrays.get(expr.strip(), [])
        table[theme] = vals
    want = {t: [u32(v) for v in vs] for t, vs in spec["hook"]["muted"]["table"].items()}
    if table != want:
        fail("PaletteFix MUTED_FILL %s != overlay %s" % (table, want))


def check_hooks():
    for rel, pat in HOOKS:
        n = len(re.findall(pat, read(rel)))
        if n != 1:
            fail("hook %r found %d times in %s" % (pat, n, rel))


def changed_lines(base, rel):
    diff = subprocess.run(["git", "-C", ROOT, "diff", "-U0", base, "--", rel],
                          check=True, capture_output=True, text=True).stdout
    return [l[1:] for l in diff.split("\n") if l.startswith("+") and not l.startswith("+++")]


def check_diff(spec, base):
    content_keys = {a for a, _ in spec["hook"]["pairs"]}
    allowed = {k for k in spec["defaults"] if k not in content_keys}
    for line in changed_lines(base, THEME_COLORS):
        m = re.match(r"\s*defaultColors\[(key_\w+)\]", line)
        if not m or m.group(1) not in allowed:
            fail("unexpected ThemeColors change: %s" % line.strip())
    for asset in ["arctic.attheme", "bluebubbles.attheme", "darkblue.attheme", "day.attheme", "night.attheme",
                  "monet_light.attheme", "monet_dark.attheme"]:
        allowed = {k[4:] for k in spec["attheme"].get(asset, {})}
        for line in changed_lines(base, ASSETS + asset):
            if line.partition("=")[0] not in allowed:
                fail("unexpected %s change: %s" % (asset, line.strip()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", help="git revision of the unpatched Forkgram snapshot")
    args = ap.parse_args()
    with open(SPEC) as f:
        spec = json.load(f)
    check_values(spec)
    check_palette_fix(spec)
    check_hooks()
    if args.base:
        check_diff(spec, args.base)
    for e in errors:
        print("palette-fix: " + e)
    print("palette-fix: %s" % ("FAILED, %d problem(s)" % len(errors) if errors else "OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
