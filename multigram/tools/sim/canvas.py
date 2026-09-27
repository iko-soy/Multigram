#!/usr/bin/env python3
"""canvas-fix: 'fix the canvas, then randomize'.

Builds a small overlay for the five bundled base themes, applies it to the bit-exact engine port
(engine.Model(parsed, spec)) and runs the seeded OKLCH generator with FREE accents on all five base
themes under plain WCAG (4.5 text / 3.0 non-text / 1.15 bubble separation / 4.5 service text).

  python3 canvas.py --build                    overlay spec for variants A and B -> overlay_A.json / overlay_B.json + table
  python3 canvas.py --stock                    stock default accent of each theme, stock model vs overlay model
  python3 canvas.py --crosscheck N             lazy vs full getColor() on the overlay models
  python3 canvas.py --measure N --variant V [--service on|off]
                                               N-seed style measurement (free accents, plain WCAG); V = A | B | B-no-c | B-no-d
  python3 canvas.py --gallery --variant B      gallery.json (36 genomes + 3 naive failures)

Overlay parts (each maps 1:1 to an app change):
  (a) neutral/secondary keys failing WCAG on their background: same OKLCH hue+chroma, nearest lightness that
      meets the threshold (translucent keys: same RGB, alpha raised if that reaches the threshold).
      -> .attheme line (bundled theme) or ThemeColors default (Blue preset 99 serves ThemeColors defaults).
      A key that is neutral on one theme but accent-coloured on another (chats_attachMessage: grey on Dark Blue,
      blue on the light themes) cannot join the global exclusion set; on the theme where it is neutral it gets
      the nearest 8-bit grey instead (HSV s = 0 is outside every 30-degree re-tint window).
  (b) those keys + surfaces that should not follow the accent -> Theme.themeAccentExclusionKeys.
      Variant A: only windowBackgroundGray (Day's settings background) is added; Dark Blue surfaces keep
      following the accent.  Variant B: the 8 surface keys are excluded too (surfaces stay stock).
  (c) on-accent content rule: after fillAccentColors, keys drawn on accent fills become white or NEAR_BLACK,
      whichever has the higher WCAG contrast with the fill; the muted unread badge (same text paint) gets a
      precomputed neutral fill that passes with the chosen text colour.
  (d) outgoing in-bubble secondary texts: the existing fillAccentColors black/white block (runs whenever
      myMessagesGradientAccentColor1 != 0, which every generated bubble sets), with its guard
      `!isMyMessagesGradientColorsNear` widened to `|| id > 100` so a runtime accent whose light bubble is near
      the theme's own bubble (Blue: 0xFFE6F2FC) still gets it, + the generator's bubble bands.
"""
import argparse
import copy
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
import style_sim as S        # noqa: E402
import tgsrc                 # noqa: E402

OUT = os.path.abspath(os.environ.get("CANVAS_OUT") or os.path.join(HERE, "palette-fix"))  # overlay_*.json live here
NEAR_BLACK = E.s32(0xFF050505)   # with white, guarantees max(contrast) >= 4.51 for ANY fill (crossover at Y ~ 0.182)
WHITE = E.s32(0xFFFFFFFF)

ON_ACCENT_PAIRS = [
    # (content key, accent fill key)            where it is drawn
    ("key_chats_actionIcon", "key_chats_actionBackground"),                  # chat-list FAB pencil
    ("key_chats_unreadCounterText", "key_chats_unreadCounter"),              # unread badge digits (DialogCell)
    ("key_featuredStickers_buttonText", "key_featuredStickers_addButton"),   # filled buttons (Join/Add/Start...)
    ("key_checkboxSquareCheck", "key_checkboxSquareBackground"),             # square checkbox mark
    ("key_dialogRoundCheckBoxCheck", "key_dialogRoundCheckBox"),             # share-sheet round checkbox mark
    ("key_chat_goDownButtonCounter", "key_chat_goDownButtonCounterBackground"),  # CounterView on go-down button
    ("key_dialogCheckboxSquareCheck", "key_dialogCheckboxSquareBackground"), # CheckBoxSquare in alerts
    ("key_chat_attachCheckBoxCheck", "key_chat_attachCheckBoxBackground"),   # photo picker check
    ("key_chat_inMediaIcon", "key_chat_inLoader"),                           # incoming play/download glyph
    ("key_chat_inContactIcon", "key_chat_inContactBackground"),              # incoming contact glyph
    ("key_picker_badgeText", "key_picker_badge"),                            # picker Done badge count
    ("key_dialogFloatingIcon", "key_dialogFloatingButton"),                  # floating send button glyph
]
MUTED_KEY = "key_chats_unreadCounterMuted"
MUTED_TEXT = "key_chats_unreadCounterText"

# Suite pairs that may be neutral (grey/near-white fg on a canvas surface).  A pair is treated as neutral on a
# theme when its stock fg (composited on its bg) has OKLCH chroma < 0.05 there.
NEUTRAL_CANDIDATES = ["list_text", "list_gray_text", "list_gray_text2", "dialog_text", "chats_name", "chats_preview",
                      "chats_preview_sender", "chats_date", "actionbar_title", "actionbar_icons", "actionbar_subtitle",
                      "in_text", "in_time", "in_reply_text", "in_file_info", "composer_text", "composer_hint",
                      "composer_icons", "settings_footnote", "chats_attach_label", "popup_menu_item", "pinned_text",
                      "in_file_name", "in_views"]
NEUTRAL_CHROMA = 0.05

SURFACES_B = ["key_windowBackgroundWhite", "key_windowBackgroundGray", "key_actionBarDefault", "key_dialogBackground",
              "key_chat_messagePanelBackground", "key_chat_topPanelBackground", "key_chat_inBubble",
              "key_actionBarDefaultSubmenuBackground"]
SURFACES_A = ["key_windowBackgroundGray"]

ASSET = {"Blue": "bluebubbles.attheme", "Dark Blue": "darkblue.attheme", "Arctic Blue": "arctic.attheme",
         "Day": "day.attheme", "Night": "night.attheme"}


def hx(c):
    return "#%08X" % (c & 0xFFFFFFFF)


