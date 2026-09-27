#!/usr/bin/env python3
"""Check the MultiGram per-install random style (multigram/random-style/README.md) in this source tree.

Run from anywhere:

    python3 multigram/tools/random_style_check.py
    python3 multigram/tools/random_style_check.py --base forkgram   # also: every line added to the hooked
                                                                     # upstream files since REV is marked

What it checks:
  * Every hook in upstream files is one inserted line, present exactly once and marked "MultiGram:", and
    every line of those files that names the feature (RandomStyle, shuffleStyleRow, setCurrentDayTheme)
    carries the marker.
  * The hooks sit where the design needs them: Stage A before the native libraries load in
    ApplicationLoader.onCreate; Stage B in Theme's static initializer after the saved accents are
    loaded and before the auto-night settings are read and the first theme is applied; the upload
    guard is the first statement of MessagesController.saveThemeToServer; the ThemeActivity hooks
    open their handlers.
  * The feature's own code never calls a server path (theme or wallpaper upload, install, request),
    saves accents only with upload = false, and gives generated accents no pattern slug.
  * Every R.string.MultiGram* it uses is defined in res/values/multigram_strings.xml, no name there
    collides with Telegram's strings.xml, and none is read through LocaleController.
  * The style table asset exists.
  * Privacy by configuration: the "rebrand_style" preferences file is in neither Forkgram's settings
    export (SettingsBackup.kt) nor the Android backup agent.

Standard library only. Exit status 0 when everything matches, 1 otherwise.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MAIN = "TMessagesProj/src/main/"
JAVA = MAIN + "java/org/telegram"
MG = JAVA + "/messenger/multigram/"
THEME = JAVA + "/ui/ActionBar/Theme.java"
APP = JAVA + "/messenger/ApplicationLoader.java"
MESSAGES = JAVA + "/messenger/MessagesController.java"
ALERTS = JAVA + "/ui/Components/AlertsCreator.java"
THEME_ACTIVITY = JAVA + "/ui/ThemeActivity.java"
PREVIEW = JAVA + "/ui/ThemePreviewActivity.java"
PREVIEW_CELL = JAVA + "/ui/DefaultThemesPreviewCell.java"
STRINGS = MAIN + "res/values/multigram_strings.xml"
ASSET = MAIN + "assets/multigram_styles.bin"
SETTINGS_BACKUP = JAVA + "/messenger/forkgram/SettingsBackup.kt"
BACKUP_AGENT = JAVA + "/messenger/BackupAgent.java"
FEATURE = [MG + "RandomStyle.java", MG + "RandomStyleUi.java", MG + "StyleTable.java"]
PREFS_NAME = "rebrand_style"

P = r"org\.telegram\.messenger\.multigram\."

# (file, regex that must match exactly once; re.M). Each hook is one inserted line ending in a "MultiGram:" comment.
HOOKS = [
    (APP, P + r"RandomStyle\.onApplicationCreate\(applicationContext\); // MultiGram: "),
    (THEME, r"applyingTheme = " + P + r"RandomStyle\.onThemeInit\(applyingTheme\); // MultiGram: "),
    (THEME, r"^    public static void setCurrentDayTheme\(ThemeInfo theme\) \{ currentDayTheme = theme; \} // MultiGram: "),
    (MESSAGES, r"^        if \(" + P + r"RandomStyle\.isUploadBlocked\(themeInfo, accent\)\) return; // MultiGram: "),
    (ALERTS, r"^        if \(" + P + r"RandomStyleUi\.interceptThemeCreate\(fragment, switchToAccent\)\) return; // MultiGram: "),
    (PREVIEW, P + r"RandomStyle\.onAccentCopied\(applyingTheme, accent, !edit\); // MultiGram: "),
    (PREVIEW_CELL, r"^        " + P + r"RandomStyleUi\.refreshCustomTile\(adapter\.items, parentFragment\.getCurrentAccount\(\)\); // MultiGram: "),
    (THEME_ACTIVITY, r"^    private int shuffleStyleRow = -1; // MultiGram: "),
    (THEME_ACTIVITY, r"^        shuffleStyleRow = -1; // MultiGram: "),
    (THEME_ACTIVITY, r"^            shuffleStyleRow = rowCount\+\+; // MultiGram: "),
    (THEME_ACTIVITY, r"^            if \(" + P + r"RandomStyleUi\.interceptShare\(this, \(Theme\.ThemeAccent\) args\[1\]\)\) return; // MultiGram: "),
    (THEME_ACTIVITY, r"^                        " + P + r"RandomStyle\.resetToGeneratedStyle\(\); // MultiGram: "),
    (THEME_ACTIVITY, r"^            if \(position == shuffleStyleRow\) \{ " + P + r"RandomStyleUi\.shuffle\(ThemeActivity\.this\); return; \} // MultiGram: "),
    (THEME_ACTIVITY, r"^                    if \(position == shuffleStyleRow\) \{ " + P + r"RandomStyleUi\.bindShuffleRow\(cell\); break; \} // MultiGram: "),
    (THEME_ACTIVITY, r"^            if \(position == shuffleStyleRow\) return TYPE_TEXT_PREFERENCE; // MultiGram: "),
]

# Lines of the hooked files that name the feature; each must carry the marker.
FEATURE_NAMES = re.compile(r"multigram\.RandomStyle|shuffleStyleRow|setCurrentDayTheme\(ThemeInfo")

# Calls the feature's own code must never make.
FORBIDDEN_CALLS = ["saveThemeToServer", "installTheme", "saveWallpaperToServer", "uploadFile", "sendRequest",
                   "saveTheme(", "createNewTheme", "getConnectionsManager", "ConnectionsManager"]

errors = []


def fail(msg):
    errors.append(msg)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def order(rel, landmarks):
    """landmarks: [(regex, description)]; each must occur after the previous one, the hook exactly once."""
    src = read(rel)
    start, last_what = 0, None
    for pattern, what in landmarks:
        m = re.compile(pattern, re.M).search(src, start)
        if not m:
            fail("%s: %s not found%s" % (rel, what, " after " + last_what if last_what else ""))
            return
        start, last_what = m.end(), what


def check_hooks():
    for rel, pat in HOOKS:
        n = len(re.findall(pat, read(rel), re.M))
        if n != 1:
            fail("hook %r found %d times in %s" % (pat, n, rel))
    for rel in sorted({h[0] for h in HOOKS}):
        for line in read(rel).split("\n"):
            if FEATURE_NAMES.search(line) and "// MultiGram: " not in line:
                fail("%s: line without a \"// MultiGram: \" marker: %s" % (rel, line.strip()))


def check_placement():
    order(APP, [
        (r"public void onCreate\(\) \{", "ApplicationLoader.onCreate"),
        (r"applicationContext = getApplicationContext\(\);", "the applicationContext assignment"),
        (r"RandomStyle\.onApplicationCreate\(", "the Stage A hook"),
        (r"NativeLoader\.initNativeLibs\(", "NativeLoader.initNativeLibs"),
    ])
    order(THEME, [
        (r'String accents = themeConfig\.getString\("accents_" \+ info\.assetName, null\);', "the saved-accent load"),
        (r"if \(oldEditor != null\) \{\s*oldEditor\.commit\(\);", "the accent migration commit"),
        (r"RandomStyle\.onThemeInit\(applyingTheme\)", "the Stage B hook"),
        (r'selectedAutoNightType = preferences\.getInt\("selectedAutoNightType"', "the auto-night settings read"),
        (r"currentDayTheme = applyingTheme;", "the day theme assignment"),
        (r"applyTheme\(applyingTheme, false, false, switchToTheme == 2\);", "the first applyTheme"),
    ])
    src = read(MESSAGES)
    if not re.search(r"public void saveThemeToServer\(Theme\.ThemeInfo themeInfo, Theme\.ThemeAccent accent\) \{\s*\n"
                     r"\s*if \(" + P + r"RandomStyle\.isUploadBlocked", src):
        fail("%s: the upload guard is not the first statement of saveThemeToServer" % MESSAGES)
    src = read(ALERTS)
    if not re.search(r"public static void createThemeCreateDialog\(BaseFragment fragment, int type, Theme\.ThemeInfo "
                     r"switchToTheme, Theme\.ThemeAccent switchToAccent\) \{\s*\n\s*if \(fragment == null \|\| "
                     r"fragment\.getParentActivity\(\) == null\) \{\s*\n\s*return;\s*\n\s*\}\s*\n\s*if \("
                     + P + r"RandomStyleUi\.interceptThemeCreate", src):
        fail("%s: the theme-create guard must directly follow the null check of createThemeCreateDialog" % ALERTS)
    src = read(PREVIEW)
    if not re.search(r"accent = applyingTheme\.getAccent\(!edit\);\s*\n\s*" + P + r"RandomStyle\.onAccentCopied", src):
        fail("%s: onAccentCopied must directly follow getAccent(!edit)" % PREVIEW)
    src = read(THEME_ACTIVITY)
    if not re.search(r"\} else if \(id == NotificationCenter\.needShareTheme\) \{\s*\n\s*if \(getParentActivity\(\) == null "
                     r"\|\| isPaused\) \{\s*\n\s*return;\s*\n\s*\}\s*\n\s*if \(" + P + r"RandomStyleUi\.interceptShare", src):
        fail("%s: interceptShare must open the needShareTheme handler" % THEME_ACTIVITY)
    if not re.search(r"themeListRow2 = rowCount\+\+;\s*\n\s*shuffleStyleRow = rowCount\+\+;", src):
        fail("%s: the shuffle row must follow themeListRow2" % THEME_ACTIVITY)
    if not re.search(r"\} else if \(id == reset_settings\) \{.*?Theme\.reloadWallpaper\(true\);\s*\n\s*\}\s*\n\s*\}\s*\n\s*"
                     + P + r"RandomStyle\.resetToGeneratedStyle\(\);[^\n]*\n\s*\}\);", src, re.S):
        fail("%s: resetToGeneratedStyle must end the Reset dialog's positive handler" % THEME_ACTIVITY)
    if not re.search(r"listView\.setOnItemClickListener\(\(view, position, x, y\) -> \{\s*\n\s*if \(position == shuffleStyleRow\)", src):
        fail("%s: the shuffle click must open the list's click listener" % THEME_ACTIVITY)
    if not re.search(r"case TYPE_TEXT_PREFERENCE: \{\s*\n\s*TextCell cell = \(TextCell\) holder\.itemView;\s*\n\s*"
                     r"cell\.heightDp = 48;\s*\n\s*if \(position == shuffleStyleRow\)", src):
        fail("%s: bindShuffleRow must open the TYPE_TEXT_PREFERENCE binding" % THEME_ACTIVITY)
    if not re.search(r"public int getItemViewType\(int position\) \{\s*\n\s*if \(position == shuffleStyleRow\) return TYPE_TEXT_PREFERENCE;", src):
        fail("%s: the shuffle row's view type must open getItemViewType" % THEME_ACTIVITY)
    src = read(PREVIEW_CELL)
    if not re.search(r"public void updateDayNightMode\(\) \{\s*\n\s*" + P + r"RandomStyleUi\.refreshCustomTile", src):
        fail("%s: refreshCustomTile must open updateDayNightMode" % PREVIEW_CELL)


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def check_feature_code():
    for rel in FEATURE:
        code = strip_comments(read(rel))
        for call in FORBIDDEN_CALLS:
            if call in code:
                fail("%s calls %s" % (rel, call))
        for m in re.finditer(r"saveThemeAccents\(([^;]*)\);", code):
            args = [a.strip() for a in m.group(1).split(",")]
            if len(args) < 5 or args[4] != "false":
                fail("%s: saveThemeAccents(%s) must pass upload = false" % (rel, m.group(1)))
        for m in re.finditer(r"\.patternSlug\s*=\s*([^;]*);", code):
            if m.group(1).strip() != '""':
                fail("%s: generated accents get no pattern slug, found patternSlug = %s" % (rel, m.group(1).strip()))
        if re.search(r"LocaleController\.(getString|formatString)\([^)]*R\.string\.MultiGram", code):
            fail("%s reads a MultiGram string through LocaleController (use Context.getString)" % rel)
    code = strip_comments(read(MG + "RandomStyle.java"))
    if not re.search(r"new SecureRandom\(\)\.nextLong\(\)", code):
        fail("RandomStyle.java: the seed must come from SecureRandom")
    if not re.search(r'PREFS = "%s"' % PREFS_NAME, code):
        fail("RandomStyle.java: PREFS is not \"%s\"" % PREFS_NAME)


def check_strings():
    xml = read(STRINGS)
    names = re.findall(r'<string name="(\w+)"', xml)
    if len(names) != len(set(names)):
        fail("%s: duplicate string names" % STRINGS)
    for n in names:
        if not n.startswith("MultiGram"):
            fail("%s: string %s must start with MultiGram" % (STRINGS, n))
    used = set()
    for dirpath, _, files in os.walk(os.path.join(ROOT, MAIN, "java")):
        for f in files:
            if f.endswith((".java", ".kt")):
                with open(os.path.join(dirpath, f), encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
                used.update(re.findall(r"R\.string\.(MultiGram\w+)", src))
                if re.search(r"LocaleController\.(getString|formatString)\([^;]*R\.string\.MultiGram", src):
                    fail("%s reads a MultiGram string through LocaleController" % f)
    for n in sorted(used - set(names)):
        fail("R.string.%s is used but not defined in %s" % (n, STRINGS))
    for n in sorted(set(names) - used):
        fail("%s: string %s is not used" % (STRINGS, n))
    for dirpath, _, files in os.walk(os.path.join(ROOT, MAIN, "res")):
        for f in files:
            full = os.path.join(dirpath, f)
            if f.endswith(".xml") and os.path.relpath(full, ROOT) != STRINGS and dirpath.endswith("/values"):
                with open(full, encoding="utf-8", errors="replace") as fh:
                    other = fh.read()
                for n in names:
                    if re.search(r'<string name="%s"' % n, other):
                        fail("string %s is also defined in %s" % (n, os.path.relpath(full, ROOT)))


def check_asset_and_backup():
    if not os.path.isfile(os.path.join(ROOT, ASSET)):
        fail("missing asset %s" % ASSET)
    kt = read(SETTINGS_BACKUP)
    m = re.search(r"ALLOWED_PREFS\s*=\s*listOf\((.*?)\)", kt, re.S)
    if not m:
        fail("%s: ALLOWED_PREFS not found" % SETTINGS_BACKUP)
    elif '"%s"' % PREFS_NAME in m.group(1):
        fail("%s exports \"%s\" (the seed stays on the install)" % (SETTINGS_BACKUP, PREFS_NAME))
    if PREFS_NAME in read(BACKUP_AGENT):
        fail("%s backs up \"%s\"" % (BACKUP_AGENT, PREFS_NAME))
    manifest = read(MAIN + "AndroidManifest.xml")
    if 'android:backupAgent=".BackupAgent"' not in manifest or "android:fullBackupOnly=\"true\"" in manifest:
        fail("AndroidManifest.xml: the key/value BackupAgent no longer owns backup; re-check the backup policy")


def check_diff(base):
    """Every non-blank line added to the hooked upstream files since base carries the marker."""
    for rel in sorted({h[0] for h in HOOKS}):
        out = subprocess.run(["git", "-C", ROOT, "diff", "-U0", base, "--", rel],
                             capture_output=True, text=True)
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
    check_feature_code()
    check_strings()
    check_asset_and_backup()
    if args.base:
        check_diff(args.base)
    for e in errors:
        print("random-style: " + e)
    print("random-style: %s" % ("FAILED, %d problem(s)" % len(errors) if errors else "OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
