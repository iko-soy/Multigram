"""Deterministic, portable math for the style generator (see detmath_tables.py for the tables).

Every function here uses only IEEE-754 double +, -, *, /, sqrt, floor and comparisons, in a fixed
order, so Java (double, no FMA contraction by the language), JavaScript (Number) and Python (float)
produce bit-identical results.
"""
import math

from detmath_tables import LINEAR_MIDPOINTS, SRGB8_TO_LINEAR

PI = 3.141592653589793
DEG2RAD = PI / 180.0
# 1/n! as exact decimal literals rounded to double (same literal in every language)
_INV_FACT = {3: 0.16666666666666666, 5: 0.008333333333333333, 7: 0.0001984126984126984, 9: 2.7557319223985893e-06,
             11: 2.505210838544172e-08, 13: 1.6059043836821613e-10, 15: 7.647163731819816e-13, 17: 2.8114572543455206e-15,
             2: 0.5, 4: 0.041666666666666664, 6: 0.001388888888888889, 8: 2.48015873015873e-05, 10: 2.755731922398589e-07,
             12: 2.08767569878681e-09, 14: 1.1470745597729725e-11, 16: 4.779477332387385e-14, 18: 1.5619206968586225e-16}


def _sin_poly(x):
    x2 = x * x
    p = _INV_FACT[17]
    for n in (15, 13, 11, 9, 7, 5, 3):
        p = _INV_FACT[n] - x2 * p
    # p = 1/3! - x^2/5! + ...  ->  sin = x - x^3 * p
    return x - x * x2 * p


def _cos_poly(x):
    x2 = x * x
    p = _INV_FACT[18]
    for n in (16, 14, 12, 10, 8, 6, 4, 2):
        p = _INV_FACT[n] - x2 * p
    return 1.0 - x2 * p


def sin_cos_deg(deg):
    """(sin, cos) of an angle in degrees; |error| < 1e-15 on [0, 360)."""
    d = deg - 360.0 * math.floor(deg / 360.0)
    k = math.floor((d + 45.0) / 90.0)
    r = (d - 90.0 * k) * DEG2RAD          # r in [-pi/4, pi/4)
    s = _sin_poly(r)
    c = _cos_poly(r)
    q = int(k) % 4
    if q == 0:
        return s, c
    if q == 1:
        return c, -s
    if q == 2:
        return -s, -c
    return -c, s


def cbrt(x):
    """Cube root by 64 fixed Newton steps (analysis only; the generator never needs it)."""
    if x == 0.0:
        return 0.0
    neg = x < 0
    if neg:
        x = -x
    y = 1.0 if x < 1.0 else x
    for _ in range(64):
        y = (2.0 * y + x / (y * y)) / 3.0
    return -y if neg else y


def linear_to_srgb8(v):
    """Nearest 8-bit sRGB code of a linear-light value (rounding in the gamma-encoded domain),
    by binary search over the literal midpoint table."""
    if not v > LINEAR_MIDPOINTS[0]:
        return 0
    lo, hi = 0, 254                       # answer = number of midpoints strictly below v
    if v > LINEAR_MIDPOINTS[254]:
        return 255
    while lo < hi:
        mid = (lo + hi) // 2
        if LINEAR_MIDPOINTS[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo


# ---- colour science (Oklab by Bjorn Ottosson, matrices as published) ----------------------

def oklab_to_linear_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l = l_ * l_ * l_
    m = m_ * m_ * m_
    s = s_ * s_ * s_
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return r, g, bl


def linear_srgb_to_oklab(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = cbrt(l), cbrt(m), cbrt(s)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


GAMUT_EPS = 1e-9


def oklch_to_rgb8(L, C, h_deg, gamut_steps=24):
    """OKLCH -> 8-bit sRGB.  Out-of-gamut colours keep L and h and get the largest chroma
    (bisection, fixed step count) that fits in the sRGB cube.  Returns (r, g, b, C_used)."""
    sn, cs = sin_cos_deg(h_deg)

    def in_gamut(c):
        r, g, b = oklab_to_linear_srgb(L, c * cs, c * sn)
        return (r >= -GAMUT_EPS and r <= 1.0 + GAMUT_EPS and g >= -GAMUT_EPS and g <= 1.0 + GAMUT_EPS
                and b >= -GAMUT_EPS and b <= 1.0 + GAMUT_EPS), (r, g, b)

    ok, rgb = in_gamut(C)
    c_used = C
    if not ok:
        lo, hi = 0.0, C
        for _ in range(gamut_steps):
            mid = (lo + hi) * 0.5
            if in_gamut(mid)[0]:
                lo = mid
            else:
                hi = mid
        c_used = lo
        rgb = in_gamut(lo)[1]
    r, g, b = rgb
    return linear_to_srgb8(r), linear_to_srgb8(g), linear_to_srgb8(b), c_used


def rgb8_to_oklch(r, g, b):
    L, a, bb = linear_srgb_to_oklab(SRGB8_TO_LINEAR[r], SRGB8_TO_LINEAR[g], SRGB8_TO_LINEAR[b])
    C = math.sqrt(a * a + bb * bb)
    h = math.degrees(math.atan2(bb, a)) % 360.0     # analysis only
    return L, C, h


# ---- WCAG 2.2 relative luminance / contrast ------------------------------------------------

def luminance(c):
    return (0.2126 * SRGB8_TO_LINEAR[(c >> 16) & 0xFF] + 0.7152 * SRGB8_TO_LINEAR[(c >> 8) & 0xFF]
            + 0.0722 * SRGB8_TO_LINEAR[c & 0xFF])


def contrast(c1, c2):
    l1 = luminance(c1)
    l2 = luminance(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)
