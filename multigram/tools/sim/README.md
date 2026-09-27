# Style simulator

A Python port of Telegram Android's accent engine (Theme.java `fillAccentColors`, the 30-degree
re-tint in `changeColorAccent`, outgoing-bubble and wallpaper code, the service pill), written against
DrKLO Telegram dc780e81ed1261c369c27870e8e0999a1eb0b600 and adapted to Forkgram (its Monet themes; the
palette fix's out-text guard, `|| PaletteFix.isRuntimeAccent(this)` or the research form `|| id > 100`,
which mean the same for a generated accent), plus a 99-pair readability model and the seeded style
generator. MultiGram uses it to build and check the per-install style table (see `../README.md`).

Python 3.9+, standard library only.

## Setup

None. The engine reads Theme.java, ThemeColors.java and the five bundled `.attheme` files straight from
the repository this folder lives in (`TG_REPO`, default: three levels up, the repository root). Point
`TG_REPO` at another checkout to model that one instead.

The parsed sources are cached in `cache/`, keyed by a hash of those files, so a changed tree re-parses
automatically; a cache file is written under a temporary name and renamed, and an unreadable one is
parsed again. The cache is not committed (`../.gitignore`).

The palette fix the style table relies on, "overlay A", is in `palette-fix/overlay_A.json`; overlay B
(`overlay_B.json`, the rejected variant) is kept for the comparisons below.

## Commands

Run these from this folder.

| What | Command |
|---|---|
| One install's style on the fixed palette (overlay A) | `python3 -c "import json, canvas as CV, style_sim as S; S.RULE['rule']='wcag'; print(json.dumps(S.genome('my-seed', mode='wcag', m=CV.overlay('A')), indent=1))"` |
| One install's style on the stock palette ("no worse than stock") | `python3 style_sim.py --seed my-seed --mode strict` |
| Measure N installs per base theme on the fixed palette | `python3 canvas.py --measure 5000 --variant A` |
| Same, with ablations | `--variant B`, `B-no-c` (no on-accent hook), `B-no-d` (no bubble guard); `--service off` drops the date-pill rule |
| Stock default accents, stock vs fixed palette | `python3 canvas.py --stock` |
| Rebuild the overlay from scratch | `python3 canvas.py --build` (writes `palette-fix/overlay_*.json`) |
| Stock-palette measurement (naive vs constrained generators) | `python3 style_sim.py --measure 5000` |
| Stock contrast table for all pairs | `python3 style_sim.py --baseline` |

`canvas.py` reads and writes `palette-fix/` by default; set `CANVAS_OUT` to use another folder.
`--procs N` sets worker processes for measurements.

The style table itself is made and checked by `../make_style_table.py` and `../check_style_table.py`,
which use this simulator as a library (`../style_table.py`).

## How it generates a style

- Seed: SHA-256 of the seed string, first 8 bytes big-endian, into SplitMix64. Three forks: day,
  night, misc. The same seed gives the same style on every machine (math is done in `detmath.py`, so no
  platform floating-point differences).
- Colour space: OKLCH. The accent, bubble and wallpaper are drawn inside bands, then lightness is
  solved (up to 8 bisection steps, up to 12 attempts) until every pair passes. If nothing passes, the
  stock accent is used; on the fixed palette that never happened in 125,000 installs.
- Rules: `strict` = every pair at least `min(WCAG threshold, stock contrast)`; `wcag` = plain WCAG
  (4.5 text, 3.0 non-text, 1.15 bubble vs wallpaper, 4.5 date-pill text).

## Limits

- The solver lands exactly on the threshold. The style table therefore solves against 4.6 / 3.1 / 1.19
  instead (`../README.md`, "Readability rule").
- `genome()` and the measurements may pick one of the built-in pattern wallpapers. A real Telegram
  pattern slug makes the app fetch it from Telegram's servers (`account.installWallPaper`), so the style
  table never uses patterns: its generator draws no pattern and validates the plain gradient.
- The bubble-vs-wallpaper 1.15:1 floor is a project threshold, not WCAG.
- Only a device build confirms the result.
