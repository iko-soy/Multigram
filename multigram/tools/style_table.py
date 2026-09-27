"""MultiGram style table: binary format, generator and validator, shared by make_style_table.py and
check_style_table.py.

A style is one runtime ThemeAccent on a bundled base theme: accent colour, outgoing-bubble colours, and a
2-4 colour wallpaper gradient with no pattern.  Every entry is produced and checked by the colour-engine
simulator in sim/ (engine.py: port of Theme.fillAccentColors / getColor; readability.py: the 99 readability
pairs) on the fixed palette "overlay A".  The format is documented in README.md next to this file; keep the
two in sync.
"""
import copy
import json
import os
import re
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, "sim")
if SIM not in sys.path:
    sys.path.insert(0, SIM)

import engine as E            # noqa: E402
import readability as R       # noqa: E402
import style_sim as S         # noqa: E402
import tgsrc                  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ASSET_REL = "TMessagesProj/src/main/assets/multigram_styles.bin"
DEFAULT_ASSET = os.path.join(REPO_ROOT, *ASSET_REL.split("/"))
# Overlay A as the palette fix ships it (multigram/palette-fix/ in the modelled tree, kept in sync with
# PaletteFix.java by palette_fix_check.py) when that tree has it, else the simulator's copy.  Both are the same
# file today.
OVERLAY_A_CANDIDATES = [os.path.join(tgsrc.REPO, "multigram", "palette-fix", "overlay_A.json"),
                        os.path.join(SIM, "palette-fix", "overlay_A.json")]

# ------------------------------------------------------------------------------------------
# binary format (big-endian; see README.md "multigram_styles.bin")
# ------------------------------------------------------------------------------------------

MAGIC = b"MGST"
VERSION = 1
HEADER = struct.Struct(">4sHHHHHHII")      # magic, version, header size, theme count, dir entry size, record size, reserved, record count, crc32
DIR_ENTRY = struct.Struct(">20sBBHII")     # theme key, flags, reserved, reserved, first record, record count
RECORD = struct.Struct(">9IHBB")           # 9 ARGB colours, rotation, flags, reserved
assert (HEADER.size, DIR_ENTRY.size, RECORD.size) == (24, 32, 40)
THEME_KEY_BYTES = 20
THEME_DARK = 0x01                           # directory flags
REC_ANIMATED = 0x01                         # record flags: ThemeAccent.myMessagesAnimated
REC_MOTION = 0x02                           #               ThemeAccent.patternMotion
ROTATIONS = tuple(S.C["rotations"])         # 0, 45, ..., 315
COLOUR_FIELDS = ["accentColor", "myMessagesAccentColor", "myMessagesGradientAccentColor1",
                 "myMessagesGradientAccentColor2", "myMessagesGradientAccentColor3", "wallpaperColor1",
                 "wallpaperColor2", "wallpaperColor3", "wallpaperColor4"]

# ------------------------------------------------------------------------------------------
# generator parameters (changing any of them changes the table)
# ------------------------------------------------------------------------------------------

TABLE_SEED = "multigram-style-table-1"
PER_THEME = 4096
DAY_THEMES = ["Blue", "Arctic Blue", "Day"]
NIGHT_THEMES = ["Dark Blue", "Night"]
TABLE_THEMES = DAY_THEMES + NIGHT_THEMES    # directory order
# Wallpapers are always gradients: 2 colours (linear, uses the rotation) or 3-4 (animated motion gradient).
WALL_COUNT_WEIGHTS = [(2, 0.25), (3, 0.20), (4, 0.55)]
# Headroom: the simulator's solver stops exactly on its thresholds, so the table is solved against these
# (+2.2 % text, +3.3 % non-text, +3.5 % bubble separation) instead of plain WCAG.
HEADROOM = {R.TEXT: 4.6, R.NONTEXT: 3.1, R.SEPARATION: 1.19}
CLASS_NAME = {R.TEXT: "text", R.NONTEXT: "non-text", R.SEPARATION: "separation"}


def wcag_thresholds():
    return [p["threshold"] for p in R.PAIRS]


# ------------------------------------------------------------------------------------------
# overlay A
# ------------------------------------------------------------------------------------------

_SPEC = {}