def oklch_of(c):
    return D.rgb8_to_oklch((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)


# ------------------------------------------------------------------------------------------
# accent sweep used to size the overlay against accent-tinted surfaces
# ------------------------------------------------------------------------------------------

def sweep_accents(step=10, Ls=(0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.92), Cs=(0.07, 0.12, 0.17)):
    out = []
    for h in range(0, 360, step):
        for L in Ls:
            for Cc in Cs:
                out.append(S.argb_from_oklch(L, Cc, float(h)))
    return out


def gen_palettes(theme, accents):
    return [E.palette(theme, E.Accent(id=S.GEN_ACCENT_ID, accentColor=a), S.GEN_ACCENT_ID) for a in accents]


def nominal_palette(theme):
    """Generated-accent path with accentColor == accentBaseColor: no re-tint, currentColors = the theme's own
    values (what an excluded key shows under every generated accent)."""
    return E.palette(theme, E.Accent(id=S.GEN_ACCENT_ID, accentColor=theme.accentBaseColor), S.GEN_ACCENT_ID)


def pair_surfaces(pal, p):
    ev = R.Evaluator(pal)
    return ev.surface(p["bg"])


def pair_contrast_with(fg, surfs):
    return min(D.contrast(R.over(fg, s), s) for s in surfs)


# ------------------------------------------------------------------------------------------
# nearest-lightness fix
# ------------------------------------------------------------------------------------------

def fix_color(fg, surfs, thr):
    """Smallest change of fg that reaches thr against every surface sample.
    Opaque fg: same OKLCH hue and chroma, nearest L.  Translucent fg: same RGB, alpha raised if that reaches thr,
    otherwise the composite (on the first surface) gets the OKLCH-L fix and becomes opaque."""
    if pair_contrast_with(fg, surfs) >= thr:
        return fg, "unchanged"
    a = (fg >> 24) & 0xFF
    if a < 255:
        for na in range(a + 1, 256):
            c = E.s32((na << 24) | (fg & 0xFFFFFF))
            if pair_contrast_with(c, surfs) >= thr:
                return c, "alpha 0x%02X->0x%02X" % (a, na)
        base = E.s32(0xFF000000 | R.over(fg, surfs[0]))
    else:
        base = fg
    L0, C0, h0 = oklch_of(base)
    yb = sum(D.luminance(s) for s in surfs) / len(surfs)
    lighter = D.luminance(base & 0xFFFFFF) > yb
    Lend = 1.0 if lighter else 0.0

    def col(t):
        L = L0 + t * (Lend - L0)
        return S.argb_from_oklch(L, C0, h0)

    lo, hi = 0.0, 1.0
    if pair_contrast_with(col(1.0), surfs) < thr:
        raise ValueError("cannot reach %.2f from %s" % (thr, hx(fg)))
    for _ in range(60):
        mid = (lo + hi) / 2
        if pair_contrast_with(col(mid), surfs) >= thr:
            hi = mid
        else:
            lo = mid
    t = hi
    c = col(t)
    while pair_contrast_with(c, surfs) < thr:          # quantisation guard
        t = min(1.0, t + 1e-4)
        c = col(t)
    L1 = L0 + t * (Lend - L0)
    return c, "OKLCH L %.3f->%.3f (C %.3f h %.1f)" % (L0, L1, C0, h0)


def fix_grey(fg, surfs, thr):
    """Per-theme 'exclusion' by data: an 8-bit grey (r == g == b, HSV s = 0, SkRGBToHSV hue 0) is never re-tinted
    by changeColorAccent on these base themes (Theme.java:6182-6184: |0 - base hue ~207..216| > 30).  Nearest
    grey level (in OKLCH L) to fg's composite that reaches thr against every surface sample."""
    assert (fg >> 24) & 0xFF == 0xFF, "grey route is for opaque keys"
    L0 = oklch_of(fg)[0]
    best = None
    for g in range(256):
        c = E.s32(0xFF000000 | (g << 16) | (g << 8) | g)
        if pair_contrast_with(c, surfs) >= thr:
            d = abs(oklch_of(c)[0] - L0)
            if best is None or d < best[0]:
                best = (d, c)
    if best is None:
        raise ValueError("no grey reaches %.2f" % thr)
    c = best[1]
    return c, "grey: OKLCH C %.3f->0, L %.3f->%.3f (HSV s=0: never re-tinted)" % (oklch_of(fg)[1], L0, oklch_of(c)[0])


# ------------------------------------------------------------------------------------------
# overlay builder
# ------------------------------------------------------------------------------------------

def muted_pins(m):
    k = m.K[MUTED_KEY]
    return sorted(m.key_names[a] for a, b in m.fallback.items() if b == k)


def classify_neutral(theme, pal):
    out = []
    for p in R.PAIRS:
        if p["name"] not in NEUTRAL_CANDIDATES:
            continue
        surfs = pair_surfaces(pal, p)
        fg = pal.get(p["fg"])
        comp = R.over(fg, surfs[0])
        L, Cc, h = oklch_of(comp)
        if Cc < NEUTRAL_CHROMA:
            out.append(p)
    return out


def accent_coloured_keys(stock_model):
    """Keys that follow the accent on at least one base theme with a chromatic (OKLCH C >= NEUTRAL_CHROMA)
    theme value there.  Two probe accents decide 'follows' (as style_sim.affected_keys does)."""
    out = set()
    for tn in S.ALL_THEMES:
        th = stock_model.themes[tn]
        pa = E.palette(th, E.Accent(id=S.GEN_ACCENT_ID, accentColor=S.argb_from_oklch(0.6, 0.12, 30.0)), S.GEN_ACCENT_ID)
        pb = E.palette(th, E.Accent(id=S.GEN_ACCENT_ID, accentColor=S.argb_from_oklch(0.6, 0.12, 150.0)), S.GEN_ACCENT_ID)
        nom = nominal_palette(th)
        for p in R.PAIRS:
            k = p["fg"]
            if k.startswith("@") or ("key_" + k) in out:
                continue
            if pa.get(k) != pb.get(k) and oklch_of(nom.get(k))[1] >= NEUTRAL_CHROMA:
                out.add("key_" + k)
    return out


def base_spec(variant, stock_model):
    surfaces = SURFACES_B if variant == "B" else SURFACES_A
    spec = {"tag": "canvas-%s" % variant, "variant": variant, "defaults": {}, "attheme": {a: {} for a in ASSET.values()},
            "exclusions": list(surfaces),
            "hook": {"near_black": NEAR_BLACK & 0xFFFFFFFF, "pairs": [list(x) for x in ON_ACCENT_PAIRS], "out_block_custom": True,
                     "muted": {"key": MUTED_KEY, "text": MUTED_TEXT, "pins": muted_pins(stock_model), "table": {}}}}
    return spec


def build(variant, sweep_step=10, log=print):
    parsed = tgsrc.load()
    stock = E.model()
    spec = base_spec(variant, stock)
    rows = []           # overlay table rows
    K = stock.K

    # --- phase 1: Blue preset 99 (fresh-install default) serves ThemeColors defaults for main keys ------------
    th = stock.themes["Blue"]
    sp = R.stock_palette(th)
    for p in classify_neutral(th, sp):
        surfs = pair_surfaces(sp, p)
        fg = sp.get(p["fg"])
        c0 = pair_contrast_with(fg, surfs)
        if c0 >= p["threshold"]:
            continue
        new, how = fix_color(fg, surfs, p["threshold"])
        key = "key_" + p["fg"]
        spec["defaults"][key] = new & 0xFFFFFFFF
        rows.append({"theme": "Blue (preset 99)", "key": p["fg"], "pair": p["name"], "stock": hx(fg), "new": hx(new),
                     "L_stock": oklch_of(E.s32(0xFF000000 | R.over(fg, surfs[0])))[0], "L_new": oklch_of(E.s32(0xFF000000 | R.over(new, surfs[0])))[0],
                     "before": c0, "after": pair_contrast_with(new, surfs), "thr": p["threshold"], "how": how,
                     "where": "ThemeColors.java:%s default" % parsed["themecolors_java"]["default_lines"].get(key, "?"),
                     "reason": "fails WCAG on the stock default theme"})
        if key not in spec["exclusions"]:
            spec["exclusions"].append(key)

    # --- phase 2: generated accents (id 101) on every base theme, sized against an accent sweep --------------
    accents = sweep_accents(sweep_step)
    # themeAccentExclusionKeys is ONE global set (Theme.java:3496): a key that is accent-coloured on some base
    # theme (follows the accent there with OKLCH C >= NEUTRAL_CHROMA, e.g. chats_attachMessage on the light
    # themes) must not be excluded, or it freezes at its stock blue there.  On the theme where it is neutral it
    # gets an 8-bit grey instead (fix_grey): HSV s = 0 puts it outside the 30-degree re-tint window, which is a
    # per-theme exclusion expressed in the .attheme alone.
    accent_coloured = accent_coloured_keys(stock)
    for it in range(6):
        m = E.Model(parsed, spec)
        changed = False
        for tn in S.ALL_THEMES:
            th = m.themes[tn]
            nom = nominal_palette(th)
            stock_th = stock.themes[tn]
            neutral = classify_neutral(stock_th, R.stock_palette(stock_th) if tn != "Blue" else nominal_palette(stock_th))
            pals = [nom] + gen_palettes(th, accents)
            if tn != "Blue":
                pals.append(R.stock_palette(th))
            for p in neutral:
                key = "key_" + p["fg"]
                mixed = key in accent_coloured
                allsurfs = []
                seen = set()
                worst = 1e9
                for pl in pals:
                    ss = pair_surfaces(pl, p)
                    worst = min(worst, pair_contrast_with(pl.get(p["fg"]), ss))
                    for s_ in ss:
                        if s_ not in seen:
                            seen.add(s_)
                            allsurfs.append(s_)
                if worst >= p["threshold"]:
                    continue
                # the key will be excluded: its value under every generated accent = nominal value
                fg_nom = nom.get(p["fg"])
                # order surfaces: nominal first (reference for the translucent->opaque route)
                ref = pair_surfaces(nom, p)
                surfs = list(ref) + [x for x in allsurfs if x not in ref]
                new, how = (fix_grey if mixed else fix_color)(fg_nom, surfs, p["threshold"])
                asset = ASSET[tn]
                if new == fg_nom and (key in spec["exclusions"] or mixed):
                    continue
                ki = m.K[key]
                fb = m.fallback.get(ki, -1)
                self_resolving = ki in th.no_accent or not (fb >= 0 and fb in th.no_accent)
                ln = parsed["atthemes"][asset]["values"].get(key)
                if new == fg_nom and self_resolving:
                    where = "exclusion only"          # the value is right; only the accent re-tint must stop
                else:
                    spec["attheme"][asset][key] = new & 0xFFFFFFFF
                    where = ("%s:%d change" % (asset, ln[1])) if ln else ("%s add line" % asset)
                if key not in spec["exclusions"] and not mixed:
                    spec["exclusions"].append(key)
                stock_c = pair_contrast_with(R.stock_palette(stock_th).get(p["fg"]) if tn != "Blue" else nominal_palette(stock_th).get(p["fg"]),
                                             pair_surfaces(R.stock_palette(stock_th) if tn != "Blue" else nominal_palette(stock_th), p))
                rows = [r for r in rows if not (r["theme"] == tn and r["key"] == p["fg"])]
                rows.append({"theme": tn, "key": p["fg"], "pair": p["name"], "stock": hx(fg_nom), "new": hx(new),
                             "before": stock_c, "before_sweep_worst": worst, "L_stock": oklch_of(E.s32(0xFF000000 | R.over(fg_nom, ref[0])))[0],
                             "L_new": oklch_of(E.s32(0xFF000000 | R.over(new, ref[0])))[0],
                             "after": pair_contrast_with(new, surfs), "thr": p["threshold"], "how": how, "where": where,
                             "reason": ("fails WCAG at stock" if stock_c < p["threshold"] else "falls below WCAG under accent re-tint")
                             + ("; accent-coloured on the light themes, so not in the global exclusion set: grey value instead" if mixed else "")})
                changed = True
        log("  build %s iteration %d: %d rows" % (variant, it + 1, len(rows)))
        if not changed:
            break

    # --- muted unread badge: precomputed neutral fill per theme for white / near-black digits ---------------
    m = E.Model(parsed, spec)
    for tn in S.ALL_THEMES:
        th = m.themes[tn]
        nom = nominal_palette(th)
        page = nom.get("windowBackgroundWhite")
        m0 = nom._get_with(nom._base_entry, m.K[MUTED_KEY])       # theme's own muted fill (before the hook)
        m0 = E.s32(0xFF000000 | R.over(m0, page))
        fw, hw = fix_color(m0, [WHITE & 0xFFFFFF], R.TEXT)
        fb, hb = fix_color(m0, [NEAR_BLACK & 0xFFFFFF], R.TEXT)
        spec["hook"]["muted"]["table"][tn] = [fw & 0xFFFFFFFF, fb & 0xFFFFFFFF]
        rows.append({"theme": tn, "key": MUTED_KEY[4:] + " (hook, white digits)", "pair": "chats_muted_badge_text", "stock": hx(m0), "new": hx(fw),
                     "before": D.contrast(0xFFFFFF, m0 & 0xFFFFFF), "after": D.contrast(0xFFFFFF, fw & 0xFFFFFF), "thr": R.TEXT, "how": hw,
                     "where": "hook table", "reason": "muted badge shares chats_unreadCounterText"})
        rows.append({"theme": tn, "key": MUTED_KEY[4:] + " (hook, near-black digits)", "pair": "chats_muted_badge_text", "stock": hx(m0), "new": hx(fb),
                     "before": D.contrast(NEAR_BLACK & 0xFFFFFF, m0 & 0xFFFFFF), "after": D.contrast(NEAR_BLACK & 0xFFFFFF, fb & 0xFFFFFF), "thr": R.TEXT, "how": hb,
                     "where": "hook table", "reason": "muted badge shares chats_unreadCounterText"})

    # --- Blue preset 99: the hook cannot reach it (getColor serves ThemeColors defaults), so bake the rule ----
    m = E.Model(parsed, spec)
    th = m.themes["Blue"]
    sp = R.stock_palette(th)
    page = sp.get("windowBackgroundWhite")
    for content, fill in ON_ACCENT_PAIRS:
        v = E.on_accent_color(sp.get(fill[4:]), page, NEAR_BLACK)
        old = sp.get(content[4:])
        if v != old:
            spec["defaults"][content] = v & 0xFFFFFFFF
            rows.append({"theme": "Blue (preset 99)", "key": content[4:], "pair": "on-accent (%s)" % fill[4:], "stock": hx(old), "new": hx(v),
                         "before": D.contrast(R.over(old, R.over(sp.get(fill[4:]), page)), R.over(sp.get(fill[4:]), page)),
                         "after": D.contrast(R.over(v, R.over(sp.get(fill[4:]), page)), R.over(sp.get(fill[4:]), page)), "thr": 0,
                         "how": "on-accent rule baked", "where": "ThemeColors.java:%s default" % parsed["themecolors_java"]["default_lines"].get(content, "?"),
                         "reason": "preset 99 reads defaults; rule result for the default fill"})
    text = E.s32(spec["defaults"].get(MUTED_TEXT, sp.get(MUTED_TEXT[4:]) & 0xFFFFFFFF))
    w, b = spec["hook"]["muted"]["table"]["Blue"]
    newm = w if text == WHITE else b
    for dep in spec["hook"]["muted"]["pins"]:
        if stock.defaults[stock.K[dep]] == 0:
            spec["defaults"][dep] = stock.get_default_color(stock.K[dep]) & 0xFFFFFFFF
    if E.s32(newm) != sp.get(MUTED_KEY[4:]):
        spec["defaults"][MUTED_KEY] = newm & 0xFFFFFFFF
    return spec, rows


def overlay(variant):
    """'A' / 'B', optionally with an ablation suffix: '-no-c' (on-accent rule and muted table off: no hook
    writes, the Blue preset-99 bake of the content keys dropped), '-no-d' (black/white out-text block keeps
    its stock isMyMessagesGradientColorsNear condition)."""
    base, _, abl = variant.partition("-")
    path = os.path.join(OUT, "overlay_%s.json" % base)
    with open(path) as f:
        spec = json.load(f)
    if abl:
        spec["tag"] += "-" + abl
        if abl == "no-c":
            spec["hook"]["pairs"] = []
            spec["hook"]["muted"] = None
            for content, _fill in ON_ACCENT_PAIRS:
                spec["defaults"].pop(content, None)
        elif abl == "no-d":
            spec["hook"]["out_block_custom"] = False
        else:
            raise ValueError(variant)
    return E.overlay_model(spec)


def fmt_rows(rows):
    lines = ["  %-18s %-34s %-24s %-11s -> %-11s %6s -> %6s %4s  %-44s %-32s %s" % (
        "theme", "key", "pair", "stock", "new", "c_bef", "c_aft", "thr", "change", "where", "reason")]
    for r in rows:
        lines.append("  %-18s %-34s %-24s %-11s -> %-11s %6.2f -> %6.2f %4.1f  %-44s %-32s %s" % (
            r["theme"], r["key"], r["pair"], r["stock"], r["new"], r["before"], r["after"], r["thr"], r["how"], r["where"], r["reason"]))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------
# stock default accent: stock model vs overlay model, plain WCAG
# ------------------------------------------------------------------------------------------

def failing_wcag(res):
    return [i for i, c in res.items() if c < R.PAIRS[i]["threshold"]]


def stock_check(variants=("A", "B")):
    lines = ["STOCK DEFAULT ACCENT UNDER PLAIN WCAG (4.5 text / 3.0 non-text / 1.15 separation / 4.5 service), %d pairs" % len(R.PAIRS)]
    models = [("stock", E.model())] + [("overlay " + v, overlay(v)) for v in variants]
    res = {}
    for tag, m in models:
        for tn in S.ALL_THEMES:
            ev = R.Evaluator(R.stock_palette(m.themes[tn]))
            res[(tag, tn)] = ev.all()
    lines.append("  %-16s" % "failing pairs" + "".join("%13s" % t for t in S.ALL_THEMES))
    for tag, _ in models:
        lines.append("  %-16s" % tag + "".join("%13d" % len(failing_wcag(res[(tag, tn)])) for tn in S.ALL_THEMES))
    lines.append("")
    for tag, _ in models[1:]:
        lines.append("  still failing with %s (pair: stock -> overlay contrast):" % tag)
        for tn in S.ALL_THEMES:
            f = failing_wcag(res[(tag, tn)])
            lines.append("    %-12s %2d: %s" % (tn, len(f), ", ".join("%s %.2f->%.2f" % (R.PAIRS[i]["name"], res[("stock", tn)][i], res[(tag, tn)][i]) for i in f)))
        fixed = {}
        for tn in S.ALL_THEMES:
            fixed[tn] = [i for i in failing_wcag(res[("stock", tn)]) if i not in failing_wcag(res[(tag, tn)])]
        lines.append("  fixed by %s (count per theme): %s" % (tag, ", ".join("%s %d" % (tn, len(fixed[tn])) for tn in S.ALL_THEMES)))
        lines.append("")
    return "\n".join(lines), res


# ------------------------------------------------------------------------------------------
# lazy vs full crosscheck of the overlay model (hook included)
# ------------------------------------------------------------------------------------------

def crosscheck(variant, n=150):
    m = overlay(variant)
    bad = 0
    total = 0
    near_seen = [0]
    for tn in S.ALL_THEMES:
        th = m.themes[tn]
        rng = S.SplitMix64(S.seed_state("xcheck/" + variant + "/" + tn))
        accs = [th.stock_accent()]
        for k in range(n):
            acc = E.Accent(id=S.GEN_ACCENT_ID, accentColor=S.rand_rgb(rng))
            if k % 3 == 0:
                acc.myMessagesAccentColor = S.rand_rgb(rng)
                acc.myMessagesGradientAccentColor1 = S.rand_rgb(rng)
            elif k % 3 == 1:
                # light bubble in the accent's hue: exercises isMyMessagesGradientColorsNear (rule (d)) on Blue
                h = oklch_of(acc.accentColor)[2]
                acc.myMessagesAccentColor = S.argb_from_oklch(0.93, 0.03, h)
                acc.myMessagesGradientAccentColor1 = S.argb_from_oklch(0.95, 0.03, h + 10.0)
            accs.append(acc)
        for acc in accs:
            lz = E.palette(th, acc, acc.id, lazy=True)
            fu = E.palette(th, acc, acc.id, lazy=False)
            near_seen[0] += 1 if lz.is_near else 0
            for key in range(m.n):
                total += 1
                if lz.get(key) != fu.get(key):
                    bad += 1
    return bad, total, near_seen[0]


# ------------------------------------------------------------------------------------------
# measurement: free accents on all five base themes, plain WCAG
# ------------------------------------------------------------------------------------------

def _near_black(c):
    return (c & 0xFFFFFFFF) == (NEAR_BLACK & 0xFFFFFFFF)


def _measure_chunk(args):
    variant, service, tn, start, stop = args
    S.RULE["rule"] = "wcag"
    S.RULE["service"] = service
    m = overlay(variant)
    th = m.themes[tn]
    thr = S.thresholds(th, 0.0, "wcag")
    st = {"n": 0, "pass": 0, "first": 0, "attempts": 0, "max_attempts": 0, "fallback": 0, "fallback_pass": 0, "evals": 0,
          "reject": {}, "fail_pairs": {}, "min_margin": 9.0, "min_margin_pair": "", "accents": set(), "hue_bins": set(), "bubbles": set(),
          "walls": set(), "light_bubble": 0, "gradient_bubble": 0, "animated": 0, "kinds": {}, "pattern": 0, "negative": 0,
          "accent_L": [], "wall_L": {}, "nb": {}, "naive_pass": 0, "naive_fail_pairs": {}, "service_scores": [], "service_lite_scores": []}
    idx_srv = R.PAIR_INDEX["service_text"]
    idx_srvl = R.PAIR_INDEX["service_text_lite"]
    for k in range(start, stop):
        seed = "measure-%d" % k
        rng = S.SplitMix64(S.seed_state(seed + "/c_wcag/" + tn))
        stats = {"evals": 0, "reject": st["reject"]}
        v, res = S.gen_variant_c(th, rng, stats, mode="wcag")
        sv = v["solver"]
        st["n"] += 1
        st["evals"] += stats["evals"]
        st["attempts"] += sv["attempt"]
        st["max_attempts"] = max(st["max_attempts"], sv["attempt"])
        f = S.failing(res, thr)
        if sv["fallback"]:
            st["fallback"] += 1
            if not f:
                st["fallback_pass"] += 1
        else:
            if not f:
                st["pass"] += 1
                if sv["attempt"] == 1:
                    st["first"] += 1
                mm = min((res[i] / thr[i], R.PAIRS[i]["name"]) for i in res if thr[i] > 0)
                if mm[0] < st["min_margin"]:
                    st["min_margin"], st["min_margin_pair"] = mm
                st["accents"].add(v["accent"])
                st["hue_bins"].add(int(math.floor(sv["base_hue"] / 30.0)) % 12)
                st["bubbles"].add((v["my_messages_accent"],) + tuple(v["my_messages_gradient"]))
                w = v["wallpaper"]
                st["walls"].add(tuple(w["colors"]))
                st["light_bubble"] += 1 if D.luminance(v["my_messages_accent"]) > 0.4 else 0
                st["gradient_bubble"] += 1 if (len(v["my_messages_gradient"]) > 1 or (v["my_messages_gradient"] and v["my_messages_gradient"][0] != v["my_messages_accent"])) else 0
                st["animated"] += 1 if v["my_messages_animated"] else 0
                kind = {1: "solid", 2: "linear", 3: "motion", 4: "motion"}.get(len(w["colors"]), "other")
                st["kinds"][kind] = st["kinds"].get(kind, 0) + 1
                st["pattern"] += 1 if w["pattern_slug"] else 0
                st["negative"] += 1 if w["pattern_intensity"] < 0 else 0
                st["accent_L"].append(sv["accent_oklch"][0])
                st["wall_L"].setdefault(kind + ("-neg" if w["pattern_intensity"] < 0 else ""), []).append(sv["wallpaper_L"])
                pal = E.palette(th, S.to_accent(v), S.GEN_ACCENT_ID)
                for ck, _ in ON_ACCENT_PAIRS:
                    if _near_black(pal.get(ck[4:])):
                        st["nb"][ck[4:]] = st["nb"].get(ck[4:], 0) + 1
                st["service_scores"].append(res[idx_srv])
                st["service_lite_scores"].append(res[idx_srvl])
        for i in f:
            nm = R.PAIRS[i]["name"]
            st["fail_pairs"][nm] = st["fail_pairs"].get(nm, 0) + 1
        # naive reference on the same overlay model: uniform-RGB accent on the stock accent (the app's own path)
        rng2 = S.SplitMix64(S.seed_state(seed + "/a_acc/" + tn))
        vn = S.gen_naive(th, rng2, S.rand_rgb, False)
        _, rn = S.evaluate(th, vn)
        fn = S.failing(rn, thr)
        if not fn:
            st["naive_pass"] += 1
        for i in fn:
            nm = R.PAIRS[i]["name"]
            st["naive_fail_pairs"][nm] = st["naive_fail_pairs"].get(nm, 0) + 1
    return tn, st


def _merge(a, b):
    for k, v in b.items():
        if k not in a:
            a[k] = v
        elif isinstance(v, set):
            a[k] |= v
        elif isinstance(v, list):
            a[k] += v
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, list):
                    a[k].setdefault(kk, []).extend(vv)
                else:
                    a[k][kk] = a[k].get(kk, 0) + vv
        elif k == "max_attempts":
            a[k] = max(a[k], v)
        elif k == "min_margin":
            if v < a[k]:
                a[k], a["min_margin_pair"] = v, b["min_margin_pair"]
        elif k == "min_margin_pair":
            pass
        else:
            a[k] += v
    return a


