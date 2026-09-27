"""Parse the Telegram-Android theme engine inputs straight from the source tree.

Everything the simulator needs is read from the checked-out sources (never hand-copied):
  * Theme.java      - colour key indices (declaration order of `key_X = colorsCount++`),
                      myMessages*Index ranges, fallbackKeys, themeAccentExclusionKeys,
                      myMessagesAccentExtraKeys, the five bundled ThemeInfo definitions
                      (setAccentColorOptions arrays), the "override default themes" constants,
                      isHome() rules, DEFALT_THEME_ACCENT_ID, MSG_OUT_COLOR_*.
  * ThemeColors.java - createDefaultColors() and createColorKeysMap() (attheme names).
  * assets/*.attheme - parsed with the exact semantics of Theme.getThemeFileValues().

The parsed result is cached as JSON keyed by a SHA-256 of the inputs.
"""
import hashlib
import json
import os
import re
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# The repository this copy lives in (multigram/tools/sim -> repository root); TG_REPO overrides it.
REPO = os.path.abspath(os.environ.get("TG_REPO") or os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(REPO, "TMessagesProj", "src", "main")
THEME_JAVA = os.path.join(SRC, "java", "org", "telegram", "ui", "ActionBar", "Theme.java")
THEMECOLORS_JAVA = os.path.join(SRC, "java", "org", "telegram", "ui", "ActionBar", "ThemeColors.java")
ASSETS = os.path.join(SRC, "assets")
ATTHEMES = ["bluebubbles.attheme", "darkblue.attheme", "arctic.attheme", "day.attheme", "night.attheme"]
CACHE_DIR = os.path.join(HERE, "cache")
PARSER_VERSION = 11


def s32(v):
    """Wrap an integer to a Java signed 32-bit int."""
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def u32(v):
    return v & 0xFFFFFFFF


# ----------------------------------------------------------------------------------------
# Java helpers
# ----------------------------------------------------------------------------------------

def strip_java_comments(src):
    """Remove // and /* */ comments while respecting string and char literals.
    Newlines are kept so that line numbers stay valid."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            q = c
            j = i + 1
            while j < n and src[j] != q:
                if src[j] == '\\':
                    j += 1
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            if j < 0:
                j = n
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                j = n
            out.append("\n" * src.count("\n", i, j + 2))
            i = j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


_NL_CACHE = {}


def line_of(src, pos):
    import bisect
    key = id(src)
    ent = _NL_CACHE.get(key)
    if ent is None or ent[0] is not src:
        idx = [i for i, ch in enumerate(src) if ch == "\n"]
        ent = (src, idx)
        _NL_CACHE[key] = ent
    return bisect.bisect_left(ent[1], pos) + 1


def java_int_literal(tok):
    tok = tok.strip()
    neg = False
    if tok.startswith("-"):
        neg = True
        tok = tok[1:].strip()
    if tok.endswith(("L", "l")):
        tok = tok[:-1]
    if tok.lower().startswith("0x"):
        v = int(tok, 16)
    else:
        v = int(tok, 10)
    return -v if neg else v


def split_top_level(s, sep=","):
    parts, depth, cur, i = [], 0, [], 0
    in_str = None
    while i < len(s):
        ch = s[i]
        if in_str:
            cur.append(ch)
            if ch == "\\":
                cur.append(s[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
            cur.append(ch)
        elif ch in "({[":
            depth += 1
            cur.append(ch)
        elif ch in ")}]":
            depth -= 1
            cur.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts]


def matching_paren(s, open_pos):
    depth = 0
    in_str = None
    i = open_pos
    while i < len(s):
        ch = s[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced parentheses")


# ----------------------------------------------------------------------------------------
# Theme.java
# ----------------------------------------------------------------------------------------

# Guard of the out-bubble black/white text block in ThemeAccent.fillAccentColors: stock, or widened for runtime
# accents by the palette fix (group 1 is set when widened).
OUT_BLOCK_GUARD_RE = re.compile(
    r"if\s*\(\s*!\s*isMyMessagesGradientColorsNear\s*"
    r"(\|\|\s*(?:id\s*>\s*100|(?:[A-Za-z_][\w.]*\.)?PaletteFix\s*\.\s*isRuntimeAccent\s*\(\s*this\s*\))\s*)?"
    r"\)\s*\{")


def parse_theme_java(path=THEME_JAVA):
    raw = open(path, encoding="utf-8").read()
    src = strip_java_comments(raw)
    res = {"file": os.path.relpath(path, REPO)}

    # colour keys, in declaration order; also the *Index markers
    keys, key_lines, markers = [], {}, {}
    count = None
    decl_re = re.compile(r"\bstatic\s+final\s+int\s+(key_\w+)\s*=\s*colorsCount\s*\+\+\s*;")
    marker_re = re.compile(r"\bstatic\s+final\s+int\s+(\w+Index)\s*=\s*colorsCount\s*;")
    start_re = re.compile(r"\bpublic\s+static\s+int\s+colorsCount\s*;")
    for m in re.finditer(r"[^\n]*\n", src):
        line = m.group(0)
        ln = line_of(src, m.start())
        if count is None:
            if start_re.search(line):
                count = 0
            continue
        for dm in decl_re.finditer(line):
            name = dm.group(1)
            if name in key_lines:
                raise ValueError("duplicate key " + name)
            keys.append(name)
            key_lines[name] = ln
            count += 1
        mm = marker_re.search(line)
        if mm:
            markers[mm.group(1)] = {"value": count, "line": ln}
    res["keys"] = keys
    res["key_lines"] = key_lines
    res["markers"] = markers
    res["decl_count_grep"] = len(re.findall(r"=\s*colorsCount\s*\+\+\s*;", src))

    # constants
    def const(name):
        m = re.search(r"\b" + name + r"\s*=\s*(-?(?:0x[0-9a-fA-F]+|\d+))\s*;", src)
        return {"value": s32(java_int_literal(m.group(1))), "line": line_of(src, m.start())}
    res["DEFALT_THEME_ACCENT_ID"] = const("DEFALT_THEME_ACCENT_ID")
    res["MSG_OUT_COLOR_BLACK"] = const("MSG_OUT_COLOR_BLACK")
    res["MSG_OUT_COLOR_WHITE"] = const("MSG_OUT_COLOR_WHITE")

    # fallbackKeys.put(key_A, key_B)
    fb = []
    for m in re.finditer(r"fallbackKeys\.put\(\s*(?:Theme\.)?(key_\w+)\s*,\s*(?:Theme\.)?(key_\w+)\s*\)\s*;", src):
        fb.append([m.group(1), m.group(2), line_of(src, m.start())])
    res["fallbackKeys"] = fb

    # int[] arrays of keys (keys_avatar_background etc.)
    arrays = {}
    for m in re.finditer(r"\bint\s*\[\]\s+(keys_\w+)\s*=\s*\{([^}]*)\}\s*;", src):
        arrays[m.group(1)] = {"keys": [t.strip() for t in m.group(2).split(",") if t.strip()],
                              "line": line_of(src, m.start())}
    res["key_arrays"] = arrays

    # themeAccentExclusionKeys
    excl = []
    for m in re.finditer(r"for\s*\(\s*int\s+(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(keys_\w+)\.length\s*;\s*\1\+\+\s*\)\s*\{\s*themeAccentExclusionKeys\.add\(\s*\2\s*\[\s*\1\s*\]\s*\)\s*;\s*\}", src):
        for k in arrays[m.group(2)]["keys"]:
            excl.append([k, line_of(src, m.start()), m.group(2)])
    for m in re.finditer(r"themeAccentExclusionKeys\.add\(\s*(?:Theme\.)?(key_\w+)\s*\)\s*;", src):
        excl.append([m.group(1), line_of(src, m.start()), None])
    res["themeAccentExclusionKeys"] = excl
    n_add_calls = len(re.findall(r"themeAccentExclusionKeys\.add\(", src))
    res["exclusion_add_calls"] = n_add_calls

    m = re.search(r"myMessagesAccentExtraKeys\s*=\s*\{([^}]*)\}\s*;", src)
    res["myMessagesAccentExtraKeys"] = {"keys": [t.strip() for t in m.group(1).split(",") if t.strip()],
                                        "line": line_of(src, m.start())}

    # bundled themes
    themes = []
    for m in re.finditer(r"themeInfo\s*=\s*new\s+ThemeInfo\s*\(\s*\)\s*;", src):
        start = m.end()
        end = src.find("themesDict.put(", start)
        block = src[start:end]
        if not re.search(r'themeInfo\.assetName\s*=\s*"[^"]+\.attheme"\s*;', block) or "new ThemeInfo(" in block:
            continue
        t = {"line": line_of(src, m.start())}
        nm = re.search(r'themeInfo\.name\s*=\s*"([^"]*)"\s*;', block)
        t["name"] = nm.group(1)
        t["name_line"] = line_of(src, start + nm.start())
        am = re.search(r'themeInfo\.assetName\s*=\s*"([^"]*)"\s*;', block)
        t["assetName"] = am.group(1)
        t["firstAccentIsDefault"] = bool(re.search(r"themeInfo\.firstAccentIsDefault\s*=\s*true\s*;", block))
        cm = re.search(r"themeInfo\.currentAccentId\s*=\s*(\w+)\s*;", block)
        t["currentAccentId_init"] = cm.group(1) if cm else None
        sm = re.search(r"themeInfo\.setAccentColorOptions\s*\(", block)
        if sm is None:
            # Forkgram's Monet Light/Dark: colours come from the system palette at run time, no accents to model
            continue
        op = start + sm.end() - 1
        cp = matching_paren(src, op)
        args = split_top_level(src[op + 1:cp])
        t["setAccentColorOptions_line"] = line_of(src, start + sm.start())
        parsed_args = []
        for a in args:
            if a == "null":
                parsed_args.append(None)
                continue
            am2 = re.match(r"new\s+(int|String)\s*\[\]\s*\{(.*)\}\s*$", a, re.S)
            typ, body = am2.group(1), am2.group(2)
            items = [x.strip() for x in split_top_level(body) if x.strip()]
            if typ == "int":
                parsed_args.append([s32(java_int_literal(x)) for x in items])
            else:
                parsed_args.append([x.strip()[1:-1] for x in items])
        names = ["accent", "myMessages", "myMessagesGradient", "background", "backgroundGradient1",
                 "backgroundGradient2", "backgroundGradient3", "ids", "patternSlugs", "patternRotations",
                 "patternIntensities"]
        if len(parsed_args) == 1:
            parsed_args += [None] * 10
        t["options"] = dict(zip(names, parsed_args))
        themes.append(t)
    res["themes"] = themes

    # setAccentColorOptions body: "override default themes" block, accentBaseColor assignment
    sm = re.search(r"private\s+void\s+setAccentColorOptions\s*\(\s*int\s*\[\]\s*accent\s*,", src)
    body_start = src.find("{", sm.end())
    depth, i = 0, body_start
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = src[body_start:i]
    res["setAccentColorOptions_line"] = line_of(src, sm.start())
    om = re.search(r'if\s*\(\s*isHome\(themeAccent\)\s*&&\s*name\.equals\("Dark Blue"\)\s*\|\|\s*name\.equals\("Night"\)\s*\)\s*\{', body)
    if not om:
        raise ValueError("override-default-themes condition changed; update the simulator")
    res["override_condition_line"] = line_of(src, body_start + om.start())
    ob_start = body_start + om.end()
    # take the block up to the matching brace
    depth, j = 1, ob_start
    while depth:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
        j += 1
    ob = src[ob_start:j]
    ov = {}
    night_part = ob[ob.find('if (name.equals("Night"))'):] if 'if (name.equals("Night"))' in ob else ""
    common_part = ob[:ob.find('if (name.equals("Night"))')] if night_part else ob
    for fm in re.finditer(r"themeAccent\.(\w+)\s*=\s*(-?[0-9.]+f|-?0x[0-9a-fA-F]+|-?\d+)\s*;", common_part):
        ov[fm.group(1)] = fm.group(2)
    res["override_all"] = {k: (s32(java_int_literal(v)) if not v.endswith("f") else float(v[:-1])) for k, v in ov.items()}
    nv = {}
    for fm in re.finditer(r"themeAccent\.(\w+)\s*=\s*(-?[0-9.]+f|-?0x[0-9a-fA-F]+|-?\d+)\s*;", night_part):
        nv[fm.group(1)] = fm.group(2)
    res["override_night"] = {k: (s32(java_int_literal(v)) if not v.endswith("f") else float(v[:-1])) for k, v in nv.items()}
    bm = re.search(r"accentBaseColor\s*=\s*themeAccentsMap\.get\(\s*(\d+)\s*\)\.accentColor\s*;", body)
    res["accentBaseColor_id"] = int(bm.group(1))
    res["accentBaseColor_line"] = line_of(src, body_start + bm.start())

    # isHome rules
    hm = re.search(r"public\s+static\s+boolean\s+isHome\s*\(\s*ThemeAccent\s+accent\s*\)", src)
    hbody = src[hm.end():src.find("return false;", hm.end())]
    home = {}
    for rm in re.finditer(r'\(?((?:accent\.parentTheme\.getKey\(\)\.equals\("[^"]+"\)\s*(?:\|\|\s*)?)+)\)?\s*&&\s*accent\.id\s*==\s*(\d+)', hbody):
        for nmx in re.findall(r'equals\("([^"]+)"\)', rm.group(1)):
            home[nmx] = int(rm.group(2))
    res["isHome"] = home
    res["isHome_line"] = line_of(src, hm.start())

    # fillAccentColors: the black/white out-text block (keys written with textColor / subTextColor /
    # seekbarColor / myMessagesAccentColor) and the constants chosen by useBlackText
    fm0 = re.search(r"public\s+boolean\s+fillAccentColors\s*\(\s*SparseIntArray\s+currentColorsNoAccent\s*,\s*SparseIntArray\s+currentColors\s*\)", src)
    res["fillAccentColors_line"] = line_of(src, fm0.start())
    # MultiGram's palette fix widens this guard (rule (d)) to
    #   if (!isMyMessagesGradientColorsNear || org.telegram.messenger.multigram.PaletteFix.isRuntimeAccent(this)) {
    # (id > 100 and no server theme behind the accent: true for the simulated accent, id 101 without info);
    # the research form `|| id > 100` means the same here.  All three forms are accepted (OUT_BLOCK_GUARD_RE) and
    # a widened guard is recorded for engine.Model.
    gm = OUT_BLOCK_GUARD_RE.search(src, fm0.end())
    if gm is None:
        raise ValueError("fillAccentColors out-text block guard not found; update the simulator")
    blk0 = gm.start()
    res["out_block_guard_id_gt_100"] = gm.group(1) is not None
    blk1 = src.find("if (isMyMessagesGradientColorsNear) {", blk0)
    if blk1 < 0:
        raise ValueError("fillAccentColors isMyMessagesGradientColorsNear block not found; update the simulator")
    blk = src[blk0:blk1]
    res["out_text_block_line"] = line_of(src, blk0)
    cm_b = re.search(r"if\s*\(\s*useBlackText\s*\)\s*\{\s*textColor\s*=\s*(\w+)\s*;\s*subTextColor\s*=\s*(0x[0-9a-fA-F]+)\s*;\s*seekbarColor\s*=\s*(0x[0-9a-fA-F]+)\s*;\s*\}\s*else\s*\{\s*textColor\s*=\s*(\w+)\s*;\s*subTextColor\s*=\s*(0x[0-9a-fA-F]+)\s*;\s*seekbarColor\s*=\s*(0x[0-9a-fA-F]+)\s*;", blk)
    res["out_text_consts"] = {"black": [cm_b.group(1), s32(java_int_literal(cm_b.group(2))), s32(java_int_literal(cm_b.group(3)))],
                              "white": [cm_b.group(4), s32(java_int_literal(cm_b.group(5))), s32(java_int_literal(cm_b.group(6)))]}
    a2 = blk.find("if (accentColor2 == 0) {")
    # end of the accentColor2 == 0 sub-block: matching brace
    depth, j = 0, a2 + len("if (accentColor2 == 0) ")
    while True:
        if blk[j] == "{":
            depth += 1
        elif blk[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    inner = blk[a2:j]
    outer = blk[j:]
    put_re = re.compile(r"currentColors\.put\(\s*(key_\w+)\s*,\s*(textColor|subTextColor|seekbarColor|myMessagesAccentColor)\s*\)\s*;")
    res["out_block_accent2_zero"] = [[m2.group(1), m2.group(2)] for m2 in put_re.finditer(inner)]
    res["out_block_always"] = [[m2.group(1), m2.group(2)] for m2 in put_re.finditer(outer)]

    # createDefaultWallpaper(): 4 colours + pattern intensity of the built-in 'd' wallpaper
    dm = re.search(r"public\s+static\s+Drawable\s+createDefaultWallpaper\s*\(\s*int\s+w\s*,\s*int\s+h\s*\)", src)
    dbody = src[dm.end():src.find("return motionBackgroundDrawable;", dm.end())]
    cm2 = re.search(r"new\s+MotionBackgroundDrawable\(\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,", dbody)
    im2 = re.search(r"setPatternBitmap\(\s*(\d+)\s*,\s*SvgHelper\.getBitmap\(\s*R\.raw\.default_pattern", dbody)
    res["default_wallpaper"] = {"colors": [s32(java_int_literal(cm2.group(i))) for i in range(1, 5)],
                                "intensity": int(im2.group(1)), "line": line_of(src, dm.end() + cm2.start())}

    # applyChatServiceMessageColor(): colour matrix applied to the gradient bitmap under service pills
    sm2 = re.search(r"if\s*\(\s*drawable\s+instanceof\s+MotionBackgroundDrawable\s*\)\s*\{\s*float\s+intensity\s*=\s*\(\(MotionBackgroundDrawable\)\s*drawable\)\.getIntensity\(\)\s*;", src)
    sbody = src[sm2.end():sm2.end() + 1500]
    f_re = r"(-?\+?\.?[0-9.]+)f"
    branch_re = re.compile(r"colorMatrix\.setSaturation\(\s*" + f_re + r"\s*\)\s*;\s*AndroidUtilities\.multiplyBrightnessColorMatrix\(\s*colorMatrix\s*,\s*isCurrentThemeDark\(\)\s*\?\s*" + f_re + r"\s*:\s*" + f_re + r"\s*\)\s*;\s*AndroidUtilities\.adjustBrightnessColorMatrix\(\s*colorMatrix\s*,\s*isCurrentThemeDark\(\)\s*\?\s*" + f_re + r"\s*:\s*" + f_re + r"\s*\)\s*;")
    br = branch_re.findall(sbody)
    def _f(x):
        return float(x.replace("+", ""))
    res["service_matrix"] = {
        "intensity_ge0": {"sat": _f(br[0][0]), "mult_dark": _f(br[0][1]), "mult_light": _f(br[0][2]), "add_dark": _f(br[0][3]), "add_light": _f(br[0][4])},
        "intensity_lt0": {"sat": _f(br[1][0]), "mult_dark": _f(br[1][1]), "mult_light": _f(br[1][2]), "add_dark": _f(br[1][3]), "add_light": _f(br[1][4])},
        "line": line_of(src, sm2.start())}
    unparsed = [x for x in re.findall(r"currentColors\.put\([^;]*;", blk) if not put_re.fullmatch(x)]
    res["out_block_unparsed"] = unparsed

    # the fresh-install accent id: getInt("accent_current_" + ..., firstAccentIsDefault ? DEFALT : 0)
    fm = re.search(r'getInt\(\s*"accent_current_"\s*\+\s*info\.assetName\s*,\s*info\.firstAccentIsDefault\s*\?\s*DEFALT_THEME_ACCENT_ID\s*:\s*(\d+)\s*\)', src)
    res["fresh_install_accent_id_non_default"] = int(fm.group(1))
    res["fresh_install_accent_line"] = line_of(src, fm.start())
    return res


# ----------------------------------------------------------------------------------------
# ThemeColors.java
# ----------------------------------------------------------------------------------------

COLOR_CONSTS = {"Color.WHITE": s32(0xFFFFFFFF), "Color.BLACK": s32(0xFF000000),
                "Color.TRANSPARENT": 0, "Color.RED": s32(0xFFFF0000), "Color.GREEN": s32(0xFF00FF00),
                "Color.BLUE": s32(0xFF0000FF)}


def eval_color_expr(expr, consts):
    e = expr.strip()
    if re.fullmatch(r"-?(0x[0-9a-fA-F]+|\d+)", e):
        return s32(java_int_literal(e))
    if e in consts:
        return consts[e]
    if e in COLOR_CONSTS:
        return COLOR_CONSTS[e]
    m = re.fullmatch(r"ColorUtils\.setAlphaComponent\((.*)\)", e)
    if m:
        a, b = split_top_level(m.group(1))
        base = eval_color_expr(a, consts)
        alpha = eval_color_expr(b, consts)
        if base is None or alpha is None:
            return None
        if not 0 <= alpha <= 255:
            raise ValueError("alpha must be 0..255")
        return s32((u32(base) & 0x00FFFFFF) | (alpha << 24))
    m = re.fullmatch(r"Color\.argb\((.*)\)", e)
    if m:
        vals = [eval_color_expr(x, consts) for x in split_top_level(m.group(1))]
        if None in vals:
            return None
        a, r, g, b = vals
        return s32((a << 24) | (r << 16) | (g << 8) | b)
    return None


def parse_themecolors_java(path=THEMECOLORS_JAVA):
    raw = open(path, encoding="utf-8").read()
    src = strip_java_comments(raw)
    res = {"file": os.path.relpath(path, REPO)}
    consts = {}
    const_lines = {}
    for m in re.finditer(r"public\s+static\s+final\s+int\s+(\w+)\s*=\s*(-?0x[0-9a-fA-F]+|-?\d+)\s*;", src):
        consts[m.group(1)] = s32(java_int_literal(m.group(2)))
        const_lines[m.group(1)] = line_of(src, m.start())
    res["consts"] = consts
    res["const_lines"] = const_lines
    cm = re.search(r"public\s+static\s+int\s*\[\]\s*createDefaultColors\s*\(\s*\)\s*\{", src)
    end = src.find("return defaultColors;", cm.end())
    body = src[cm.end():end]
    defaults, unevaluated, lines = {}, [], {}
    stmt_count = 0
    for m in re.finditer(r"defaultColors\s*\[\s*(key_\w+)\s*\]\s*=\s*([^;]+);", body):
        stmt_count += 1
        v = eval_color_expr(m.group(2), consts)
        ln = line_of(src, cm.end() + m.start())
        if v is None:
            unevaluated.append([m.group(1), m.group(2).strip(), ln])
            continue
        defaults[m.group(1)] = v          # later assignments win, like Java
        lines[m.group(1)] = ln
    res["defaults"] = defaults
    res["default_lines"] = lines
    res["default_statements"] = stmt_count
    res["unevaluated"] = unevaluated
    km = re.search(r"public\s+static\s+SparseArray<String>\s+createColorKeysMap\s*\(\s*\)\s*\{", src)
    kend = src.find("return colorKeysMap;", km.end())
    kbody = src[km.end():kend]
    keymap = []
    for m in re.finditer(r'colorKeysMap\.put\(\s*(key_\w+)\s*,\s*"([^"]*)"\s*\)\s*;', kbody):
        keymap.append([m.group(1), m.group(2), line_of(src, km.end() + m.start())])
    res["colorKeysMap"] = keymap
    res["createColorKeysMap_line"] = line_of(src, km.start())
    res["createDefaultColors_line"] = line_of(src, cm.start())
    return res


# ----------------------------------------------------------------------------------------
# .attheme files, parsed like Theme.getThemeFileValues()
# ----------------------------------------------------------------------------------------

def java_utilities_parse_int(value):
    """Port of org.telegram.messenger.Utilities.parseInt(CharSequence).
    Quirk: when a non [-0-9] char follows the number, `end++` makes the substring include
    that char, so Integer.parseInt throws and the result is 0."""
    if value is None:
        return 0
    start = -1
    end = 0
    n = len(value)
    while end < n:
        ch = value[end]
        allowed = ch == "-" or ("0" <= ch <= "9")
        if allowed and start < 0:
            start = end
        elif not allowed and start >= 0:
            end += 1
            break
        end += 1
    if start < 0:
        return 0
    s = value[start:end]
    if not re.fullmatch(r"[-+]?\d+", s):
        return 0
    v = int(s)
    if v < -2 ** 31 or v > 2 ** 31 - 1:
        return 0
    return v


def java_parse_color(s):
    """android.graphics.Color.parseColor for '#RRGGBB' / '#AARRGGBB'; raises like Java."""
    if s[0] != "#":
        raise ValueError("Unknown color")
    v = int(s[1:], 16)            # Long.parseLong(..., 16): raises on bad digits
    if len(s) == 7:
        v |= 0xFF000000
    elif len(s) != 9:
        raise ValueError("Unknown color")
    return s32(v)


def parse_attheme(path, name_to_key):
    data = open(path, "rb").read()
    values = {}
    unknown = []
    dropped_tail = None
    wallpaper_offset = -1
    pos = 0
    ln = 0
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            tail = data[pos:]
            if tail:
                dropped_tail = tail.decode("latin-1")
            break
        ln += 1
        line = data[pos:nl].decode("latin-1")
        length = nl - pos + 1
        if line.startswith("WLS="):
            pass
        elif line.startswith("WPS"):
            wallpaper_offset = pos + length
            break
        else:
            idx = line.find("=")
            if idx != -1:
                key = line[:idx]
                param = line[idx + 1:]
                if len(param) > 0 and param[0] == "#":
                    try:
                        value = java_parse_color(param)
                    except Exception:
                        value = java_utilities_parse_int(param)
                else:
                    value = java_utilities_parse_int(param)
                k = name_to_key.get(key)
                if k is not None:
                    values[k] = [value, ln]
                else:
                    unknown.append([key, ln])
        pos = nl + 1
    values["key_wallpaperFileOffset"] = [wallpaper_offset, None]
    return {"values": values, "unknown": unknown, "dropped_tail": dropped_tail,
            "wallpaperFileOffset": wallpaper_offset, "file": os.path.relpath(path, REPO)}


# ----------------------------------------------------------------------------------------
# cache
# ----------------------------------------------------------------------------------------

def _inputs_digest():
    h = hashlib.sha256()
    h.update(str(PARSER_VERSION).encode())
    for p in [THEME_JAVA, THEMECOLORS_JAVA] + [os.path.join(ASSETS, a) for a in ATTHEMES]:
        h.update(p.encode())
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def load(force=False):
    digest = _inputs_digest()
    os.makedirs(CACHE_DIR, exist_ok=True)
    cpath = os.path.join(CACHE_DIR, "parsed_%s.json" % digest)
    if not force and os.path.exists(cpath):
        try:
            with open(cpath) as f:
                cached = json.load(f)
            if cached.get("digest") == digest:
                return cached
        except (OSError, ValueError):
            pass                        # unreadable or truncated cache file: parse again and rewrite it
    tj = parse_theme_java()
    tc = parse_themecolors_java()
    name_to_key = {}
    dup_names = []
    for k, nm, _ in tc["colorKeysMap"]:
        if nm in name_to_key:
            dup_names.append(nm)
        name_to_key[nm] = k
    at = {}
    for a in ATTHEMES:
        at[a] = parse_attheme(os.path.join(ASSETS, a), name_to_key)
    out = {"digest": digest, "repo": REPO, "theme_java": tj, "themecolors_java": tc, "atthemes": at,
           "keymap_duplicate_names": dup_names}
    # write-then-rename, so an interrupted run or two concurrent runs never leave a partial cache file
    fd, tmp = tempfile.mkstemp(prefix=".parsed_", suffix=".tmp", dir=CACHE_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(out, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, cpath)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return out


if __name__ == "__main__":
    d = load(force=True)
    tj, tc = d["theme_java"], d["themecolors_java"]
    print("keys:", len(tj["keys"]), "grep count:", tj["decl_count_grep"], "markers:", tj["markers"])
    print("fallbackKeys:", len(tj["fallbackKeys"]), "exclusions:", len(tj["themeAccentExclusionKeys"]),
          "add calls:", tj["exclusion_add_calls"])
    print("extra keys:", tj["myMessagesAccentExtraKeys"])
    print("defaults:", len(tc["defaults"]), "statements:", tc["default_statements"], "unevaluated:", tc["unevaluated"])
    print("keymap:", len(tc["colorKeysMap"]), "dups:", d["keymap_duplicate_names"])
    print("override_all:", tj["override_all"], "override_night:", tj["override_night"])
    print("isHome:", tj["isHome"], "accentBaseColor id:", tj["accentBaseColor_id"])
    for t in tj["themes"]:
        o = t["options"]
        print(t["name"], t["assetName"], "firstDefault", t["firstAccentIsDefault"], "init", t["currentAccentId_init"],
              "n", len(o["accent"]), "ids", o["ids"])
    for a, v in d["atthemes"].items():
        print(a, "values", len(v["values"]), "unknown", v["unknown"], "dropped tail", v["dropped_tail"])
