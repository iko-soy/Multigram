#!/usr/bin/env python3
"""Check the MultiGram "Hide chat list search" option (multigram/hide-search-bar/README.md) in this source tree.

Run from anywhere:

    python3 multigram/tools/hide_search_bar_check.py
    python3 multigram/tools/hide_search_bar_check.py --base forkgram   # also: every line added to the hooked
                                                                        # upstream files since REV is marked

What it checks:
  * Every hook in DialogsActivity and ForkSettingsActivity is present exactly once, is one line marked
    "MultiGram:", and keeps the stock token inside the original dp(...) (HideSearchBar.restHeight returns it while
    the option is off). Every line of those files that names HideSearchBar carries the marker.
  * Update guard: every other line of DialogsActivity that uses SEARCH_FIELD_HEIGHT is one of the reviewed stock
    lines, with the reviewed count. A new use in a Forkgram or Telegram update (or a stock line a hook replaced
    coming back) fails here, so it gets reviewed before it ships.
  * Placement: the max-scroll hook opens getMaxScrollYOffset; the tabs hook directly follows the stories overscroll
    in updateContextViewPosition, before the tabs are placed; the refresh hook directly follows super.onResume()
    (before onResume's notifyDataSetChanged); the alpha hook feeds the field's visibility and the stock search icon
    swap in checkUi_searchFieldVisibility, whose own factor0 line stays stock and is its only factor0; the icon hook
    (the "no search" variant) is the factor0 line that opens checkUi_itemSearchVisibility, the only other copy of
    that stock line (the stock lines of both methods are counted on code with comments stripped);
    the entries left stock on purpose (the icon's click listener, which the topics column's search icon calls, the
    Downloads item and tg://search links) still open search; the action mode hooks pair up in hideActionMode and
    showOrUpdateActionMode; every DialogsActivity hook but the alpha hook sits right next to a stock neighbour
    line (the two fling stop hooks and the page height hook also inside their stock if blocks), so moving one
    within its method fails; the settings row directly follows Disable Global Search and the click hook opens
    onClick.
  * HideSearchBar.java: one owned mainconfig key, written in one place and read with default false; a row id clear
    of Forkgram's ids; restHeight and restAlpha pass the stock value through; strings through Context.getString;
    FragmentSearchField is not touched; only the two hooked upstream files name the class.

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
DA = JAVA + "/ui/DialogsActivity.java"
FORK = JAVA + "/ui/ForkSettingsActivity.java"
FIELD = JAVA + "/ui/Components/FragmentSearchField.java"
TOPICS = JAVA + "/ui/TopicsFragment.java"
CLS = MG + "HideSearchBar.java"
STRINGS = MAIN + "res/values/multigram_strings.xml"
SETTINGS_BACKUP = JAVA + "/messenger/forkgram/SettingsBackup.kt"
KEY = "multigramHideSearchBar"
STRING_NAMES = ["MultiGramHideSearchBar", "MultiGramHideSearchBarInfo"]

P = r"org\.telegram\.messenger\.multigram\.HideSearchBar\."
M = r" // MultiGram: "
RH = P + r"restHeight\(DialogsActivity\.this, SEARCH_FIELD_HEIGHT\)"
ST = r"\(hasStories \? DialogStoriesCell\.HEIGHT_IN_DP : 0\)"

# Hook bodies (the code of the line, without its indentation and marker), named by the spec's numbers.
H = {
    1: r"h \+= dp\(" + RH + r"\) \* \(1f - progressToActionMode\) \* \(1f - searchAnimationProgress\) \* \(1f - rightSlidingProgress\);",
    2: r"dp" + ST + r" \+ dp\(" + RH + r"\) \+ scrollYOffset,",
    3: r"progressToActionMode \* \(dp" + ST + r" \+ dp\(" + RH + r"\)\)",
    4: r"addH \+= dp\(" + RH + r"\);",
    5: r"scrollYOffset \+ tabsYOffset \+ storiesOverscroll - dp\(4\) - dp\(SEARCH_FIELD_HEIGHT - " + RH + r"\),",
    6: r"h \+= dp\(" + RH + r"\);",
    7: r"t \+= dp\(" + RH + r"\);",
    8: r"offset \+= dp\(" + RH + r"\);",
    9: r"canScrollDy -= dp\(" + RH + r"\);",
    10: r"canScrollDy \+= dp\(" + RH + r"\);",
    11: r"if \(" + P + r"hides\(this\)\) return getMaxScrollYOffsetWithoutSearch\(\);",
    12: r"if \(" + P + r"hides\(this\)\) totalOffset -= dp\(SEARCH_FIELD_HEIGHT\) \* \(1f - searchAnimationProgress\);",
    13: r"if \(" + P + r"refresh\(this, viewPages\)\) \{ setScrollY\(Math\.max\(scrollYOffset, -getMaxScrollYOffset\(\)\)\); "
        r"invalidateScrollY = true; checkUi_searchFieldVisibility\(\); checkUi_menuItems\(\); \}",
    14: r"translateListHeight = Math\.max\(0, dp\(" + ST + r" \+ " + RH + r"\) \+ scrollYOffset\);",
    15: r"scrollAdditionalOffset = -\(dp\(" + ST + r" \+ " + RH + r"\) - finalTranslateListHeight\);",
    16: r"translateListHeight = Math\.max\(0, dp\(" + ST + r" \+ " + RH + r"\) \+ scrollYOffset\);",
    17: r"scrollAdditionalOffset = dp\(" + ST + r" \+ " + RH + r"\) - finalTranslateListHeight;",
    18: r"final float alphaByScrollOffset = " + P + r"restAlpha\(this, 1f - MathUtils\.clamp\(\(-scrollYOffset - "
        r"maxScrollWithoutSearch\) / dp\(SEARCH_FIELD_HEIGHT\), 0, 1\)\);",
    19: r"items\.add\(" + P + r"settingsRow\(\)\);",
    20: r"if \(" + P + r"onSettingsClick\(item, view\)\) return;",
    21: r"final float factor0 = isSupportSearch\(\) && !" + P + r"hides\(this\) \? 1 : 0;",
}

# (file, hook number, indentation). Each hook is one line ending in a "MultiGram:" comment, present exactly once.
LAYOUT = [
    (DA, 1, 12), (DA, 2, 16), (DA, 3, 16), (DA, 4, 16), (DA, 5, 24), (DA, 6, 24), (DA, 7, 16), (DA, 8, 24),
    (DA, 9, 36), (DA, 10, 36), (DA, 11, 8), (DA, 12, 8), (DA, 13, 8), (DA, 14, 8), (DA, 15, 16), (DA, 16, 12),
    (DA, 17, 20), (DA, 18, 8), (DA, 21, 8),
    (FORK, 19, 8), (FORK, 20, 8),
]
HOOKS = [(rel, r"^" + " " * indent + H[n] + M, 1) for rel, n, indent in LAYOUT]
UPSTREAM = [DA, FORK]

# Update guard, which also covers the replaced stock lines: every DialogsActivity line matching \bSEARCH_FIELD_HEIGHT\b
# and lacking the marker must be exactly one of these (stripped text), with exactly these counts.
REVIEWED = {
    "public static final int SEARCH_FIELD_HEIGHT = 48;": 1,
    "-dp(SEARCH_FIELD_HEIGHT + (hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0)),": 1,
    "childTop += dp(SEARCH_FIELD_HEIGHT);": 2,
    "//    childTop -= dp(SEARCH_FIELD_HEIGHT);": 1,
    "return -lerp(dp(4), dp(SEARCH_FIELD_HEIGHT), animatorSearchVisible.getFloatValue());": 1,
    "int h = dp(SEARCH_FIELD_HEIGHT);": 1,
    "return dp(DialogStoriesCell.HEIGHT_IN_DP) + dp(SEARCH_FIELD_HEIGHT);": 1,
    "return dp(SEARCH_FIELD_HEIGHT);": 1,
    "(dp(SEARCH_FIELD_HEIGHT))": 1,
    "float translationY = dp(DialogStoriesCell.HEIGHT_IN_DP) + scrollYOffset + dp(SEARCH_FIELD_HEIGHT);": 1,
    "+ dp(DialogsActivity.SEARCH_FIELD_HEIGHT)": 1,
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
    """Source of the method whose declaration matches signature (a regex, re.M), up to its closing brace."""
    m = re.search(signature, src, re.M)
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


def hook(n):
    """Hook n as it sits in a line: its code, marker and comment, up to the end of the line (no indentation)."""
    return H[n] + M + r"[^\n]*"


def java_sources():
    for dirpath, dirnames, files in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "build", ".gradle")]
        for f in files:
            if f.endswith((".java", ".kt")):
                full = os.path.join(dirpath, f)
                with open(full, encoding="utf-8", errors="replace") as fh:
                    yield os.path.relpath(full, ROOT), fh.read()


def check_hooks():
    for rel, pat, count in HOOKS:
        n = len(re.findall(pat, read(rel), re.M))
        if n != count:
            fail("hook %r found %d times in %s (expected %d)" % (pat, n, rel, count))
    for rel in UPSTREAM:
        for line in read(rel).split("\n"):
            if "HideSearchBar" in line and "// MultiGram: " not in line:
                fail("%s: line without a \"// MultiGram: \" marker: %s" % (rel, line.strip()))
    seen = {}
    for line in read(DA).split("\n"):
        if re.search(r"\bSEARCH_FIELD_HEIGHT\b", line) and "// MultiGram: " not in line:
            text = line.strip()
            if text not in REVIEWED:
                fail("%s: unreviewed use of the bar height (a new upstream use, or a stock line a hook replaced): %s"
                     % (DA, text))
            seen[text] = seen.get(text, 0) + 1
    for text, count in REVIEWED.items():
        if seen.get(text, 0) != count:
            fail("%s: reviewed line %r found %d times (expected %d); review the bar height uses again"
                 % (DA, text, seen.get(text, 0), count))


def need(rel, cond, msg):
    if not cond:
        fail("%s: %s" % (rel, msg))


def check_placement():
    src = read(DA)

    body = method_body(src, r"^    private int getMaxScrollYOffset\(\) \{")
    need(DA, body is not None and re.match(r"\{\s*\n\s*" + hook(11), body),
         "the max-scroll hook must be the first statement of getMaxScrollYOffset")

    body = method_body(src, r"^    private void updateContextViewPosition\(\) \{")
    m = body and re.search(r"totalOffset \+= storiesOverscroll;\s*\n\s*" + hook(12), body)
    need(DA, m, "the tabs hook must directly follow \"totalOffset += storiesOverscroll;\" in updateContextViewPosition")
    if m:
        for later in ["float fadeViewT = totalOffset;", "filterTabsView.setTranslationY("]:
            i = body.find(later)
            need(DA, i > m.end(), "the tabs hook must come before %r in updateContextViewPosition" % later)

    body = method_body(src, r"^    public void onResume\(\) \{")
    need(DA, body is not None and re.search(r"super\.onResume\(\);\s*\n\s*" + hook(13), body),
         "the refresh hook must directly follow super.onResume() in onResume")
    if body is not None:
        i, j = body.find("HideSearchBar.refresh("), body.find(".notifyDataSetChanged()")
        need(DA, 0 <= i < j, "the refresh hook must run before onResume's notifyDataSetChanged")

    # The stock lines of the two checkUi methods are counted on code with comments stripped, so a stock line that an
    # update comments out (Telegram often leaves old code commented out here) does not count as present.
    body = method_body(src, r"^    private void checkUi_searchFieldVisibility\(\) \{") or ""
    code = strip_comments(body)
    need(DA, re.search(hook(18), body), "checkUi_searchFieldVisibility must contain %r" % hook(18))
    for text in ["fragmentSearchField.setVisibility(alpha > 0 ? View.VISIBLE : View.GONE);",
                 "animatorSearchButtonVisible.setValue(alpha <= 0.01f, true);"]:
        need(DA, code.count(text) == 1, "checkUi_searchFieldVisibility must contain %r once, as code" % text)

    stock_factor0 = "final float factor0 = isSupportSearch() ? 1 : 0;"
    need(DA, src.count(stock_factor0) == 1 and code.count(stock_factor0) == 1
         and code.count("final float factor0 =") == 1
         and code.count("final float alpha = factor0 * factor1 * factor2;") == 1,
         "%r must remain exactly once, stock and not commented out, as the only factor0 of "
         "checkUi_searchFieldVisibility, feeding its stock alpha line (the icon hook replaces the other copy, in "
         "checkUi_itemSearchVisibility)" % stock_factor0)
    need(DA, body.count("HideSearchBar") == 1, "checkUi_searchFieldVisibility must hold the alpha hook only")

    body = method_body(src, r"^    private void checkUi_itemSearchVisibility\(\) \{") or ""
    code = strip_comments(body)
    need(DA, re.match(r"\{\s*\n\s*" + hook(21) + r"\s*\n\s*"
                      + re.escape("final float factor1 = animatorSearchButtonVisible.getFloatValue();"), body)
         and code.count("final float factor0 =") == 1,
         "the icon hook (\"no search\" variant) must be the only factor0 line of checkUi_itemSearchVisibility, "
         "opening it, directly followed by the stock factor1 line")
    for text in ["final float factor1 = animatorSearchButtonVisible.getFloatValue();",
                 "final float factor = factor0 * factor1 * factor2 * factor3;",
                 "FragmentFloatingButton.setAnimatedVisibility(searchItem, factor);"]:
        need(DA, code.count(text) == 1,
             "checkUi_itemSearchVisibility must contain %r once, as code (the icon hook feeds it)" % text)
    need(DA, body.count("HideSearchBar") == 1, "checkUi_itemSearchVisibility must hold the icon hook only")

    # Entries left stock on purpose (README: "What still opens search"). Each still opens search with the field.
    need(DA, re.search(r"searchItem\.setOnClickListener\(v -> \{\s*\n\s*showSearch\(true, false, true\);", src),
         "the hidden header icon's listener must still open search (the topics column's search icon calls it)")
    need(TOPICS, "parentDialogsActivity.searchItem.performClick();" in read(TOPICS),
         "the topics column's search icon no longer clicks the list's header icon; review the README's "
         "\"What still opens search\"")
    need(DA, re.search(r"\} else if \(id == 3\) \{\s*\n\s*showSearch\(true, true, true\);", src),
         "the Downloads item must still open search (onItemClick id 3 -> showSearch)")
    need(DA, re.search(r"public void search\(String query, boolean animated\) \{\s*\n\s*showSearch\(true, false, animated\);",
                       src),
         "tg://search links must still open search (search(query, animated) -> showSearch)")

    body = method_body(src, r"^    private void hideActionMode\(boolean animateCheck\) \{") or ""
    need(DA, re.search(hook(14), body) and re.search(hook(15), body), "hideActionMode must contain hooks 14 and 15")
    body = method_body(src, r"^    private void showOrUpdateActionMode\(long dialogId, View cell\) \{") or ""
    need(DA, re.search(hook(16), body) and re.search(hook(17), body),
         "showOrUpdateActionMode must contain hooks 16 and 17")
    body = method_body(src, r"^        public int getActionBarFullHeight\(\) \{") or ""
    need(DA, re.search(re.escape("h += storiesOverscroll;") + r"\s*\n\s*" + hook(1), body),
         "the header band hook must directly follow \"h += storiesOverscroll;\" in getActionBarFullHeight")

    need(DA, re.search(hook(5) + r"\s*\n\s*" + re.escape("-dp(SEARCH_FIELD_HEIGHT + (hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0)),")
                       + r"\s*\n\s*searchAnimationProgress", src),
         "the search slide hook must be the start term of the field's lerp (end term and progress stock)")
    need(DA, re.search(re.escape("tabsYOffset -= Math.min(") + r"\s*\n\s*" + hook(2) + r"\s*\n\s*" + hook(3), src),
         "the two tab lift hooks must directly follow \"tabsYOffset -= Math.min(\"")
    need(DA, re.search(hook(4) + r"\s*\n\s*" + re.escape("addH *= rightSlidingDialogContainer.openedProgress;"), src),
         "the topics column hook must directly precede \"addH *= rightSlidingDialogContainer.openedProgress;\"")
    need(DA, re.search(re.escape("if (!actionModeFullyShowed) {") + r"\s*\n\s*" + hook(7), src),
         "the list padding hook must directly follow \"if (!actionModeFullyShowed) {\"")
    need(DA, re.search(re.escape("if (backward) {") + r"\s*\n\s*" + hook(8), src),
         "the topics column close hook must directly follow \"if (backward) {\"")
    need(DA, re.search(re.escape("h += dp(DialogStoriesCell.HEIGHT_IN_DP);") + r"\s*\n\s*\}\s*\n\s*" + hook(6)
                       + r"\s*\n\s*\}\s*\n\s*" + re.escape("h += actionModeAdditionalHeight;"), src),
         "the page height hook must be the last statement of \"if (rightSlidingDialogContainer.hasFragment()) {\" "
         "in ContentView.onMeasure, after the stories block")
    need(DA, re.search(re.escape("int canScrollDy = -(view.getTop() - pTop) + viewsH;") + r"\s*\n\s*"
                       + re.escape("if (!rightSlidingDialogContainer.hasFragment() && !(actionBar != null && "
                                   "actionBar.isActionModeShowed())) {") + r"\s*\n\s*" + hook(9) + r"\s*\n\s*\}", src),
         "the fling stop hook must be the only statement of the stock if that directly follows "
         "\"int canScrollDy = ...\"")
    need(DA, re.search(re.escape("if ((viewPage.scroller.isRunning() || dialogStoriesCell.isExpanded()) && "
                                 "!rightSlidingDialogContainer.hasFragment() && !fixScrollYAfterArchiveOpened && "
                                 "!(actionBar != null && actionBar.isActionModeShowed())) {") + r"\s*\n\s*" + hook(10)
                       + r"\s*\n\s*\}\s*\n\s*" + re.escape("int positiveDy = Math.abs(dy);"), src),
         "the fling stop pair hook must be the only statement of the stock if that directly precedes "
         "\"int positiveDy = Math.abs(dy);\"")
    for n, nxt in [(14, "float finalTranslateListHeight = translateListHeight;"),
                   (15, "viewPages[0].setTranslationY(0);"),
                   (16, "if (translateListHeight != 0) {"),
                   (17, "viewPages[0].setTranslationY(0);")]:
        need(DA, re.search(hook(n) + r"\s*\n\s*" + re.escape(nxt), src),
             "action mode hook %d must directly precede %r" % (n, nxt))

    src = read(FORK)
    body = method_body(src, r"^    private void fillSettings\(ArrayList<UItem> items\) \{") or ""
    need(FORK, re.search(re.escape('.setChecked(pref("disableGlobalSearch", false)).setMultiline(true));') + r"\s*\n\s*"
                         + hook(19), body),
         "the \"Hide chat list search\" row must directly follow Disable Global Search in fillSettings")
    body = method_body(src, r"^    private void onClick\(UItem item, View view, int position, float x, float y\) \{")
    need(FORK, body is not None and re.match(r"\{\s*\n\s*final int id = item\.id;\s*\n\s*" + hook(20), body),
         "the click hook must directly follow \"final int id = item.id;\" at the start of onClick")


def check_class():
    raw = read(CLS)
    code = strip_comments(raw)
    need(CLS, re.search(r'static final String KEY = "%s";' % KEY, code), "KEY must be \"%s\"" % KEY)
    for rel, src in java_sources():
        if rel != CLS and '"%s"' % KEY in src:
            fail("%s names the key \"%s\" (only HideSearchBar may)" % (rel, KEY))
        if "/multigram/" not in rel and rel not in UPSTREAM and "multigram.HideSearchBar" in src:
            fail("%s names multigram.HideSearchBar (only DialogsActivity and ForkSettingsActivity may)" % rel)
    need(CLS, len(re.findall(r"\.putBoolean\(KEY, ", code)) == 1, "exactly one .putBoolean(KEY, ...) expected")
    puts = re.findall(r"\.put(?:Boolean|Int|Long|Float|String|StringSet)\(", code)
    need(CLS, len(puts) == 1, "writes preferences other than its one key: %s" % puts)
    need(CLS, not re.search(r"\b(remove|clear)\(", code), "must not remove or clear preferences")
    reads = re.findall(r"getBoolean\(KEY, (\w+)\)", code)
    need(CLS, reads and all(r == "false" for r in reads), "every getBoolean(KEY, ...) must default to false")

    m = re.search(r"static final int ROW_ID = (\d+);", code)
    need(CLS, m, "ROW_ID not found")
    if m:
        row = int(m.group(1))
        fork = strip_comments(read(FORK))
        ids = {int(v) for v in re.findall(r"\bID_\w+ = (\d+);", fork)}
        ids |= {int(v) for v in re.findall(r"\bMENU_SEARCH = (\d+);", fork)}
        need(CLS, row > 100 and row not in ids,
             "ROW_ID %d must be above 100 and clear of ForkSettingsActivity's ids" % row)

    for name, ret in [("restHeight", r"return hides\(f\) \? 0 : stock;"), ("restAlpha", r"return hides\(f\) \? 0f : stock;")]:
        body = method_body(code, r"public static \w+ %s\(DialogsActivity f, \w+ stock\) \{" % name) or ""
        need(CLS, re.fullmatch(r"\{\s*" + ret + r"\s*\}", body), "%s must be exactly \"%s\"" % (name, ret.replace("\\", "")))
    need(CLS, "LocaleController" not in code, "MultiGram strings are read with Context.getString, not LocaleController")

    xml = read(STRINGS)
    for n in STRING_NAMES:
        need(STRINGS, '<string name="%s">' % n in xml, "string %s is missing" % n)
        need(CLS, "R.string.%s)" % n in code, "does not use R.string.%s" % n)
    need(FIELD, "multigram" not in read(FIELD).lower(), "FragmentSearchField must stay stock")

    kt = read(SETTINGS_BACKUP)
    m = re.search(r"ALLOWED_PREFS\s*=\s*listOf\((.*?)\)", kt, re.S)
    need(SETTINGS_BACKUP, m and '"mainconfig"' in m.group(1),
         "Forkgram's settings export no longer carries mainconfig; update the README's Preferences section")


def check_diff(base):
    """Every non-blank line added to the hooked upstream files since base carries the marker, or directly follows
    an added line that is a "// MultiGram:" comment (the Rebrand hooks' two-line form)."""
    for rel in UPSTREAM:
        out = subprocess.run(["git", "-C", ROOT, "diff", "-U0", base, "--", rel], capture_output=True, text=True)
        if out.returncode != 0:
            fail("git diff %s -- %s failed: %s" % (base, rel, out.stderr.strip()))
            continue
        prev = None
        for line in out.stdout.split("\n"):
            if line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
                prev = None
                continue
            if not line.startswith("+"):
                prev = None
                continue
            text = line[1:].strip()
            if text and "MultiGram:" not in line and not (prev is not None and prev.startswith("// MultiGram:")):
                fail("%s: added line without a \"MultiGram:\" marker: %s" % (rel, text))
            prev = text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", help="git revision of the unpatched Forkgram snapshot (optional diff check)")
    args = ap.parse_args()
    check_hooks()
    check_placement()
    check_class()
    if args.base:
        check_diff(args.base)
    for e in errors:
        print("hide-search-bar: " + e)
    print("hide-search-bar: %s" % ("FAILED, %d problem(s)" % len(errors) if errors else "OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