def measure(variant, n, procs, service="on"):
    jobs = []
    step = max(1, (n + 7) // 8)
    for t in S.ALL_THEMES:
        for s0 in range(0, n, step):
            jobs.append((variant, service, t, s0, min(n, s0 + step)))
    t0 = time.time()
    if procs > 1:
        from multiprocessing import Pool
        with Pool(procs) as pool:
            results = pool.map(_measure_chunk, jobs, chunksize=1)
    else:
        results = [_measure_chunk(j) for j in jobs]
    agg = {}
    for tn, st in results:
        if tn not in agg:
            agg[tn] = st
        else:
            _merge(agg[tn], st)
    dt = time.time() - t0
    T = S.ALL_THEMES
    L = []
    L.append("canvas-fix overlay %s; free OKLCH accent on all five base themes; %d seeds per base theme; %d pairs; "
             "pass = every pair >= plain WCAG (4.5 text, 3.0 non-text, 1.15 bubble/wallpaper%s)" % (
                 variant, n, len(R.PAIRS), ", service text 4.5" if service == "on" else "; service_text/_lite scored but NOT in the rule"))
    L.append("fallbacks (stock accent after 12 rejected attempts) count as failures")
    L.append("")
    hdr = "%-38s" % "" + "".join("%13s" % t for t in T)
    L.append(hdr)
    row = lambda label, f: L.append("%-38s" % label + "".join(f(agg[t]) for t in T))
    row("pass rate (generated, all pairs)", lambda a: "%12.2f%%" % (100.0 * a["pass"] / a["n"]))
    row("first-attempt success", lambda a: "%12.2f%%" % (100.0 * a["first"] / a["n"]))
    row("mean attempts", lambda a: "%13.3f" % (a["attempts"] / a["n"]))
    row("max attempts", lambda a: "%13d" % a["max_attempts"])
    row("deterministic fallbacks used", lambda a: "%13d" % a["fallback"])
    row("  ... of which pass WCAG", lambda a: "%13d" % a["fallback_pass"])
    row("palette evaluations per seed", lambda a: "%13.2f" % (a["evals"] / a["n"]))
    row("min contrast/threshold (passes)", lambda a: "%13.4f" % a["min_margin"])
    row("  ... on pair", lambda a: "%13s" % a["min_margin_pair"][:12])
    row("distinct accent colours", lambda a: "%13d" % len(a["accents"]))
    row("base-hue 30-degree bins covered", lambda a: "%10d/12" % len(a["hue_bins"]))
    row("distinct outgoing-bubble colourings", lambda a: "%13d" % len(a["bubbles"]))
    row("distinct wallpaper colourings", lambda a: "%13d" % len(a["walls"]))
    row("accent OKLCH L: mean", lambda a: "%13.3f" % (sum(a["accent_L"]) / max(1, len(a["accent_L"]))))
    row("accent OKLCH L: min / max", lambda a: "%13s" % ("%.3f/%.3f" % (min(a["accent_L"]), max(a["accent_L"])) if a["accent_L"] else "-"))
    row("light (black-text) bubbles", lambda a: "%12.1f%%" % (100.0 * a["light_bubble"] / max(1, a["pass"])))
    row("gradient bubbles", lambda a: "%12.1f%%" % (100.0 * a["gradient_bubble"] / max(1, a["pass"])))
    row("animated bubble gradients", lambda a: "%12.1f%%" % (100.0 * a["animated"] / max(1, a["pass"])))
    for kind in ("solid", "linear", "motion"):
        row("wallpaper kind: " + kind, lambda a, kind=kind: "%12.1f%%" % (100.0 * a["kinds"].get(kind, 0) / max(1, a["pass"])))
    row("wallpapers with pattern", lambda a: "%12.1f%%" % (100.0 * a["pattern"] / max(1, a["pass"])))
    row("negative-intensity (dark) patterns", lambda a: "%12.1f%%" % (100.0 * a["negative"] / max(1, a["pass"])))
    for kind in ("solid", "linear", "motion", "motion-neg"):
        row("wallpaper OKLCH L mean: " + kind, lambda a, kind=kind: "%13s" % (("%.3f" % (sum(a["wall_L"][kind]) / len(a["wall_L"][kind]))) if a["wall_L"].get(kind) else "-"))
    row("service_text contrast: min", lambda a: "%13.2f" % (min(a["service_scores"]) if a["service_scores"] else 0))
    row("service_text_lite contrast: min", lambda a: "%13.2f" % (min(a["service_lite_scores"]) if a["service_lite_scores"] else 0))
    row("  share < 4.5 (service_text)", lambda a: "%12.2f%%" % (100.0 * sum(1 for x in a["service_scores"] if x < 4.5) / max(1, len(a["service_scores"]))))
    row("  share < 4.5 (service_text_lite)", lambda a: "%12.2f%%" % (100.0 * sum(1 for x in a["service_lite_scores"] if x < 4.5) / max(1, len(a["service_lite_scores"]))))
    L.append("on-accent rule: share of passing styles where the content is NEAR_BLACK")
    for ck, _ in ON_ACCENT_PAIRS:
        row("  " + ck[4:], lambda a, ck=ck: "%12.1f%%" % (100.0 * a["nb"].get(ck[4:], 0) / max(1, a["pass"])))
    row("(a) uniform-RGB accent, same overlay", lambda a: "%12.2f%%" % (100.0 * a["naive_pass"] / a["n"]))
    rej = set()
    for t in T:
        rej.update(agg[t]["reject"])
    if rej:
        L.append("rejected attempts by stage / final-check pair:")
        for k in sorted(rej, key=lambda k: (-sum(agg[t]["reject"].get(k, 0) for t in T), k)):
            L.append("  %-36s" % k + "".join("%13d" % agg[t]["reject"].get(k, 0) for t in T))
    names = set()
    for t in T:
        names.update(agg[t]["fail_pairs"])
    L.append("residual failing pairs (final variant incl. fallbacks), seeds per theme:")
    if not names:
        L.append("  (none)")
    for nm in sorted(names, key=lambda k: (-sum(agg[t]["fail_pairs"].get(k, 0) for t in T), k)):
        L.append("  %-36s" % nm + "".join("%13d" % agg[t]["fail_pairs"].get(nm, 0) for t in T))
    names = set()
    for t in T:
        names.update(agg[t]["naive_fail_pairs"])
    L.append("(a) uniform-RGB accent on the same overlay: seeds failing each pair (top 12)")
    for nm in sorted(names, key=lambda k: (-sum(agg[t]["naive_fail_pairs"].get(k, 0) for t in T), k))[:12]:
        L.append("  %-36s" % nm + "".join("%13d" % agg[t]["naive_fail_pairs"].get(nm, 0) for t in T))
    L.append("")
    L.append("elapsed %.1f s on %d process(es)" % (dt, procs))
    return "\n".join(L), agg


# ------------------------------------------------------------------------------------------
# gallery export
# ------------------------------------------------------------------------------------------

GALLERY_KEYS = [
    # action bar
    "actionBarDefault", "actionBarDefaultTitle", "actionBarDefaultIcon", "actionBarDefaultSubtitle", "actionBarTabActiveText",
    "actionBarTabUnactiveText", "actionBarTabLine",
    # windows
    "windowBackgroundWhite", "windowBackgroundGray", "windowBackgroundWhiteBlackText", "windowBackgroundWhiteGrayText",
    "windowBackgroundWhiteGrayText4", "windowBackgroundWhiteBlueHeader", "windowBackgroundWhiteBlueText4",
    # switches
    "switchTrack", "switchTrackChecked",
    # chat list
    "chats_name", "chats_message", "chats_nameMessage", "chats_date", "chats_unreadCounter", "chats_unreadCounterText",
    "chats_unreadCounterMuted", "chats_actionBackground", "chats_actionIcon", "chats_sentReadCheck", "chats_pinnedIcon", "divider",
    # bubbles
    "chat_inBubble", "chat_outBubble", "chat_outBubbleGradient1", "chat_outBubbleGradient2", "chat_outBubbleGradient3",
    # message text and links
    "chat_messageTextIn", "chat_messageTextOut", "chat_messageLinkIn", "chat_messageLinkOut",
    # time and read check
    "chat_inTimeText", "chat_outTimeText", "chat_outSentCheckRead",
    # replies
    "chat_inReplyNameText", "chat_inReplyLine", "chat_outReplyNameText", "chat_outReplyLine", "chat_inReplyMessageText",
    "chat_outReplyMessageText",
    # header
    "chat_status",
    # composer
    "chat_messagePanelBackground", "chat_messagePanelText", "chat_messagePanelHint", "chat_messagePanelIcons", "chat_messagePanelSend",
    # filled buttons
    "featuredStickers_addButton", "featuredStickers_buttonText",
]
HEADLINE = ["list_gray_text", "list_accent_text", "chats_preview", "unread_badge_text", "fab_icon", "actionbar_subtitle", "in_text",
            "in_link", "in_time", "out_text", "out_time", "filled_button_text", "service_text"]


def variant_record(th, v, stock_res=None):
    """Genome variant -> gallery record: declared fields + FINAL getColor() values (overlay + fillAccentColors + hook)."""
    acc = S.to_accent(v)
    pal = E.palette(th, acc, S.GEN_ACCENT_ID)
    ev = R.Evaluator(pal)
    res = ev.all()
    thr = S.thresholds(th, 0.0, "wcag")
    wp = ev.wp
    w = v["wallpaper"]
    if w.get("source") == "theme":
        kind = "base theme's own"
    elif w.get("source") == "default":
        kind = "built-in default"
    else:
        kind = {1: "solid", 2: "linear-gradient"}.get(len(w["colors"]), "motion-gradient")
    # service message as rendered: worst sample of the pill against the text actually drawn
    srv_text = wp.service_text
    samples = list(wp.service)
    worst = min(samples, key=lambda c_: D.contrast(R.over(srv_text, c_), c_))
    mm_i = min((i for i in res if thr[i] > 0), key=lambda i: res[i] / thr[i])
    rec = {
        "base_theme": th.name,
        "accent": hx(v["accent"]),
        "my_messages_accent": hx(v["my_messages_accent"]),
        "my_messages_gradient": [hx(c) for c in v["my_messages_gradient"]],
        "my_messages_animated": bool(v["my_messages_animated"]),
        "wallpaper": {
            "colors": [hx(c) for c in w["colors"]] if w.get("source") != "theme" else [hx(E.s32(0xFF000000 | c)) for c in wp.colors if c != 0],
            "kind": kind,
            "rotation": w["rotation"],
            "pattern_intensity": w["pattern_intensity"],
            "pattern_slug": w["pattern_slug"],
            "parallax_motion": bool(w["motion"]),
            "rendered": {"kind": wp.kind, "intensity_percent": wp.intensity, "pattern": bool(wp.pattern),
                         "stored_patternIntensity_float32": acc.patternIntensity},
        },
        "colors": {k: hx(pal.get(k)) for k in GALLERY_KEYS},
        "service_text": hx(srv_text),
        "service_pill_color": hx(E.s32(0xFF000000 | worst)),
        "service_mode": "gradient service shader (WHITE text on ColorMatrix(wallpaper))" if wp.shader else "pill: chat_serviceBackground or calcDrawableColor over the wallpaper, chat_serviceText",
        "contrast": {nm: round(res[R.PAIR_INDEX[nm]], 3) for nm in HEADLINE},
        "min_margin": round(res[mm_i] / thr[mm_i], 4),
        "min_margin_pair": R.PAIRS[mm_i]["name"],
    }
    if "solver" in v:
        rec["solver"] = v["solver"]
    fails = {R.PAIRS[i]["name"]: {"contrast": round(res[i], 3), "threshold": thr[i]} for i in sorted(res) if res[i] < thr[i]}
    return rec, fails, res


def _forks(seed):
    root = S.SplitMix64(S.seed_state(seed))
    return root.fork(), root.fork(), root.fork()


def gallery(variant="B", n=36, n_naive=3):
    S.RULE["rule"] = "wcag"
    S.RULE["service"] = "on"
    m = overlay(variant)
    dc, nc = S.DAY_CHOICES["wcag"], S.NIGHT_CHOICES["wcag"]
    lo, hi = S.C["bubble_radius"]
    genomes = []
    for k in range(n):
        seed = "gallery-%02d" % k
        day_rng, night_rng, misc_rng = _forks(seed)
        day_theme = m.themes[dc[day_rng.below(len(dc))]]
        night_theme = m.themes[nc[night_rng.below(len(nc))]]
        day, _ = S.gen_variant_c(day_theme, day_rng, mode="wcag")
        night, _ = S.gen_variant_c(night_theme, night_rng, mode="wcag")
        radius = lo + misc_rng.below(hi - lo + 1)
        # determinism cross-check against style_sim.genome() (same forks, same draws)
        g0 = S.genome(seed, mode="wcag", m=m)
        assert g0["day"] == S.variant_json(day) and g0["night"] == S.variant_json(night) and g0["bubble_radius"] == radius, seed
        rd, fd, _ = variant_record(day_theme, day)
        rn, fn, _ = variant_record(night_theme, night)
        assert not fd and not fn, (seed, fd, fn)
        genomes.append({"seed": seed, "day": rd, "night": rn, "bubble_radius": radius})
    # naive: uniform-RGB accent (the app's own change-accent path: stock accent copy with a new accentColor),
    # STOCK model (no overlay, no hook); the first seeds whose day and night variants both fail
    stock = E.model()
    naive = []
    k = 0
    while len(naive) < n_naive:
        seed = "naive-%02d" % k
        k += 1
        day_rng, night_rng, misc_rng = _forks(seed)
        day_theme = stock.themes[dc[day_rng.below(len(dc))]]
        night_theme = stock.themes[nc[night_rng.below(len(nc))]]
        day = S.gen_naive(day_theme, day_rng, S.rand_rgb, False)
        night = S.gen_naive(night_theme, night_rng, S.rand_rgb, False)
        radius = lo + misc_rng.below(hi - lo + 1)
        rd, fd, _ = variant_record(day_theme, day)
        rn, fn, _ = variant_record(night_theme, night)
        if not fd or not fn:
            continue
        for rec, fails, th in ((rd, fd, day_theme), (rn, fn, night_theme)):
            rec["failing_pairs"] = fails
            st = R.Evaluator(R.stock_palette(th)).all()
            thr = S.thresholds(th, 0.0, "wcag")
            rec["failing_pairs_that_pass_with_the_stock_accent"] = sorted(nm for nm in fails if st[R.PAIR_INDEX[nm]] >= thr[R.PAIR_INDEX[nm]])
        naive.append({"seed": seed, "generator": "uniform RGB accentColor on the stock accent, stock model", "day": rd, "night": rn,
                      "bubble_radius": radius})
    out = {
        "format": "canvas-fix gallery v1; colours '#AARRGGBB'; 'colors' = Theme.getColor() after overlay + fillAccentColors + on-accent hook; "
                  "service_pill_color = the rendered pill sample with the lowest contrast against service_text; contrast = WCAG ratio of the "
                  "13 headline pairs; min_margin = min over all 99 pairs of contrast / threshold",
        "overlay": variant,
        "rule": "plain WCAG 2.x: 4.5 text, 3.0 non-text, 1.15 bubble vs wallpaper, service text 4.5",
        "prng": "SHA-256(seed)[0:8] big-endian -> SplitMix64; forks: day, night, misc (detmath OKLCH)",
        "genomes": genomes,
        "naive": naive,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sweep-step", type=int, default=10)
    ap.add_argument("--stock", action="store_true")
    ap.add_argument("--crosscheck", type=int)
    ap.add_argument("--measure", type=int)
    ap.add_argument("--variant", default="B")
    ap.add_argument("--service", default="on", choices=["on", "off"])
    ap.add_argument("--procs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--gallery", action="store_true")
    a = ap.parse_args()
    if a.gallery:
        g = gallery(a.variant)
        path = os.path.join(OUT, "gallery.json")
        with open(path, "w") as f:
            json.dump(g, f, indent=1)
        print("wrote %s: %d genomes, %d naive" % (path, len(g["genomes"]), len(g["naive"])))
    if a.stock:
        print(stock_check()[0])
    if a.crosscheck:
        for v in ("A", "B"):
            bad, total, near = crosscheck(v, a.crosscheck)
            print("crosscheck overlay %s: lazy vs full getColor mismatches %d of %d (%d palettes with a near-theme bubble)" % (v, bad, total, near))
    if a.measure:
        print(measure(a.variant, a.measure, a.procs, a.service)[0])
    if a.build:
        for variant in ("B", "A"):
            t0 = time.time()
            spec, rows = build(variant, a.sweep_step)
            with open(os.path.join(OUT, "overlay_%s.json" % variant), "w") as f:
                json.dump(spec, f, indent=1, sort_keys=True)
            with open(os.path.join(OUT, "overlay_%s_rows.json" % variant), "w") as f:
                json.dump(rows, f, indent=1)
            print("VARIANT %s (%.1f s): %d defaults, %d attheme lines, %d exclusions" % (
                variant, time.time() - t0, len(spec["defaults"]), sum(len(v) for v in spec["attheme"].values()), len(spec["exclusions"])))
            print(fmt_rows(rows))


if __name__ == "__main__":
    main()