def overlay_path():
    for p in OVERLAY_A_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("overlay_A.json not found (looked in %s)" % ", ".join(OVERLAY_A_CANDIDATES))


def overlay_spec():
    p = overlay_path()
    if p not in _SPEC:
        with open(p) as f:
            _SPEC[p] = json.load(f)
    return _SPEC[p]


def hook_content_keys(spec):
    return set(a for a, _ in spec["hook"]["pairs"])


# Probe of the accent space used to find the pairs a style cannot move: 24 hues x 3 chromas (the generator's
# band ends and middle) x 9 lightnesses over the generator's accent L band, each on the base theme with no
# bubble or wallpaper override.
PROBE_HUES = [15.0 * i for i in range(24)]
PROBE_L_STEPS = 9
# A pair is palette-limited when the probe moves its contrast by less than this share of its threshold.
PALETTE_LIMITED_RANGE = 0.10

_PROBE = {}


def probe_ranges(theme):
    """{pair index: (min, max) contrast over the probe accents} for the accent-surface pairs (S.ACCENT_PAIRS)."""
    key = (theme.model.tag, id(theme.model), theme.name)
    r = _PROBE.get(key)
    if r is None:
        lo, hi, _ = S.C["accent_L"]["dark" if theme.is_dark else "light"]
        c0, c1 = S.C["accent_chroma"]["dark" if theme.is_dark else "light"]
        r = {}
        for h in PROBE_HUES:
            for cc in (c0, (c0 + c1) * 0.5, c1):
                for j in range(PROBE_L_STEPS):
                    L = lo + (hi - lo) * j / (PROBE_L_STEPS - 1)
                    _, res = S.evaluate(theme, S.base_variant(theme, S.argb_from_oklch(L, cc, h)), S.ACCENT_PAIRS)
                    for i, c in res.items():
                        a, b = r.get(i, (c, c))
                        r[i] = (min(a, c), max(b, c))
        _PROBE[key] = r
    return r


def palette_limited(theme):
    """Indices of the pairs whose contrast the palette sets, not the style.  They are held to plain WCAG instead
    of the headroom thresholds (README.md, "Readability rule"):
      - pairs no accent moves by more than PALETTE_LIMITED_RANGE of their threshold (probe_ranges) and that fall
        below the headroom level for some accent: neutral greys on the page, list, composer and incoming bubble,
        which overlay A sized at the plain WCAG threshold (on the light themes they are constant at 4.50-4.54:1,
        on Night the accent tint moves them by at most 0.2), and on Night the stock grey chats_attachMessage;
      - the digits on the muted unread badge, while they fall below the headroom level for some accent: the
        on-accent hook fills that badge from its per-theme table, one entry for white and one for near-black
        digits, each sized at 4.5:1 today; the style only picks which one.
    Both rules follow the palette: once the palette fix gives a pair headroom for every probe accent, the pair is
    no longer palette-limited and the generator holds it to HEADROOM (regenerate the table then)."""
    muted = overlay_spec()["hook"]["muted"]["key"]
    out = set()
    for i, (lo, hi) in probe_ranges(theme).items():
        p = R.PAIRS[i]
        t = p["threshold"]
        if lo < HEADROOM[t] and ((hi - lo) < PALETTE_LIMITED_RANGE * t or ("key_" + p["bg"]) == muted):
            out.add(i)
    return out


def headroom_thresholds(theme):
    """Generator thresholds: HEADROOM for every pair the style controls, plain WCAG for palette-limited pairs."""
    own = palette_limited(theme)
    return [p["threshold"] if i in own else HEADROOM[p["threshold"]] for i, p in enumerate(R.PAIRS)]


OVERLAY_MODES = ("auto", "apply", "in-tree")


# The out-text guard exactly as the palette fix writes it in Theme.ThemeAccent.fillAccentColors (the line
# multigram/tools/palette_fix_check.py requires).  PaletteFix.isRuntimeAccent(accent) is `accent.id > 100 &&
# (accent.info == null || accent.info.creator)`: true for the table's accents (id > 100, no server theme), like
# the research form `|| id > 100`.  tgsrc.OUT_BLOCK_GUARD_RE accepts both.
PALETTE_FIX_GUARD = ("if (!isMyMessagesGradientColorsNear || org.telegram.messenger.multigram.PaletteFix.isRuntimeAccent(this)) "
                     "{ // MultiGram: runtime accents (generated/custom) always get readable black/white out-bubble texts")
