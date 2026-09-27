#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build-time rebrand for MultiGram (Forkgram plus the MultiGram stack, GPLv2).

One command gives a build its own identity:

  - a unique applicationId                   -> rebrand.properties, read by rebrand.gradle
  - its own app name (AppName, AppNameBeta,  -> resource overlay (launcher label) and the
    AppNameFdroid)                              bundled in-app strings
  - its own adaptive launcher icon, the      -> resource overlay (vector layers + PNGs)
    splash-screen icon and the notification
    icon
  - a fresh signing key                      -> keytool; path and credentials in the properties
  - a matching Android account type          -> patched in place in three source files

The identity (applicationId, name, icon, account type) is deterministic per --seed; the
signing key and its passwords are not. Everything goes under multigram/rebrand/generated/
and multigram/rebrand/rebrand.properties (both git-ignored); the three account-type files
are edited in place with backups, and --clean restores them byte for byte.

This is white-label rebranding of your own build of open-source software. The generated
names and ids come from neutral word lists. Values you pass yourself are only checked
against a short blocklist (Telegram's name and namespace, Forkgram's names, some well-known
apps' names and packages), so choosing ones that belong to you is up to you.

Standard library only; keytool (from any JDK) is needed for the signing key.
"""

import argparse
import colorsys
import hashlib
import json
import math
import os
import random
import re
import secrets
import shlex
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent            # multigram/rebrand
REPO = HERE.parent.parent
GEN = HERE / "generated"
GEN_RES = GEN / "res"
BACKUP = GEN / "backup"
BACKUP_INDEX = BACKUP / "index.json"
PROPS = HERE / "rebrand.properties"
DEFAULT_KEYSTORE = GEN / "rebrand.keystore"

APP_MODULE = REPO / "TMessagesProj_App"
LIB_MODULE = REPO / "TMessagesProj"
# Resource roots whose icons and app names the overlay must beat (every source set of the
# two modules in settings.gradle, e.g. TMessagesProj_App/src/forkTest/res).
RES_ROOT_GLOBS = ["TMessagesProj/src/*/res", "TMessagesProj_App/src/*/res"]
# Manifests that can supply the application label and icon (checked, never edited).
MANIFESTS = ["TMessagesProj/src/main/AndroidManifest.xml",
             "TMessagesProj_App/src/main/AndroidManifest.xml"]
CONFIG_MANIFEST_GLOB = "TMessagesProj/config/*/AndroidManifest*.xml"

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"

# The three app-name strings. Non-F-Droid release builds take their launcher label from
# config/debug/AndroidManifest_SDK23.xml (@string/AppNameBeta), F-Droid builds from
# config/release/AndroidManifest_SDK23.xml (@string/AppName); AppNameFdroid feeds the
# unused appLabel placeholder in TMessagesProj/build.gradle. All three get the new name.
APP_NAME_STRINGS = ("AppName", "AppNameBeta", "AppNameFdroid")

# Icon resources the overlay replaces, and how each one is drawn.
#   square / round : a launcher icon (adaptive XML in anydpi-v26, legacy PNG per density)
#   fg_layer       : a foreground layer PNG (108dp canvas), as used by the in-app icon picker
#   bg_layer       : a background layer PNG (108dp canvas), as used by the in-app icon picker
#   splash         : the Android 12+ splash-screen icon (a 320dp vector)
#   notif          : a status-bar notification icon (white on transparent PNG)
ICON_TARGETS = {
    ("mipmap", "ic_launcher"): "square",                # application icon, share targets
    ("mipmap", "ic_launcher_round"): "round",
    ("mipmap", "icon_01_launcher"): "square",           # DefaultIcon launcher alias
    ("mipmap", "icon_01_launcher_round"): "round",
    ("mipmap", "icon_01_launcher_adaptive"): "square",  # AdaptiveIcon launcher alias
    ("mipmap", "icon_01_launcher_sa"): "square",
    ("mipmap", "icon_01_foreground_sa"): "fg_layer",    # icon picker preview, Default/Adaptive
    ("drawable", "icon_01_background_sa"): "bg_layer",
    ("drawable", "ic_launcher_dr"): "round",            # account, contacts and call icon
    ("drawable", "splash_fork_320"): "splash",          # splash screen (values-v31 styles)
    ("drawable", "tg_splash_320"): "splash",            # splash screen, dark mode (values-night)
    ("drawable", "notification"): "notif",              # notification small icon
}
# Theme attribute whose drawable must be in ICON_TARGETS (checked, never edited).
SPLASH_ATTR = "android:windowSplashScreenAnimatedIcon"

# --- account type ---------------------------------------------------------------------
# Android's AccountManager keys the contact-sync account on one string that must be the
# same in the authenticator XML, the sync-adapter XML and the Java code. In this tree the
# XML says android:accountType="${applicationId}" (AGP does not expand placeholders in
# resource files, so that literal text is what ships) while ContactsController.java uses
# "org.telegram.messenger". A rebranded build sets all three to one value derived from its
# own applicationId. A Java literal cannot be overlaid, so these files are patched in place.
STOCK_JAVA_ACCOUNT_TYPE = "org.telegram.messenger"
JAVA_EXPECTED_LITERALS = 5
CONTACTS_JAVA = LIB_MODULE / "src/main/java/org/telegram/messenger/ContactsController.java"
ACCOUNT_XMLS = [LIB_MODULE / "src/main/res/xml/auth.xml",
                LIB_MODULE / "src/main/res/xml/sync_contacts.xml"]
ACCOUNT_XML_ATTR = re.compile(rb'android:accountType="[^"]*"')
STOCK_XML_ACCOUNT_TYPE = b"${applicationId}"
# Written into each patched file, so a patched tree is recognisable without generated/:
# rebrand.gradle refuses to build it as the stock identity, and --clean refuses to call it
# clean. rebrand.gradle looks for the same text.
PATCH_MARKER = "MultiGram rebrand: patched by multigram/rebrand/generate_rebrand.py"

# --- neutral word pools ---------------------------------------------------------------
# Plain nature and colour words. Words that are the names of well-known apps or brands
# (messengers above all) are deliberately left out, and generated names are checked
# against BLOCKED_NAME_PARTS as well.
ADJ = ["amber", "cobalt", "quiet", "north", "violet", "cedar", "ivory", "coral", "slate",
       "marble", "willow", "lunar", "misty", "velvet", "golden", "silver", "crimson",
       "azure", "maple", "rustic", "gentle", "bright", "calm", "clear", "hidden", "mellow",
       "olive", "sandy", "tidal", "copper", "frosty", "hazel", "indigo", "jade", "linen",
       "mossy", "pale", "rosy", "sunlit", "wild"]
NOUN = ["harbor", "meadow", "canyon", "cove", "ridge", "birch", "fern", "heron", "brook",
        "grove", "dune", "isle", "lagoon", "valley", "thistle", "kestrel", "orchard", "tern",
        "wren", "hollow", "bay", "pine", "cliff", "creek", "marsh", "aspen", "bluff",
        "cairn", "fjord", "heath", "inlet", "knoll", "ledge", "moor", "oak", "pond", "rill",
        "shoal", "spruce", "stream"]
TLDS = ["com", "net", "io", "app", "me", "co", "org", "dev"]
SEGS = ["app", "chat", "mobile", "client", "talk", "messages", "android", "im"]
# Refused in any name, package or account type: Telegram's name (its API terms forbid it
# for third-party apps), Forkgram's own names (a rebrand must not pass for the upstream
# build) and the names of some other well-known apps. This is a short blocklist, not a
# guarantee: a name or id you pass yourself must be one that belongs to you.
BLOCKED_NAME_PARTS = ["telegram", "forkgram", "fork client", "forkclient", "whatsapp",
                      "signal", "viber", "threema", "wechat", "kakaotalk", "facebook",
                      "instagram", "snapchat", "discord", "skype", "imessage"]
# Refused as the start of an applicationId or account type: the namespaces of the platform
# and of some well-known vendors and messengers.
BLOCKED_PACKAGE_PREFIXES = ["android.", "com.android.", "com.google.", "com.samsung.",
                            "com.apple.", "com.microsoft.", "com.facebook.", "com.instagram.",
                            "com.whatsapp.", "com.skype.", "com.snapchat.", "com.discord.",
                            "com.viber.", "com.tencent.", "com.kakao.", "jp.naver.line.",
                            "org.thoughtcrime.", "org.thunderdog.", "ch.threema.",
                            "im.vector.", "org.telegram."]
PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")
JAVA_KEYWORDS = set("""abstract assert boolean break byte case catch char class const continue
default do double else enum extends final finally float for goto if implements import
instanceof int interface long native new package private protected public return short static
strictfp super switch synchronized this throw throws transient try void volatile while true
false null""".split())

# Plain geometric marks. Rings and crosses are left out: on some hues they look like
# well-known logos and emblems.
SHAPES = ["disc", "square", "diamond", "triangle", "pentagon", "hexagon"]


class RebrandError(Exception):
    pass


def rel(p):
    try:
        return Path(p).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


# --- identity -------------------------------------------------------------------------
def rng_from_seed(seed):
    return random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16))


def contrast(c1, c2):
    def lum(c):
        def ch(v):
            v /= 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])
    a, b = sorted((lum(c1), lum(c2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def hsv(h, s, v):
    return tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(h % 1.0, s, v))


def gen_identity(r):
    """Draw every random value in a fixed order, so an override (e.g. --app-name) never
    shifts the others: the same seed always gives the same icon, name and id."""
    ident = {}
    # applicationId: <tld>.<adjective><noun>.<segment>, e.g. net.quietcove.chat
    ident["application_id"] = "%s.%s%s.%s" % (r.choice(TLDS), r.choice(ADJ), r.choice(NOUN),
                                              r.choice(SEGS))
    # app name: short enough for a launcher label
    for _ in range(50):
        style = r.random()
        adj, noun = r.choice(ADJ).capitalize(), r.choice(NOUN).capitalize()
        if style < 0.6:
            name = "%s %s" % (adj, noun)
        elif style < 0.8:
            name = "%s Chat" % noun
        else:
            name = "%s%s" % (adj, noun.lower())
        if len(name) <= 13:
            break
    ident["app_name"] = name
    # icon colours: a saturated background and a light mark with at least 3:1 contrast
    hue = r.random()
    sat = r.uniform(0.50, 0.85)
    val = r.uniform(0.50, 0.85)
    light_mark = r.random() < 0.7
    shape = r.choice(SHAPES)
    fg = (255, 255, 255) if light_mark else hsv(hue + 0.5, 0.18, 0.98)
    bg = hsv(hue, sat, val)
    while contrast(bg, fg) < 3.0 and val > 0.2:
        val -= 0.03
        bg = hsv(hue, sat, val)
    ident["bg"], ident["fg"], ident["shape"] = bg, fg, shape
    return ident


def hexc(rgb):
    return "#%02X%02X%02X" % rgb


def check_not_blocked(what, value):
    low = value.lower()
    for part in BLOCKED_NAME_PARTS:
        if part in low:
            raise RebrandError("%s %r contains %r: pick a name of your own, never the name "
                               "of Telegram or of another app" % (what, value, part))


def check_package(what, value):
    if not PACKAGE_RE.match(value):
        raise RebrandError("%s %r is not a valid package name (a.b[.c...], each part "
                           "starting with a letter, then letters, digits or _)" % (what, value))
    if any(p in JAVA_KEYWORDS for p in value.split(".")):
        raise RebrandError("%s %r uses a Java keyword as a segment" % (what, value))
    for prefix in BLOCKED_PACKAGE_PREFIXES:
        if (value + ".").startswith(prefix):
            raise RebrandError("%s %r is in the %s namespace, which belongs to someone else: "
                               "use a domain of your own" % (what, value, prefix[:-1]))
    check_not_blocked(what, value)


def check_app_name(value):
    if not value.strip() or len(value) > 30 or any(ord(c) < 32 for c in value):
        raise RebrandError("app name must be 1 to 30 printable characters")
    check_not_blocked("app name", value)


# --- escaping -------------------------------------------------------------------------
def android_string(s):
    """Escape text for a <string> resource."""
    s = s.replace("\\", "\\\\")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("'", "\\'").replace('"', '\\"')
    if s[:1] in ("@", "?"):
        s = "\\" + s
    return s


def prop_escape(s, key=False):
    """Escape a value for java.util.Properties.load (ISO-8859-1 with \\u escapes)."""
    out = []
    for i, c in enumerate(s):
        o = ord(c)
        if c == "\\":
            out.append("\\\\")
        elif c in "=:#!" or (c == " " and (key or i == 0)):
            out.append("\\" + c)
        elif c == "\t":
            out.append("\\t")
        elif o < 0x20 or o > 0x7e:
            if o > 0xffff:
                o -= 0x10000
                out.append("\\u%04x\\u%04x" % (0xd800 + (o >> 10), 0xdc00 + (o & 0x3ff)))
            else:
                out.append("\\u%04x" % o)
        else:
            out.append(c)
    return "".join(out)


def prop_unescape(s):
    def one(m):
        e = m.group(1)
        if e[0] == "u":
            return chr(int(e[1:], 16))
        return {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(e, e)
    # \uXXXX pairs for characters above U+FFFF are joined by the encode/decode round trip
    out = re.sub(r"\\(u[0-9a-fA-F]{4}|.)", one, s)
    return out.encode("utf-16", "surrogatepass").decode("utf-16")


def read_properties(path):
    """Reader for the one-line key=value files this script writes."""
    props = {}
    if not path.is_file():
        return props
    for line in path.read_text(encoding="latin-1").splitlines():
        line = line.lstrip()
        if not line or line[0] in "#!":
            continue
        m = re.match(r"((?:\\.|[^=:\s])+)\s*[=:]?\s*(.*)$", line)
        if m:
            props[prop_unescape(m.group(1))] = prop_unescape(m.group(2))
    return props


# --- minimal PNG writer (RGBA, standard library only) -----------------------------------
def png_bytes(w, h, px):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += px[y * stride:(y + 1) * stride]
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise RebrandError("%s is not a PNG" % rel(path))
    return struct.unpack(">II", head[16:24])


def _blend(px, w, x, y, rgb, a):
    if a <= 0:
        return
    i = (y * w + x) * 4
    if a >= 1:
        px[i:i + 4] = bytes((rgb[0], rgb[1], rgb[2], 255))
        return
    da = px[i + 3] / 255.0
    oa = a + da * (1 - a)
    for k in range(3):
        px[i + k] = int(round((rgb[k] * a + px[i + k] * da * (1 - a)) / oa))
    px[i + 3] = int(round(oa * 255))


def _cov(d):
    """Pixel coverage from a signed distance in pixels (negative = inside)."""
    if d <= -0.5:
        return 1.0
    if d >= 0.5:
        return 0.0
    return 0.5 - d


# Shapes in units of the mark radius (26dp on the 108dp adaptive canvas), centred on (0, 0),
# y pointing down. No point is further than 1.21 units (31.5dp) from the centre, so the
# mark stays inside the 33dp safe-zone circle that every launcher mask keeps.
def _poly(n, radius, phase):
    return [(radius * math.cos(phase + 2 * math.pi * k / n),
             radius * math.sin(phase + 2 * math.pi * k / n)) for k in range(n)]


def shape_parts(shape):
    """Return a list of ('circle', r) or ('poly', [points]) parts (their union is drawn)."""
    if shape == "disc":
        return [("circle", 1.0)]
    if shape == "square":
        s = 0.85
        return [("poly", [(-s, -s), (s, -s), (s, s), (-s, s)])]
    if shape == "diamond":
        return [("poly", [(0, -1.05), (1.05, 0), (0, 1.05), (-1.05, 0)])]
    if shape == "triangle":
        return [("poly", _poly(3, 1.1, -math.pi / 2))]
    if shape == "pentagon":
        return [("poly", _poly(5, 1.05, -math.pi / 2))]
    if shape == "hexagon":
        return [("poly", _poly(6, 1.0, math.pi / 6))]
    raise ValueError(shape)


def _poly_sd(points, x, y):
    """Signed distance to a convex polygon given clockwise on screen (y down)."""
    d = -1e9
    n = len(points)
    for k in range(n):
        x1, y1 = points[k]
        x2, y2 = points[(k + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        ln = (ex * ex + ey * ey) ** 0.5
        # outward normal of a clockwise (screen) polygon
        nx, ny = ey / ln, -ex / ln
        d = max(d, (x - x1) * nx + (y - y1) * ny)
    return d


def shape_sd(parts, x, y):
    d = 1e9
    for p in parts:
        if p[0] == "circle":
            dd = (x * x + y * y) ** 0.5 - p[1]
        else:
            dd = _poly_sd(p[1], x, y)
        d = min(d, dd)
    return d


def draw_mark(px, size, cx, cy, rad, fg, parts):
    lo_x, hi_x = int(cx - 1.2 * rad) - 1, int(cx + 1.2 * rad) + 2
    lo_y, hi_y = int(cy - 1.2 * rad) - 1, int(cy + 1.2 * rad) + 2
    for y in range(max(0, lo_y), min(size, hi_y)):
        for x in range(max(0, lo_x), min(size, hi_x)):
            d = shape_sd(parts, (x + 0.5 - cx) / rad, (y + 0.5 - cy) / rad) * rad
            _blend(px, size, x, y, fg, _cov(d))


def render_png(kind, size, bg, fg, parts):
    px = bytearray(size * size * 4)
    c = size / 2.0
    if kind in ("square", "round"):
        # legacy (pre-Android 8) launcher icon: shape with a small margin, mark on top
        half = size * 0.46
        corner = size * 0.12
        for y in range(size):
            for x in range(size):
                u, v = x + 0.5 - c, y + 0.5 - c
                if kind == "round":
                    d = (u * u + v * v) ** 0.5 - half
                else:
                    dx, dy = abs(u) - (half - corner), abs(v) - (half - corner)
                    if dx < 0 and dy < 0:
                        d = max(dx, dy) - corner
                    else:
                        d = (max(dx, 0) ** 2 + max(dy, 0) ** 2) ** 0.5 - corner
                _blend(px, size, x, y, bg, _cov(d))
        draw_mark(px, size, c, c, size * 0.26, fg, parts)
    elif kind == "bg_layer":
        for i in range(0, len(px), 4):
            px[i:i + 4] = bytes((bg[0], bg[1], bg[2], 255))
    elif kind == "fg_layer":
        # same geometry as the vector foreground: radius 26 on the 108 canvas
        draw_mark(px, size, c, c, size * 26.0 / 108.0, fg, parts)
    elif kind == "notif":
        # white disc with the mark cut out, like the stock icon (the system tints it);
        # disc and mark keep the launcher's proportions (mark radius 26 : visible radius 36)
        disc = size * 0.458
        rad = disc * 26.0 / 36.0
        for y in range(size):
            for x in range(size):
                u, v = x + 0.5 - c, y + 0.5 - c
                a = _cov((u * u + v * v) ** 0.5 - disc)
                if a > 0:
                    a *= 1.0 - _cov(shape_sd(parts, u / rad, v / rad) * rad)
                i = (y * size + x) * 4
                px[i:i + 4] = bytes((255, 255, 255, int(round(a * 255))))
    else:
        raise ValueError(kind)
    return png_bytes(size, size, px)


# --- vector layers (108dp adaptive canvas) ----------------------------------------------
def _circle_path(cx, cy, r):
    return ("M%.2f,%.2f A%.2f,%.2f 0 1,1 %.2f,%.2f A%.2f,%.2f 0 1,1 %.2f,%.2f Z"
            % (cx - r, cy, r, r, cx + r, cy, r, r, cx - r, cy))


def vector_layer(parts, color):
    cx = cy = 54.0
    rad = 26.0
    paths = []
    for p in parts:
        if p[0] == "circle":
            d = _circle_path(cx, cy, p[1] * rad)
        else:
            pts = [(cx + x * rad, cy + y * rad) for x, y in p[1]]
            d = "M" + " L".join("%.2f,%.2f" % pt for pt in pts) + " Z"
        paths.append(d)
    body = "\n".join('    <path\n        android:fillColor="%s"\n        android:pathData="%s" />'
                     % (color, d) for d in paths)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!-- Generated by multigram/rebrand/generate_rebrand.py -->\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    android:width="108dp"\n'
            '    android:height="108dp"\n'
            '    android:viewportWidth="108"\n'
            '    android:viewportHeight="108">\n'
            '%s\n'
            '</vector>\n' % body)


def splash_vector(parts, bg, fg):
    """The splash-screen icon on its 320dp canvas: the launcher icon as a disc of radius 100
    (the 36dp visible radius of the adaptive icon, scaled), mark in the same proportion."""
    cx = cy = 160.0
    scale = 100.0 / 36.0
    rad = 26.0 * scale
    paths = [(hexc(bg), _circle_path(cx, cy, 100.0))]
    for p in parts:
        if p[0] == "circle":
            d = _circle_path(cx, cy, p[1] * rad)
        else:
            pts = [(cx + x * rad, cy + y * rad) for x, y in p[1]]
            d = "M" + " L".join("%.2f,%.2f" % pt for pt in pts) + " Z"
        paths.append((hexc(fg), d))
    body = "\n".join('    <path\n        android:fillColor="%s"\n        android:pathData="%s" />'
                     % cd for cd in paths)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!-- Generated by multigram/rebrand/generate_rebrand.py -->\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    android:width="320dp"\n'
            '    android:height="320dp"\n'
            '    android:viewportWidth="320"\n'
            '    android:viewportHeight="320">\n'
            '%s\n'
            '</vector>\n' % body)


ADAPTIVE_ICON = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<!-- Generated by multigram/rebrand/generate_rebrand.py -->\n'
                 '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                 '    <background android:drawable="@color/multigram_rebrand_icon_bg" />\n'
                 '    <foreground android:drawable="@drawable/multigram_rebrand_icon_fg" />\n'
                 '    <monochrome android:drawable="@drawable/multigram_rebrand_icon_mono" />\n'
                 '</adaptive-icon>\n')


# --- scanning the tree ------------------------------------------------------------------
def res_roots():
    roots = []
    for g in RES_ROOT_GLOBS:
        roots += sorted(p for p in REPO.glob(g) if p.is_dir())
    return roots


def scan_icons():
    """{(type, name): {qualifier_dir: (ext, (w, h) or None)}} for every ICON_TARGETS entry
    defined in the tree."""
    found = {}
    for root in res_roots():
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            rtype = d.name.split("-", 1)[0]
            for f in sorted(d.iterdir()):
                name, _, ext = f.name.partition(".")
                key = (rtype, name)
                if key not in ICON_TARGETS:
                    continue
                info = (ext, png_size(f) if ext == "png" else None)
                prev = found.setdefault(key, {}).get(d.name)
                if prev is not None and prev[0] != ext:
                    raise RebrandError("%s/%s exists as .%s and .%s in different source sets"
                                       % (d.name, name, prev[0], ext))
                if prev is None or (info[1] and prev[1] and info[1][0] > prev[1][0]):
                    found[key][d.name] = info
    return found


def scan_app_name_dirs():
    """values* directories whose strings.xml defines one of APP_NAME_STRINGS."""
    dirs = {"values"}
    for root in res_roots():
        for f in sorted(root.glob("values*/strings.xml")):
            try:
                names = {e.get("name") for e in ET.parse(f).getroot().iter("string")}
            except ET.ParseError as e:
                raise RebrandError("cannot parse %s: %s" % (rel(f), e))
            if names & set(APP_NAME_STRINGS):
                dirs.add(f.parent.name)
    return sorted(dirs)


def check_manifests(icons):
    """Warn when a label or launcher icon comes from a resource the overlay does not cover
    (e.g. Forkgram renamed its default icon)."""
    warnings = []
    files = [REPO / m for m in MANIFESTS] + sorted(REPO.glob(CONFIG_MANIFEST_GLOB))
    for f in files:
        if not f.is_file():
            continue
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as e:
            raise RebrandError("cannot parse %s: %s" % (rel(f), e))
        app = root.find("application")
        if app is None:
            continue
        nodes = [app]
        for alias in app.findall("activity-alias"):
            enabled = alias.get(ANDROID_NS + "enabled", "true") == "true"
            launcher = any(c.get(ANDROID_NS + "name") == "android.intent.category.LAUNCHER"
                           for c in alias.iter("category"))
            if enabled and launcher:
                nodes.append(alias)
        for node in nodes:
            label = node.get(ANDROID_NS + "label")
            if label and label.startswith("@string/") and label[8:] not in APP_NAME_STRINGS:
                warnings.append("%s: label %s is not rebranded" % (rel(f), label))
            for attr in ("icon", "roundIcon"):
                ref = node.get(ANDROID_NS + attr)
                if not ref or not ref.startswith("@"):
                    continue
                rtype, _, name = ref[1:].partition("/")
                key = (rtype, name)
                if key in ICON_TARGETS:
                    continue
                exists = any(next(r.glob("%s*/%s.*" % (rtype, name)), None) is not None
                             for r in res_roots())
                if exists:
                    warnings.append("%s: %s %s is not rebranded" % (rel(f), attr, ref))
    return warnings


def check_splash_styles():
    """Warn when a theme's splash-screen icon is a drawable the overlay does not cover."""
    warnings = []
    for root in res_roots():
        for f in sorted(root.glob("values*/*.xml")):
            try:
                tree = ET.parse(f)
            except ET.ParseError as e:
                raise RebrandError("cannot parse %s: %s" % (rel(f), e))
            for item in tree.getroot().iter("item"):
                ref = (item.text or "").strip()
                if item.get("name") != SPLASH_ATTR or not ref.startswith("@"):
                    continue
                rtype, _, name = ref[1:].partition("/")
                if (rtype, name) not in ICON_TARGETS:
                    warnings.append("%s: splash icon %s is not rebranded" % (rel(f), ref))
    return warnings


def google_services_plugin_applied():
    f = APP_MODULE / "build.gradle"
    if not f.is_file():
        return False
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.split("//", 1)[0]
        if "com.google.gms.google-services" in line:
            return True
    return False


# --- overlay ----------------------------------------------------------------------------
def write_overlay(app_name, bg, fg, shape, icons, name_dirs):
    if GEN_RES.exists():
        shutil.rmtree(GEN_RES)
    parts = shape_parts(shape)
    written = []

    def put(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        path.write_bytes(data)
        written.append(path)

    esc = android_string(app_name)
    strings = "".join('    <string name="%s">%s</string>\n' % (n, esc) for n in APP_NAME_STRINGS)
    for d in name_dirs:
        put(GEN_RES / d / "rebrand_strings.xml",
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!-- Generated by multigram/rebrand/generate_rebrand.py -->\n'
            '<resources>\n%s</resources>\n' % strings)
    put(GEN_RES / "values" / "rebrand_colors.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!-- Generated by multigram/rebrand/generate_rebrand.py -->\n'
        '<resources>\n'
        '    <color name="multigram_rebrand_icon_bg">%s</color>\n'
        '</resources>\n' % hexc(bg))
    put(GEN_RES / "drawable" / "multigram_rebrand_icon_fg.xml", vector_layer(parts, hexc(fg)))
    put(GEN_RES / "drawable" / "multigram_rebrand_icon_mono.xml", vector_layer(parts, "#FFFFFFFF"))
    # Read by org.telegram.messenger.multigram.Rebrand (default false in the library).
    put(GEN_RES / "values" / "rebrand_flags.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!-- Generated by multigram/rebrand/generate_rebrand.py -->\n'
        '<resources>\n'
        '    <bool name="multigram_rebrand_active">true</bool>\n'
        '</resources>\n')

    cache = {}
    for (rtype, name), kind in sorted(ICON_TARGETS.items()):
        for qdir, (ext, size) in sorted(icons.get((rtype, name), {}).items()):
            if ext == "xml" and kind == "splash":
                put(GEN_RES / qdir / (name + ".xml"), splash_vector(parts, bg, fg))
            elif ext == "xml":
                m = re.search(r"-v(\d+)", qdir)
                if kind not in ("square", "round") or "anydpi" not in qdir or not m \
                        or int(m.group(1)) < 26:
                    raise RebrandError("unexpected %s/%s.xml: update ICON_TARGETS in %s"
                                       % (qdir, name, rel(__file__)))
                put(GEN_RES / qdir / (name + ".xml"), ADAPTIVE_ICON)
            elif ext == "png" and kind != "splash":
                w, h = size
                if w != h:
                    raise RebrandError("%s/%s.png is not square (%dx%d)" % (qdir, name, w, h))
                k = (kind, w)
                if k not in cache:
                    cache[k] = render_png(kind, w, bg, fg, parts)
                put(GEN_RES / qdir / (name + ".png"), cache[k])
            else:
                raise RebrandError("unexpected %s/%s.%s: update ICON_TARGETS in %s"
                                   % (qdir, name, ext, rel(__file__)))
    return written


# --- in-place patches with backups ------------------------------------------------------
def load_index():
    if BACKUP_INDEX.is_file():
        return json.loads(BACKUP_INDEX.read_text(encoding="utf-8"))
    return {}


def save_index(idx):
    BACKUP_INDEX.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_INDEX.write_text(json.dumps(idx, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def original_bytes(path, idx):
    """The stock content of a file this script may have patched before: the backup while
    the file still holds our last patch, otherwise the file itself. Refuses a file that
    changed after we patched it, or that still carries a patch whose backup is gone, since
    neither is the stock original any more."""
    cur = path.read_bytes()
    entry = idx.get(rel(path))
    bak = BACKUP / rel(path)
    if entry:
        if sha256(cur) == entry["patched"]:
            if not bak.is_file() or sha256(bak.read_bytes()) != entry["orig"]:
                raise RebrandError("the backup of %s is missing or damaged; restore the file "
                                   "(git checkout -- %s) and run again" % (rel(path), rel(path)))
            return bak.read_bytes()
        if sha256(cur) != entry["orig"]:
            raise RebrandError("%s changed after the rebrand patched it, so it is not the stock "
                               "file any more; restore it (git checkout -- %s), or put your "
                               "change back after --clean, and run again" % (rel(path), rel(path)))
    if PATCH_MARKER.encode() in cur:
        raise RebrandError("%s still carries an earlier rebrand's patch and its backup is gone "
                           "(was generated/ deleted?); restore it (git checkout -- %s) and run "
                           "again" % (rel(path), rel(path)))
    return cur


def add_marker(data, xml):
    """Put PATCH_MARKER at the top of a patched file (after an XML declaration)."""
    if not xml:
        return ("// %s; undo with --clean\n" % PATCH_MARKER).encode() + data
    # (an XML comment must not contain "--", so the option is not spelled out here)
    line = ("<!-- %s; its clean option undoes this -->\n" % PATCH_MARKER).encode()
    m = re.match(rb"<\?xml[^>]*\?>\r?\n?", data)
    if m:
        head = m.group(0) if m.group(0).endswith(b"\n") else m.group(0) + b"\n"
        return head + line + data[m.end():]
    return line + data


def plan_account_type(account_type, idx):
    """Compute the patched bytes of the three files without writing anything."""
    plan = []
    notes = []
    if not CONTACTS_JAVA.is_file():
        raise RebrandError("%s is missing" % rel(CONTACTS_JAVA))
    orig = original_bytes(CONTACTS_JAVA, idx)
    old = b'"' + STOCK_JAVA_ACCOUNT_TYPE.encode() + b'"'
    n = orig.count(old)
    if n == 0:
        raise RebrandError('%s has no "%s" literal left; restore it (git checkout -- %s) '
                           "and run again" % (rel(CONTACTS_JAVA), STOCK_JAVA_ACCOUNT_TYPE,
                                              rel(CONTACTS_JAVA)))
    new = add_marker(orig.replace(old, b'"' + account_type.encode() + b'"'), xml=False)
    note = "%d literal(s)" % n
    if n != JAVA_EXPECTED_LITERALS:
        note += " (expected %d: check the file)" % JAVA_EXPECTED_LITERALS
    plan.append((CONTACTS_JAVA, orig, new, note))
    for x in ACCOUNT_XMLS:
        if not x.is_file():
            raise RebrandError("%s is missing" % rel(x))
        orig = original_bytes(x, idx)
        found = ACCOUNT_XML_ATTR.findall(orig)
        if len(found) != 1:
            raise RebrandError("%s: expected one android:accountType, found %d"
                               % (rel(x), len(found)))
        was = found[0][len(b'android:accountType="'):-1]
        if was != STOCK_XML_ACCOUNT_TYPE:
            notes.append("%s had android:accountType=\"%s\" before patching (stock is %s); "
                         "--clean puts that value back" % (rel(x), was.decode("utf-8", "replace"),
                                                           STOCK_XML_ACCOUNT_TYPE.decode()))
        new = ACCOUNT_XML_ATTR.sub(b'android:accountType="' + account_type.encode() + b'"', orig)
        plan.append((x, orig, add_marker(new, xml=True), "android:accountType"))
    return plan, notes


def patched_files_left():
    """The account-type files that still carry PATCH_MARKER."""
    return [rel(f) for f in [CONTACTS_JAVA] + ACCOUNT_XMLS
            if f.is_file() and PATCH_MARKER.encode() in f.read_bytes()]


def apply_plan(plan, idx):
    for path, orig, new, _ in plan:
        bak = BACKUP / rel(path)
        bak.parent.mkdir(parents=True, exist_ok=True)
        bak.write_bytes(orig)
        path.write_bytes(new)
        idx[rel(path)] = {"orig": sha256(orig), "patched": sha256(new)}
    save_index(idx)


def restore_patched(idx, only_check=False):
    """Put back the stock files. Refuses (returns the list) when a patched file has been
    changed since this script wrote it, so nobody's edits are overwritten."""
    conflicts = []
    todo = []
    for relpath, entry in sorted(idx.items()):
        p = REPO / relpath
        bak = BACKUP / relpath
        cur = sha256(p.read_bytes()) if p.is_file() else None
        if cur == entry["orig"]:
            continue
        if cur == entry["patched"] and bak.is_file() and sha256(bak.read_bytes()) == entry["orig"]:
            todo.append((p, bak))
        else:
            conflicts.append(relpath)
    if conflicts or only_check:
        return conflicts, 0
    for p, bak in todo:
        p.write_bytes(bak.read_bytes())
    return [], len(todo)


def unrestorable_patches(idx):
    """Files that carry PATCH_MARKER but that restore_patched cannot put back, because
    their backup is gone (e.g. generated/ was deleted) or they changed since."""
    bad = []
    for relpath in patched_files_left():
        entry = idx.get(relpath)
        cur = sha256((REPO / relpath).read_bytes())
        bak = BACKUP / relpath
        if not (entry and cur == entry["patched"] and bak.is_file()
                and sha256(bak.read_bytes()) == entry["orig"]):
            bad.append(relpath)
    return bad


def stock_account_type_warnings():
    """After a restore: say so when the three files do not hold Forkgram's values."""
    out = []
    if CONTACTS_JAVA.is_file() and \
            ('"%s"' % STOCK_JAVA_ACCOUNT_TYPE).encode() not in CONTACTS_JAVA.read_bytes():
        out.append('%s has no "%s" literal' % (rel(CONTACTS_JAVA), STOCK_JAVA_ACCOUNT_TYPE))
    for x in ACCOUNT_XMLS:
        if x.is_file() and b'android:accountType="' + STOCK_XML_ACCOUNT_TYPE + b'"' \
                not in x.read_bytes():
            out.append('%s does not say android:accountType="%s"'
                       % (rel(x), STOCK_XML_ACCOUNT_TYPE.decode()))
    return out


def warn_leftover_account_types():
    """Report other files that still carry an account type, e.g. after an upstream change
    (reports only: they may be unrelated, so they are never edited)."""
    hits = []
    java_lit = ('"%s"' % STOCK_JAVA_ACCOUNT_TYPE).encode()
    patched = {CONTACTS_JAVA.resolve()} | {x.resolve() for x in ACCOUNT_XMLS}
    for root in [LIB_MODULE / "src", APP_MODULE / "src"]:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.resolve() in patched or p.suffix not in (".java", ".kt", ".xml"):
                continue
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if p.suffix == ".xml":
                if ACCOUNT_XML_ATTR.search(data):
                    hits.append(rel(p))
            elif java_lit in data:
                hits.append(rel(p))
    return hits


# --- keystore ---------------------------------------------------------------------------
def keytool():
    exe = shutil.which("keytool")
    if not exe and os.environ.get("JAVA_HOME"):
        cand = Path(os.environ["JAVA_HOME"]) / "bin" / "keytool"
        if cand.is_file():
            exe = str(cand)
    if not exe:
        raise RebrandError("keytool not found (install a JDK, set JAVA_HOME) or use --no-keystore")
    return exe


def keystore_fingerprint(path, store_pw, alias):
    out = subprocess.run([keytool(), "-list", "-v", "-keystore", str(path), "-storepass",
                          store_pw, "-alias", alias], capture_output=True, text=True)
    if out.returncode != 0:
        raise RebrandError("keytool cannot open %s: %s" % (path, (out.stdout + out.stderr).strip()))
    m = re.search(r"SHA256:\s*([0-9A-F:]+)", out.stdout)
    return m.group(1) if m else "?"


def make_keystore(path, cn):
    """Create a fresh RSA key. PKCS12 keystores use one password for store and key."""
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    alias = "k" + secrets.token_hex(5)
    pw = secrets.token_urlsafe(24)
    safe_cn = re.sub(r"[^A-Za-z0-9 ]", "", cn).strip() or "Rebrand"
    cmd = [keytool(), "-genkeypair", "-noprompt", "-storetype", "PKCS12",
           "-keystore", str(path), "-alias", alias, "-keyalg", "RSA", "-keysize", "3072",
           "-validity", "10000", "-storepass", pw, "-keypass", pw,
           "-dname", "CN=%s, O=%s" % (safe_cn, safe_cn)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RebrandError("keytool failed: %s" % (out.stdout + out.stderr).strip())
    os.chmod(path, 0o600)
    return {"alias": alias, "store_password": pw, "key_password": pw}


def keystore_for(args, app_name):
    """Returns (path, creds, note) or None for --no-keystore."""
    if args.no_keystore:
        return None
    if args.keystore:
        path = Path(args.keystore).expanduser().resolve()
        side = path.with_name(path.name + ".properties")
        try:
            path.relative_to(REPO)
            raise RebrandError("keep the --keystore file outside the repository (%s), so the "
                               "private key can never be committed" % REPO)
        except ValueError:
            pass
        if path.exists():
            p = read_properties(side)
            if not all(k in p for k in ("KEY_ALIAS", "STORE_PASSWORD", "KEY_PASSWORD")):
                raise RebrandError("%s exists but %s with KEY_ALIAS, STORE_PASSWORD and "
                                   "KEY_PASSWORD is missing" % (path, side))
            creds = {"alias": p["KEY_ALIAS"], "store_password": p["STORE_PASSWORD"],
                     "key_password": p["KEY_PASSWORD"]}
            fp = keystore_fingerprint(path, creds["store_password"], creds["alias"])
            return path, creds, "reused %s (SHA-256 %s)" % (path, fp)
        creds = make_keystore(path, app_name)
        side.write_text("# Credentials for %s. Keep both files together and private.\n"
                        "KEY_ALIAS=%s\nSTORE_PASSWORD=%s\nKEY_PASSWORD=%s\n"
                        % (prop_escape(path.name), prop_escape(creds["alias"]),
                           prop_escape(creds["store_password"]),
                           prop_escape(creds["key_password"])), encoding="latin-1")
        os.chmod(side, 0o600)
        fp = keystore_fingerprint(path, creds["store_password"], creds["alias"])
        return path, creds, "created %s (SHA-256 %s); reuse it for every update" % (path, fp)
    creds = make_keystore(DEFAULT_KEYSTORE, app_name)
    fp = keystore_fingerprint(DEFAULT_KEYSTORE, creds["store_password"], creds["alias"])
    return DEFAULT_KEYSTORE, creds, ("new key (SHA-256 %s); --clean deletes it, see the "
                                     "README before shipping updatable builds" % fp)


# --- commands ---------------------------------------------------------------------------
def clean():
    idx = load_index()
    conflicts, _ = restore_patched(idx, only_check=True)
    if conflicts:
        raise RebrandError("not cleaning: these files changed after the rebrand patched them, "
                           "so restoring the backup would lose those changes:\n  "
                           + "\n  ".join(conflicts)
                           + "\nResolve them (e.g. git checkout -- <file>) and run --clean again.")
    lost = unrestorable_patches(idx)
    if lost:
        raise RebrandError("not cleaning: these files still carry a rebrand's account type and "
                           "there is no backup to restore them from (was generated/ deleted?):"
                           "\n  " + "\n  ".join(lost)
                           + "\nRestore them with: git checkout -- " + " ".join(lost)
                           + "\nthen run --clean again.")
    _, restored = restore_patched(idx)
    left = patched_files_left()
    if left:
        raise RebrandError("still patched after restoring: " + ", ".join(left))
    had_key = DEFAULT_KEYSTORE.exists()
    if PROPS.exists():
        PROPS.unlink()
    if GEN.exists():
        shutil.rmtree(GEN)
    print("Rebrand removed: stock identity restored (%d source file(s) put back)." % restored)
    if had_key:
        print("The generated signing key was deleted with it.")
    for w in stock_account_type_warnings():
        print("WARNING: %s (not Forkgram's stock value; check the file)" % w)


def generate(args):
    seed = args.seed if args.seed is not None else secrets.token_hex(8)
    ident = gen_identity(rng_from_seed(seed))
    app_id = args.application_id or ident["application_id"]
    app_name = args.app_name or ident["app_name"]
    check_package("applicationId", app_id)
    check_app_name(app_name)
    account_type = None
    if not args.no_account_type:
        account_type = args.account_type or app_id
        check_package("account type", account_type)
    bg, fg, shape = ident["bg"], ident["fg"], ident["shape"]

    # Check everything before writing anything.
    icons = scan_icons()
    missing = [n for (t, n) in ICON_TARGETS if (t, n) not in icons]
    name_dirs = scan_app_name_dirs()
    warnings = check_manifests(icons) + check_splash_styles()
    warnings += ["icon resource %s not found in the tree (skipped)" % n for n in missing]
    if google_services_plugin_applied():
        warnings.append("TMessagesProj_App applies the google-services plugin now: its "
                        "google-services.json must list %s, %s.beta, %s.web (and your "
                        "flavor ids); use your own Firebase project" % (app_id, app_id, app_id))
    idx = load_index()
    plan, notes = plan_account_type(account_type, idx) if account_type else ([], [])
    warnings += notes
    if not account_type:
        conflicts, _ = restore_patched(idx, only_check=True)
        if conflicts:
            raise RebrandError("cannot put back the stock account type, these files changed "
                               "since: " + ", ".join(conflicts))
        lost = unrestorable_patches(idx)
        if lost:
            raise RebrandError("cannot put back the stock account type, there is no backup "
                               "for: %s; restore them with git checkout -- %s and run again"
                               % (", ".join(lost), " ".join(lost)))

    GEN.mkdir(parents=True, exist_ok=True)
    ks = keystore_for(args, app_name)
    write_overlay(app_name, bg, fg, shape, icons, name_dirs)
    if plan:
        apply_plan(plan, idx)
    else:
        restore_patched(idx)
        for relpath in list(idx):
            (BACKUP / relpath).unlink(missing_ok=True)
        save_index({})
    leftovers = warn_leftover_account_types() if account_type else []

    # The options that repeat this identity, for rebrand.gradle's error messages.
    rerun = ["--seed", seed]
    for opt, val in (("--app-name", args.app_name), ("--application-id", args.application_id),
                     ("--account-type", args.account_type),
                     ("--version-name", args.version_name)):
        if val:
            rerun += [opt, val]
    if args.version_code:
        rerun += ["--version-code", str(args.version_code)]
    if args.no_account_type:
        rerun.append("--no-account-type")
    if args.keystore:
        rerun += ["--keystore", str(Path(args.keystore).expanduser().resolve())]
    elif args.no_keystore:
        rerun.append("--no-keystore")

    lines = [
        "# Generated by multigram/rebrand/generate_rebrand.py. Do not commit.",
        "# To build the stock identity again run generate_rebrand.py --clean. Deleting this",
        "# file alone leaves three source files patched, and Gradle then refuses to build.",
        "REBRAND_ACTIVE=true",
        "REBRAND_SEED=" + prop_escape(seed),
        "REBRAND_RERUN=" + prop_escape(shlex.join(rerun)),
        "REBRAND_APPLICATION_ID=" + app_id,
        "REBRAND_APP_NAME=" + prop_escape(app_name),
        "REBRAND_ICON=%s %s %s" % (shape, hexc(bg), hexc(fg)),
    ]
    if account_type:
        lines.append("REBRAND_ACCOUNT_TYPE=" + account_type)
    if args.version_name:
        lines.append("REBRAND_VERSION_NAME=" + prop_escape(args.version_name))
    if args.version_code:
        lines.append("REBRAND_VERSION_CODE=%d" % args.version_code)
    if ks:
        path, creds, _ = ks
        try:
            ks_ref = path.resolve().relative_to(REPO).as_posix()
        except ValueError:
            ks_ref = str(path.resolve())
        lines += ["REBRAND_KEYSTORE=" + prop_escape(ks_ref),
                  "REBRAND_KEY_ALIAS=" + prop_escape(creds["alias"]),
                  "REBRAND_STORE_PASSWORD=" + prop_escape(creds["store_password"]),
                  "REBRAND_KEY_PASSWORD=" + prop_escape(creds["key_password"])]
    PROPS.write_text("\n".join(lines) + "\n", encoding="latin-1")
    os.chmod(PROPS, 0o600)

    print("Rebrand identity")
    print("  seed           %s" % seed)
    print("  applicationId  %s  (Gradle adds the build type suffix, e.g. .beta)" % app_id)
    print("  app name       %s" % app_name)
    print("  icon           %s, background %s, mark %s" % (shape, hexc(bg), hexc(fg)))
    if account_type:
        print("  account type   %s" % account_type)
        for path, _, _, note in plan:
            print("                   %s: %s" % (rel(path), note))
    else:
        print("  account type   left as in the tree (--no-account-type)")
    print("  signing        %s" % (ks[2] if ks else "the module's own config (--no-keystore); "
                                   "without RELEASE_KEYSTORE_FILE that is the public test key"))
    print("  overlay        %s" % rel(GEN_RES))
    print("  properties     %s" % rel(PROPS))
    for w in warnings:
        print("WARNING: " + w)
    for h in leftovers:
        print("WARNING: %s still carries an account type; check it by hand" % h)
    print()
    print("Build as usual, e.g. ./gradlew :TMessagesProj_App:assembleAfatRelease")
    print("Undo with: python3 multigram/rebrand/generate_rebrand.py --clean")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Give this MultiGram build its own identity (see multigram/rebrand/README.md).")
    ap.add_argument("--seed", help="reproduce an identity (default: a new random seed)")
    ap.add_argument("--app-name", help="use this app name instead of a generated one")
    ap.add_argument("--application-id", help="use this applicationId instead of a generated one")
    ap.add_argument("--account-type", help="Android account type (default: the applicationId)")
    ap.add_argument("--no-account-type", action="store_true",
                    help="leave the account type files as they are in the tree")
    ap.add_argument("--version-name",
                    help="override the APK's versionName, which Telegram's servers see; the "
                         "in-app version string stays the tree's (default: keep the tree's)")
    ap.add_argument("--version-code", type=int,
                    help="override the base versionCode (default: keep the tree's)")
    ap.add_argument("--keystore", metavar="PATH",
                    help="keep the signing key at PATH (outside the repository): created on "
                         "the first run, reused on later runs; --clean leaves it alone")
    ap.add_argument("--no-keystore", action="store_true",
                    help="no new key: sign with the module's own signing config (without "
                         "RELEASE_KEYSTORE_FILE that is the public test key: never "
                         "distribute such an APK)")
    ap.add_argument("--clean", action="store_true", help="undo everything this script wrote")
    args = ap.parse_args(argv)
    if args.keystore and args.no_keystore:
        ap.error("--keystore and --no-keystore exclude each other")
    if args.account_type and args.no_account_type:
        ap.error("--account-type and --no-account-type exclude each other")
    if args.version_code is not None and args.version_code <= 0:
        ap.error("--version-code must be positive")
    try:
        if args.clean:
            clean()
        else:
            generate(args)
    except RebrandError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
