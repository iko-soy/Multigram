"""Faithful float32 port of the Telegram-Android accent engine.

Ported (Java/Skia float semantics, every intermediate rounded to IEEE binary32):
  * android.graphics.Color.colorToHSV / HSVToColor  -> Skia SkRGBToHSV / SkHSVToColor
  * AndroidUtilities.computePerceivedBrightness, getColorDistance, getAverageColor
  * Theme.changeColorAccent(float[],float[],int,boolean,int), getAccentColor, useBlackText,
    changeBrightness, ThemeAccent.fillAccentColors (+ its post-processing helpers),
    applyCalculatedTableColors / applyCalculatedArticleCodeColors, getColor / getDefaultColor.

Colours are Java signed 32-bit ints throughout (the Java code compares colour values as signed
ints in a few places, e.g. `currentColorsNoAccent.get(fallbackKey, -1) >= 0`).
"""
import math
import struct

import tgsrc
from detmath_tables import SRGB8_TO_LINEAR as _SRGB8_TO_LINEAR

# ----------------------------------------------------------------------------------------
# IEEE binary32 helpers
# ----------------------------------------------------------------------------------------
_F = struct.Struct("<f")
_pack, _unpack = _F.pack, _F.unpack
INF = math.inf
NAN = math.nan

# Skia rounding: current Skia rounds via double (floor((double)x + 0.5)); older Skia used
# floorf(x + 0.5f).  Select with set_round_mode().
ROUND_MODE = "double"


def f32(x):
    try:
        return _unpack(_pack(x))[0]
    except OverflowError:
        return math.copysign(INF, x)


def fdiv(a, b):
    """Java float division (IEEE: x/0 = +-inf, 0/0 = NaN)."""
    if b == 0.0:
        if a == 0.0 or a != a:
            return NAN
        return math.copysign(INF, a) * math.copysign(1.0, b)
    return f32(a / b)


def fmul(a, b):
    return f32(a * b)


def fadd(a, b):
    return f32(a + b)


def fsub(a, b):
    return f32(a - b)


def f2i(x):
    """Java (int) cast of a float/double."""
    if x != x:
        return 0
    if x >= 2147483647.0:
        return 2147483647
    if x <= -2147483648.0:
        return -2147483648
    return int(x)


def jmin(a, b):
    """java.lang.Math.min(float,float) (NaN-propagating)."""
    if a != a or b != b:
        return NAN
    return a if a <= b else b


def jmax(a, b):
    if a != a or b != b:
        return NAN
    return a if a >= b else b


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def alpha(c):
    return (c >> 24) & 0xFF


def red(c):
    return (c >> 16) & 0xFF


def green(c):
    return (c >> 8) & 0xFF


def blue(c):
    return c & 0xFF


def argb(a, r, g, b):
    return s32(((a & 0xFFFFFFFF) << 24) | ((r & 0xFFFFFFFF) << 16) | ((g & 0xFFFFFFFF) << 8) | (b & 0xFFFFFFFF))


def hexc(c):
    return "0x%08X" % (c & 0xFFFFFFFF)


# float32 constants as the Java compiler stores them
F0_2126, F0_7152, F0_0722 = f32(0.2126), f32(0.7152), f32(0.0722)
F0_705 = f32(0.705)
F0_3 = f32(0.3)
F0_6 = f32(0.6)
F1_5 = 1.5
F30 = 30.0
F360 = 360.0
F255 = 255.0
SK_NEARLY_ZERO = 1.0 / 4096.0


# ----------------------------------------------------------------------------------------
# Skia colour conversions (what Color.colorToHSV / HSVToColor call through JNI)
# ----------------------------------------------------------------------------------------

def color_to_hsv(c):
    """SkRGBToHSV(r, g, b) with float (SkScalar) math. Returns (h, s, v)."""
    r = (c >> 16) & 0xFF
    g = (c >> 8) & 0xFF
    b = c & 0xFF
    mx = r if r > g else g
    if b > mx:
        mx = b
    mn = r if r < g else g
    if b < mn:
        mn = b
    delta = mx - mn
    v = f32(mx / 255.0)
    if delta == 0:
        return (0.0, 0.0, v)
    s = f32(delta / mx)
    if r == mx:
        h = f32((g - b) / delta)
    elif g == mx:
        h = f32(2.0 + f32((b - r) / delta))
    else:
        h = f32(4.0 + f32((r - g) / delta))
    h = f32(h * 60.0)
    if h < 0:
        h = f32(h + 360.0)
    return (h, s, v)


def _sk_pin01(x):
    # SkTPin(x, 0, 1) == std::max(0.f, std::min(x, 1.f)); NaN -> 0
    m = 1.0 if 1.0 < x else x
    return m if 0.0 < m else 0.0


def sk_round2int(x):
    if x != x:
        return 2147483520
    if ROUND_MODE == "double":
        r = math.floor(x + 0.5)            # (float)floor((double)x + 0.5)
    else:
        r = math.floor(f32(x + 0.5))       # floorf(x + 0.5f)
    if r > 2147483520:
        r = 2147483520
    if r < -2147483520:
        r = -2147483520
    return int(r)


class NaNHue(ValueError):
    pass


def hsv_to_color(a, h, s, v):
    """SkHSVToColor(a, hsv). Hue outside [0, 360) is treated as 0 (red) -- no wrapping."""
    s = _sk_pin01(s)
    v = _sk_pin01(v)
    v_byte = sk_round2int(f32(v * 255.0))
    if abs(s) <= SK_NEARLY_ZERO:
        return argb(a, v_byte, v_byte, v_byte)
    if h != h:
        raise NaNHue("NaN hue reached SkHSVToColor (undefined behaviour in C++)")
    hx = 0.0 if (h < 0 or h >= 360.0) else f32(h / 60.0)
    w = math.floor(hx)
    f = f32(hx - w)
    p = sk_round2int(f32(f32(f32(1.0 - s) * v) * 255.0))
    q = sk_round2int(f32(f32(f32(1.0 - f32(s * f)) * v) * 255.0))
    t = sk_round2int(f32(f32(f32(1.0 - f32(s * f32(1.0 - f))) * v) * 255.0))
    wi = int(w)
    if wi == 0:
        r, g, b = v_byte, t, p
    elif wi == 1:
        r, g, b = q, v_byte, p
    elif wi == 2:
        r, g, b = p, v_byte, t
    elif wi == 3:
        r, g, b = p, q, v_byte
    elif wi == 4:
        r, g, b = t, p, v_byte
    else:
        r, g, b = v_byte, p, q
    return argb(a, r, g, b)


# ----------------------------------------------------------------------------------------
# AndroidUtilities
# ----------------------------------------------------------------------------------------

def perceived_brightness(c):
    """AndroidUtilities.computePerceivedBrightness (gamma-encoded Rec.709 weights, float)."""
    r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
    return f32(f32(f32(f32(r * F0_2126) + f32(g * F0_7152)) + f32(b * F0_0722)) / 255.0)


def color_distance(c1, c2):
    r1, g1, b1 = red(c1), green(c1), blue(c1)
    r2, g2, b2 = red(c2), green(c2), blue(c2)
    r_mean = (r1 + r2) // 2            # both non-negative: Java int division == floor
    r = r1 - r2
    g = g1 - g2
    b = b1 - b2
    return (((512 + r_mean) * r * r) >> 8) + (4 * g * g) + (((767 - r_mean) * b * b) >> 8)