GUARD_FORMS = [("stock", "if (!isMyMessagesGradientColorsNear) {", False),
               ("research `|| id > 100`", "if (!isMyMessagesGradientColorsNear || id > 100) {", True),
               ("palette fix `|| PaletteFix.isRuntimeAccent(this)`", PALETTE_FIX_GUARD, True)]


def parse_theme_java_with_guard(guard_line):
    """tgsrc.parse_theme_java() of this tree's Theme.java with its out-text guard line (the `if (...) {` and the
    rest of that line) replaced by guard_line; line numbers are unchanged."""
    with open(tgsrc.THEME_JAVA, encoding="utf-8") as f:
        raw = f.read()
    fm = re.search(r"public\s+boolean\s+fillAccentColors\s*\(", raw)
    gm = tgsrc.OUT_BLOCK_GUARD_RE.search(raw, fm.end()) if fm else None
    if gm is None:
        raise ValueError("fillAccentColors out-text block guard not found in %s" % tgsrc.THEME_JAVA)
    eol = raw.find("\n", gm.end())
    eol = len(raw) if eol < 0 else eol
    os.makedirs(tgsrc.CACHE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".Theme_", suffix=".java", dir=tgsrc.CACHE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw[:gm.start()] + guard_line + raw[eol:])
        tj = tgsrc.parse_theme_java(tmp)
    finally:
        os.unlink(tmp)
    tj["file"] = os.path.relpath(tgsrc.THEME_JAVA, tgsrc.REPO)
    return tj


def overlay_state(parsed=None):
    """Which parts of overlay A the parsed tree already carries.  The 12 on-accent ThemeColors defaults are
    left out: the app's palette fix keeps them stock and sets them at run time (runtime accents, id > 100)."""
    parsed = parsed or tgsrc.load()
    spec = overlay_spec()
    hook_content = hook_content_keys(spec)
    tc = parsed["themecolors_java"]["defaults"]
    differs = []
    n = 0
    for k, v in sorted(spec["defaults"].items()):
        if k in hook_content:
            continue
        n += 1
        if (tc.get(k, 0) & 0xFFFFFFFF) != v:
            differs.append("ThemeColors %s = %s (overlay A 0x%08X)" % (k, "0x%08X" % (tc[k] & 0xFFFFFFFF) if k in tc else "unset", v))
    for asset, kv in sorted(spec["attheme"].items()):
        vals = parsed["atthemes"][asset]["values"]
        for k, v in sorted(kv.items()):
            n += 1
            if k not in vals or (vals[k][0] & 0xFFFFFFFF) != v:
                differs.append("%s %s = %s (overlay A 0x%08X)" % (asset, k, "0x%08X" % (vals[k][0] & 0xFFFFFFFF) if k in vals else "unset", v))
    guard = bool(parsed["theme_java"].get("out_block_guard_id_gt_100", False))
    return {"values": n, "values_in_tree": n - len(differs), "differs": differs, "out_block_guard": guard}


def resolve_mode(mode, state):
    """auto: 'in-tree' when the tree carries the palette fix (its widened out-text guard, PALETTE_FIX_GUARD, or
    every overlay value), else 'apply'."""
    if mode != "auto":
        return mode
    return "in-tree" if (state["out_block_guard"] or not state["differs"]) else "apply"


def build_model(parsed, mode):
    """engine.Model for parsed theme sources plus overlay A.
      apply   : the whole overlay on top of the sources: ThemeColors defaults and .attheme values assigned,
                accent exclusions added to the set, on-accent hook and the widened out-text guard switched on.
                Every part assigns an absolute value or adds to a set, so applying it to a tree that already
                carries overlay A changes nothing (check_style_table.py's self-test shows this).
      in-tree : the tree already carries the palette fix; its own ThemeColors/.attheme values are used as they
                are (so a later change to them is seen), and only the parts that live in Java code the parser
                does not read are added: the accent exclusions (PaletteFix.addAccentExclusions), the on-accent
                hook (PaletteFix.applyToCurrentColors) and the out-text guard."""
    spec = overlay_spec()
    if mode == "in-tree":
        spec = dict(spec, defaults={}, attheme={}, tag=spec["tag"] + "-in-tree")
    elif mode != "apply":
        raise ValueError(mode)
    return E.Model(parsed, spec)


