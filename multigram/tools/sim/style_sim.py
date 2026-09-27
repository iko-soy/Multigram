#!/usr/bin/env python3
"""Seeded, readability-checked style generator for the Telegram-Android theme engine (simulation).

  python3 style_sim.py --seed X        genome JSON for seed string X
  python3 style_sim.py --measure N     pass rates of (a) uniform RGB, (b) uniform HSV, (c) the
                                       constrained OKLCH generator, N seeds per base theme
  python3 style_sim.py --baseline      the suite on each base theme with its stock default accent

Everything colour-related runs through engine.py (bit-exact port of fillAccentColors / getColor,
verified against the verbatim Java) and readability.py (pair suite, wallpaper and service models).
Generator math uses only + - * / floor and comparisons on IEEE doubles plus literal tables
(detmath.py), so a Java or JavaScript port reproduces the same genome bit for bit.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import detmath as D          # noqa: E402
import engine as E           # noqa: E402
import readability as R      # noqa: E402

GENOME_VERSION = 1
LIGHT_THEMES = ["Blue", "Arctic Blue", "Day"]
DARK_THEMES = ["Dark Blue", "Night"]
ALL_THEMES = ["Blue", "Dark Blue", "Arctic Blue", "Day", "Night"]
GEN_ACCENT_ID = 101                 # first id ThemeInfo.createNewAccent()/getAccent(true) hands out (lastAccentId = 100)
DELETE = 0x100000000                # ThemeAccent "remove this wallpaper key" sentinel (long), as setAccentColorOptions uses
BUBBLE_RADIUS_RANGE = (0, 17)       # ThemeActivity bubble-radius slider (SharedConfig.bubbleRadius, default 17)
# The 25 distinct non-empty pattern slugs of the built-in accent presets, in source order
# (Theme.java:3909 Blue, 3933 Dark Blue, 3957 Arctic Blue, 3981 Day (none), 4005 Night).
# Checked against the parsed source at start-up (check_pattern_slugs).
PATTERN_SLUGS = [
    "p-pXcflrmFIBAAAAvXYQk-mCwZU", "JqSUrO0-mFIBAAAAWwTvLzoWGQI", "O-wmAfBPSFADAAAA4zINVfD_bro", "RepJ5uE_SVABAAAAr4d0YhgB850",
    "-Xc-np9y2VMCAAAARKr0yNNPYW0", "fqv01SQemVIBAAAApND8LDRUhRU", "lp0prF8ISFAEAAAA_p385_CvG0w", "heptcj-hSVACAAAAC9RrMzOa-cs",
    "PllZ-bf_SFAEAAAA8crRfwZiDNg", "dhf9pceaQVACAAAAbzdVo4SCiZA", "Ujx2TFcJSVACAAAARJ4vLa50MkM", "dk_wwlghOFACAAAAfz9xrxi6euw",
    "9LW_RcoOSVACAAAAFTk3DTyXN-M", "kO4jyq55SFABAAAA0WEpcLfahXk", "CJNyxPMgSVAEAAAAvW9sMwc51cw", "9GcNVISdSVADAAAAUcw5BYjELW4",
    "F5oWoCs7QFACAAAAgf2bD_mg8Bw", "9ShF73d1MFIIAAAAjWnm8_ZMe8Q", "3rX-PaKbSFACAAAAEiHNvcEm6X4", "MIo6r0qGSFAFAAAAtL8TsDzNX60",
    "pgJfpFNRSFABAAAACDT8s5sEjfc", "ptuUd96JSFACAAAATobI23sPpz0", "9iklpvIPQVABAAAAORQXKur_Eyc", "YIxYGEALQVADAAAAA3QbEH0AowY",
    "Nl8Pg2rBQVACAAAA25Lxtb8SDp0",
]


def check_pattern_slugs(model):
    seen = []
    for tn in ALL_THEMES:
        th = model.themes[tn]
        for aid in th.accent_order:
            x = th.accents[aid].patternSlug
            if x and x not in seen:
                seen.append(x)
    return seen == PATTERN_SLUGS

MASK64 = (1 << 64) - 1


# ------------------------------------------------------------------------------------------
# PRNG: seed string -> SHA-256 -> first 8 bytes big-endian -> SplitMix64
# ------------------------------------------------------------------------------------------

def seed_state(seed):
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")


class SplitMix64:
    def __init__(self, state):
        self.s = state & MASK64

    def next_u64(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & MASK64
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def uniform(self):
        """[0, 1) with 53 random bits: (x >>> 11) * 2^-53."""
        return (self.next_u64() >> 11) * (1.0 / 9007199254740992.0)

    def between(self, a, b):
        return a + (b - a) * self.uniform()

    def below(self, n):
        return int(math.floor(self.uniform() * n))

    def fork(self):
        """Child stream seeded with the next output (keeps day/night/misc independent)."""
        return SplitMix64(self.next_u64())


# ------------------------------------------------------------------------------------------
# generator constants
# ------------------------------------------------------------------------------------------

C = {
    # accent (OKLCH); L is solved per attempt by bisection inside [L_lo, L_hi] starting at L_start
    "accent_chroma": {"light": (0.07, 0.17), "dark": (0.07, 0.17)},
    "accent_L": {"light": (0.30, 0.80, (0.42, 0.70)), "dark": (0.45, 0.92, (0.62, 0.80))},   # lo, hi, start range (uniform)
    "accent_steps": 8,
    # outgoing bubble
    "bubble_count_weights": [(1, 0.30), (2, 0.30), (3, 0.15), (4, 0.25)],  # 1 = solid (gradient1 == colour)
    "bubble_hue_offset": 50.0,          # bubble hue = accent hue + U(-x, x)
    "bubble_extra_hue": 35.0,           # each extra gradient stop: bubble hue + U(-x, x)
    "bubble_extra_L": 0.03,             # each extra stop: L + U(-x, x)
    "bubble_light_share": 0.55,         # light themes: share of light (black-text) bubbles
    "bubble_light": {"L": (0.905, 0.955), "C": (0.025, 0.075), "step": 0.012, "L_max": 0.975},
    "bubble_dark_on_light": {"L": (0.40, 0.50), "C": (0.08, 0.16), "step": -0.025, "L_min": 0.30},
    "bubble_dark_on_dark": {"L": (0.36, 0.50), "C": (0.06, 0.16), "step": -0.025, "L_min": 0.28},
    "bubble_steps": 4,
    "animated_share": 0.5,              # >= 3 stops: animated flag
    # wallpaper
    "wall_count_weights": [(1, 0.15), (2, 0.20), (3, 0.15), (4, 0.50)],
    "wall_hue_offset": 50.0,            # wallpaper hue = accent hue + U(-x, x) (+180 with p=complement_share)
    "wall_complement_share": 0.20,
    "wall_extra_hue": 25.0,
    "wall_extra_L": 0.05,
    "wall": {
        "light": {"C": (0.02, 0.07), "L": (0.50, 0.90), "L_start": (0.72, 0.84)},
        "dark": {"C": (0.015, 0.05), "L": (0.06, 0.40), "L_start": (0.12, 0.20)},
        "dark_neg": {"C": (0.03, 0.10), "L": (0.25, 0.75), "L_start": (0.40, 0.60)},   # intensity < 0: seen through the pattern only
    },
    "wall_steps": 7,
    "intensity": {"light": (0.25, 0.60), "dark_pos": (0.20, 0.50), "dark_neg": (-0.75, -0.35)},
    "dark_negative_share": 0.40,
    "pattern_share": 0.80,              # motion wallpapers with a pattern (negative intensity always has one)
    "rotations": [0, 45, 90, 135, 180, 225, 270, 315],
    "bubble_radius": (6, 17),
    "max_attempts": 12,
    # accent policy under the strict pass rule (derived from the feasibility scan, see findings):
    # "free" = OKLCH hue/chroma drawn, lightness solved; "anchored" = accentColor kept at the theme's
    # stock default accent (main-accent keys stay exactly stock), only bubbles and wallpaper vary.
    # "wallpaper-only" = accent and outgoing bubble both kept at the stock default accent's values.
    "accent_policy": {"Blue": "wallpaper-only", "Dark Blue": "anchored", "Night": "anchored", "Arctic Blue": "free", "Day": "free"},
    "free_mode_slack": 0.10,
}


def weighted(rng, table):
    u = rng.uniform()
    acc = 0.0
    for v, w in table:
        acc += w
        if u < acc:
            return v
    return table[-1][0]


def argb_from_oklch(L, Cc, h):
    r, g, b, _ = D.oklch_to_rgb8(L, Cc, h)
    return E.s32(0xFF000000 | (r << 16) | (g << 8) | b)


def hex32(c):
    return "0x%08X" % (c & 0xFFFFFFFF)


# ------------------------------------------------------------------------------------------
# genome <-> ThemeAccent
# ------------------------------------------------------------------------------------------

def to_accent(v):
    """Genome variant -> ThemeAccent fields (what the app would assign before refreshThemeColors())."""
    acc = E.Accent(id=GEN_ACCENT_ID)
    acc.accentColor = v["accent"]
    acc.myMessagesAccentColor = v["my_messages_accent"]
    g = v["my_messages_gradient"] + [0, 0, 0]
    acc.myMessagesGradientAccentColor1, acc.myMessagesGradientAccentColor2, acc.myMessagesGradientAccentColor3 = g[0], g[1], g[2]
    acc.myMessagesAnimated = bool(v["my_messages_animated"])
    w = v["wallpaper"]
    cs = list(w["colors"])
    if w.get("source") == "theme":
        slots = [0, 0, 0, 0]              # no override: the base theme's chat_wallpaper* keys stay
    else:                                 # "default" (no colours) -> all removed -> built-in wallpaper
        slots = [(cs[i] if i < len(cs) else DELETE) for i in range(4)]
    acc.backgroundOverrideColor = slots[0]
    acc.backgroundGradientOverrideColor1 = slots[1]
    acc.backgroundGradientOverrideColor2 = slots[2]
    acc.backgroundGradientOverrideColor3 = slots[3]
    acc.backgroundRotation = w["rotation"]
    acc.patternSlug = w["pattern_slug"]
    # sim-verify fix: the app reads (int)(patternIntensity * 100f) (Theme.java:9361), which truncates
    # 0.53f -> 52 and 0.59f -> 58.  Store the percent p as (p + 0.5*sign(p)) / 100f so the
    # truncation yields exactly p for every p in [-100, 100].
    pct = int(math.floor(w["pattern_intensity"] * 100.0 + 0.5)) if w["pattern_intensity"] >= 0 else -int(math.floor(-w["pattern_intensity"] * 100.0 + 0.5))
    acc.patternIntensity = E.f32((pct + (0.5 if pct > 0 else (-0.5 if pct < 0 else 0.0))) / 100.0)
    acc.patternMotion = bool(w["motion"])
    return acc


def evaluate(theme, v, idx=None):
    acc = to_accent(v)
    ev = R.Evaluator(E.palette(theme, acc, GEN_ACCENT_ID))
    return ev, ev.all(idx)


# ------------------------------------------------------------------------------------------
# thresholds, accent-affected keys, pair groups
# ------------------------------------------------------------------------------------------

_THR = {}
_AFFECTED = {}
BG_SPECIAL = ("@in_bubble", "@out_bubble", "@wallpaper", "@service", "@service_lite")
ACCENT_PAIRS = [i for i, p in enumerate(R.PAIRS) if p["bg"] not in ("@out_bubble", "@wallpaper", "@service", "@service_lite")]
BUBBLE_PAIRS = [i for i, p in enumerate(R.PAIRS) if p["bg"] == "@out_bubble"]
WALL_PAIRS = [i for i, p in enumerate(R.PAIRS) if p["bg"] in ("@wallpaper", "@service", "@service_lite")]


# canvas-fix: pass rule selector.  "strict" = min(WCAG, stock) (sim/sim_fixed); "wcag" = plain WCAG
# thresholds (4.5 text, 3.0 non-text, 1.15 bubble separation).  SERVICE = "on": the two service-text
# pairs count at 4.5; "off": they are scored but not part of the pass rule (to show what they force).
RULE = {"rule": "strict", "service": "on"}
SERVICE_PAIRS = ("service_text", "service_text_lite")


def thresholds(theme, slack=0.0, rule=None):
    """Effective per-pair thresholds.  rule 'strict': min(WCAG threshold, stock contrast); with slack > 0
    the stock-relative ones (pairs Telegram's stock already fails) are relaxed to stock * (1 - slack).
    rule 'wcag': the plain WCAG threshold of every pair (service pairs 0.0 when RULE['service'] == 'off')."""
    rule = rule or RULE["rule"]
    key = (theme.model.tag, theme.name, slack, rule, RULE["service"])
    t = _THR.get(key)
    if t is None:
        if rule == "wcag":
            t = [(0.0 if (RULE["service"] == "off" and p["name"] in SERVICE_PAIRS) else p["threshold"]) for p in R.PAIRS]
        else:
            base = R.baseline(theme)
            t = []
            for i, p in enumerate(R.PAIRS):
                if base[i] >= p["threshold"]:
                    t.append(p["threshold"])
                else:
                    t.append(base[i] * (1.0 - slack))
        _THR[key] = t
    return t


def affected_keys(theme):
    """Keys whose resolved colour depends on accentColor for this base theme (two probe accents)."""
    a = _AFFECTED.get((theme.model.tag, theme.name))
    if a is None:
        names = set()
        for p in R.PAIRS:
            for k in (p["fg"], p["bg"]):
                if not k.startswith("@"):
                    names.add(k)
        pa = E.palette(theme, E.Accent(id=GEN_ACCENT_ID, accentColor=argb_from_oklch(0.6, 0.12, 30.0)), GEN_ACCENT_ID)
        pb = E.palette(theme, E.Accent(id=GEN_ACCENT_ID, accentColor=argb_from_oklch(0.6, 0.12, 150.0)), GEN_ACCENT_ID)
        a = set(n for n in names if pa.get(n) != pb.get(n))
        _AFFECTED[(theme.model.tag, theme.name)] = a
    return a


def lum_over(c, bg):
    return D.luminance(R.over(c, bg))


def failing(res, thr):
    return [i for i, c in res.items() if c < thr[i]]


# ------------------------------------------------------------------------------------------
# (c) constrained generator
# ------------------------------------------------------------------------------------------

def draw_attempt(rng, dark):
    """Every attempt consumes exactly the same number of draws, in this order."""
    d = {}
    d["accent_h"] = rng.between(0.0, 360.0)
    d["accent_C"] = rng.between(*C["accent_chroma"]["dark" if dark else "light"])
    d["bubble_count"] = weighted(rng, C["bubble_count_weights"])
    d["bubble_tone_u"] = rng.uniform()
    d["bubble_hue_off"] = rng.between(-C["bubble_hue_offset"], C["bubble_hue_offset"])
    d["bubble_L_u"] = rng.uniform()
    d["bubble_C_u"] = rng.uniform()
    d["bubble_extra"] = [(rng.between(-C["bubble_extra_hue"], C["bubble_extra_hue"]),
                          rng.between(-C["bubble_extra_L"], C["bubble_extra_L"])) for _ in range(3)]
    d["animated_u"] = rng.uniform()
    d["wall_count"] = weighted(rng, C["wall_count_weights"])
    d["wall_complement_u"] = rng.uniform()
    d["wall_hue_off"] = rng.between(-C["wall_hue_offset"], C["wall_hue_offset"])
    d["wall_C_u"] = rng.uniform()
    d["wall_L_u"] = rng.uniform()
    d["wall_extra"] = [(rng.between(-C["wall_extra_hue"], C["wall_extra_hue"]),
                        rng.between(-C["wall_extra_L"], C["wall_extra_L"])) for _ in range(3)]
    d["negative_u"] = rng.uniform()
    d["intensity_u"] = rng.uniform()
    d["pattern_u"] = rng.uniform()
    d["rotation_i"] = rng.below(len(C["rotations"]))
    d["motion_u"] = rng.uniform()
    d["accent_L_u"] = rng.uniform()
    d["pattern_i"] = rng.below(len(PATTERN_SLUGS))
    return d


def _direction(ev, i, moving_fg):
    """+1: the moving element must get lighter, -1: darker (move away from the other side)."""
    p = R.PAIRS[i]
    pal = ev.pal
    bgs = ev.surface(p["bg"])
    if p["bg"] == "@service":
        fg = ev.wp.service_text
    elif p["bg"] == "@service_lite":
        fg = ev.wp.service_lite_text
    elif p["bg"] == "@wallpaper":
        bub = ev.surface("@in_bubble" if p["fg"] == "chat_inBubble" else "@out_bubble")
        yb = sum(D.luminance(b) for b in bub) / len(bub)
        yw = sum(D.luminance(w) for w in ev.wp.fill) / len(ev.wp.fill)
        # moving element = wallpaper (bg)
        return 1 if yw > yb else -1
    else:
        fg = pal.get(p["fg"])
    yf = sum(lum_over(fg, s) for s in bgs) / len(bgs)
    yb = sum(D.luminance(s) for s in bgs) / len(bgs)
    if moving_fg:
        return 1 if yf > yb else -1
    return 1 if yb > yf else -1


def base_variant(theme, accent):
    return {"base_theme": theme.name, "accent": accent, "my_messages_accent": 0, "my_messages_gradient": [],
            "my_messages_animated": False,
            "wallpaper": {"source": "custom", "colors": [], "rotation": 45, "pattern_intensity": 0.0, "pattern_slug": "", "motion": False}}


def solve_accent(theme, d, thr, stats):
    dark = theme.is_dark
    lo, hi, (s0, s1) = C["accent_L"]["dark" if dark else "light"]
    L = s0 + (s1 - s0) * d["accent_L_u"]
    aff = affected_keys(theme)
    h, Cc = d["accent_h"], d["accent_C"]
    for _ in range(C["accent_steps"]):
        acc = argb_from_oklch(L, Cc, h)
        v = base_variant(theme, acc)
        ev, res = evaluate(theme, v, ACCENT_PAIRS)
        stats["evals"] += 1
        f = failing(res, thr)
        if not f:
            return acc, L
        up = down = False
        for i in f:
            p = R.PAIRS[i]
            fg_m = p["fg"] in aff
            bg_m = (not p["bg"].startswith("@")) and p["bg"] in aff
            if not fg_m and not bg_m:
                return None, None           # the accent cannot fix this pair
            dr = _direction(ev, i, moving_fg=fg_m)
            if dr > 0:
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


def bubble_colors(theme, d, accent_h, L, Cc, count):
    h = accent_h + d["bubble_hue_off"]
    cols = [argb_from_oklch(L, Cc, h)]
    for k in range(count - 1):
        dh, dL = d["bubble_extra"][k]
        cols.append(argb_from_oklch(min(0.99, max(0.05, L + dL)), Cc, h + dh))
    return cols


def solve_bubble(theme, d, accent, accent_h, thr, stats):
    dark = theme.is_dark
    count = d["bubble_count"]
    if dark:
        band = C["bubble_dark_on_dark"]
    elif d["bubble_tone_u"] < C["bubble_light_share"]:
        band = C["bubble_light"]
    else:
        band = C["bubble_dark_on_light"]
    L = band["L"][0] + (band["L"][1] - band["L"][0]) * d["bubble_L_u"]
    Cc = band["C"][0] + (band["C"][1] - band["C"][0]) * d["bubble_C_u"]
    animated = count >= 3 and d["animated_u"] < C["animated_share"]
    for _ in range(C["bubble_steps"]):
        cols = bubble_colors(theme, d, accent_h, L, Cc, count)
        grad = cols[1:] if count > 1 else [cols[0]]          # solid: gradient1 == colour (see notes)
        v = base_variant(theme, accent)
        v["my_messages_accent"] = cols[0]
        v["my_messages_gradient"] = grad
        v["my_messages_animated"] = animated
        ev, res = evaluate(theme, v, BUBBLE_PAIRS)
        stats["evals"] += 1
        if not failing(res, thr):
            return v, L
        L = L + band["step"]
        if ("L_max" in band and L > band["L_max"]) or ("L_min" in band and L < band["L_min"]):
            break
    return None, None


def wall_params(theme, d):
    dark = theme.is_dark
    count = d["wall_count"]
    negative = dark and count >= 3 and d["negative_u"] < C["dark_negative_share"]
    if negative:
        band = C["wall"]["dark_neg"]
        lo_i, hi_i = C["intensity"]["dark_neg"]
    elif dark:
        band = C["wall"]["dark"]
        lo_i, hi_i = C["intensity"]["dark_pos"]
    else:
        band = C["wall"]["light"]
        lo_i, hi_i = C["intensity"]["light"]
    pattern = count >= 3 and (negative or d["pattern_u"] < C["pattern_share"])
    intensity = (lo_i + (hi_i - lo_i) * d["intensity_u"]) if count >= 3 else 0.0
    intensity = math.floor(intensity * 100.0 + 0.5) / 100.0
    return count, negative, band, pattern, intensity


def wall_colors(d, accent_h, band, L, count):
    h = accent_h + d["wall_hue_off"] + (180.0 if d["wall_complement_u"] < C["wall_complement_share"] else 0.0)
    Cc = band["C"][0] + (band["C"][1] - band["C"][0]) * d["wall_C_u"]
    cols = [argb_from_oklch(L, Cc, h)]
    for k in range(count - 1):
        dh, dL = d["wall_extra"][k]
        cols.append(argb_from_oklch(min(0.99, max(0.02, L + dL)), Cc, h + dh))
    return cols


def solve_wallpaper(theme, d, v0, accent_h, thr, stats):
    count, negative, band, pattern, intensity = wall_params(theme, d)
    lo, hi = band["L"]
    L = band["L_start"][0] + (band["L_start"][1] - band["L_start"][0]) * d["wall_L_u"]
    for _ in range(C["wall_steps"]):
        v = json.loads(json.dumps(v0))
        v["wallpaper"] = {"source": "custom", "colors": wall_colors(d, accent_h, band, L, count), "rotation": C["rotations"][d["rotation_i"]],
                          "pattern_intensity": intensity, "pattern_slug": PATTERN_SLUGS[d["pattern_i"]] if pattern else "",
                          "motion": d["motion_u"] < 0.5}
        ev, res = evaluate(theme, v, WALL_PAIRS)
        stats["evals"] += 1
        f = failing(res, thr)
        if not f:
            return v, L
        up = down = False
        for i in f:
            if _direction(ev, i, moving_fg=False) > 0:
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


def fallback_variant(theme):
    """The theme's stock accent expressed as a generated accent: passes by construction (== baseline)."""
    a = theme.stock_accent()
    w = []
    source = "custom"
    if a.backgroundOverrideColor == 0:
        source = "theme"
    elif a.backgroundOverrideColor == DELETE:
        source = "default"
    else:
        for f in ("backgroundOverrideColor", "backgroundGradientOverrideColor1", "backgroundGradientOverrideColor2", "backgroundGradientOverrideColor3"):
            x = getattr(a, f)
            if x == 0 or x == DELETE:
                break
            w.append(E.s32(x))
    g = [c for c in (a.myMessagesGradientAccentColor1, a.myMessagesGradientAccentColor2, a.myMessagesGradientAccentColor3) if c != 0]
    return {"base_theme": theme.name, "accent": a.accentColor, "my_messages_accent": a.myMessagesAccentColor,
            "my_messages_gradient": g, "my_messages_animated": bool(a.myMessagesAnimated),
            "wallpaper": {"source": source, "colors": w, "rotation": a.backgroundRotation, "pattern_intensity": float(a.patternIntensity),
                          "pattern_slug": a.patternSlug, "motion": bool(a.patternMotion)}}


def _tiered(tiers, fn):
    """Run a stage solver against each threshold tier in order; first success wins."""
    for k, thr in enumerate(tiers):
        out = fn(thr)
        if out[0] is not None:
            return out + (k,)
    return (None, None, None)


def gen_variant_c(theme, rng, stats=None, mode="strict"):
    """mode 'strict': pass rule of the task (>= min(WCAG, stock)); accent policy per theme.
    mode 'free': every theme gets a free OKLCH accent.  Each stage is solved against the strict
    thresholds first and only if that fails against the slack tier (pairs Telegram's stock
    already fails may drop to stock * (1 - C['free_mode_slack'])); the final check accepts a
    strict pass first, then a slack pass (solver.used_slack records which)."""
    if stats is None:
        stats = {}
    stats.setdefault("evals", 0)
    stats.setdefault("reject", {})
    if mode == "wcag":
        # canvas-fix: free OKLCH accent on every base theme, plain WCAG thresholds, no slack tier
        thr_strict = thresholds(theme, 0.0, "wcag")
        tiers = [thr_strict]
        policy = "free"
    else:
        thr_strict = thresholds(theme, 0.0)
        tiers = [thr_strict]
        if mode == "free":
            tiers.append(thresholds(theme, C["free_mode_slack"]))
        policy = "free" if mode == "free" else C["accent_policy"][theme.name]
    for attempt in range(C["max_attempts"]):
        d = draw_attempt(rng, theme.is_dark)
        stage = "accent"
        if policy in ("anchored", "wallpaper-only"):
            accent, aL = theme.stock_accent().accentColor, None
        else:
            accent, aL, _ = _tiered(tiers, lambda thr: solve_accent(theme, d, thr, stats))
        if accent is not None:
            stage = "bubble"
            if policy == "wallpaper-only":
                sv = fallback_variant(theme)
                v = base_variant(theme, accent)
                v["my_messages_accent"], v["my_messages_gradient"] = sv["my_messages_accent"], sv["my_messages_gradient"]
                v["my_messages_animated"], bL = sv["my_messages_animated"], None
            else:
                v, bL, _ = _tiered(tiers, lambda thr: solve_bubble(theme, d, accent, d["accent_h"], thr, stats))
            if v is not None:
                stage = "wallpaper"
                v0 = v
                v, wL, _ = _tiered(tiers, lambda thr: solve_wallpaper(theme, d, v0, d["accent_h"], thr, stats))
                if v is not None:
                    stage = "final"
                    ev, res = evaluate(theme, v)
                    stats["evals"] += 1
                    for k, thr in enumerate(tiers):
                        if not failing(res, thr):
                            v["solver"] = {"attempt": attempt + 1, "fallback": False, "mode": mode, "accent_policy": policy,
                                           "used_slack": k > 0,
                                           "accent_oklch": [round(aL, 4), round(d["accent_C"], 4), round(d["accent_h"], 2)] if aL is not None else None,
                                           "base_hue": round(d["accent_h"], 2),
                                           "bubble_L": round(bL, 4) if bL is not None else None, "wallpaper_L": round(wL, 4),
                                           "min_margin": round(min(res[i] / thr_strict[i] for i in res if thr_strict[i] > 0), 4)}
                            return v, res
                    for i in failing(res, tiers[-1]):
                        stats["reject"][R.PAIRS[i]["name"]] = stats["reject"].get(R.PAIRS[i]["name"], 0) + 1
        stats["reject"]["<" + stage + " stage>"] = stats["reject"].get("<" + stage + " stage>", 0) + 1
    v = fallback_variant(theme)
    ev, res = evaluate(theme, v)
    v["solver"] = {"attempt": C["max_attempts"], "fallback": True, "mode": mode, "accent_policy": policy, "used_slack": False}
    return v, res


# ------------------------------------------------------------------------------------------
# (a) / (b) naive generators
# ------------------------------------------------------------------------------------------

def rand_rgb(rng):
    return E.s32(0xFF000000 | (rng.next_u64() >> 40))


def rand_hsv(rng):
    h = rng.between(0.0, 360.0)
    s = rng.uniform()
    v = rng.uniform()
    return E.hsv_to_color(255, E.f32(h), E.f32(s), E.f32(v))


def gen_naive(theme, rng, colour, full):
    if not full:
        # the app's own "change accent" path: copy of the current (stock) accent with a new accentColor
        v = fallback_variant(theme)
        v["accent"] = colour(rng)
        return v
    v = base_variant(theme, colour(rng))
    n_b = 1 + rng.below(4)
    cols = [colour(rng) for _ in range(n_b)]
    v["my_messages_accent"] = cols[0]
    v["my_messages_gradient"] = cols[1:] if n_b > 1 else [cols[0]]
    v["my_messages_animated"] = n_b >= 3 and rng.uniform() < 0.5
    n_w = 1 + rng.below(4)
    lo_i = -1.0 if theme.is_dark else 0.0
    intensity = rng.between(lo_i, 1.0) if n_w >= 3 else 0.0
    v["wallpaper"] = {"source": "custom", "colors": [colour(rng) for _ in range(n_w)], "rotation": C["rotations"][rng.below(8)],
                      "pattern_intensity": math.floor(intensity * 100 + 0.5) / 100.0,
                      "pattern_slug": PATTERN_SLUGS[rng.below(len(PATTERN_SLUGS))] if (n_w >= 3 and rng.uniform() < 0.8) else "",
                      "motion": False}
    return v


# ------------------------------------------------------------------------------------------
# genome
# ------------------------------------------------------------------------------------------

def variant_json(v):
    w = v["wallpaper"]
    out = {
        "base_theme": v["base_theme"],
        "accent": hex32(v["accent"]),
        "my_messages_accent": hex32(v["my_messages_accent"]),
        "my_messages_gradient": [hex32(c) for c in v["my_messages_gradient"]],
        "my_messages_animated": bool(v["my_messages_animated"]),
        "wallpaper": {
            "colors": [hex32(c) for c in w["colors"]],
            "kind": ("base theme's own" if w.get("source") == "theme" else
                     {0: "built-in default", 1: "solid", 2: "linear-gradient"}.get(len(w["colors"]), "motion-gradient")),
            "rotation": w["rotation"],
            "pattern_intensity": w["pattern_intensity"],
            "pattern_slug": w["pattern_slug"],
            "parallax_motion": bool(w["motion"]),
        },
    }
    if "solver" in v:
        out["solver"] = v["solver"]
    return out


# base themes the genome may pick: under the strict rule only themes whose accent can vary are
# offered for the day variant (Blue would only vary its wallpaper); night keeps both dark themes
# (accent anchored, bubbles and wallpaper vary)
DAY_CHOICES = {"strict": ["Arctic Blue", "Day"], "free": ["Blue", "Arctic Blue", "Day"], "wcag": ["Blue", "Arctic Blue", "Day"]}
NIGHT_CHOICES = {"strict": ["Dark Blue", "Night"], "free": ["Dark Blue", "Night"], "wcag": ["Dark Blue", "Night"]}


def genome(seed, mode="strict", m=None):
    root = SplitMix64(seed_state(seed))
    day_rng, night_rng, misc_rng = root.fork(), root.fork(), root.fork()
    m = m or E.model()
    dc, nc = DAY_CHOICES[mode], NIGHT_CHOICES[mode]
    day_theme = m.themes[dc[day_rng.below(len(dc))]]
    night_theme = m.themes[nc[night_rng.below(len(nc))]]
    day, day_res = gen_variant_c(day_theme, day_rng, mode=mode)
    night, night_res = gen_variant_c(night_theme, night_rng, mode=mode)
    lo, hi = C["bubble_radius"]
    g = {
        "genome_version": GENOME_VERSION,
        "seed": seed,
        "mode": mode,
        "prng": "SHA-256(seed)[0:8] big-endian -> SplitMix64; forks: day, night, misc",
        "day": variant_json(day),
        "night": variant_json(night),
        "bubble_radius": lo + misc_rng.below(hi - lo + 1),
        "readability": {
            "rule": "strict: every pair >= min(WCAG threshold, stock contrast on that base theme)",
            "day_pairs_passed_strict": "%d/%d" % (sum(1 for i, c in day_res.items() if c >= thresholds(day_theme)[i]), len(R.PAIRS)),
            "night_pairs_passed_strict": "%d/%d" % (sum(1 for i, c in night_res.items() if c >= thresholds(night_theme)[i]), len(R.PAIRS)),
            "day_lowest_vs_wcag": {R.PAIRS[i]["name"]: round(day_res[i], 3) for i in sorted(day_res, key=lambda i: day_res[i] / R.PAIRS[i]["threshold"])[:3]},
            "night_lowest_vs_wcag": {R.PAIRS[i]["name"]: round(night_res[i], 3) for i in sorted(night_res, key=lambda i: night_res[i] / R.PAIRS[i]["threshold"])[:3]},
        },
    }
    return g


# ------------------------------------------------------------------------------------------
# measurement
# ------------------------------------------------------------------------------------------

SHORT_BUCKETS = [1.0, 0.99, 0.98, 0.95, 0.0]

GENERATORS = [
    ("a_acc", "(a) uniform RGB, accent only"),
    ("a_full", "(a) uniform RGB, full genome"),
    ("b_acc", "(b) uniform HSV, accent only"),
    ("b_full", "(b) uniform HSV, full genome"),
    ("c", "(c) OKLCH constrained + solve"),
    ("c_free", "(c') free accent, two-tier"),
]


def _measure_chunk(args):
    theme_name, start, stop = args
    m = E.model()
    th = m.themes[theme_name]
    thr = thresholds(th)
    out = {g: {"pass": 0, "fail_pairs": {}} for g, _ in GENERATORS}
    cstats = {"first": 0, "attempts": 0, "max_attempts": 0, "fallback": 0, "evals": 0, "reject": {}, "min_margin": 1e9}
    cfree = {"slack_pass": 0, "fallback": 0, "worst": (9.0, ""), "short": [0] * len(SHORT_BUCKETS)}
    cstats["cfree"] = cfree
    var = {"accents": set(), "bubbles": set(), "walls": set(), "hue_bins": set(), "light_bubble": 0, "gradient_bubble": 0,
           "animated": 0, "kinds": {}, "pattern": 0, "negative": 0}
    cstats["variety"] = var
    for k in range(start, stop):
        seed = "measure-%d" % k
        for g, _ in GENERATORS:
            rng = SplitMix64(seed_state(seed + "/" + g + "/" + theme_name))
            if g == "c_free":
                st = {"evals": 0, "reject": {}}
                v, res = gen_variant_c(th, rng, st, mode="free")
                if not failing(res, thresholds(th, C["free_mode_slack"])):
                    cfree["slack_pass"] += 1
                cfree["fallback"] += 1 if v["solver"]["fallback"] else 0
                r0 = min(res[i] / thr[i] for i in res)
                for b, lim in enumerate(SHORT_BUCKETS):
                    if r0 >= lim:
                        cfree["short"][b] += 1
                        break
                base = R.baseline(th)
                for i, c in res.items():
                    if base[i] < R.PAIRS[i]["threshold"]:
                        r = c / base[i]
                        if r < cfree["worst"][0]:
                            cfree["worst"] = (r, R.PAIRS[i]["name"])
            elif g == "c":
                st = {"evals": 0, "reject": cstats["reject"]}
                v, res = gen_variant_c(th, rng, st)
                s = v["solver"]
                cstats["attempts"] += s["attempt"]
                cstats["max_attempts"] = max(cstats["max_attempts"], s["attempt"])
                cstats["first"] += 1 if s["attempt"] == 1 and not s["fallback"] else 0
                cstats["fallback"] += 1 if s["fallback"] else 0
                cstats["evals"] += st["evals"]
                if not s["fallback"]:
                    cstats["min_margin"] = min(cstats["min_margin"], s["min_margin"])
                    var["accents"].add(v["accent"])
                    bub = (v["my_messages_accent"],) + tuple(v["my_messages_gradient"])
                    var["bubbles"].add(bub)
                    w = v["wallpaper"]
                    var["walls"].add(tuple(w["colors"]))
                    var["hue_bins"].add(int(math.floor(s["base_hue"] / 30.0)) % 12)
                    var["light_bubble"] += 1 if D.luminance(v["my_messages_accent"]) > 0.4 else 0
                    var["gradient_bubble"] += 1 if (len(v["my_messages_gradient"]) > 1 or
                                                    (v["my_messages_gradient"] and v["my_messages_gradient"][0] != v["my_messages_accent"])) else 0
                    var["animated"] += 1 if v["my_messages_animated"] else 0
                    kind = {1: "solid", 2: "linear", 3: "motion", 4: "motion"}.get(len(w["colors"]), "other")
                    var["kinds"][kind] = var["kinds"].get(kind, 0) + 1
                    var["pattern"] += 1 if w["pattern_slug"] else 0
                    var["negative"] += 1 if w["pattern_intensity"] < 0 else 0
            else:
                colour = rand_rgb if g.startswith("a") else rand_hsv
                v = gen_naive(th, rng, colour, g.endswith("full"))
                _, res = evaluate(th, v)
            f = failing(res, thr)
            if not f:
                out[g]["pass"] += 1
            for i in f:
                nm = R.PAIRS[i]["name"]
                out[g]["fail_pairs"][nm] = out[g]["fail_pairs"].get(nm, 0) + 1
    return theme_name, out, cstats


def measure(n, procs):
    jobs = []
    step = max(1, (n + 7) // 8)
    for t in ALL_THEMES:
        for s in range(0, n, step):
            jobs.append((t, s, min(n, s + step)))
    t0 = time.time()
    if procs > 1:
        from multiprocessing import Pool
        with Pool(procs) as pool:
            results = pool.map(_measure_chunk, jobs, chunksize=1)
    else:
        results = [_measure_chunk(j) for j in jobs]
    agg = {t: {g: {"pass": 0, "fail_pairs": {}} for g, _ in GENERATORS} for t in ALL_THEMES}
    cst = {t: {"first": 0, "attempts": 0, "max_attempts": 0, "fallback": 0, "evals": 0, "reject": {}, "min_margin": 1e9} for t in ALL_THEMES}
    for t, out, cs in results:
        for g in out:
            agg[t][g]["pass"] += out[g]["pass"]
            for k, v in out[g]["fail_pairs"].items():
                agg[t][g]["fail_pairs"][k] = agg[t][g]["fail_pairs"].get(k, 0) + v
        c = cst[t]
        for k in ("first", "attempts", "fallback", "evals"):
            c[k] += cs[k]
        c["max_attempts"] = max(c["max_attempts"], cs["max_attempts"])
        c.setdefault("cfree", {"slack_pass": 0, "fallback": 0, "worst": (9.0, ""), "short": [0] * len(SHORT_BUCKETS)})
        for b in range(len(SHORT_BUCKETS)):
            c["cfree"]["short"][b] += cs["cfree"]["short"][b]
        vv = c.setdefault("variety", {"accents": set(), "bubbles": set(), "walls": set(), "hue_bins": set(), "light_bubble": 0,
                                      "gradient_bubble": 0, "animated": 0, "kinds": {}, "pattern": 0, "negative": 0})
        for k in ("accents", "bubbles", "walls", "hue_bins"):
            vv[k] |= cs["variety"][k]
        for k in ("light_bubble", "gradient_bubble", "animated", "pattern", "negative"):
            vv[k] += cs["variety"][k]
        for k, x in cs["variety"]["kinds"].items():
            vv["kinds"][k] = vv["kinds"].get(k, 0) + x
        c["cfree"]["slack_pass"] += cs["cfree"]["slack_pass"]
        c["cfree"]["fallback"] += cs["cfree"]["fallback"]
        c["cfree"]["worst"] = min(c["cfree"]["worst"], cs["cfree"]["worst"])
        c["min_margin"] = min(c["min_margin"], cs["min_margin"])
        for k, v in cs["reject"].items():
            c["reject"][k] = c["reject"].get(k, 0) + v
    dt = time.time() - t0
    lines = []
    lines.append("seeds per base theme: %d   pairs in suite: %d   pass = every pair >= min(WCAG threshold, stock contrast of that pair on that base theme)" % (n, len(R.PAIRS)))
    lines.append("")
    lines.append("PASS RATE (all %d pairs)" % len(R.PAIRS))
    hdr = "%-34s" % "generator" + "".join("%13s" % t for t in ALL_THEMES)
    lines.append(hdr)
    for g, label in GENERATORS:
        lines.append("%-34s" % label + "".join("%12.2f%%" % (100.0 * agg[t][g]["pass"] / n) for t in ALL_THEMES))
    lines.append("")
    lines.append("(c) SOLVER STATS")
    lines.append("%-34s" % "first-attempt success" + "".join("%12.2f%%" % (100.0 * cst[t]["first"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "mean attempts" + "".join("%13.3f" % (cst[t]["attempts"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "max attempts" + "".join("%13d" % cst[t]["max_attempts"] for t in ALL_THEMES))
    lines.append("%-34s" % "deterministic fallbacks used" + "".join("%13d" % cst[t]["fallback"] for t in ALL_THEMES))
    lines.append("%-34s" % "palette evaluations per seed" + "".join("%13.2f" % (cst[t]["evals"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "min contrast/threshold (passes)" + "".join("%13.4f" % cst[t]["min_margin"] for t in ALL_THEMES))
    lines.append("%-34s" % "accent policy (strict mode)" + "".join("%13s" % C["accent_policy"][t] for t in ALL_THEMES))
    lines.append("")
    lines.append("(c) VARIETY over the %d seeds per base theme" % n)
    vt = {t: cst[t]["variety"] for t in ALL_THEMES}
    lines.append("%-34s" % "distinct accent colours" + "".join("%13d" % len(vt[t]["accents"]) for t in ALL_THEMES))
    lines.append("%-34s" % "distinct outgoing-bubble colourings" + "".join("%13d" % len(vt[t]["bubbles"]) for t in ALL_THEMES))
    lines.append("%-34s" % "distinct wallpaper colourings" + "".join("%13d" % len(vt[t]["walls"]) for t in ALL_THEMES))
    lines.append("%-34s" % "base-hue 30-degree bins covered" + "".join("%10d/12" % len(vt[t]["hue_bins"]) for t in ALL_THEMES))
    lines.append("%-34s" % "light (black-text) bubbles" + "".join("%12.1f%%" % (100.0 * vt[t]["light_bubble"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "gradient bubbles" + "".join("%12.1f%%" % (100.0 * vt[t]["gradient_bubble"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "animated bubble gradients" + "".join("%12.1f%%" % (100.0 * vt[t]["animated"] / n) for t in ALL_THEMES))
    for kind in ("solid", "linear", "motion"):
        lines.append("%-34s" % ("wallpaper kind: " + kind) + "".join("%12.1f%%" % (100.0 * vt[t]["kinds"].get(kind, 0) / n) for t in ALL_THEMES))
    lines.append("%-34s" % "wallpapers with pattern" + "".join("%12.1f%%" % (100.0 * vt[t]["pattern"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "negative-intensity (dark) patterns" + "".join("%12.1f%%" % (100.0 * vt[t]["negative"] / n) for t in ALL_THEMES))
    lines.append("")
    lines.append("(c') free accent everywhere; each stage solved strict first, then with %d%% slack on pairs stock already fails" % int(C["free_mode_slack"] * 100))
    lines.append("%-34s" % "pass, strict rule (table above)" + "".join("%12.2f%%" % (100.0 * agg[t]["c_free"]["pass"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "pass, slack rule" + "".join("%12.2f%%" % (100.0 * cst[t]["cfree"]["slack_pass"] / n) for t in ALL_THEMES))
    lines.append("%-34s" % "deterministic fallbacks used" + "".join("%13d" % cst[t]["cfree"]["fallback"] for t in ALL_THEMES))
    lines.append("%-34s" % "worst contrast / stock contrast" + "".join("%13.4f" % cst[t]["cfree"]["worst"][0] for t in ALL_THEMES))
    lines.append("%-34s" % "  ... on pair" + "".join("%13s" % cst[t]["cfree"]["worst"][1][:12] for t in ALL_THEMES))
    lines.append("strict-rule shortfall of (c'): seeds by min over pairs of contrast / strict threshold")
    prev = None
    for b, lim in enumerate(SHORT_BUCKETS):
        label = ("  >= %.2f (strict pass)" % lim) if b == 0 else ("  [%.2f, %.2f)" % (lim, prev))
        lines.append("%-34s" % label + "".join("%12.2f%%" % (100.0 * cst[t]["cfree"]["short"][b] / n) for t in ALL_THEMES))
        prev = lim
    rej = set()
    for t in ALL_THEMES:
        rej.update(cst[t]["reject"])
    if rej:
        lines.append("rejected attempts by stage / final-check pair:")
        for k in sorted(rej, key=lambda k: (-sum(cst[t]["reject"].get(k, 0) for t in ALL_THEMES), k)):
            lines.append("  %-32s" % k + "".join("%13d" % cst[t]["reject"].get(k, 0) for t in ALL_THEMES))
    lines.append("")
    lines.append("PER-PAIR FAILURE COUNTS (seeds failing the pair, summed over the 5 base themes = %d seeds per generator)" % (5 * n))
    short = {"a_acc": "a:acc", "a_full": "a:full", "b_acc": "b:acc", "b_full": "b:full", "c": "c", "c_free": "c'"}
    lines.append("  %-26s" % "pair" + "".join("%9s" % short[g] for g, _ in GENERATORS))
    tot = {g: {} for g, _ in GENERATORS}
    for g, _ in GENERATORS:
        for t in ALL_THEMES:
            for k, v in agg[t][g]["fail_pairs"].items():
                tot[g][k] = tot[g].get(k, 0) + v
    names = [p["name"] for p in R.PAIRS if any(tot[g].get(p["name"], 0) for g, _ in GENERATORS)]
    for nm in sorted(names, key=lambda k: (-sum(tot[g].get(k, 0) for g, _ in GENERATORS), k)):
        lines.append("  %-26s" % nm + "".join("%9d" % tot[g].get(nm, 0) for g, _ in GENERATORS))
    for g, label in GENERATORS:
        if g not in ("c", "c_free"):
            continue
        lines.append("")
        lines.append("RESIDUAL FAILURES PER BASE THEME " + label + " (strict rule)")
        names = set()
        for t in ALL_THEMES:
            names.update(agg[t][g]["fail_pairs"])
        if not names:
            lines.append("  (none)")
            continue
        lines.append("  %-26s" % "pair" + "".join("%13s" % t for t in ALL_THEMES))
        for nm in sorted(names, key=lambda k: (-sum(agg[t][g]["fail_pairs"].get(k, 0) for t in ALL_THEMES), k)):
            lines.append("  %-26s" % nm + "".join("%13d" % agg[t][g]["fail_pairs"].get(nm, 0) for t in ALL_THEMES))
    lines.append("")
    lines.append("elapsed %.1f s on %d process(es)" % (dt, procs))
    return "\n".join(lines)


def baseline_report():
    m = E.model()
    lines = []
    lines.append("STOCK BASELINE: each base theme with its stock default accent (Blue: id %d via ThemeColors defaults; others: id 0)" % m.DEFAULT_ACCENT_ID)
    for t in ALL_THEMES:
        th = m.themes[t]
        ev = R.Evaluator(R.stock_palette(th))
        w = ev.wp
        lines.append("  %-12s accent %s  wallpaper %s %s intensity %d pattern %s  service text %s (%s)" % (
            t, hex32(th.stock_accent().accentColor), w.kind, "/".join(hex32(c) for c in w.colors if c), w.intensity, w.pattern,
            hex32(w.service_text), "gradient shader" if w.shader else "flat pill"))
    lines.append("")
    lines.append("  %-26s %-40s %-34s %5s" % ("pair", "fg key", "bg", "thr") + "".join("%12s" % t for t in ALL_THEMES))
    base = {t: R.baseline(m.themes[t]) for t in ALL_THEMES}
    nfail = {t: 0 for t in ALL_THEMES}
    for i, p in enumerate(R.PAIRS):
        cells = []
        for t in ALL_THEMES:
            c = base[t][i]
            bad = c < p["threshold"]
            nfail[t] += 1 if bad else 0
            cells.append("%11.2f%s" % (c, "*" if bad else " "))
        lines.append("  %-26s %-40s %-34s %5.2f" % (p["name"], p["fg"], p["bg"], p["threshold"]) + "".join(cells))
    lines.append("  %-26s %-40s %-34s %5s" % ("pairs below threshold (*)", "", "", "") + "".join("%12d" % nfail[t] for t in ALL_THEMES))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed")
    ap.add_argument("--measure", type=int)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--mode", choices=["strict", "free"], default="strict",
                    help="--seed only: strict = task pass rule (accent policy per theme); free = free accent everywhere, 10%% slack")
    ap.add_argument("--procs", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args()
    missing = R.check_keys(E.model())
    if missing:
        raise SystemExit("suite names unknown keys: %r" % missing)
    if not check_pattern_slugs(E.model()):
        raise SystemExit("PATTERN_SLUGS differs from the built-in accent presets in Theme.java")
    if a.baseline:
        print(baseline_report())
    if a.seed is not None:
        print(json.dumps(genome(a.seed, a.mode), indent=2))
    if a.measure:
        print(measure(a.measure, a.procs))


if __name__ == "__main__":
    main()