def average_color(c1, c2):
    return argb(255, red(c1) // 2 + red(c2) // 2, green(c1) // 2 + green(c2) // 2, blue(c1) // 2 + blue(c2) // 2)


def lerp_f(a, b, f):
    return f32(a + f32(f * f32(b - a)))


def lerp_i(a, b, f):
    return f2i(f32(a + f32(f * (b - a))))


def mathutils_clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def utilities_clamp(v, mx, mn):
    """Utilities.clamp(float value, float maxValue, float minValue)."""
    if v != v:
        return mn
    if v in (INF, -INF):
        return mx
    return jmax(jmin(v, mx), mn)


def set_alpha_component(c, a):
    if a < 0 or a > 255:
        raise ValueError("alpha must be between 0 and 255.")
    return s32((c & 0x00FFFFFF) | (a << 24))


def blend_argb(c1, c2, ratio):
    inv = f32(1.0 - ratio)
    a = f32(f32(alpha(c1) * inv) + f32(alpha(c2) * ratio))
    r = f32(f32(red(c1) * inv) + f32(red(c2) * ratio))
    g = f32(f32(green(c1) * inv) + f32(green(c2) * ratio))
    b = f32(f32(blue(c1) * inv) + f32(blue(c2) * ratio))
    return argb(f2i(a), f2i(r), f2i(g), f2i(b))


# ----------------------------------------------------------------------------------------
# Theme.java statics
# ----------------------------------------------------------------------------------------

def change_brightness(c, amount):
    r = f2i(f32(red(c) * amount))
    g = f2i(f32(green(c) * amount))
    b = f2i(f32(blue(c) * amount))
    r = 0 if r < 0 else min(r, 255)
    g = 0 if g < 0 else min(g, 255)
    b = 0 if b < 0 else min(b, 255)
    return argb(alpha(c), r, g, b)


def change_color_accent(base_hsv, accent_hsv, color, is_dark, fallback, trace=None):
    """Theme.changeColorAccent(float[] baseHsv, float[] accentHsv, int color, boolean isDarkTheme, int fallback)."""
    h, s, v = color_to_hsv(color)
    bh, bs, bv = base_hsv
    ah, as_, av = accent_hsv
    d = f32(h - bh)
    diff_h = jmin(abs(d), abs(f32(d - 360.0)))
    if diff_h > 30.0:
        return fallback
    dist = jmin(fdiv(f32(1.5 * s), bs), 1.0)
    nh = f32(f32(h + ah) - bh)
    ns = fdiv(f32(s * as_), bs)
    nv = f32(v * f32(f32(1.0 - dist) + fdiv(f32(dist * av), bv)))
    new = hsv_to_color(alpha(color), nh, ns, nv)
    orig_b = perceived_brightness(color)
    new_b = perceived_brightness(new)
    need_revert = (orig_b > new_b) if is_dark else (orig_b < new_b)
    if trace is not None:
        trace.update(h=h, s=s, v=v, nh=nh, ns=ns, nv=nv, hue_wrapped_to_red=(nh < 0 or nh >= 360.0) and ns > SK_NEARLY_ZERO,
                     pre_revert=new, revert=need_revert)
    if need_revert:
        fallback_amount = f32(fdiv(f32(f32(1.0 - F0_6) * orig_b), new_b) + F0_6)
        new = change_brightness(new, fallback_amount)
    return new


def get_accent_color(base_hsv, base_color, element_color):
    """Theme.getAccentColor(float[] baseHsv, int baseColor, int elementColor)."""
    h3, s3, v3 = color_to_hsv(base_color)
    h4, s4, v4 = color_to_hsv(element_color)
    bh, bs, bv = base_hsv
    dist = jmin(fdiv(f32(1.5 * s3), bs), 1.0)
    nh = f32(f32(h4 - h3) + bh)
    ns = fdiv(f32(s4 * bs), s3)
    nv = fdiv(f32(f32(f32(fdiv(v4, v3) + dist) - 1.0) * bv), dist)
    if nv < F0_3:
        return element_color
    return hsv_to_color(255, nh, ns, nv)


def use_black_text(c1, c2):
    r1, r2 = f32(red(c1) / 255.0), f32(red(c2) / 255.0)
    g1, g2 = f32(green(c1) / 255.0), f32(green(c2) / 255.0)
    b1, b2 = f32(blue(c1) / 255.0), f32(blue(c2) / 255.0)
    r = f32(f32(r1 * 0.5) + f32(r2 * 0.5))
    g = f32(f32(g1 * 0.5) + f32(g2 * 0.5))
    b = f32(f32(b1 * 0.5) + f32(b2 * 0.5))
    lightness = f32(f32(f32(F0_2126 * r) + f32(F0_7152 * g)) + f32(F0_0722 * b))
    lightness2 = f32(f32(f32(F0_2126 * r1) + f32(F0_7152 * g1)) + f32(F0_0722 * b1))
    return lightness > F0_705 or lightness2 > F0_705


def mult_alpha(c, m):
    if m == 1.0:
        return c
    return set_alpha_component(c, mathutils_clamp(f2i(f32(alpha(c) * m)), 0, 0xFF))


def blend_over(A, B):
    aB = f32(alpha(B) / 255.0)
    aA = f32(alpha(A) / 255.0)
    one_m = f32(1.0 - aB)
    aC = f32(aB + f32(aA * one_m))
    if aC == 0.0:
        return 0

    def ch(cb, ca):
        return f2i(fdiv(f32(f32(cb * aB) + f32(f32(ca * aA) * one_m)), aC))
    return argb(f2i(f32(aC * 255.0)), ch(red(B), red(A)), ch(green(B), green(A)), ch(blue(B), blue(A)))


def adapt_hue(color, hue_from):
    h, s, _ = color_to_hsv(hue_from)
    _, cs, cv = color_to_hsv(color)
    return hsv_to_color(alpha(color), h, lerp_f(cs, s, f32(0.25)), cv)


# ----------------------------------------------------------------------------------------
# Parsed model
# ----------------------------------------------------------------------------------------

class Model:
    def __init__(self, parsed, spec=None):
        tj, tc = parsed["theme_java"], parsed["themecolors_java"]
        self.parsed = parsed
        self.spec = spec                   # canvas-fix overlay (None = stock Telegram)
        self.tag = spec["tag"] if spec else "stock"
        self.key_names = tj["keys"]
        self.K = {n: i for i, n in enumerate(self.key_names)}
        self.n = len(self.key_names)
        m = tj["markers"]
        self.bub_start = m["myMessagesBubblesStartIndex"]["value"]
        self.bub_end = m["myMessagesBubblesEndIndex"]["value"]
        self.my_start = m["myMessagesStartIndex"]["value"]
        self.my_end = m["myMessagesEndIndex"]["value"]
        self.my2_start = m["myMessages2StartIndex"]["value"]
        self.my2_end = m["myMessages2EndIndex"]["value"]
        self.defaults = [0] * self.n
        for k, v in tc["defaults"].items():
            self.defaults[self.K[k]] = v
        self.fallback = {}
        for a, b, _ in tj["fallbackKeys"]:
            self.fallback[self.K[a]] = self.K[b]
        self.exclusions = set(self.K[k] for k, _, _ in tj["themeAccentExclusionKeys"])
        self.extra_keys = [self.K[k] for k in tj["myMessagesAccentExtraKeys"]["keys"]]
        self.DEFAULT_ACCENT_ID = tj["DEFALT_THEME_ACCENT_ID"]["value"]
        self.MSG_OUT_COLOR_BLACK = tj["MSG_OUT_COLOR_BLACK"]["value"]
        self.MSG_OUT_COLOR_WHITE = tj["MSG_OUT_COLOR_WHITE"]["value"]
        self.name_of_key = {self.K[k]: nm for k, nm, _ in tc["colorKeysMap"]}
        oc = tj["out_text_consts"]
        self.out_consts = {}
        for which in ("black", "white"):
            txt, sub, seek = oc[which]
            self.out_consts[which] = (tj[txt]["value"], sub, seek)
        # MultiGram: rule (d) already in the parsed source (the out-text block guard widened with
        # `|| PaletteFix.isRuntimeAccent(this)` or `|| id > 100`, see tgsrc.OUT_BLOCK_GUARD_RE)
        self.src_out_block_custom = bool(tj.get("out_block_guard_id_gt_100", False))
        self.out_block_accent2_zero = [(self.K[k], v) for k, v in tj["out_block_accent2_zero"]]
        self.out_block_always = [(self.K[k], v) for k, v in tj["out_block_always"]]
        if tj["out_block_unparsed"]:
            raise ValueError("unparsed puts in fillAccentColors out-text block: %r" % tj["out_block_unparsed"])
        self.themes = {}
        for t in tj["themes"]:
            th = ThemeInfo(self, t, parsed["atthemes"][t["assetName"]])
            self.themes[th.name] = th
        self.hook = None
        if spec:
            self._apply_spec(spec)

    def _apply_spec(self, spec):
        """canvas-fix overlay, applied exactly where the app would carry it:
          spec['defaults']   -> ThemeColors.createDefaultColors() values
          spec['attheme']    -> lines added/changed in the bundled .attheme files (currentColorsNoAccent)
          spec['exclusions'] -> keys added to Theme.themeAccentExclusionKeys
          spec['hook']       -> the on-accent content rule run at the end of refreshThemeColors()"""
        K = self.K
        for k, v in spec.get("defaults", {}).items():
            self.defaults[K[k]] = s32(v)
        for k in spec.get("exclusions", []):
            self.exclusions.add(K[k])
        by_asset = {th.assetName: th for th in self.themes.values()}
        for asset, kv in spec.get("attheme", {}).items():
            th = by_asset[asset]
            for k, v in kv.items():
                th.no_accent[K[k]] = s32(v)
        hk = spec.get("hook")
        if hk:
            mu = hk.get("muted")                       # None only in the '-no-c' ablation (rule (c) off)
            self.hook = {
                "near_black": s32(hk["near_black"]),
                "pairs": [(K[a], K[b]) for a, b in hk["pairs"]],
                "content": {K[a]: K[b] for a, b in hk["pairs"]},
                "muted": K[mu["key"]] if mu else -1, "muted_text": K[mu["text"]] if mu else -1,
                "muted_pins": [K[x] for x in mu["pins"]] if mu else [],
                "muted_table": {tn: (s32(w), s32(b)) for tn, (w, b) in mu["table"].items()} if mu else {},
                # (d) Theme.java:677 `if (!isMyMessagesGradientColorsNear)` -> `... || id > 100`: runtime-created
                # accents (ids from ++lastAccentId, first 101) always get the black/white out-text block
                "out_block_custom": bool(hk.get("out_block_custom", False)),
            }

    def key(self, name):
        if not name.startswith("key_"):
            name = "key_" + name
        return self.K[name]

    def get_default_color(self, key):
        """Theme.getDefaultColor(int key)."""
        value = self.defaults[key]
        if value == 0:
            fb = self.fallback.get(key, -1)
            if fb != -1:
                return self.get_default_color(fb)
            K = self.K
            if (self.bub_start <= key < self.bub_end or key in (K["key_chats_menuTopShadow"], K["key_chats_menuTopBackground"],
                    K["key_chats_menuTopShadowCats"], K["key_chat_wallpaper_gradient_to2"], K["key_chat_wallpaper_gradient_to3"])):
                return 0
            return s32(0xFFFF0000)
        return value


class Accent:
    __slots__ = ("id", "accentColor", "accentColor2", "myMessagesAccentColor", "myMessagesGradientAccentColor1",
                 "myMessagesGradientAccentColor2", "myMessagesGradientAccentColor3", "myMessagesAnimated",
                 "backgroundOverrideColor", "backgroundGradientOverrideColor1", "backgroundGradientOverrideColor2",
                 "backgroundGradientOverrideColor3", "backgroundRotation", "patternSlug", "patternIntensity",
                 "patternMotion", "info", "isDefault")

    def __init__(self, **kw):
        self.id = 0
        self.accentColor = 0
        self.accentColor2 = 0
        self.myMessagesAccentColor = 0
        self.myMessagesGradientAccentColor1 = 0
        self.myMessagesGradientAccentColor2 = 0
        self.myMessagesGradientAccentColor3 = 0
        self.myMessagesAnimated = False
        self.backgroundOverrideColor = 0          # Java long
        self.backgroundGradientOverrideColor1 = 0
        self.backgroundGradientOverrideColor2 = 0
        self.backgroundGradientOverrideColor3 = 0
        self.backgroundRotation = 45
        self.patternSlug = ""
        self.patternIntensity = 0.0
        self.patternMotion = False
        self.info = None
        self.isDefault = False
        for k, v in kw.items():
            setattr(self, k, v)

    def copy(self, **kw):
        a = Accent(**{k: getattr(self, k) for k in self.__slots__})
        for k, v in kw.items():
            setattr(a, k, v)
        return a


def long_to_int(v):
    return s32(v)


class ThemeInfo:
    def __init__(self, model, t, at):
        self.model = model
        self.name = t["name"]
        self.assetName = t["assetName"]
        self.firstAccentIsDefault = t["firstAccentIsDefault"]
        tj = model.parsed["theme_java"]
        self.is_dark = self.name in ("Dark Blue", "Night")       # ThemeInfo.isDark() name table
        self.no_accent = {}
        for kname, (val, _ln) in at["values"].items():
            self.no_accent[model.K[kname]] = val
        o = t["options"]
        self.accents = {}
        self.accent_order = []
        home = tj["isHome"]
        for a in range(len(o["accent"])):
            acc = Accent()
            acc.id = o["ids"][a] if o["ids"] is not None else a
            acc.isDefault = home.get(self.name) == acc.id
            acc.accentColor = o["accent"][a]
            if o["myMessages"] is not None:
                acc.myMessagesAccentColor = o["myMessages"][a]
            if o["myMessagesGradient"] is not None:
                acc.myMessagesGradientAccentColor1 = o["myMessagesGradient"][a]
            first_default = self.firstAccentIsDefault and acc.id == model.DEFAULT_ACCENT_ID
            if o["background"] is not None:
                acc.backgroundOverrideColor = 0x100000000 if first_default else o["background"][a]
            if o["backgroundGradient1"] is not None:
                acc.backgroundGradientOverrideColor1 = 0x100000000 if first_default else o["backgroundGradient1"][a]
            if o["backgroundGradient2"] is not None:
                acc.backgroundGradientOverrideColor2 = 0x100000000 if first_default else o["backgroundGradient2"][a]
            if o["backgroundGradient3"] is not None:
                acc.backgroundGradientOverrideColor3 = 0x100000000 if first_default else o["backgroundGradient3"][a]
            if o["patternSlugs"] is not None:
                acc.patternIntensity = f32(o["patternIntensities"][a] / 100.0)
                acc.backgroundRotation = o["patternRotations"][a]
                acc.patternSlug = o["patternSlugs"][a]
            # "override default themes": (isHome(accent) && name.equals("Dark Blue")) || name.equals("Night")
            if (acc.isDefault and self.name == "Dark Blue") or self.name == "Night":
                for k, v in tj["override_all"].items():
                    setattr(acc, k, v)
                if self.name == "Night":
                    for k, v in tj["override_night"].items():
                        setattr(acc, k, f32(v) if isinstance(v, float) else v)
            self.accents[acc.id] = acc
            self.accent_order.append(acc.id)
        self.accentBaseColor = self.accents[tj["accentBaseColor_id"]].accentColor
        self.default_accent_id = model.DEFAULT_ACCENT_ID if self.firstAccentIsDefault else tj["fresh_install_accent_id_non_default"]

    def stock_accent(self):
        return self.accents[self.default_accent_id]

    # ThemeInfo.isDefaultMyMessagesBubbles / isDefaultMyMessages / isDefaultMainAccent
    def _default_accent_pair(self, accent, current_id):
        if not self.firstAccentIsDefault:
            return None, None, False
        if current_id == self.model.DEFAULT_ACCENT_ID:
            return None, None, True
        return self.accents.get(self.model.DEFAULT_ACCENT_ID), accent, None

    def is_default_my_messages_bubbles(self, accent, current_id):
        d, a, short = self._default_accent_pair(accent, current_id)
        if short is not None:
            return short
        if d is None or a is None:
            return False
        return (d.myMessagesAccentColor == a.myMessagesAccentColor and d.myMessagesGradientAccentColor1 == a.myMessagesGradientAccentColor1
                and d.myMessagesGradientAccentColor2 == a.myMessagesGradientAccentColor2 and d.myMessagesGradientAccentColor3 == a.myMessagesGradientAccentColor3
                and d.myMessagesAnimated == a.myMessagesAnimated)

    def is_default_my_messages(self, accent, current_id):
        d, a, short = self._default_accent_pair(accent, current_id)
        if short is not None:
            return short
        if d is None or a is None:
            return False
        return (d.accentColor2 == a.accentColor2 and d.myMessagesAccentColor == a.myMessagesAccentColor
                and d.myMessagesGradientAccentColor1 == a.myMessagesGradientAccentColor1 and d.myMessagesGradientAccentColor2 == a.myMessagesGradientAccentColor2
                and d.myMessagesGradientAccentColor3 == a.myMessagesGradientAccentColor3 and d.myMessagesAnimated == a.myMessagesAnimated)

    def is_default_main_accent(self, accent, current_id):
        d, a, short = self._default_accent_pair(accent, current_id)
        if short is not None:
            return short
        return a is not None and d is not None and d.accentColor == a.accentColor


# ----------------------------------------------------------------------------------------
# ThemeAccent.fillAccentColors - literal port over full maps
# ----------------------------------------------------------------------------------------

class Palette:
    """The result of Theme.refreshThemeColors() for (theme, accent): the currentColors map plus the
    getColor() resolution rules that sit on top of it."""

    def __init__(self, theme, accent, current_id=None, colors=None, should_draw_gradient_icons=True):
        self.theme = theme
        self.model = theme.model
        self.accent = accent
        self.current_id = accent.id if current_id is None else current_id
        self.colors = colors
        self.should_draw_gradient_icons = should_draw_gradient_icons
        # Theme.serviceMessageColor / serviceSelectedMessageColor: computed from the wallpaper at
        # runtime (calcDrawableColor); 0 until a wallpaper is loaded.
        self.service_message_color = 0
        self.service_selected_message_color = 0

    def get(self, key):
        """Theme.getColor(key) (no animation, serviceBitmapShader handled separately)."""
        m, th, K = self.model, self.theme, self.model.K
        if isinstance(key, str):
            key = m.key(key)
        if th.name == "Blue":               # currentTheme == defaultTheme
            if m.bub_start <= key < m.bub_end:
                use_default = th.is_default_my_messages_bubbles(self.accent, self.current_id)
            elif m.my_start <= key < m.my_end:
                use_default = th.is_default_my_messages(self.accent, self.current_id)
            elif key in (K["key_chat_wallpaper"], K["key_chat_wallpaper_gradient_to1"], K["key_chat_wallpaper_gradient_to2"], K["key_chat_wallpaper_gradient_to3"]):
                use_default = False
            else:
                use_default = th.is_default_main_accent(self.accent, self.current_id)
            if use_default:
                if key == K["key_chat_serviceBackground"]:
                    return self.service_message_color
                if key == K["key_chat_serviceBackgroundSelected"]:
                    return self.service_selected_message_color
                return m.get_default_color(key)
        cur = self.colors
        if key not in cur:
            fb = m.fallback.get(key, -1)
            if fb != -1 and fb in cur:
                return cur[fb]
            if key == K["key_chat_serviceBackground"]:
                return self.service_message_color
            if key == K["key_chat_serviceBackgroundSelected"]:
                return self.service_selected_message_color
            return m.get_default_color(key)
        color = cur[key]
        if key in (K["key_windowBackgroundWhite"], K["key_windowBackgroundGray"], K["key_actionBarDefault"], K["key_actionBarDefaultArchived"]):
            color = s32(color | 0xFF000000)
        return color


def _force_out_block(m, acc):
    """canvas-fix (d): the black/white out-text block also runs for near-theme bubbles of runtime accents,
    whether the guard comes from the overlay spec or is already in the parsed Theme.java."""
    if acc.id <= 100:
        return False
    return m.src_out_block_custom or (m.hook is not None and m.hook.get("out_block_custom", False))


def fill_accent_colors(theme, acc, no_accent, cur, current_id=None):
    """Literal port of ThemeAccent.fillAccentColors(currentColorsNoAccent, currentColors).
    `cur` is mutated. Returns !isMyMessagesGradientColorsNear."""
    m = theme.model
    K = m.K
    defaults = m.defaults
    fallback = m.fallback
    is_near = False
    hsv1 = color_to_hsv(theme.accentBaseColor)
    hsv2 = color_to_hsv(acc.accentColor)
    is_dark = theme.is_dark
    if acc.accentColor != theme.accentBaseColor or acc.accentColor2 != 0:
        excl = m.exclusions
        for key in range(m.n):
            if key in excl:
                continue
            if key not in no_accent:
                fb = fallback.get(key, -1)
                if fb >= 0 and fb in no_accent:
                    continue
                color = defaults[key]
            else:
                color = no_accent[key]
            new = change_color_accent(hsv1, hsv2, color, is_dark, color)
            if new != color:
                cur[key] = new
    my_acc = acc.myMessagesAccentColor
    g1, g2, g3 = acc.myMessagesGradientAccentColor1, acc.myMessagesGradientAccentColor2, acc.myMessagesGradientAccentColor3
    if (acc.myMessagesAccentColor != 0 or acc.accentColor != 0) and g1 != 0:
        first = acc.myMessagesAccentColor if acc.myMessagesAccentColor != 0 else acc.accentColor
        color = no_accent.get(K["key_chat_outBubble"], 0)
        if color == 0:
            color = defaults[K["key_chat_outBubble"]]
        new = change_color_accent(hsv1, hsv2, color, is_dark, color)
        d1 = color_distance(first, new)
        d2 = color_distance(first, g1)
        if g2 != 0:
            avg = average_color(acc.myMessagesAccentColor, g1)
            avg = average_color(avg, g2)
            if g3 != 0:
                avg = average_color(avg, g3)
            ubt = perceived_brightness(avg) > F0_705
        else:
            ubt = use_black_text(acc.myMessagesAccentColor, g1)
        is_near = (d1 <= 35000 and d2 <= 35000) if ubt else False
        my_acc = get_accent_color(hsv1, color, first)
    change_my = (my_acc != 0 and ((theme.accentBaseColor != 0 and my_acc != theme.accentBaseColor) or (acc.accentColor != 0 and acc.accentColor != my_acc)))
    if change_my or acc.accentColor2 != 0:
        hsv2 = color_to_hsv(acc.accentColor2 if acc.accentColor2 != 0 else my_acc)
        for key in range(m.my_start, m.my_end):
            if key not in no_accent:
                fb = fallback.get(key, -1)
                if fb >= 0 and no_accent.get(fb, -1) >= 0:      # value test, as in Java
                    continue
                color = defaults[key]
            else:
                color = no_accent[key]
            new = change_color_accent(hsv1, hsv2, color, is_dark, color)
            if new != color:
                cur[key] = new
        for key in m.extra_keys:
            color = defaults[key] if key not in no_accent else no_accent[key]
            new = change_color_accent(hsv1, hsv2, color, is_dark, color)
            if new != color:
                cur[key] = new
        if change_my:
            hsv2 = color_to_hsv(my_acc)
            for key in range(m.bub_start, m.bub_end):
                if key not in no_accent:
                    fb = fallback.get(key, -1)
                    if fb >= 0 and no_accent.get(fb, -1) >= 0:
                        continue
                    color = defaults[key]
                else:
                    color = no_accent[key]
                new = change_color_accent(hsv1, hsv2, color, is_dark, color)
                if new != color:
                    cur[key] = new
    if not is_near or _force_out_block(m, acc):
        if g1 != 0:
            if g2 != 0:
                c = average_color(acc.myMessagesAccentColor, g1)
                c = average_color(c, g2)
                if g3 != 0:
                    c = average_color(c, g3)
                ubt = perceived_brightness(c) > F0_705
            else:
                ubt = use_black_text(acc.myMessagesAccentColor, g1)
            text, sub, seek = m.out_consts["black" if ubt else "white"]
            vals = {"textColor": text, "subTextColor": sub, "seekbarColor": seek,
                    "myMessagesAccentColor": acc.myMessagesAccentColor}
            if acc.accentColor2 == 0:
                for k, var in m.out_block_accent2_zero:
                    cur[k] = vals[var]
            for k, var in m.out_block_always:
                cur[k] = vals[var]
    if is_near:
        out_color = cur[K["key_chat_outLoader"]] if K["key_chat_outLoader"] in cur else 0
        if color_distance(s32(0xffffffff), out_color) < 5000:
            is_near = False
    if acc.myMessagesAccentColor != 0 and g1 != 0:
        cur[K["key_chat_outBubble"]] = acc.myMessagesAccentColor
        cur[K["key_chat_outBubbleGradient1"]] = g1
        if g2 != 0:
            cur[K["key_chat_outBubbleGradient2"]] = g2
            if g3 != 0:
                cur[K["key_chat_outBubbleGradient3"]] = g3
        cur[K["key_chat_outBubbleGradientAnimated"]] = 1 if acc.myMessagesAnimated else 0
    for fld, kname in (("backgroundOverrideColor", "key_chat_wallpaper"),
                       ("backgroundGradientOverrideColor1", "key_chat_wallpaper_gradient_to1"),
                       ("backgroundGradientOverrideColor2", "key_chat_wallpaper_gradient_to2"),
                       ("backgroundGradientOverrideColor3", "key_chat_wallpaper_gradient_to3")):
        lv = getattr(acc, fld)
        iv = long_to_int(lv)
        if iv != 0:
            cur[K[kname]] = iv
        elif lv != 0:
            cur.pop(K[kname], None)
    if acc.backgroundRotation != 45:
        cur[K["key_chat_wallpaper_gradient_rotation"]] = acc.backgroundRotation

    pal = Palette(theme, acc, current_id, cur)        # getColor() during fill reads the same map
    out_bubble = cur.get(K["key_chat_outBubble"], 0)
    if out_bubble == 0:
        out_bubble = pal.get(K["key_chat_outBubble"])
    in_bubble = cur.get(K["key_chat_inBubble"], 0)
    if in_bubble == 0:
        in_bubble = pal.get(K["key_chat_inBubble"])
    # (info != null && info.emoticon != null) branch: cloud chat themes only; generated accents have info == null.
    if not is_dark:
        cur[K["key_chat_inTextSelectionHighlight"]] = _text_selection_background(False, in_bubble, acc.accentColor)
        cur[K["key_chat_outTextSelectionHighlight"]] = _text_selection_background(True, out_bubble, acc.accentColor)
        cur[K["key_chat_outTextSelectionCursor"]] = _text_selection_handle(out_bubble, acc.accentColor)
    accent_hue = color_to_hsv(pal.get(K["key_windowBackgroundWhiteBlueText"]))[0]
    cur[K["key_chat_outBubbleLocationPlaceholder"]] = _location_placeholder(accent_hue, out_bubble, is_dark)
    cur[K["key_chat_inBubbleLocationPlaceholder"]] = _location_placeholder(accent_hue, in_bubble, is_dark)
    in_link = cur.get(K["key_chat_messageLinkIn"], 0)
    if in_link == 0:
        in_link = pal.get(K["key_chat_messageLinkIn"])
    out_link = cur.get(K["key_chat_messageLinkOut"], 0)
    if out_link == 0:
        out_link = pal.get(K["key_chat_messageLinkOut"])
    cur[K["key_chat_linkSelectBackground"]] = _link_selection_background(in_link, in_bubble, is_dark)
    cur[K["key_chat_outLinkSelectBackground"]] = _link_selection_background(out_link, out_bubble, is_dark)
    sb = cur.get(K["key_actionBarDefaultSubmenuBackground"], 0)
    if sb == 0:
        sb = pal.get(K["key_actionBarDefaultSubmenuBackground"])
    cur[K["key_actionBarDefaultSubmenuSeparator"]] = argb(alpha(sb), max(0, red(sb) - 10), max(0, green(sb) - 10), max(0, blue(sb) - 10))
    if is_dark and cur.get(K["key_chat_outBubbleGradient1"], 0) != 0:
        avg = _average_color_keys(cur, [K["key_chat_outBubbleGradient1"], K["key_chat_outBubbleGradient2"], K["key_chat_outBubbleGradient3"]])
        h, s, v = color_to_hsv(avg)
        s = utilities_clamp(f32(s + f32(0.1)), 1.0, 0.0)
        v = utilities_clamp(f32(v - f32(0.8)), 1.0, 0.0)
        cur[K["key_chat_outCodeBackground"]] = hsv_to_color(0x40, h, s, v)
    else:
        cur[K["key_chat_outCodeBackground"]] = _code_background(out_bubble, is_dark)
    apply_calculated_table_colors(m, no_accent, cur, is_dark)
    apply_calculated_article_code_colors(m, no_accent, cur, is_dark)
    return not is_near


def _text_selection_background(is_out, bubble, accent_color):
    h_acc = color_to_hsv(accent_color)[0]
    h, s, v = color_to_hsv(bubble)
    if s <= 0 or (h > 45 and h < 85):
        h = h_acc
    s = jmax(0.0, jmin(1.0, f32(s + (f32(0.25) if v > f32(0.85) else f32(0.45)))))
    v = jmax(0.0, jmin(1.0, f32(v - f32(0.15))))
    return hsv_to_color(80, h, s, v)


def _text_selection_handle(bubble, accent_color):
    h_acc = color_to_hsv(accent_color)[0]
    h, s, v = color_to_hsv(bubble)
    if s <= 0 or (h > 45 and h < 85):
        h = h_acc
    s = jmax(0.0, jmin(1.0, f32(s + F0_6)))
    v = jmax(0.0, jmin(1.0, f32(v - (f32(0.25) if v > f32(0.7) else f32(0.125)))))
    return blend_over(bubble, hsv_to_color(255, h, s, v))


def _link_selection_background(link, bg, is_dark):
    h, s, v = color_to_hsv(blend_argb(link, bg, f32(0.25)))
    s = jmax(0.0, jmin(1.0, f32(s - f32(0.1))))
    v = jmax(0.0, jmin(1.0, f32(v + (f32(0.1) if is_dark else 0.0))))
    return hsv_to_color(0x33, h, s, v)


def _code_background(bubble, is_dark):
    h, s, v = color_to_hsv(bubble)
    a = 0x20
    if is_dark:
        a = 0x40
        s = utilities_clamp(f32(s - f32(0.08)), 1.0, 0.0)
        v = f32(0.03)
    else:
        if s <= 0 or v >= 1 or v <= 0:
            v = jmax(0.0, jmin(1.0, f32(v + f32(-0.2))))
        else:
            s = jmax(0.0, jmin(1.0, f32(s + f32(0.28))))
            v = jmax(0.0, jmin(1.0, f32(v + f32(-0.1))))
    return hsv_to_color(a, h, s, v)


def _location_placeholder(accent_hue, bubble, is_dark):
    if is_dark:
        return s32(0x1effffff)
    h, s, v = color_to_hsv(bubble)
    if s <= 0 or v >= 1 or v <= 0:
        h = accent_hue
        s = f32(0.2)
    else:
        h = mathutils_clamp(f32(h + f32(0.22)), 0.0, 1.0)
        s = mathutils_clamp(f32(s - f32(0.35)), 0.0, 1.0)
    v = mathutils_clamp(f32(v - f32(0.65)), 0.0, 1.0)
    return hsv_to_color(0x5a, h, s, v)


def _average_color_keys(colors, keys):
    r = g = b = c = 0
    for k in keys:
        if k not in colors:
            continue
        col = colors[k]
        r += red(col)
        g += green(col)
        b += blue(col)
        c += 1
    if c == 0:
        return 0
    return argb(255, r // c, g // c, b // c)


def _calculated_table_background(bubble, is_dark, is_out):
    if is_dark and is_out:
        return mult_alpha(s32(0xFFFFFFFF), f32(0.07))
    h, s, v = color_to_hsv(bubble)
    if is_dark:
        v = jmin(1.0, f32(v + f32(0.07)))
        if is_out:
            s = jmin(1.0, f32(s + f32(0.02)))
    else:
        v = jmax(0.0, f32(v - (f32(0.06) if is_out else f32(0.03))))
        if is_out and s > f32(0.02):
            s = jmin(1.0, f32(s + f32(0.02)))
    return hsv_to_color(alpha(bubble), h, s, v)


def _calculated_table_border(bubble, is_dark, is_out):
    if is_dark and is_out:
        return mult_alpha(s32(0xFFFFFFFF), f32(0.14))
    h, s, v = color_to_hsv(bubble)
    if is_dark:
        v = jmin(1.0, f32(v + f32(0.14)))
        if is_out:
            s = jmin(1.0, f32(s + f32(0.03)))
    else:
        v = jmax(0.0, f32(v - (f32(0.14) if is_out else f32(0.12))))
        if is_out and s > f32(0.02):
            s = jmin(1.0, f32(s + f32(0.04)))
    return hsv_to_color(alpha(bubble), h, s, v)


def _table_out_bubble(m, colors):
    K = m.K
    r = g = b = n = 0
    for kname in ("key_chat_outBubble", "key_chat_outBubbleGradient1", "key_chat_outBubbleGradient2", "key_chat_outBubbleGradient3"):
        k = K[kname]
        if kname != "key_chat_outBubble" and k not in colors:
            continue
        c = colors.get(k, m.defaults[k])
        r += red(c)
        g += green(c)
        b += blue(c)
        n += 1
    return argb(255, r // n, g // n, b // n)


def apply_calculated_table_colors(m, src, colors, is_dark):
    K = m.K
    in_b = colors.get(K["key_chat_inBubble"], m.defaults[K["key_chat_inBubble"]])
    out_b = _table_out_bubble(m, colors)
    if K["key_chat_inTableBackground"] not in src:
        colors[K["key_chat_inTableBackground"]] = _calculated_table_background(in_b, is_dark, False)
    if K["key_chat_outTableBackground"] not in src:
        colors[K["key_chat_outTableBackground"]] = _calculated_table_background(out_b, is_dark, True)
    if K["key_chat_inTableBorder"] not in src:
        colors[K["key_chat_inTableBorder"]] = _calculated_table_border(in_b, is_dark, False)
    if K["key_chat_outTableBorder"] not in src:
        colors[K["key_chat_outTableBorder"]] = _calculated_table_border(out_b, is_dark, True)
    if K["key_chat_outDivider"] not in src:
        rl = colors.get(K["key_chat_outReplyLine"], m.defaults[K["key_chat_outReplyLine"]])
        colors[K["key_chat_outDivider"]] = mult_alpha(rl, f32(0.2))
    if is_dark and K["key_chat_inDivider"] not in src:
        rt = colors.get(K["key_chat_inReplyMessageText"], m.defaults[K["key_chat_inReplyMessageText"]])
        colors[K["key_chat_inDivider"]] = mult_alpha(rt, f32(0.2))


def _article_details(bubble, is_dark, is_out, arrow):
    if is_dark:
        return mult_alpha(s32(0xFFFFFFFF), f32(0.62) if arrow else f32(0.18))
    base = s32(0xff9ea4a8) if arrow else s32(0xffd8d8d8)
    s = color_to_hsv(bubble)[1]
    return adapt_hue(base, bubble) if (is_out and s > f32(0.02)) else base


def _article_scrollbar(bubble, is_dark, thumb):
    if is_dark:
        return mult_alpha(s32(0xFFFFFFFF), f32(0.22) if thumb else f32(0.12))
    base = s32(0xffc5cdd5) if thumb else s32(0xffe1e6eb)
    s = color_to_hsv(bubble)[1]
    return adapt_hue(base, bubble) if s > f32(0.02) else base


def apply_calculated_article_code_colors(m, src, colors, is_dark):
    K = m.K
    if is_dark and K["key_chat_inArticleCodeBackground"] not in src:
        colors[K["key_chat_inArticleCodeBackground"]] = mult_alpha(s32(0xFFFFFFFF), f32(0.10))
    in_b = colors.get(K["key_chat_inBubble"], m.defaults[K["key_chat_inBubble"]])
    out_b = _table_out_bubble(m, colors)
    for kname, bub, thumb in (("key_chat_inArticleCodeScrollbarBackground", in_b, False), ("key_chat_inArticleCodeScrollbar", in_b, True),
                              ("key_chat_outArticleCodeScrollbarBackground", out_b, False), ("key_chat_outArticleCodeScrollbar", out_b, True)):
        if K[kname] not in src:
            colors[K[kname]] = _article_scrollbar(bub, is_dark, thumb)
    for kname, bub, is_out, arrow in (("key_chat_inArticleDetailsArrow", in_b, False, True), ("key_chat_outArticleDetailsArrow", out_b, True, True),
                                      ("key_chat_inArticleDetailsLine", in_b, False, False), ("key_chat_outArticleDetailsLine", out_b, True, False)):
        if K[kname] not in src:
            colors[K[kname]] = _article_details(bub, is_dark, is_out, arrow)


def refresh_theme_colors(theme, accent, current_id=None):
    """Theme.refreshThemeColors(): currentColors = currentColorsNoAccent.clone(); accent.fillAccentColors(...);
    applyCalculatedTableColors(...); applyCalculatedArticleCodeColors(...)."""
    no_accent = theme.no_accent
    cur = dict(no_accent)
    sdgi = fill_accent_colors(theme, accent, no_accent, cur, current_id)
    apply_calculated_table_colors(theme.model, no_accent, cur, theme.is_dark)
    apply_calculated_article_code_colors(theme.model, no_accent, cur, theme.is_dark)
    if theme.model.hook is not None:
        apply_on_accent_hook(theme, accent, current_id, cur)
    return Palette(theme, accent, current_id, cur, sdgi)


# ----------------------------------------------------------------------------------------
# canvas-fix: on-accent content rule (the code hook at the end of refreshThemeColors)
# ----------------------------------------------------------------------------------------

def wcag_luminance(c):
    L = _SRGB8_TO_LINEAR
    return 0.2126 * L[(c >> 16) & 0xFF] + 0.7152 * L[(c >> 8) & 0xFF] + 0.0722 * L[c & 0xFF]


def wcag_contrast(c1, c2):
    l1, l2 = wcag_luminance(c1), wcag_luminance(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def src_over_rgb(fg, bg):
    """8-bit src-over of ARGB fg on opaque bg, (a*x + (255-a)*y + 127) / 255 per channel (integer)."""
    a = (fg >> 24) & 0xFF
    if a == 255:
        return fg & 0xFFFFFF
    ia = 255 - a
    r = (((fg >> 16) & 0xFF) * a + ((bg >> 16) & 0xFF) * ia + 127) // 255
    g = (((fg >> 8) & 0xFF) * a + ((bg >> 8) & 0xFF) * ia + 127) // 255
    b = ((fg & 0xFF) * a + (bg & 0xFF) * ia + 127) // 255
    return (r << 16) | (g << 8) | b


def on_accent_color(fill, page, near_black):
    """White or near-black, whichever has the higher WCAG contrast with the (composited) fill; ties -> white."""
    f = src_over_rgb(fill, page)
    return s32(0xFFFFFFFF) if wcag_contrast(0xFFFFFF, f) >= wcag_contrast(near_black & 0xFFFFFF, f) else near_black


def apply_on_accent_hook(theme, accent, current_id, cur):
    m = theme.model
    hk = m.hook
    K = m.K
    pal = Palette(theme, accent, current_id, cur)          # getColor() on the refreshed map
    page = pal.get(K["key_windowBackgroundWhite"])
    for content, fill in hk["pairs"]:
        cur[content] = on_accent_color(pal.get(fill), page, hk["near_black"])
    if hk["muted"] < 0:
        return
    text = cur[hk["muted_text"]]
    for dep in hk["muted_pins"]:                         # keys that fall back to chats_unreadCounterMuted keep their colour
        if dep not in cur:
            cur[dep] = pal.get(dep)
    w, b = hk["muted_table"][theme.name]
    cur[hk["muted"]] = w if text == s32(0xFFFFFFFF) else b


_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = Model(tgsrc.load())
    return _MODEL


_OVERLAY_MODELS = {}


def overlay_model(spec):
    """Model with a canvas-fix overlay applied (cached by spec tag)."""
    m = _OVERLAY_MODELS.get(spec["tag"])
    if m is None:
        m = Model(tgsrc.load(), spec)
        _OVERLAY_MODELS[spec["tag"]] = m
    return m


# ----------------------------------------------------------------------------------------
# Lazy evaluation of the same refresh (only the keys that are asked for)
# ----------------------------------------------------------------------------------------

POST_KEY_NAMES = [
    "key_chat_inTextSelectionHighlight", "key_chat_outTextSelectionHighlight", "key_chat_outTextSelectionCursor",
    "key_chat_outBubbleLocationPlaceholder", "key_chat_inBubbleLocationPlaceholder", "key_chat_linkSelectBackground",
    "key_chat_outLinkSelectBackground", "key_actionBarDefaultSubmenuSeparator", "key_chat_outCodeBackground",
    "key_chat_inTableBackground", "key_chat_outTableBackground", "key_chat_inTableBorder", "key_chat_outTableBorder",
    "key_chat_outDivider", "key_chat_inDivider", "key_chat_inArticleCodeBackground", "key_chat_inArticleCodeScrollbarBackground",
    "key_chat_inArticleCodeScrollbar", "key_chat_outArticleCodeScrollbarBackground", "key_chat_outArticleCodeScrollbar",
    "key_chat_inArticleDetailsArrow", "key_chat_outArticleDetailsArrow", "key_chat_inArticleDetailsLine",
    "key_chat_outArticleDetailsLine", "key_chat_selectedBackground", "key_chat_outBubbleSelectedOverlay",
    "key_chat_outBubbleGradientSelectedOverlay", "key_chat_outBubbleSelected", "key_chat_inBubbleSelectedOverlay",
    "key_chat_inBubbleSelected",
]


class LazyPalette(Palette):
    """Same result as refresh_theme_colors(theme, accent).get(key) for every key, but each key's
    value is computed on demand by replaying, for that key only, the writes fillAccentColors()
    performs in order.  Keys written by the post-processing tail fall back to the full port."""

    def __init__(self, theme, acc, current_id=None):
        super().__init__(theme, acc, current_id, None)
        m = theme.model
        K = m.K
        self._memo = {}
        self._memo_hook = {}
        self._full = None
        self._post = set(K[k] for k in POST_KEY_NAMES)
        self.hsv1 = color_to_hsv(theme.accentBaseColor)
        self.hsv2 = color_to_hsv(acc.accentColor)
        self.main_on = acc.accentColor != theme.accentBaseColor or acc.accentColor2 != 0
        my_acc = acc.myMessagesAccentColor
        g1, g2, g3 = acc.myMessagesGradientAccentColor1, acc.myMessagesGradientAccentColor2, acc.myMessagesGradientAccentColor3
        is_near = False
        no_accent = theme.no_accent
        if (acc.myMessagesAccentColor != 0 or acc.accentColor != 0) and g1 != 0:
            first = acc.myMessagesAccentColor if acc.myMessagesAccentColor != 0 else acc.accentColor
            color = no_accent.get(K["key_chat_outBubble"], 0)
            if color == 0:
                color = m.defaults[K["key_chat_outBubble"]]
            new = change_color_accent(self.hsv1, self.hsv2, color, theme.is_dark, color)
            d1 = color_distance(first, new)
            d2 = color_distance(first, g1)
            if g2 != 0:
                avg = average_color(acc.myMessagesAccentColor, g1)
                avg = average_color(avg, g2)
                if g3 != 0:
                    avg = average_color(avg, g3)
                ubt = perceived_brightness(avg) > F0_705
            else:
                ubt = use_black_text(acc.myMessagesAccentColor, g1)
            is_near = (d1 <= 35000 and d2 <= 35000) if ubt else False
            my_acc = get_accent_color(self.hsv1, color, first)
        self.my_acc = my_acc
        self.is_near = is_near
        self.change_my = (my_acc != 0 and ((theme.accentBaseColor != 0 and my_acc != theme.accentBaseColor) or (acc.accentColor != 0 and acc.accentColor != my_acc)))
        self.my_loop_on = self.change_my or acc.accentColor2 != 0
        self.hsv_my = color_to_hsv(acc.accentColor2 if acc.accentColor2 != 0 else my_acc) if self.my_loop_on else None
        self.hsv_bub = color_to_hsv(my_acc) if self.change_my else None
        self.out_vals = None
        if (not is_near or _force_out_block(m, acc)) and g1 != 0:
            if g2 != 0:
                c = average_color(acc.myMessagesAccentColor, g1)
                c = average_color(c, g2)
                if g3 != 0:
                    c = average_color(c, g3)
                ubt = perceived_brightness(c) > F0_705
            else:
                ubt = use_black_text(acc.myMessagesAccentColor, g1)
            text, sub, seek = m.out_consts["black" if ubt else "white"]
            self.use_black_text_out = ubt
            vals = {"textColor": text, "subTextColor": sub, "seekbarColor": seek, "myMessagesAccentColor": acc.myMessagesAccentColor}
            ov = {}
            if acc.accentColor2 == 0:
                for k, var in m.out_block_accent2_zero:
                    ov[k] = vals[var]
            for k, var in m.out_block_always:
                ov[k] = vals[var]
            self.out_vals = ov
        else:
            self.use_black_text_out = None
        bub = {}
        if acc.myMessagesAccentColor != 0 and g1 != 0:
            bub[K["key_chat_outBubble"]] = acc.myMessagesAccentColor
            bub[K["key_chat_outBubbleGradient1"]] = g1
            if g2 != 0:
                bub[K["key_chat_outBubbleGradient2"]] = g2
                if g3 != 0:
                    bub[K["key_chat_outBubbleGradient3"]] = g3
            bub[K["key_chat_outBubbleGradientAnimated"]] = 1 if acc.myMessagesAnimated else 0
        self.bub_puts = bub
        wp = {}
        for fld, kname in (("backgroundOverrideColor", "key_chat_wallpaper"),
                           ("backgroundGradientOverrideColor1", "key_chat_wallpaper_gradient_to1"),
                           ("backgroundGradientOverrideColor2", "key_chat_wallpaper_gradient_to2"),
                           ("backgroundGradientOverrideColor3", "key_chat_wallpaper_gradient_to3")):
            lv = getattr(acc, fld)
            iv = long_to_int(lv)
            if iv != 0:
                wp[K[kname]] = ("put", iv)
            elif lv != 0:
                wp[K[kname]] = ("delete", None)
        if acc.backgroundRotation != 45:
            wp[K["key_chat_wallpaper_gradient_rotation"]] = ("put", acc.backgroundRotation)
        self.wp_ops = wp

    def full(self):
        if self._full is None:
            self._full = refresh_theme_colors(self.theme, self.accent, self.current_id)
        return self._full

    def cur_entry(self, key):
        """(present, value) of `key` in currentColors after refreshThemeColors() (incl. the canvas-fix hook)."""
        hk = self.model.hook
        if hk is None:
            return self._base_entry(key)
        r = self._memo_hook.get(key)
        if r is not None:
            return r
        if key in hk["content"]:
            page = self.get(self.model.K["key_windowBackgroundWhite"])
            r = (True, on_accent_color(self.get(hk["content"][key]), page, hk["near_black"]))
        elif key == hk["muted"]:
            text = self.cur_entry(hk["muted_text"])[1]
            w, b = hk["muted_table"][self.theme.name]
            r = (True, w if text == s32(0xFFFFFFFF) else b)
        elif key in hk["muted_pins"]:
            r = self._base_entry(key)
            if not r[0]:
                r = (True, self._get_with(self._base_entry, key))
        else:
            r = self._base_entry(key)
        self._memo_hook[key] = r
        return r

    def _base_entry(self, key):
        """(present, value) of `key` after fillAccentColors + calculated colours (before the hook)."""
        r = self._memo.get(key)
        if r is not None:
            return r
        if key in self._post:
            full = self.full().colors
            r = (key in full, full.get(key, 0))
            self._memo[key] = r
            return r
        th, m, acc = self.theme, self.model, self.accent
        no_accent = th.no_accent
        present = key in no_accent
        val = no_accent.get(key, 0)
        is_dark = th.is_dark
        if self.main_on and key not in m.exclusions:
            skip = False
            if key not in no_accent:
                fb = m.fallback.get(key, -1)
                if fb >= 0 and fb in no_accent:
                    skip = True
                color = m.defaults[key]
            else:
                color = no_accent[key]
            if not skip:
                new = change_color_accent(self.hsv1, self.hsv2, color, is_dark, color)
                if new != color:
                    present, val = True, new
        if self.my_loop_on:
            if m.my_start <= key < m.my_end:
                skip = False
                if key not in no_accent:
                    fb = m.fallback.get(key, -1)
                    if fb >= 0 and no_accent.get(fb, -1) >= 0:
                        skip = True
                    color = m.defaults[key]
                else:
                    color = no_accent[key]
                if not skip:
                    new = change_color_accent(self.hsv1, self.hsv_my, color, is_dark, color)
                    if new != color:
                        present, val = True, new
            if key in m.extra_keys:
                color = m.defaults[key] if key not in no_accent else no_accent[key]
                new = change_color_accent(self.hsv1, self.hsv_my, color, is_dark, color)
                if new != color:
                    present, val = True, new
            if self.change_my and m.bub_start <= key < m.bub_end:
                skip = False
                if key not in no_accent:
                    fb = m.fallback.get(key, -1)
                    if fb >= 0 and no_accent.get(fb, -1) >= 0:
                        skip = True
                    color = m.defaults[key]
                else:
                    color = no_accent[key]
                if not skip:
                    new = change_color_accent(self.hsv1, self.hsv_bub, color, is_dark, color)
                    if new != color:
                        present, val = True, new
        if self.out_vals is not None and key in self.out_vals:
            present, val = True, self.out_vals[key]
        if key in self.bub_puts:
            present, val = True, self.bub_puts[key]
        op = self.wp_ops.get(key)
        if op is not None:
            if op[0] == "put":
                present, val = True, op[1]
            else:
                present, val = False, 0
        r = (present, val)
        self._memo[key] = r
        return r

    def get(self, key):
        return self._get_with(self.cur_entry, key)

    def _get_with(self, entry, key):
        m, th, K = self.model, self.theme, self.model.K
        if isinstance(key, str):
            key = m.key(key)
        if th.name == "Blue":
            if m.bub_start <= key < m.bub_end:
                use_default = th.is_default_my_messages_bubbles(self.accent, self.current_id)
            elif m.my_start <= key < m.my_end:
                use_default = th.is_default_my_messages(self.accent, self.current_id)
            elif key in (K["key_chat_wallpaper"], K["key_chat_wallpaper_gradient_to1"], K["key_chat_wallpaper_gradient_to2"], K["key_chat_wallpaper_gradient_to3"]):
                use_default = False
            else:
                use_default = th.is_default_main_accent(self.accent, self.current_id)
            if use_default:
                if key == K["key_chat_serviceBackground"]:
                    return self.service_message_color
                if key == K["key_chat_serviceBackgroundSelected"]:
                    return self.service_selected_message_color
                return m.get_default_color(key)
        present, val = entry(key)
        if not present:
            fb = m.fallback.get(key, -1)
            if fb != -1:
                fp, fv = entry(fb)
                if fp:
                    return fv
            if key == K["key_chat_serviceBackground"]:
                return self.service_message_color
            if key == K["key_chat_serviceBackgroundSelected"]:
                return self.service_selected_message_color
            return m.get_default_color(key)
        if key in (K["key_windowBackgroundWhite"], K["key_windowBackgroundGray"], K["key_actionBarDefault"], K["key_actionBarDefaultArchived"]):
            val = s32(val | 0xFF000000)
        return val

    def raw(self, key):
        """currentColors.get(key) (0 when absent) -- what the wallpaper code reads."""
        if isinstance(key, str):
            key = self.model.key(key)
        p, v = self.cur_entry(key)
        return v if p else 0


def _palette_raw(self, key):
    if isinstance(key, str):
        key = self.model.key(key)
    return self.colors.get(key, 0)


Palette.raw = _palette_raw


def palette(theme, accent, current_id=None, lazy=True):
    if lazy:
        return LazyPalette(theme, accent, current_id)
    return refresh_theme_colors(theme, accent, current_id)