_MODELS = {}


def model(mode="auto"):
    """(engine.Model, resolved mode, overlay state) for the tree's Theme.java / ThemeColors.java / .attheme
    files (TG_REPO, default: this repository) plus overlay A; see build_model()."""
    parsed = tgsrc.load()
    state = overlay_state(parsed)
    mode = resolve_mode(mode, state)
    m = _MODELS.get(mode)
    if m is None:
        m = build_model(parsed, mode)
        _MODELS[mode] = m
    return m, mode, state


def baked_parsed(parsed):
    """A copy of the parsed tree with overlay A written into it the way the palette fix does it (ThemeColors
    defaults except the 12 on-accent ones, .attheme values, and Theme.java parsed with PALETTE_FIX_GUARD), for
    the idempotency test."""
    spec = overlay_spec()
    hook_content = hook_content_keys(spec)
    p = copy.deepcopy(parsed)
    p["theme_java"] = parse_theme_java_with_guard(PALETTE_FIX_GUARD)
    for k, v in spec["defaults"].items():
        if k not in hook_content:
            p["themecolors_java"]["defaults"][k] = E.s32(v)
    for asset, kv in spec["attheme"].items():
        for k, v in kv.items():
            p["atthemes"][asset]["values"][k] = [E.s32(v), None]
    if not p["theme_java"]["out_block_guard_id_gt_100"]:
        raise ValueError("the simulator does not recognise the palette fix's out-text guard; update sim/tgsrc.py")
    return p


def forbidden_accents(theme):
    """Accent colours a generated accent must not equal: the theme's accentBaseColor (no re-tint at all) and
    every built-in preset accent (on Blue, preset 99's colour would switch getColor to ThemeColors defaults)."""
    out = {theme.accentBaseColor}
    for a in theme.accents.values():
        out.add(a.accentColor)
    return out


# ------------------------------------------------------------------------------------------
# generator: the simulator's seeded OKLCH solver, wallpaper always a 2-4 colour gradient, no pattern
# ------------------------------------------------------------------------------------------

def draw_attempt(rng, dark):
    """style_sim.draw_attempt without the pattern draws and with WALL_COUNT_WEIGHTS; fixed draw order."""
    C = S.C
    d = {}
    d["accent_h"] = rng.between(0.0, 360.0)
    d["accent_C"] = rng.between(*C["accent_chroma"]["dark" if dark else "light"])
    d["bubble_count"] = S.weighted(rng, C["bubble_count_weights"])
    d["bubble_tone_u"] = rng.uniform()
    d["bubble_hue_off"] = rng.between(-C["bubble_hue_offset"], C["bubble_hue_offset"])
    d["bubble_L_u"] = rng.uniform()
    d["bubble_C_u"] = rng.uniform()
    d["bubble_extra"] = [(rng.between(-C["bubble_extra_hue"], C["bubble_extra_hue"]),
                          rng.between(-C["bubble_extra_L"], C["bubble_extra_L"])) for _ in range(3)]
    d["animated_u"] = rng.uniform()
    d["wall_count"] = S.weighted(rng, WALL_COUNT_WEIGHTS)
    d["wall_complement_u"] = rng.uniform()
    d["wall_hue_off"] = rng.between(-C["wall_hue_offset"], C["wall_hue_offset"])
    d["wall_C_u"] = rng.uniform()
    d["wall_L_u"] = rng.uniform()
    d["wall_extra"] = [(rng.between(-C["wall_extra_hue"], C["wall_extra_hue"]),
                        rng.between(-C["wall_extra_L"], C["wall_extra_L"])) for _ in range(3)]
    d["rotation_i"] = rng.below(len(C["rotations"]))
    d["motion_u"] = rng.uniform()
    d["accent_L_u"] = rng.uniform()
    return d


