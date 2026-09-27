#!/usr/bin/env python3
"""Regenerate TMessagesProj/src/main/assets/multigram_styles.bin, the table of validated per-install styles.

  python3 multigram/tools/make_style_table.py                  write the asset (same bytes on every run)
  python3 multigram/tools/make_style_table.py --check          regenerate in memory, compare with the asset
  python3 multigram/tools/make_style_table.py --report r.json  also write per-theme statistics

For each base theme, candidate k uses the seed "<TABLE_SEED>/<theme>/<k>" (style_table.candidate_seed) and the
simulator's seeded solver (up to 12 attempts).  Candidates are taken in k order; a candidate is kept when the
solver finds a style that passes every readability pair (headroom thresholds on the pairs the style controls,
plain WCAG on the palette-limited pairs) and no earlier entry of that theme has the same accent colour, until
PER_THEME records per theme.  The result does not depend on --procs.  Format: README.md next to this file.

The generator gives up instead of running on when a theme's yield collapses (no entry from the first
STALL_CANDIDATES candidates, a yield below --min-yield, or more than per_theme / min_yield + STALL_CANDIDATES
candidates): it prints the pairs that failed most often and exits with status 4.

Exit status: 0 written / identical, 3 --check found a different asset, 4 the yield collapsed, 1 on errors.
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

import style_table as T       # noqa: E402  (puts sim/ on sys.path)
import detmath as D           # noqa: E402
import readability as R       # noqa: E402

CHUNK = 64
STALL_CANDIDATES = 256        # first round per theme; no entry from these = stalled
YIELD_CANDIDATES = 1024       # the yield test starts after this many candidates of a theme
MIN_YIELD = 0.2               # default --min-yield (today's yield is 0.94 to 0.99)
EXIT_STALLED = 4


class Stalled(RuntimeError):
    pass


def _work(job):
    theme_name, k0, k1, mode, thr = job
    m, _, _ = T.model(mode)
    out = []
    for k in range(k0, k1):
        v, res, st = T.gen_candidate(m, theme_name, k, thr)
        if v is None:
            out.append((k, None, st.get("reject", {}), st["evals"], 0))
            continue
        rec = T.encode_record(v)
        # the record must decode to exactly the style that was validated
        full = [res[i] for i in range(len(R.PAIRS))]
        if T.evaluate(m, T.decode_record(rec, theme_name)) != full:
            raise RuntimeError("record round trip changed the evaluation: %s candidate %d" % (theme_name, k))
        out.append((k, rec, full, st["evals"], v["solver"]["attempt"]))
    return theme_name, k0, out


def stall_report(t, inf, n_accepted, min_yield):
    c = inf["candidates"]
    rej = inf["reject"]
    stages = sorted(((n, k[1:-1]) for k, n in rej.items() if k.startswith("<")), reverse=True)
    pairs = sorted(((n, k) for k, n in rej.items() if not k.startswith("<")), reverse=True)[:8]
    return ("%s: %d entries from %d candidates (yield %.1f %%, minimum %.0f %%). Failed attempts of the rejected candidates "
            "by stage: %s. Pairs failing most often: %s. A pair the style cannot move is below its threshold, or the "
            "headroom cannot be reached any more: run check_style_table.py and see README.md." % (
                t, n_accepted, c, 100.0 * n_accepted / max(1, c), 100.0 * min_yield,
                ", ".join("%s %d" % (k, n) for n, k in stages) or "none",
                ", ".join("%s %d" % (k, n) for n, k in pairs) or "none"))


def generate(per_theme, procs, mode="auto", log=print, min_yield=MIN_YIELD):
    m, mode, state = T.model(mode)
    for tn in T.TABLE_THEMES:
        if tn not in m.themes:
            raise SystemExit("base theme %r is not a bundled theme in this tree" % tn)
    log("overlay A (%s): %s mode, %d/%d overlay values already in the tree, out-text guard %s" % (
        T.overlay_path(), mode, state["values_in_tree"], state["values"],
        "present" if state["out_block_guard"] else "absent"))
    thresholds = {t: T.headroom_thresholds(m.themes[t]) for t in T.TABLE_THEMES}
    for t in T.TABLE_THEMES:
        lim = sorted(T.palette_limited(m.themes[t]))
        log("  %s: %d palette-limited pairs held to plain WCAG: %s" % (t, len(lim), ", ".join(R.PAIRS[i]["name"] for i in lim)))
    accepted = {t: [] for t in T.TABLE_THEMES}
    results = {t: [] for t in T.TABLE_THEMES}
    seen = {t: set() for t in T.TABLE_THEMES}
    info = {t: {"candidates": 0, "solver_failed": 0, "duplicates": 0, "evals": 0, "attempts": {}, "reject": {}} for t in T.TABLE_THEMES}
    cap = int(math.ceil(per_theme / min_yield)) + STALL_CANDIDATES
    next_k = {t: 0 for t in T.TABLE_THEMES}
    pool = None
    if procs > 1:
        from multiprocessing import Pool
        pool = Pool(procs)
    t0 = time.time()
    try:
        while True:
            open_themes = [t for t in T.TABLE_THEMES if len(accepted[t]) < per_theme]
            if not open_themes:
                break
            stalled = []
            for t in open_themes:
                c, a = info[t]["candidates"], len(accepted[t])
                if (c >= STALL_CANDIDATES and a == 0) or (c >= YIELD_CANDIDATES and a < min_yield * c) or c >= cap:
                    stalled.append(stall_report(t, info[t], a, min_yield))
            if stalled:
                raise Stalled("\n".join(stalled))
            jobs = []
            for t in open_themes:
                want = per_theme - len(accepted[t])
                c = info[t]["candidates"]
                # round size from the yield so far (the first round is small, so a stall shows early); the output
                # does not depend on it: candidates are always taken in k order
                y = max(min_yield, len(accepted[t]) / c) if c else 1.0
                n = int(math.ceil((want / y * 1.05 + 8) / CHUNK)) * CHUNK
                if not c:
                    n = min(n, STALL_CANDIDATES)
                left = int(math.ceil(max(0, cap - next_k[t]) / CHUNK)) * CHUNK
                n = max(CHUNK, min(n, left))
                for k0 in range(next_k[t], next_k[t] + n, CHUNK):
                    jobs.append((t, k0, k0 + CHUNK, mode, thresholds[t]))
                next_k[t] += n
            done = pool.map(_work, jobs, chunksize=1) if pool else [_work(j) for j in jobs]
            done.sort(key=lambda x: (T.TABLE_THEMES.index(x[0]), x[1]))
            for t, _, out in done:
                for k, rec, res, evals, attempt in out:
                    if len(accepted[t]) >= per_theme:
                        break
                    inf = info[t]
                    inf["candidates"] += 1
                    inf["evals"] += evals
                    if rec is None:
                        inf["solver_failed"] += 1
                        for key, cnt in res.items():
                            inf["reject"][key] = inf["reject"].get(key, 0) + cnt
                        continue
                    accent = rec[:4]                  # accentColor: every entry of a theme has its own
                    if accent in seen[t]:
                        inf["duplicates"] += 1
                        continue
                    seen[t].add(accent)
                    accepted[t].append(rec)
                    results[t].append(res)
                    inf["attempts"][attempt] = inf["attempts"].get(attempt, 0) + 1
            log("  %.1f s: %s" % (time.time() - t0, ", ".join("%s %d" % (t, len(accepted[t])) for t in T.TABLE_THEMES)))
    finally:
        if pool:
            pool.close()
            pool.join()
    themes = [(t, m.themes[t].is_dark) for t in T.TABLE_THEMES]
    data = T.build_asset(accepted, themes)
    return data, accepted, results, info, m


def _count(d, k):
    d[k] = d.get(k, 0) + 1


def statistics(m, accepted, results, info):
    """Per-theme report: yield, smallest margins, variety."""
    rep = {}
    for t in T.TABLE_THEMES:
        th = m.themes[t]
        own = T.palette_limited(th)
        hthr = T.headroom_thresholds(th)
        cls = {}
        owned_min = {}
        for res in results[t]:
            for i, p in enumerate(R.PAIRS):
                key = ("palette-limited " if i in own else "") + T.CLASS_NAME[p["threshold"]]
                r = res[i] / p["threshold"]
                if key not in cls or r < cls[key][0]:
                    cls[key] = (r, p["name"], res[i])
                if i in own:
                    lo_hi = owned_min.setdefault(p["name"], [res[i], res[i]])
                    lo_hi[0], lo_hi[1] = min(lo_hi[0], res[i]), max(lo_hi[1], res[i])
        headroom_ok = all(res[i] >= hthr[i] for res in results[t] for i in range(len(R.PAIRS)))
        var = {"hue_bins": {}, "bubble_colours": {}, "wall_colours": {}, "animated": 0, "motion": 0, "rotations": {},
               "light_bubbles": 0, "accent_L": [9.0, 0.0]}
        for rec in accepted[t]:
            v = T.decode_record(rec, t)
            a = v["accent"]
            L, _, h = D.rgb8_to_oklch((a >> 16) & 0xFF, (a >> 8) & 0xFF, a & 0xFF)
            _count(var["hue_bins"], "%03d" % (int(h // 30) % 12 * 30))
            var["accent_L"] = [min(var["accent_L"][0], L), max(var["accent_L"][1], L)]
            g = v["my_messages_gradient"]
            _count(var["bubble_colours"], 1 if (len(g) == 1 and g[0] == v["my_messages_accent"]) else 1 + len(g))
            _count(var["wall_colours"], len(v["wallpaper"]["colors"]))
            var["animated"] += 1 if v["my_messages_animated"] else 0
            var["motion"] += 1 if v["wallpaper"]["motion"] else 0
            _count(var["rotations"], v["wallpaper"]["rotation"])
            var["light_bubbles"] += 1 if D.luminance(v["my_messages_accent"] & 0xFFFFFF) > 0.4 else 0
        inf = info[t]
        rep[t] = {
            "dark": th.is_dark, "records": len(accepted[t]), "candidates": inf["candidates"],
            "solver_failed": inf["solver_failed"], "duplicate_accents": inf["duplicates"],
            "evals_per_candidate": round(inf["evals"] / max(1, inf["candidates"]), 2),
            "attempts": {str(k): v for k, v in sorted(inf["attempts"].items())},
            "all_pairs_meet_generator_thresholds": headroom_ok,
            "min_contrast_over_wcag": {k: {"ratio": round(v[0], 4), "pair": v[1], "contrast": round(v[2], 4)} for k, v in sorted(cls.items())},
            "palette_limited_pairs_min_max": {k: [round(v[0], 3), round(v[1], 3)] for k, v in sorted(owned_min.items())},
            "accent_hue_bins_of_30deg": dict(sorted(var["hue_bins"].items())),
            "accent_oklch_L_range": [round(x, 3) for x in var["accent_L"]],
            "bubble_colours": {str(k): v for k, v in sorted(var["bubble_colours"].items())},
            "light_bubbles": var["light_bubbles"], "animated_bubbles": var["animated"],
            "wallpaper_colours": {str(k): v for k, v in sorted(var["wall_colours"].items())},
            "parallax_motion": var["motion"], "rotations": {str(k): v for k, v in sorted(var["rotations"].items())},
        }
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=T.DEFAULT_ASSET, help="asset path (default: %(default)s)")
    ap.add_argument("--check", action="store_true", help="compare with the asset at --out instead of writing it")
    ap.add_argument("--per-theme", type=int, default=T.PER_THEME)
    ap.add_argument("--procs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--overlay", choices=T.OVERLAY_MODES, default="auto",
                    help="auto (default): detect whether the tree already carries overlay A; see style_table.build_model()")
    ap.add_argument("--report", help="write per-theme statistics as JSON to this path")
    ap.add_argument("--min-yield", type=float, default=MIN_YIELD,
                    help="give up when fewer than this share of a theme's candidates become entries (default %(default)s)")
    a = ap.parse_args()
    if not 0.0 < a.min_yield <= 1.0:
        ap.error("--min-yield must be in (0, 1]")
    t0 = time.time()
    try:
        data, accepted, results, info, m = generate(a.per_theme, a.procs, a.overlay, min_yield=a.min_yield)
    except Stalled as e:
        print("STALLED: the generator cannot build the table on these theme sources:\n%s" % e)
        sys.exit(EXIT_STALLED)
    rep = statistics(m, accepted, results, info)
    for t, r in rep.items():
        print("%-12s %s %5d records from %5d candidates (%d solver failures, %d repeated accents), generator thresholds met: %s, "
              "accent hues per 30 deg: %s" % (t, "night" if r["dark"] else "day  ", r["records"], r["candidates"], r["solver_failed"],
                                              r["duplicate_accents"], r["all_pairs_meet_generator_thresholds"],
                                              "/".join(str(x) for x in r["accent_hue_bins_of_30deg"].values())))
        for k, v in r["min_contrast_over_wcag"].items():
            print("    min %-26s %.4f x WCAG  (%s %.3f)" % (k, v["ratio"], v["pair"], v["contrast"]))
    if a.report:
        with open(a.report, "w") as f:
            json.dump(rep, f, indent=1, sort_keys=True)
    digest = hashlib.sha256(data).hexdigest()
    print("asset: %d bytes, %d records, sha256 %s (%.1f s)" % (len(data), sum(len(v) for v in accepted.values()), digest, time.time() - t0))
    if a.check:
        try:
            with open(a.out, "rb") as f:
                old = f.read()
        except OSError as e:
            print("cannot read %s: %s" % (a.out, e))
            sys.exit(1)
        if old != data:
            print("DIFFERS from %s (sha256 %s)" % (a.out, hashlib.sha256(old).hexdigest()))
            sys.exit(3)
        print("identical to %s" % a.out)
        return
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "wb") as f:
        f.write(data)
    print("wrote %s" % a.out)


if __name__ == "__main__":
    main()
