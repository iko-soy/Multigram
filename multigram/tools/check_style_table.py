#!/usr/bin/env python3
"""Check TMessagesProj/src/main/assets/multigram_styles.bin against its format and against the theme sources
in this tree (run by check.sh on CI).

  python3 multigram/tools/check_style_table.py [--asset PATH] [--procs N] [--sample N] [--overlay MODE]

1. Format: header, directory and every record follow README.md; theme keys are bundled base themes of this
   tree with the right day/night flag; no two entries of a theme share an accent colour.
2. Model self-test: the model gives the same 99 contrasts whether overlay A is applied by the simulator or is
   already written into the sources (as the palette fix does), and the per-key palette replay agrees with the
   full refreshThemeColors port, on a deterministic sample of entries.
3. Readability: every entry (or a deterministic sample of --sample N) is re-evaluated on the current theme
   sources plus overlay A.  Any pair below its WCAG threshold (4.5 text, 3.0 non-text, 1.15 bubble vs
   wallpaper) fails the check; pairs that only lost the generator's headroom are reported as warnings, and
   palette-limited pairs (held only to WCAG, style_table.palette_limited) are counted in a note.

Exit status 0 when everything passes (warnings allowed), 1 otherwise.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import style_table as T       # noqa: E402  (puts sim/ on sys.path)
import readability as R       # noqa: E402
import tgsrc                  # noqa: E402

SELF_TEST_ENTRIES = 250       # entries compared across the overlay modes
FULL_PORT_ENTRIES = 25        # entries compared lazy vs full palette


class Report:
    def __init__(self):
        self.failures = []
        self.warnings = []

    def fail(self, msg):
        self.failures.append(msg)
        print("FAIL: " + msg)

    def warn(self, msg):
        self.warnings.append(msg)
        print("WARNING: " + msg)


def check_format(data, m, rep):
    """-> [(theme name, [record bytes])] or None when the file cannot be parsed."""
    try:
        hdr, dirs, recs = T.parse_asset(data)
    except T.FormatError as e:
        rep.fail("asset format: %s" % e)
        return None
    print("format: magic %s, version %d, %d base themes, %d records of %d bytes, CRC-32 %08X, %d bytes" % (
        hdr["magic"].decode(), hdr["version"], hdr["theme_count"], hdr["record_count"], hdr["record_size"], hdr["crc32"], len(data)))
    out = []
    kinds = set()
    for d in dirs:
        name = d["name"]
        th = m.themes.get(name)
        if th is None:
            rep.fail("theme %r is not one of this tree's bundled base themes (%s)" % (name, ", ".join(sorted(m.themes))))
            continue
        if d["dark"] != th.is_dark:
            rep.fail("theme %s: dark flag %s, but the theme is %s" % (name, d["dark"], "dark" if th.is_dark else "light"))
        kinds.add(th.is_dark)
        rs = recs[d["first"]: d["first"] + d["count"]]
        bad = 0
        for j, b in enumerate(rs):
            probs = T.record_problems(b)
            if probs:
                bad += 1
                if bad <= 5:
                    rep.fail("%s entry %d: %s" % (name, j, "; ".join(probs)))
        if bad > 5:
            rep.fail("%s: %d malformed entries in all" % (name, bad))
        accents = [b[:4] for b in rs]
        if len(set(accents)) != len(accents):
            rep.fail("%s: %d entries repeat an accent colour" % (name, len(accents) - len(set(accents))))
        presets = set(T.u32(c) for c in T.forbidden_accents(th))
        clash = sum(1 for b in rs if int.from_bytes(b[:4], "big") in presets)
        if clash:
            rep.warn("%s: %d entries use a built-in preset accent colour of this tree" % (name, clash))
        if d["count"] != T.PER_THEME:
            rep.warn("%s: %d entries, the generator makes %d" % (name, d["count"], T.PER_THEME))
        print("  %-12s %-5s %5d entries (records %d-%d)" % (name, "night" if th.is_dark else "day", d["count"], d["first"], d["first"] + d["count"] - 1))
        out.append((name, rs))
    if kinds != {False, True}:
        rep.fail("the table needs at least one day and one night base theme")
    return out


def sample_indices(n, k):
    """k evenly spread indices out of n (all when k >= n)."""
    if k >= n:
        return list(range(n))
    return sorted(set((i * n) // k for i in range(k)))


def parser_self_test(parsed, rep):
    """The parser must recognise every form of the out-text guard (T.GUARD_FORMS, including the palette fix's real
    line) and parse the rest of Theme.java the same way with each."""
    ref = dict(parsed["theme_java"])
    ref.pop("out_block_guard_id_gt_100", None)
    ok = True
    for label, line, widened in T.GUARD_FORMS:
        try:
            tj = T.parse_theme_java_with_guard(line)
        except ValueError as e:
            rep.fail("self-test: Theme.java with the %s out-text guard does not parse: %s; update sim/tgsrc.py" % (label, e))
            ok = False
            continue
        got = tj.pop("out_block_guard_id_gt_100", None)
        if got != widened:
            rep.fail("self-test: the parser reads the %s out-text guard as %s; update sim/tgsrc.py OUT_BLOCK_GUARD_RE" % (
                label, "widened" if got else "stock"))
            ok = False
        elif tj != ref:
            rep.fail("self-test: Theme.java parses differently with the %s out-text guard" % label)
            ok = False
    print("self-test: out-text guard forms (%s): %s" % (", ".join(f[0] for f in T.GUARD_FORMS), "recognised" if ok else "NOT RECOGNISED"))
    return ok


def self_test(entries, mode, rep):
    parsed = tgsrc.load()
    if not parser_self_test(parsed, rep):
        return
    baked = T.baked_parsed(parsed)
    models = {
        "simulator applies overlay A to this tree": T.build_model(parsed, "apply"),
        "simulator applies overlay A to this tree with overlay A written in": T.build_model(baked, "apply"),
        "overlay A written in, simulator adds only the Java parts": T.build_model(baked, "in-tree"),
    }
    flat = [(name, b) for name, rs in entries for b in rs]
    picks = [flat[i] for i in sample_indices(len(flat), SELF_TEST_ENTRIES)]
    ref_name = None
    ref = None
    idempotent = True
    for label, mm in models.items():
        res = [T.evaluate(mm, T.decode_record(b, name)) for name, b in picks]
        if ref is None:
            ref_name, ref = label, res
            continue
        diff = sum(1 for a, b in zip(ref, res) if a != b)
        if diff:
            idempotent = False
            rep.fail("self-test: %d/%d entries evaluate differently with '%s' than with '%s'; the overlay application is "
                     "not idempotent, fix style_table.build_model()" % (diff, len(picks), label, ref_name))
    if mode == "in-tree":
        mm = T.build_model(parsed, "in-tree")
        res = [T.evaluate(mm, T.decode_record(b, name)) for name, b in picks]
        diff = sum(1 for a, b in zip(ref, res) if a != b)
        if diff:
            rep.warn("self-test: this tree carries the palette fix but differs from overlay A (%d/%d sampled entries evaluate "
                     "differently); the tree's own values are used" % (diff, len(picks)))
    m, _, _ = T.model(mode)
    lazy_full = 0
    full_picks = [picks[i] for i in sample_indices(len(picks), FULL_PORT_ENTRIES)]
    for name, b in full_picks:
        v = T.decode_record(b, name)
        if T.evaluate(m, v, lazy=True) != T.evaluate(m, v, lazy=False):
            lazy_full += 1
    if lazy_full:
        rep.fail("self-test: per-key palette replay and the full refreshThemeColors port disagree on %d/%d entries" % (lazy_full, len(full_picks)))
    print("self-test: overlay A applied by the simulator vs already in the sources, %d entries: %s; per-key replay vs full "
          "port, %d entries: %s" % (len(picks), "identical" if idempotent else "DIFFERENT", len(full_picks),
                                    "identical" if not lazy_full else "DIFFERENT"))


def _validate(job):
    name, idx, recs, mode, hthr = job
    m, _, _ = T.model(mode)
    wcag = T.wcag_thresholds()
    out = []
    for j, b in zip(idx, recs):
        res = T.evaluate(m, T.decode_record(b, name))
        below = [i for i in range(len(R.PAIRS)) if res[i] < wcag[i]]
        eroded = [i for i in range(len(R.PAIRS)) if res[i] < hthr[i] and res[i] >= wcag[i]]
        out.append((j, res, below, eroded))
    return name, out


def check_readability(entries, mode, procs, sample, rep):
    m, _, _ = T.model(mode)
    jobs = []
    for name, rs in entries:
        idx = sample_indices(len(rs), sample) if sample else list(range(len(rs)))
        hthr = T.headroom_thresholds(m.themes[name])
        step = 256
        for s in range(0, len(idx), step):
            part = idx[s: s + step]
            jobs.append((name, part, [rs[j] for j in part], mode, hthr))
    if procs > 1:
        from multiprocessing import Pool
        with Pool(procs) as pool:
            done = pool.map(_validate, jobs, chunksize=1)
    else:
        done = [_validate(j) for j in jobs]
    by = {}
    for name, out in done:
        by.setdefault(name, []).extend(out)
    for name, _ in entries:
        th = m.themes[name]
        lim = T.palette_limited(th)
        out = by.get(name, [])
        mins = {}
        n_below = n_eroded = n_limited = 0
        worst = {}
        eroded_pairs = {}
        limited_pairs = set()
        for j, res, below, eroded in out:
            short = [i for i in lim if res[i] < T.HEADROOM[R.PAIRS[i]["threshold"]]]
            if short:
                n_limited += 1
                limited_pairs.update(R.PAIRS[i]["name"] for i in short)
            for i, p in enumerate(R.PAIRS):
                key = ("palette-limited " if i in lim else "") + T.CLASS_NAME[p["threshold"]]
                r = res[i] / p["threshold"]
                if key not in mins or r < mins[key][0]:
                    mins[key] = (r, p["name"], res[i], j)
            if below:
                n_below += 1
                for i in below:
                    if i not in worst or res[i] < worst[i][0]:
                        worst[i] = (res[i], j)
            if eroded and not below:
                n_eroded += 1
                for i in eroded:
                    eroded_pairs[R.PAIRS[i]["name"]] = eroded_pairs.get(R.PAIRS[i]["name"], 0) + 1
        print("  %-12s %5d entries checked: %d below WCAG, %d more below the generator's thresholds" % (name, len(out), n_below, n_eroded))
        if n_limited:
            print("      note: %d entries have palette-limited pairs held only to WCAG, below the %s headroom (%s); only the "
                  "palette fix can give them headroom (README.md, \"Readability rule\")" % (
                      n_limited, "/".join("%g" % T.HEADROOM[t] for t in sorted(T.HEADROOM, reverse=True)), ", ".join(sorted(limited_pairs))))
        for k in sorted(mins):
            r, pn, c, j = mins[k]
            print("      min %-26s %.4f x WCAG  (%s %.3f, entry %d)" % (k, r, pn, c, j))
        if n_below:
            rep.fail("%s: %d entries are unreadable on the current theme sources: %s" % (name, n_below, ", ".join(
                "%s %.3f < %.2f (entry %d)" % (R.PAIRS[i]["name"], c, R.PAIRS[i]["threshold"], j) for i, (c, j) in sorted(worst.items()))))
        if n_eroded:
            rep.warn("%s: %d entries lost the generator's headroom but still pass WCAG (%s); regenerate the table with "
                     "make_style_table.py" % (name, n_eroded, ", ".join("%s x%d" % kv for kv in sorted(eroded_pairs.items()))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asset", default=T.DEFAULT_ASSET)
    ap.add_argument("--procs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--sample", type=int, default=0, help="entries to re-validate per theme (default 0: all of them)")
    ap.add_argument("--overlay", choices=T.OVERLAY_MODES, default="auto",
                    help="auto (default): detect whether the tree already carries overlay A; see style_table.build_model()")
    a = ap.parse_args()
    t0 = time.time()
    rep = Report()
    try:
        with open(a.asset, "rb") as f:
            data = f.read()
    except OSError as e:
        print("FAIL: cannot read %s: %s" % (a.asset, e))
        sys.exit(1)
    m, mode, state = T.model(a.overlay)
    print("theme sources: %s; overlay A: %s; %s mode (%d/%d overlay values already in the tree, out-text guard %s)" % (
        tgsrc.REPO, T.overlay_path(), mode, state["values_in_tree"], state["values"], "present" if state["out_block_guard"] else "absent"))
    if mode == "in-tree" and not state["out_block_guard"]:
        rep.warn("the tree carries overlay A's values but not the palette fix's out-text guard in Theme.java "
                 "(`if (!isMyMessagesGradientColorsNear || ...PaletteFix.isRuntimeAccent(this))`)")
    if mode == "in-tree" and state["differs"]:
        rep.warn("the tree carries the palette fix but %d values differ from overlay A, e.g. %s" % (len(state["differs"]), state["differs"][0]))
    entries = check_format(data, m, rep)
    if entries:
        self_test(entries, mode, rep)
        check_readability(entries, mode, a.procs, a.sample, rep)
    print("style table check: %s (%d failures, %d warnings, %.1f s)" % (
        "FAIL" if rep.failures else "PASS", len(rep.failures), len(rep.warnings), time.time() - t0))
    sys.exit(1 if rep.failures else 0)


if __name__ == "__main__":
    main()