def wallpaper_of(d, band, L):
    """No pattern: empty slug and zero intensity, so the model renders the plain gradient (fill = the gradient
    samples; service pill through the intensity >= 0 colour matrix, as MotionBackgroundDrawable's default
    intensity 100 selects in Theme.applyChatServiceMessageColor), which is what the app draws when
    ThemeAccent.getPathToWallpaper() is null."""
    return {"source": "custom", "colors": S.wall_colors(d, d["accent_h"], band, L, d["wall_count"]),
            "rotation": S.C["rotations"][d["rotation_i"]], "pattern_intensity": 0.0, "pattern_slug": "",
            "motion": d["motion_u"] < 0.5}


def solve_wallpaper(theme, d, v0, thr, stats):
    """style_sim.solve_wallpaper for the no-pattern case: bisection on the wallpaper's OKLCH L."""
    band = S.C["wall"]["dark" if theme.is_dark else "light"]
    lo, hi = band["L"]
    L = band["L_start"][0] + (band["L_start"][1] - band["L_start"][0]) * d["wall_L_u"]
    for _ in range(S.C["wall_steps"]):
        v = dict(v0)
        v["wallpaper"] = wallpaper_of(d, band, L)
        ev, res = S.evaluate(theme, v, S.WALL_PAIRS)
        stats["evals"] += 1
        f = S.failing(res, thr)
        if not f:
            return v, L
        up = down = False
        for i in f:
            if S._direction(ev, i, moving_fg=False) > 0:
                up = True
            else:
                down = True
        if up and down:
            return None, None
        if up:
            lo = L
        else:
            hi = L
        L = (lo + hi) * 0.5
    return None, None


def shape_ok(v):
    """The colour counts the record declares are the ones the app renders: distinct bubble stops for a
    gradient bubble, distinct wallpaper colours (two equal colours would collapse to a solid ColorDrawable)."""
    bub = [v["my_messages_accent"]] + list(v["my_messages_gradient"])
    if not (len(v["my_messages_gradient"]) == 1 and bub[0] == bub[1]):    # solid bubble: gradient1 == colour by design
        if len(set(bub)) != len(bub):
            return False
    w = v["wallpaper"]["colors"]
    return 2 <= len(w) <= 4 and len(set(w)) == len(w)


def _reject(stats, why, pairs=()):
    """Diagnostics of failed attempts (only read when the generator stalls): stage counts and failing pairs."""
    r = stats.setdefault("reject", {})
    r["<%s>" % why] = r.get("<%s>" % why, 0) + 1
    for i in pairs:
        r[R.PAIRS[i]["name"]] = r.get(R.PAIRS[i]["name"], 0) + 1


def gen_entry(theme, rng, thr, stats):
    """One candidate: up to max_attempts solver attempts; (variant, contrasts) or (None, None)."""
    bad_accents = forbidden_accents(theme)
    for attempt in range(S.C["max_attempts"]):
        d = draw_attempt(rng, theme.is_dark)
        accent, aL = S.solve_accent(theme, d, thr, stats)
        if accent is None:
            # which accent pairs fail at the attempt's starting lightness (diagnostics only; not counted in evals)
            lo, hi, (s0, s1) = S.C["accent_L"]["dark" if theme.is_dark else "light"]
            acc0 = S.argb_from_oklch(s0 + (s1 - s0) * d["accent_L_u"], d["accent_C"], d["accent_h"])
            _, res0 = S.evaluate(theme, S.base_variant(theme, acc0), S.ACCENT_PAIRS)
            _reject(stats, "accent stage", S.failing(res0, thr))
            continue
        if accent in bad_accents:
            _reject(stats, "preset accent")
            continue
        v, bL = S.solve_bubble(theme, d, accent, d["accent_h"], thr, stats)
        if v is None:
            _reject(stats, "bubble stage")
            continue
        v, wL = solve_wallpaper(theme, d, v, thr, stats)
        if v is None or not shape_ok(v):
            _reject(stats, "wallpaper stage" if v is None else "repeated colour")
            continue
        _, res = S.evaluate(theme, v)
        stats["evals"] += 1
        f = S.failing(res, thr)
        if f:
            _reject(stats, "final check", f)
            continue
        v["solver"] = {"attempt": attempt + 1, "accent_oklch": [aL, d["accent_C"], d["accent_h"]], "bubble_L": bL, "wallpaper_L": wL}
        return v, res
    return None, None


def candidate_seed(theme_name, k):
    return "%s/%s/%d" % (TABLE_SEED, theme_name, k)


