#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-test for the MultiGram rebrand toolkit. Standard library only (plus git, and keytool
for the signing checks).

It copies the tracked sources the generator reads (TMessagesProj/src, TMessagesProj/config,
TMessagesProj_App) and the toolkit from this working tree into a throwaway git repository,
then checks there:

  - the outputs are well formed (XML parses, PNG chunks and CRCs, keystore opens)
  - the overlay replaces every icon and app-name resource in the same qualifier folders,
    including the splash-screen and notification icons, and sets the rebrand flag
  - the account type is the same in ContactsController.java, auth.xml and sync_contacts.xml,
    and each of them carries the patch marker
  - the identity is deterministic per seed (also through REBRAND_RERUN) and differs between
    seeds (the key does not repeat)
  - git sees only the three patched files; everything generated is ignored
  - --no-account-type, --keystore reuse, the name and namespace guards, the conflict guard
    and the guards against a lost backup behave
  - --clean leaves the tree byte-identical to the commit, with nothing left behind

Run it from anywhere:  python3 multigram/rebrand/selftest.py [--keep]
"""

import argparse
import hashlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

sys.dont_write_bytecode = True   # importing the generator must not leave __pycache__ behind

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TOOL_FILES = ["generate_rebrand.py", "rebrand.gradle", ".gitignore", "README.md", "selftest.py"]
COPY_PATHS = ["TMessagesProj/src", "TMessagesProj/config", "TMessagesProj_App", ".gitignore"]
PATCHED = ["TMessagesProj/src/main/java/org/telegram/messenger/ContactsController.java",
           "TMessagesProj/src/main/res/xml/auth.xml",
           "TMessagesProj/src/main/res/xml/sync_contacts.xml"]
ANDROID = "{http://schemas.android.com/apk/res/android}"

failures = []


def check(ok, what):
    print("%s  %s" % ("ok  " if ok else "FAIL", what))
    if not ok:
        failures.append(what)
    return ok


def git(tree, *args):
    return subprocess.run(["git", "-C", str(tree)] + list(args), capture_output=True,
                          text=True, check=True).stdout


def build_tree(tmp):
    tree = tmp / "tree"
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--"] + COPY_PATHS,
                           capture_output=True, check=True).stdout.split(b"\0")
    for f in files:
        if not f:
            continue
        src = REPO / f.decode()
        if src.is_file():
            dst = tree / f.decode()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for name in TOOL_FILES:
        dst = tree / "multigram/rebrand" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (HERE / name).is_file():
            shutil.copy2(HERE / name, dst)
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    git(tree, "add", "-A")
    git(tree, "-c", "user.name=selftest", "-c", "user.email=selftest@invalid",
        "-c", "commit.gpgsign=false", "commit", "-q", "-m", "baseline")
    return tree


def run(tree, *args):
    p = subprocess.run([sys.executable, str(tree / "multigram/rebrand/generate_rebrand.py")]
                       + list(args), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


_tool = {}


def tool(tree):
    """The generator module of the throwaway tree (for its constants and helpers)."""
    if "mod" not in _tool:
        import importlib.util
        path = tree / "multigram/rebrand/generate_rebrand.py"
        spec = importlib.util.spec_from_file_location("rebrand_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _tool["mod"] = mod
    return _tool["mod"]


def props(tree):
    return tool(tree).read_properties(tree / "multigram/rebrand/rebrand.properties")


def png_ok(path):
    b = path.read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return False, None
    i, idat, ihdr, last = 8, b"", None, None
    while i + 8 <= len(b) and last != b"IEND":     # (some upstream PNGs have bytes after IEND)
        ln = struct.unpack(">I", b[i:i + 4])[0]
        typ, data = b[i + 4:i + 8], b[i + 8:i + 8 + ln]
        crc = struct.unpack(">I", b[i + 8 + ln:i + 12 + ln])[0]
        if zlib.crc32(typ + data) & 0xffffffff != crc:
            return False, None
        if typ == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", data)
        elif typ == b"IDAT":
            idat += data
        last = typ
        i += 12 + ln
    if ihdr is None or last != b"IEND":
        return False, None
    w, h = ihdr[0], ihdr[1]
    raw = zlib.decompress(idat)
    rows_ok = len(raw) == h * (1 + 4 * w) and all(raw[y * (1 + 4 * w)] <= 4 for y in range(h))
    return rows_ok and ihdr[2:] == (8, 6, 0, 0, 0), (w, h)


def png_chunks(path, typ):
    b = path.read_bytes()
    i = 8
    while i + 8 <= len(b):
        ln = struct.unpack(">I", b[i:i + 4])[0]
        if b[i + 4:i + 8] == typ:
            yield b[i + 8:i + 8 + ln]
        i += 12 + ln


def upstream_icons(tree, targets):
    found = {}
    for g in ("TMessagesProj/src/*/res", "TMessagesProj_App/src/*/res"):
        for root in tree.glob(g):
            for d in root.iterdir():
                if not d.is_dir():
                    continue
                for f in d.iterdir():
                    name, _, ext = f.name.partition(".")
                    if (d.name.split("-", 1)[0], name) in targets:
                        size = png_ok(f)[1] if ext == "png" else None
                        found[(d.name, name)] = (ext, size)
    return found


def snapshot(tree):
    """Hashes of everything that makes up the identity (not the signing key)."""
    h = {}
    gen = tree / "multigram/rebrand/generated/res"
    for f in sorted(gen.rglob("*")):
        if f.is_file():
            h[f.relative_to(gen).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    for rel in PATCHED:
        h[rel] = hashlib.sha256((tree / rel).read_bytes()).hexdigest()
    p = {k: v for k, v in props(tree).items() if not k.startswith(("REBRAND_KEY", "REBRAND_STORE"))}
    h["properties"] = repr(sorted(p.items()))
    return h


def fingerprint(path, pw, alias):
    out = subprocess.run(["keytool", "-list", "-v", "-keystore", str(path), "-storepass", pw,
                          "-alias", alias], capture_output=True, text=True)
    m = re.search(r"SHA256:\s*([0-9A-F:]+)", out.stdout)
    ok = out.returncode == 0 and "PrivateKeyEntry" in out.stdout and m is not None
    return ok, (m.group(1) if m else None)


def status(tree, ignored=False):
    args = ["status", "--porcelain", "--untracked-files=all"] + (["--ignored"] if ignored else [])
    return sorted(git(tree, *args).splitlines())


def check_active(tree, label):
    p = props(tree)
    gen = tree / "multigram/rebrand/generated/res"
    app_id, name, acct = p.get("REBRAND_APPLICATION_ID"), p.get("REBRAND_APP_NAME"), p.get("REBRAND_ACCOUNT_TYPE")
    check(p.get("REBRAND_ACTIVE") == "true" and app_id and name, "%s: properties written" % label)
    check(bool(re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", app_id or "")),
          "%s: applicationId %s is a valid package" % (label, app_id))
    xml_ok = True
    for f in gen.rglob("*.xml"):
        try:
            ET.parse(f)
        except ET.ParseError:
            xml_ok = False
            print("      bad XML: %s" % f)
    check(xml_ok, "%s: every generated XML parses" % label)
    pngs = list(gen.rglob("*.png"))
    bad = [f for f in pngs if not png_ok(f)[0]]
    check(pngs and not bad, "%s: %d PNGs valid (signature, CRCs, IHDR, IDAT)" % (label, len(pngs)))

    targets = set(tool(tree).ICON_TARGETS)
    names = set(tool(tree).APP_NAME_STRINGS)
    up = upstream_icons(tree, targets)
    ours = {}
    for f in gen.rglob("*"):
        if f.is_file() and f.parent.name.split("-", 1)[0] in ("mipmap", "drawable"):
            n, _, ext = f.name.partition(".")
            if (f.parent.name.split("-", 1)[0], n) in targets:
                ours[(f.parent.name, n)] = (ext, png_ok(f)[1] if ext == "png" else None)
    check(up and set(up) == set(ours),
          "%s: overlay covers all %d upstream icon files in the same folders" % (label, len(up)))
    check(all(up[k] == ours.get(k) for k in up), "%s: same file type and pixel size as upstream" % label)
    adaptive_ok = True
    for (qdir, n), (ext, _) in ours.items():
        if ext == "xml" and qdir.startswith("mipmap-anydpi"):
            root = ET.parse(gen / qdir / (n + ".xml")).getroot()
            refs = [c.get(ANDROID + "drawable") for c in root]
            adaptive_ok &= root.tag == "adaptive-icon" and [c.tag for c in root] == [
                "background", "foreground", "monochrome"]
            adaptive_ok &= refs == ["@color/multigram_rebrand_icon_bg",
                                    "@drawable/multigram_rebrand_icon_fg",
                                    "@drawable/multigram_rebrand_icon_mono"]
    colors = ET.parse(gen / "values/rebrand_colors.xml").getroot()
    adaptive_ok &= any(c.get("name") == "multigram_rebrand_icon_bg" for c in colors)
    adaptive_ok &= (gen / "drawable/multigram_rebrand_icon_fg.xml").is_file()
    adaptive_ok &= (gen / "drawable/multigram_rebrand_icon_mono.xml").is_file()
    check(adaptive_ok, "%s: adaptive icons point at generated layers that exist" % label)
    shape, bg, fg = (p.get("REBRAND_ICON") or "? ? ?").split()
    splash = [(q, n) for (q, n), kind in ((k, tool(tree).ICON_TARGETS.get((k[0].split("-")[0], k[1])))
                                          for k in ours) if kind == "splash"]
    splash_ok = bool(splash)
    for q, n in splash:
        root = ET.parse(gen / q / (n + ".xml")).getroot()
        colors = [c.get(ANDROID + "fillColor") for c in root.iter("path")]
        splash_ok &= root.tag == "vector" and root.get(ANDROID + "viewportWidth") == "320" \
            and colors[:1] == [bg] and set(colors[1:]) == {fg}
    check(splash_ok, "%s: %d splash icons are vectors in the icon's colours" % (label, len(splash)))
    notif = [f for f in gen.rglob("notification.png")]
    notif_ok = bool(notif)
    for f in notif:
        size = png_ok(f)[1][0]
        raw = zlib.decompress(b"".join(c for c in png_chunks(f, b"IDAT")))
        rows = [raw[y * (1 + 4 * size) + 1:(y + 1) * (1 + 4 * size)] for y in range(size)]
        px = [r[i:i + 4] for r in rows for i in range(0, len(r), 4)]
        alphas = {q[3] for q in px}
        notif_ok &= all(q[:3] == b"\xff\xff\xff" for q in px) and 0 in alphas and 255 in alphas
    check(notif_ok, "%s: %d notification icons are white on transparent" % (label, len(notif)))
    flags = {e.get("name"): e.text for e in ET.parse(gen / "values/rebrand_flags.xml").getroot()}
    check(flags == {"multigram_rebrand_active": "true"}, "%s: overlay sets multigram_rebrand_active" % label)
    strings_ok = True
    for f in gen.glob("values*/rebrand_strings.xml"):
        got = {e.get("name"): e.text for e in ET.parse(f).getroot().iter("string")}
        strings_ok &= set(got) == names and all(
            v.replace("\\'", "'").replace('\\"', '"') == name for v in got.values())
    check(strings_ok and (gen / "values/rebrand_strings.xml").is_file(),
          "%s: AppName, AppNameBeta and AppNameFdroid are '%s'" % (label, name))

    java = (tree / PATCHED[0]).read_text(encoding="utf-8")
    xml_types = [ET.parse(tree / f).getroot().get(ANDROID + "accountType") for f in PATCHED[1:]]
    check(acct == app_id, "%s: account type derived from the applicationId" % label)
    check(java.count('"%s"' % acct) == 5 and '"org.telegram.messenger"' not in java
          and xml_types == [acct, acct],
          "%s: account type %s in Java (5x) and both XML files" % (label, acct))
    marker = tool(tree).PATCH_MARKER
    check(all(marker in (tree / f).read_text(encoding="utf-8") for f in PATCHED),
          "%s: the three patched files carry the patch marker" % label)
    check(status(tree) == sorted(" M " + f for f in PATCHED),
          "%s: git shows only the three patched files" % label)
    ign = [l for l in status(tree, True) if l.startswith("!!")]
    check("!! multigram/rebrand/rebrand.properties" in ign and all(
        l.startswith("!! multigram/rebrand/generated/")
        or l == "!! multigram/rebrand/rebrand.properties" for l in ign),
          "%s: everything generated is git-ignored" % label)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--keep", action="store_true", help="keep the throwaway tree")
    args = ap.parse_args()
    if (HERE / "rebrand.properties").exists() or (HERE / "generated").exists():
        print("This tree is rebranded; run generate_rebrand.py --clean first.")
        return 2
    have_keytool = shutil.which("keytool") is not None
    tmp = Path(tempfile.mkdtemp(prefix="rebrand-selftest-"))
    try:
        tree = build_tree(tmp)
        print("throwaway tree: %s" % tree)
        hook = (tree / "TMessagesProj_App/build.gradle").read_text(encoding="utf-8")
        check('apply from: "${rootDir}/multigram/rebrand/rebrand.gradle"' in hook,
              "TMessagesProj_App/build.gradle applies rebrand.gradle")
        base = hashlib.sha256(b"".join((tree / f).read_bytes() for f in PATCHED)).hexdigest()
        ks = [] if have_keytool else ["--no-keystore"]

        rc, out = run(tree, "--seed", "selftest-a", *ks)
        check(rc == 0, "seed A: generator succeeds")
        print("\n".join("      " + l for l in out.splitlines()[:6]))
        check("WARNING" not in out, "seed A: no warnings")
        pa = check_active(tree, "seed A")
        snap_a = snapshot(tree)
        fp_a = None
        if have_keytool:
            ok, fp_a = fingerprint(tree / pa["REBRAND_KEYSTORE"], pa["REBRAND_STORE_PASSWORD"],
                                   pa["REBRAND_KEY_ALIAS"])
            check(ok and pa["REBRAND_STORE_PASSWORD"] == pa["REBRAND_KEY_PASSWORD"],
                  "seed A: keystore opens with keytool and holds the key")

        rc, _ = run(tree, "--seed", "selftest-a", *ks)
        check(rc == 0 and snapshot(tree) == snap_a, "seed A again: identical identity")
        rerun = shlex.split(props(tree).get("REBRAND_RERUN", ""))
        rc, _ = run(tree, *rerun)
        check(rc == 0 and rerun[:2] == ["--seed", "selftest-a"] and snapshot(tree) == snap_a,
              "REBRAND_RERUN (%s) repeats the identity" % " ".join(rerun))
        if ks:
            run(tree, "--seed", "selftest-a", *ks)
        if have_keytool:
            p2 = props(tree)
            ok, fp2 = fingerprint(tree / p2["REBRAND_KEYSTORE"], p2["REBRAND_STORE_PASSWORD"],
                                  p2["REBRAND_KEY_ALIAS"])
            check(ok and fp2 != fp_a, "seed A again: a fresh signing key (not from the seed)")

        rc, _ = run(tree, "--seed", "selftest-b", *ks)
        check(rc == 0, "seed B: generator succeeds (re-patches from the backup)")
        pb = check_active(tree, "seed B")
        check(snapshot(tree) != snap_a and pb["REBRAND_APPLICATION_ID"] != pa["REBRAND_APPLICATION_ID"],
              "seed B: a different identity (%s, '%s')" % (pb["REBRAND_APPLICATION_ID"],
                                                         pb["REBRAND_APP_NAME"]))
        java = (tree / PATCHED[0]).read_text(encoding="utf-8")
        check('"%s"' % pa["REBRAND_ACCOUNT_TYPE"] not in java, "seed B: nothing of seed A left in the Java file")

        rc, _ = run(tree, "--seed", "selftest-b", "--no-account-type", "--no-keystore")
        check(rc == 0 and status(tree) == [] and "REBRAND_ACCOUNT_TYPE" not in props(tree),
              "--no-account-type: the three files are back to stock")

        rc, _ = run(tree, "--app-name", "Telegram Lite", "--no-keystore")
        check(rc == 1, "refuses an app name with 'Telegram' in it")
        rc, _ = run(tree, "--application-id", "org.telegram.lite", "--no-keystore")
        check(rc == 1, "refuses an applicationId in org.telegram")
        rc, _ = run(tree, "--application-id", "Not A Package", "--no-keystore")
        check(rc == 1, "refuses an invalid applicationId")
        rc, _ = run(tree, "--application-id", "com.facebook.orca", "--no-keystore")
        check(rc == 1, "refuses an applicationId in another vendor's namespace")
        rc, _ = run(tree, "--app-name", "Facebook Lite", "--no-keystore")
        check(rc == 1, "refuses another app's name")
        odd = "Tom's <Chat> & \"Co\" #1 \u00e9"
        rc, _ = run(tree, "--app-name", odd, "--no-keystore", "--seed", "x")
        check(rc == 0 and props(tree).get("REBRAND_APP_NAME") == odd,
              "escapes an app name with quotes, <, >, &, # and non-ASCII")
        if rc == 0:
            check_active(tree, "escaped name")
            snap = snapshot(tree)
            rc, _ = run(tree, *shlex.split(props(tree).get("REBRAND_RERUN", "")))
            check(rc == 0 and snapshot(tree) == snap, "REBRAND_RERUN repeats an escaped --app-name")

        if have_keytool:
            ext = tmp / "keys" / "mine.keystore"
            rc, _ = run(tree, "--seed", "selftest-a", "--keystore", str(ext))
            p1 = props(tree)
            ok1, f1 = fingerprint(ext, p1.get("REBRAND_STORE_PASSWORD", ""), p1.get("REBRAND_KEY_ALIAS", ""))
            rc2, _ = run(tree, "--seed", "selftest-b", "--keystore", str(ext))
            p2 = props(tree)
            ok2, f2 = fingerprint(ext, p2.get("REBRAND_STORE_PASSWORD", ""), p2.get("REBRAND_KEY_ALIAS", ""))
            check(rc == 0 and rc2 == 0 and ok1 and ok2 and f1 == f2
                  and p2.get("REBRAND_KEYSTORE") == str(ext.resolve()),
                  "--keystore: created once, then reused (same certificate)")
            rc, _ = run(tree, "--keystore", str(tree / "inside.keystore"))
            check(rc == 1, "--keystore refuses a path inside the repository")

        run(tree, "--seed", "selftest-a", "--no-keystore")
        auth = tree / PATCHED[1]
        auth.write_bytes(auth.read_bytes() + b"\n")
        rc, _ = run(tree, "--clean")
        check(rc == 1 and (tree / "multigram/rebrand/rebrand.properties").exists(),
              "--clean refuses to overwrite a patched file that was edited since")
        rc, _ = run(tree, "--seed", "selftest-b", "--no-keystore")
        check(rc == 1 and props(tree).get("REBRAND_SEED") == "selftest-a",
              "a new seed refuses to take an edited patched file as the original")
        git(tree, "checkout", "--", PATCHED[1])
        rc, _ = run(tree, "--seed", "selftest-b", "--no-keystore")
        check(rc == 0 and ET.parse(auth).getroot().get(ANDROID + "accountType")
              == props(tree).get("REBRAND_ACCOUNT_TYPE"),
              "a patched file restored by git is patched again from the stock original")

        # generated/ lost while the three files are still patched
        shutil.rmtree(tree / "multigram/rebrand/generated")
        rc, out = run(tree, "--seed", "selftest-a", "--no-keystore")
        check(rc == 1 and "git checkout" in out,
              "a new run refuses files patched by a rebrand whose backup is gone")
        rc, out = run(tree, "--clean")
        check(rc == 1 and "git checkout -- " in out and status(tree) == sorted(" M " + f for f in PATCHED)
              and (tree / "multigram/rebrand/rebrand.properties").exists(),
              "--clean without a backup refuses and names git checkout, changing nothing")
        git(tree, "checkout", "--", *PATCHED)
        rc, _ = run(tree, "--clean")
        check(rc == 0 and status(tree, True) == [], "--clean succeeds once git restored the files")
        run(tree, "--seed", "selftest-a", "--no-keystore")

        rc, _ = run(tree, "--clean")
        after = hashlib.sha256(b"".join((tree / f).read_bytes() for f in PATCHED)).hexdigest()
        check(rc == 0 and status(tree, True) == [] and after == base,
              "--clean: git status clean (incl. ignored files), files byte-identical")
        check(subprocess.run(["git", "-C", str(tree), "diff", "--quiet", "HEAD"]).returncode == 0,
              "--clean: no difference to the commit")
        if have_keytool:
            check((tmp / "keys" / "mine.keystore").is_file(), "--clean keeps a --keystore key")
        rc, _ = run(tree, "--clean")
        check(rc == 0 and status(tree, True) == [], "--clean twice is harmless")
    finally:
        if args.keep:
            print("kept %s" % tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    if not have_keytool:
        print("note: keytool not found, signing checks skipped")
    print("\n%s: %d failure(s)" % ("FAILED" if failures else "PASSED", len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
