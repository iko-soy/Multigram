#!/usr/bin/env python3
"""Check the MultiGram style knobs (multigram/style-knobs/README.md) in this source tree.

Run from anywhere:

    python3 multigram/tools/style_knobs_check.py
    python3 multigram/tools/style_knobs_check.py --base forkgram   # also: every line added to the hooked
                                                                    # upstream files since REV is marked

What it checks:
  * Every hook in an upstream file is present exactly once, is one line marked "MultiGram:", and passes the
    stock value the line had before (so the hook returns stock while the install has no seed). Every line of
    those files that names StyleKnobs carries the marker.
  * Placement: the start hook directly follows RandomStyle's in ApplicationLoader.onCreate (before the native
    libraries load) and then copies what it wrote into SharedConfig's in-memory fields (large screens load
    SharedConfig before the hook); RandomStyle calls StyleKnobs.onStyleApplying right before it shows the style
    in shuffle, undoShuffle and resetToGeneratedStyle; the wallpaper hook directly follows the phase
    Theme.reloadWallpaper takes from the old wallpaper; ThemeActivity's Reset uses the install's radius, and its
    bind hook covers the three rows refreshStyleKnobRows rebinds.
  * StyleKnobs.java: never writes accessibility settings (text size), the avatar shape, or any key other than its
    own file and the two stock settings it owns; makes no server calls; every knob has its own stream name; the
    value tables stay inside the documented safe ranges.

Standard library only. Exit status 0 when everything matches, 1 otherwise.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
JAVA = "TMessagesProj/src/main/java/org/telegram"
MG = JAVA + "/messenger/multigram/"
KNOBS = MG + "StyleKnobs.java"
RANDOM_STYLE = MG + "RandomStyle.java"
RANDOM_STYLE_UI = MG + "RandomStyleUi.java"
APP = JAVA + "/messenger/ApplicationLoader.java"
THEME = JAVA + "/ui/ActionBar/Theme.java"
THEME_ACTIVITY = JAVA + "/ui/ThemeActivity.java"
ACTION_CELL = JAVA + "/ui/Cells/ChatActionCell.java"
REACTIONS = JAVA + "/ui/Components/Reactions/ReactionsLayoutInBubble.java"
CTA = JAVA + "/ui/Stories/recorder/ButtonWithCounterView.java"
FAB = JAVA + "/ui/Components/FragmentFloatingButton.java"
LIST = JAVA + "/ui/Components/RecyclerListView.java"
UNIVERSAL_LIST = JAVA + "/ui/Components/UniversalRecyclerView.java"
GRADIENT_CTA = JAVA + "/ui/Components/Premium/boosts/GradientButtonWithCounterView.java"

P = r"org\.telegram\.messenger\.multigram\.StyleKnobs\."
M = r" // MultiGram: "

# (file, regex, expected count). Each hook is one line ending in a "MultiGram:" comment.
HOOKS = [
    (APP, r"^        " + P + r"onApplicationCreate\(applicationContext\);" + M, 1),
    (THEME, r"^        previousPhase = " + P + r"wallpaperPhase\(previousPhase, wallpaper instanceof MotionBackgroundDrawable\);" + M, 1),
    (THEME_ACTIVITY, r"^                        if \(setBubbleRadius\(" + P + r"resetBubbleRadius\(17\), true\)\) \{" + M, 1),
    (THEME_ACTIVITY, r"^    public void refreshStyleKnobRows\(\) \{ .*\}" + M, 1),
    (THEME_ACTIVITY, r"^                case TYPE_TEXT_SIZE: case TYPE_BUBBLE_RADIUS: case TYPE_CHAT_LIST: "
                     r"org\.telegram\.messenger\.multigram\.RandomStyleUi\.bindStyleKnobRow\(holder\.itemView\); break;" + M, 1),
    (ACTION_CELL, r"^            final int corner = " + P + r"servicePillRadius\(dp\(11\)\);" + M, 1),
    (ACTION_CELL, r"^            final int cornerIn = " + P + r"servicePillRadius\(dp\(8\)\);" + M, 1),
    (ACTION_CELL, r"^            final int cornerOffset = " + P + r"servicePillCornerOffset\(dp\(3\), corner, dp\(11\)\);" + M, 1),
    (ACTION_CELL, r"^            final int cornerInSmall = " + P + r"servicePillRadius\(dp\(6\)\);" + M, 1),
    (REACTIONS, r"^            float rad = " + P + r"reactionChipRadius\(height / 2f\);" + M, 2),
    (CTA, r"^    private int radiusDp = " + P + r"ctaRadiusDp\(8\);" + M, 1),
    (CTA, r"^            setBackground\(Theme\.createRoundRectDrawable\(dp\(radiusDp\), backgroundColor = Theme\.getColor\(Theme\.key_featuredStickers_addButton, resourcesProvider\)\)\);" + M, 1),
    (FAB, r"^            setOutlineProvider\(android\.view\.ViewOutlineProvider\.BACKGROUND\);" + M, 1),
    (FAB, r"^            int rad = " + P + r"floatingSubButtonRadius\(dp\(18\)\);" + M, 1),
    (FAB, r"^            iBlur3Background\.setRadius\(rad\);" + M, 1),
    (FAB, r"^            setBackground\(" + P + r"floatingButtonBackground\(dp\(48\),[^\n]*" + M, 1),
    (LIST, r"^        setSections\(dp\(12\), " + P + r"sectionRadius\(dp\(16\)\), (false|topPadding)\);" + M, 2),
    (UNIVERSAL_LIST, r"^        setSections\(dp\(12\), " + P + r"sectionRadius\(dp\(16\)\), (false|topPadding)\);" + M, 2),
    (GRADIENT_CTA, r"^        setRoundRadius\(8\);" + M, 1),
]
UPSTREAM = sorted({h[0] for h in HOOKS})

# Stock lines that must be gone (the hook replaced them), per file.
REPLACED = [
    (THEME_ACTIVITY, r"setBubbleRadius\(17, true\)"),
    (ACTION_CELL, r"final int corner = dp\(11\);"),
    (ACTION_CELL, r"final int cornerIn = dp\(8\);"),
    (ACTION_CELL, r"final int cornerOffset = dp\(3\);"),
    (ACTION_CELL, r"final int cornerInSmall = dp\(6\);"),
    (REACTIONS, r"float rad = height / 2f;"),
    (CTA, r"private int radiusDp = 8;"),
    (CTA, r"createRoundRectDrawable\(dp\(8\), backgroundColor = "),
    (FAB, r"ViewOutlineProviderImpl\.BOUNDS_OVAL\)"),
    (FAB, r"createSimpleSelectorCircleDrawable\(dp\(48\)"),
    (LIST, r"setSections\(dp\(12\), dp\(16\)"),
    (UNIVERSAL_LIST, r"setSections\(dp\(12\), dp\(16\)"),
]

# Keys StyleKnobs may write in mainconfig (its own file aside). Text size ("fons_size") is read only; the avatar
# shape ("avatarCorners", "squareAvatars") is never touched: Forkgram's Rounded mode scales every image corner.
OWNED_MAIN_KEYS = {"bubbleRadius", "useThreeLinesLayout"}
NEVER_NAMED = ["avatarCorners", "squareAvatars", "AVATAR_CORNERS_"]
FORBIDDEN_CALLS = ["sendRequest", "getConnectionsManager", "ConnectionsManager", "saveThemeToServer", "installTheme",
                   "uploadFile", "setFontSize", "fontSizeIsDefault"]

# name of the Java table -> (allowed values)
RANGES = {
    "BUBBLE_RADII": set(range(8, 18)),                  # stock slider 0-17, never below 8
    "CTA_SCALES": set(range(25, 101)),                  # result clamped to 6-12dp in code
    "FAB_RADII": {-1} | set(range(14, 19)),             # circle or 14-18dp on a 48dp button
    "SECTION_RADII": set(range(8, 25)),                 # <= inset 12dp + 12dp
}

errors = []


def fail(msg):
    errors.append(msg)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def method_body(src, signature):
    """Source of the method whose declaration matches signature (a regex), up to its closing brace."""
    m = re.search(signature, src)
    if not m:
        return None
    i = src.index("{", m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return None


def check_hooks():
    for rel, pat, count in HOOKS:
        n = len(re.findall(pat, read(rel), re.M))
        if n != count:
            fail("hook %r found %d times in %s (expected %d)" % (pat, n, rel, count))
    for rel, pat in REPLACED:
        if re.search(pat, read(rel)):
            fail("%s: stock line %r is back (the hook must replace it)" % (rel, pat))
    for rel in UPSTREAM:
        for line in read(rel).split("\n"):
            if "StyleKnobs" in line and "// MultiGram: " not in line:
                fail("%s: line without a \"// MultiGram: \" marker: %s" % (rel, line.strip()))


def check_placement():
    src = read(APP)
    if not re.search(r"multigram\.RandomStyle\.onApplicationCreate\(applicationContext\);[^\n]*\n\s*"
                     r"org\.telegram\.messenger\.multigram\.StyleKnobs\.onApplicationCreate\(applicationContext\);", src):
        fail("%s: StyleKnobs.onApplicationCreate must directly follow RandomStyle.onApplicationCreate" % APP)
    start = 0
    for pattern, what in [(r"public void onCreate\(\) \{", "ApplicationLoader.onCreate"),
                          (r"StyleKnobs\.onApplicationCreate\(", "the StyleKnobs start hook"),
                          (r"NativeLoader\.initNativeLibs\(", "NativeLoader.initNativeLibs")]:
        m = re.compile(pattern).search(src, start)
        if not m:
            fail("%s: %s not found in order (onCreate, StyleKnobs hook, NativeLoader.initNativeLibs)" % (APP, what))
            break
        start = m.end()

    src = read(THEME)
    body = method_body(src, r"public static void reloadWallpaper\(boolean async\) \{")
    if body is None or not re.search(r"previousPhase = 0;\s*\n\s*\}\s*\n\s*previousPhase = " + P + r"wallpaperPhase\(", body):
        fail("%s: the wallpaper hook must directly follow the phase reloadWallpaper takes from the old wallpaper" % THEME)

    body = method_body(read(KNOBS), r"public static void onApplicationCreate\(Context context\) \{")
    if body is None or not re.search(r"applyAtStart\(knobs, main, v\);(?:.|\n)*"
                                     r"SharedConfig\.bubbleRadius = main\.getInt\(MAIN_BUBBLE_RADIUS, STOCK_BUBBLE_RADIUS\);\s*\n\s*"
                                     r"SharedConfig\.useThreeLinesLayout = main\.getBoolean\(MAIN_THREE_LINES, STOCK_THREE_LINES\);", body):
        fail("%s: onApplicationCreate must copy the written settings into SharedConfig after applyAtStart "
             "(on sw600dp screens SharedConfig is loaded before the hook)" % KNOBS)

    src = read(RANDOM_STYLE)
    for sig, seed in [(r"public static boolean shuffle\(Context context\) \{", r"seed"),
                      (r"public static boolean undoShuffle\(\) \{", r"u\.seed"),
                      (r"public static boolean resetToGeneratedStyle\(\) \{", r"p\.getLong\(KEY_SEED, 0\)")]:
        body = method_body(src, sig)
        if body is None or not re.search(r"StyleKnobs\.onStyleApplying\(" + seed + r"\);[^\n]*\n\s*show\(pair\);", body):
            fail("%s: %s must call StyleKnobs.onStyleApplying(%s) right before show(pair)" % (RANDOM_STYLE, sig, seed))

    src = read(RANDOM_STYLE_UI)
    if len(re.findall(r"refreshStyleKnobRows\(fragment\);", src)) != 2:
        fail("%s: Shuffle and Undo must both refresh Chat Settings' rows (refreshStyleKnobRows)" % RANDOM_STYLE_UI)

    src = read(THEME_ACTIVITY)
    if not re.search(r"\} else if \(id == reset_settings\) \{.*?if \(setBubbleRadius\(" + P + r"resetBubbleRadius\(17\), true\)\)",
                     src, re.S):
        fail("%s: Reset must set the bubble radius through StyleKnobs.resetBubbleRadius" % THEME_ACTIVITY)


def check_knobs_code():
    raw = read(KNOBS)
    code = strip_comments(raw)
    for call in FORBIDDEN_CALLS:
        if call in code:
            fail("%s calls or names %s" % (KNOBS, call))
    # Writes into mainconfig: only the owned settings, through constants.
    consts = dict(re.findall(r'static final String (\w+) = "([^"]*)";', code))
    for m in re.finditer(r"\.put(?:Int|Boolean|String|Long)\((\w+)", code):
        key = consts.get(m.group(1), m.group(1))
        if m.group(1).startswith("MAIN_") and key not in OWNED_MAIN_KEYS:
            fail("%s writes mainconfig key %r, which is not one of its owned settings" % (KNOBS, key))
    if re.search(r'put\w*\(\s*"fons_size"', code) or re.search(r"put\w*\(MAIN_FONT_SIZE", code):
        fail("%s writes the text size (accessibility setting)" % KNOBS)
    streams = re.findall(r'static final String KNOB_\w+ = "([^"]+)";', code)
    if len(streams) != len(set(streams)):
        fail("%s: two knobs share a stream name" % KNOBS)
    for s in streams:
        if len(re.findall(r'"%s"' % re.escape(s), code)) != 1:
            fail("%s: stream name %r must be defined once, as a KNOB_ constant" % (KNOBS, s))
    for name, allowed in RANGES.items():
        m = re.search(r"static final int\[\] %s = \{([^}]*)\};" % name, code)
        if not m:
            fail("%s: table %s not found" % (KNOBS, name))
            continue
        values = [int(v) for v in m.group(1).replace(" ", "").split(",")]
        bad = [v for v in values if v not in allowed]
        if bad:
            fail("%s: %s has values outside its safe range: %s" % (KNOBS, name, bad))
    for name in NEVER_NAMED:
        if name in code:
            fail("%s names %s: the avatar shape is not a style knob (Forkgram's modes scale every image corner)" % (KNOBS, name))
    if 'getSharedPreferences("mainconfig"' in code and "MessagesController" in code:
        fail("%s: use Context.getSharedPreferences only (no MessagesController before the first frame)" % KNOBS)


def check_diff(base):
    """Every non-blank line added to the hooked upstream files since base carries the marker."""
    for rel in UPSTREAM:
        out = subprocess.run(["git", "-C", ROOT, "diff", "-U0", base, "--", rel], capture_output=True, text=True)
        if out.returncode != 0:
            fail("git diff %s -- %s failed: %s" % (base, rel, out.stderr.strip()))
            continue
        for line in out.stdout.split("\n"):
            if line.startswith("+") and not line.startswith("+++") and line[1:].strip() and "MultiGram:" not in line:
                fail("%s: added line without a \"MultiGram:\" marker: %s" % (rel, line[1:].strip()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", help="git revision of the unpatched Forkgram snapshot (optional diff check)")
    args = ap.parse_args()
    check_hooks()
    check_placement()
    check_knobs_code()
    if args.base:
        check_diff(args.base)
    for e in errors:
        print("style-knobs: " + e)
    print("style-knobs: %s" % ("FAILED, %d problem(s)" % len(errors) if errors else "OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