def gen_candidate(m, theme_name, k, thr=None):
    th = m.themes[theme_name]
    rng = S.SplitMix64(S.seed_state(candidate_seed(theme_name, k)))
    stats = {"evals": 0}
    v, res = gen_entry(th, rng, thr or headroom_thresholds(th), stats)
    return v, res, stats


# ------------------------------------------------------------------------------------------
# records
# ------------------------------------------------------------------------------------------

def u32(c):
    return c & 0xFFFFFFFF


def encode_record(v):
    grad = list(v["my_messages_gradient"]) + [0] * (3 - len(v["my_messages_gradient"]))
    w = v["wallpaper"]
    if w.get("pattern_slug") or w.get("pattern_intensity"):
        raise ValueError("table entries have no wallpaper pattern")
    wc = list(w["colors"]) + [0] * (4 - len(w["colors"]))
    flags = (REC_ANIMATED if v["my_messages_animated"] else 0) | (REC_MOTION if w["motion"] else 0)
    return RECORD.pack(u32(v["accent"]), u32(v["my_messages_accent"]), *[u32(c) for c in grad], *[u32(c) for c in wc],
                       ROTATIONS[ROTATIONS.index(w["rotation"])], flags, 0)


def decode_record(b, theme_name):
    """Record bytes -> simulator variant (what the app assigns to its runtime ThemeAccent, see README.md)."""
    f = RECORD.unpack(b)
    grad = [E.s32(c) for c in f[2:5] if c != 0]
    wc = [E.s32(c) for c in f[5:9] if c != 0]
    return {"base_theme": theme_name, "accent": E.s32(f[0]), "my_messages_accent": E.s32(f[1]), "my_messages_gradient": grad,
            "my_messages_animated": bool(f[10] & REC_ANIMATED),
            "wallpaper": {"source": "custom", "colors": wc, "rotation": f[9], "pattern_intensity": 0.0, "pattern_slug": "",
                          "motion": bool(f[10] & REC_MOTION)}}


def record_problems(b):
    """Format rules of one 40-byte record (README.md); [] when it is well-formed."""
    f = RECORD.unpack(b)
    out = []
    for i, c in enumerate(f[:9]):
        if c != 0 and (c >> 24) != 0xFF:
            out.append("%s 0x%08X is not opaque" % (COLOUR_FIELDS[i], c))
    for i in (0, 1, 2, 5, 6):
        if f[i] == 0:
            out.append("%s is 0 but required" % COLOUR_FIELDS[i])
    if f[4] != 0 and f[3] == 0:
        out.append("myMessagesGradientAccentColor3 set without myMessagesGradientAccentColor2")
    if f[8] != 0 and f[7] == 0:
        out.append("wallpaperColor4 set without wallpaperColor3")
    if f[9] not in ROTATIONS:
        out.append("rotation %d is not a multiple of 45 in [0, 315]" % f[9])
    if f[10] & ~(REC_ANIMATED | REC_MOTION):
        out.append("unknown flag bits 0x%02X" % f[10])
    if (f[10] & REC_ANIMATED) and f[3] == 0:
        out.append("animated bubble with fewer than 3 colours")
    if f[11] != 0:
        out.append("reserved byte is 0x%02X" % f[11])
    bub = [f[1], f[2]] + [c for c in f[3:5] if c]
    if (len(bub) > 2 or f[2] != f[1]) and len(set(bub)) != len(bub):
        out.append("repeated bubble gradient colour")
    wc = [c for c in f[5:9] if c]
    if len(set(wc)) != len(wc):
        out.append("repeated wallpaper colour")
    return out


def build_asset(entries_by_theme, themes):
    """entries_by_theme: {theme name: [record bytes]}; themes: [(name, is_dark)] in directory order."""
    dir_bytes = b""
    rec_bytes = b""
    first = 0
    for name, dark in themes:
        key = name.encode("utf-8")
        if not 0 < len(key) < THEME_KEY_BYTES:
            raise ValueError("theme key %r does not fit the %d-byte field" % (name, THEME_KEY_BYTES))
        recs = entries_by_theme[name]
        dir_bytes += DIR_ENTRY.pack(key, THEME_DARK if dark else 0, 0, 0, first, len(recs))
        rec_bytes += b"".join(recs)
        first += len(recs)
    body = dir_bytes + rec_bytes
    head = HEADER.pack(MAGIC, VERSION, HEADER.size, len(themes), DIR_ENTRY.size, RECORD.size, 0, first, zlib.crc32(body) & 0xFFFFFFFF)
    return head + body


class FormatError(ValueError):
    pass


def parse_asset(data):
    """-> (header dict, [directory dicts], [record bytes]); raises FormatError on any layout violation."""
    if len(data) < HEADER.size:
        raise FormatError("file shorter than the %d-byte header" % HEADER.size)
    magic, version, hsize, tcount, dsize, rsize, reserved, rcount, crc = HEADER.unpack_from(data, 0)
    hdr = {"magic": magic, "version": version, "header_size": hsize, "theme_count": tcount, "dir_entry_size": dsize,
           "record_size": rsize, "reserved": reserved, "record_count": rcount, "crc32": crc}
    if magic != MAGIC:
        raise FormatError("bad magic %r" % magic)
    if version != VERSION:
        raise FormatError("version %d, expected %d" % (version, VERSION))
    if (hsize, dsize, rsize) != (HEADER.size, DIR_ENTRY.size, RECORD.size):
        raise FormatError("sizes header/dir/record = %d/%d/%d, expected %d/%d/%d" % (hsize, dsize, rsize, HEADER.size, DIR_ENTRY.size, RECORD.size))
    if reserved != 0:
        raise FormatError("reserved header field is %d" % reserved)
    if tcount == 0:
        raise FormatError("no base themes")
    expect = hsize + tcount * dsize + rcount * rsize
    if len(data) != expect:
        raise FormatError("file is %d bytes, header implies %d" % (len(data), expect))
    if zlib.crc32(data[hsize:]) & 0xFFFFFFFF != crc:
        raise FormatError("CRC-32 mismatch")
    dirs = []
    nxt = 0
    for t in range(tcount):
        raw, flags, r1, r2, first, count = DIR_ENTRY.unpack_from(data, hsize + t * dsize)
        name_b = raw.rstrip(b"\0")
        if b"\0" in name_b or not name_b or len(name_b) == THEME_KEY_BYTES:
            raise FormatError("theme %d: key is empty, unterminated or not NUL-padded" % t)
        try:
            name = name_b.decode("utf-8")
        except UnicodeDecodeError:
            raise FormatError("theme %d: key is not UTF-8" % t)
        if flags & ~THEME_DARK or r1 or r2:
            raise FormatError("theme %s: unknown flag bits or non-zero reserved fields" % name)
        if first != nxt or count == 0:
            raise FormatError("theme %s: records [%d, +%d) are not contiguous after the previous theme" % (name, first, count))
        nxt = first + count
        dirs.append({"name": name, "dark": bool(flags & THEME_DARK), "first": first, "count": count})
    if nxt != rcount:
        raise FormatError("directory covers %d records, header says %d" % (nxt, rcount))
    if len(set(d["name"] for d in dirs)) != len(dirs):
        raise FormatError("duplicate theme key in the directory")
    base = hsize + tcount * dsize
    recs = [data[base + i * rsize: base + (i + 1) * rsize] for i in range(rcount)]
    return hdr, dirs, recs


# ------------------------------------------------------------------------------------------
# evaluation
# ------------------------------------------------------------------------------------------

def evaluate(m, v, lazy=True):
    """All 99 pair contrasts of a variant on model m, as a list in R.PAIRS order.  lazy=False runs the full
    refreshThemeColors port instead of the per-key replay (same result; used as a cross-check)."""
    th = m.themes[v["base_theme"]]
    acc = S.to_accent(v)
    ev = R.Evaluator(E.palette(th, acc, S.GEN_ACCENT_ID, lazy=lazy))
    res = ev.all()
    return [res[i] for i in range(len(R.PAIRS))]


def margins(res):
    """Per threshold class: (min contrast / WCAG threshold, pair name, contrast)."""
    out = {}
    for i, p in enumerate(R.PAIRS):
        t = p["threshold"]
        r = res[i] / t
        cur = out.get(t)
        if cur is None or r < cur[0]:
            out[t] = (r, p["name"], res[i])
    return out
