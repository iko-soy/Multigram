# MultiGram tools

Python 3.9+ and bash, standard library only. Run everything from the repository root.

| File | What it does |
|---|---|
| `check.sh` | The checks CI runs after the compile (`bash multigram/tools/check.sh`). About a minute locally on 4 cores, 2 to 3 minutes on CI. |
| `make_style_table.py` | Regenerates `TMessagesProj/src/main/assets/multigram_styles.bin` (deterministic). |
| `check_style_table.py` | Checks the asset's format and re-validates every entry against the theme sources in this tree. |
| `style_table.py` | Shared code: binary format, generator, validator. |
| `sim/` | The colour-engine simulator both of them use (`sim/README.md`). |
| `palette_fix_check.py` | Part of the palette fix, when the tree has it (`multigram/palette-fix/README.md`). `check.sh` runs it first when it is present. |
| `sim/palette-fix/overlay_A.json` | The palette fix ("overlay A") the table is validated on. When the tree also has `multigram/palette-fix/overlay_A.json` (the palette fix itself), that file is used instead; they are the same. |

## The style table: `multigram_styles.bin`

Each install picks one day style and one night style from this table (by its seed). A style is:

- a base theme: day from Blue, Arctic Blue, Day; night from Dark Blue, Night (never the Monet themes);
- an accent colour;
- outgoing-bubble colours: 1 to 4 colours, optionally animated;
- a wallpaper: a gradient of 2 to 4 colours and a rotation, and **no pattern** (a pattern slug would
  make the app fetch the pattern from Telegram's servers). A motion flag is stored too, but it has no
  visible effect today (see the record's flags).

Every entry passes all 99 readability pairs of the simulator's model on top of the palette fix
(overlay A): every pair the style controls with headroom (4.6:1 text, 3.1:1 non-text, 1.19 bubble vs
wallpaper), and the **palette-limited pairs only at the plain WCAG threshold** (4.5:1 / 3.0:1). Those are
neutral greys that overlay A sized at exactly the threshold, so no style can give them headroom; every
entry has some of them between 4.50 and 4.54 (3.03 for the composer icons on the light themes). Only a
palette fix with headroom can raise them; see "Readability rule". Without the palette fix in the app,
the entries are not readable.

### Format, version 1

All multi-byte integers are **big-endian** (the default of `java.nio.ByteBuffer` and
`java.io.DataInputStream`). The file is three contiguous parts, with no padding and nothing after them:

    header (24 bytes) | directory (theme_count x 32 bytes) | records (record_count x 40 bytes)

so its size is exactly `24 + 32 * theme_count + 40 * record_count` (today 5 themes and 20,480 records:
819,384 bytes).

**Header** (24 bytes)

| Offset | Size | Field | Value |
|---|---|---|---|
| 0 | 4 | magic | ASCII `MGST` (`0x4D 0x47 0x53 0x54`) |
| 4 | 2 | version | `1` (u16). A parser rejects any other version. |
| 6 | 2 | header_size | `24` (u16) |
| 8 | 2 | theme_count | number of directory entries (u16), today 5 |
| 10 | 2 | dir_entry_size | `32` (u16) |
| 12 | 2 | record_size | `40` (u16) |
| 14 | 2 | reserved | `0` |
| 16 | 4 | record_count | total number of records (u32), today 20,480 |
| 20 | 4 | crc32 | CRC-32 (zlib / `java.util.zip.CRC32`) of every byte after the header, offset 24 to the end. Also a fingerprint of the table's contents. |

**Directory entry** (32 bytes each, right after the header, in directory order)

| Offset | Size | Field | Value |
|---|---|---|---|
| 0 | 20 | theme_key | the base theme's key, UTF-8, padded with NUL bytes to 20 (at least one NUL). It is `ThemeInfo.getKey()` of the bundled theme, i.e. the string `Theme.getTheme(key)` takes: `Blue`, `Arctic Blue`, `Day`, `Dark Blue`, `Night`. |
| 20 | 1 | flags | bit 0: night theme (`ThemeInfo.isDark()`); other bits 0 |
| 21 | 1 | reserved | `0` |
| 22 | 2 | reserved | `0` |
| 24 | 4 | first_record | index (u32) of the theme's first record |
| 28 | 4 | record_count | number of records (u32) of this theme, at least 1 |

The themes' record ranges are contiguous and in directory order: the first theme starts at record 0 and
each next one starts where the previous one ends; together they cover all `record_count` records.
Today's order: Blue, Arctic Blue, Day, Dark Blue, Night, 4,096 records each.

**Record** (40 bytes each). Record `i` starts at byte `24 + 32 * theme_count + 40 * i`.

| Offset | Size | Field | Maps to `Theme.ThemeAccent` |
|---|---|---|---|
| 0 | 4 | accent | `accentColor` |
| 4 | 4 | bubble | `myMessagesAccentColor` |
| 8 | 4 | bubble_gradient1 | `myMessagesGradientAccentColor1`, never 0 |
| 12 | 4 | bubble_gradient2 | `myMessagesGradientAccentColor2`, 0 = unused |
| 16 | 4 | bubble_gradient3 | `myMessagesGradientAccentColor3`, 0 = unused |
| 20 | 4 | wallpaper1 | `backgroundOverrideColor` |
| 24 | 4 | wallpaper2 | `backgroundGradientOverrideColor1`, never 0 |
| 28 | 4 | wallpaper3 | `backgroundGradientOverrideColor2`, 0 = unused |
| 32 | 4 | wallpaper4 | `backgroundGradientOverrideColor3`, 0 = unused |
| 36 | 2 | rotation | `backgroundRotation`, degrees (u16): 0, 45, 90, ..., 315 |
| 38 | 1 | flags | bit 0: `myMessagesAnimated`; bit 1: `patternMotion` (see below); other bits 0 |
| 39 | 1 | reserved | `0` |

Colours are 32-bit ARGB, `0xAARRGGBB`, exactly an Android `@ColorInt`: read them with `getInt()` /
`readInt()` and use the value as is. Every colour in the table is opaque (alpha `0xFF`), so `0` is never
a colour; it marks an unused slot.

- Bubble colour count: 1 (solid) when `bubble_gradient1 == bubble` and `bubble_gradient2 == 0`; otherwise
  2, 3 or 4 = 2 + (gradient2 != 0) + (gradient3 != 0). A solid bubble keeps `gradient1 == bubble`: pass it
  to the accent as is, do not turn it into 0 (`fillAccentColors` only applies the bubble colours when
  gradient1 is non-zero). gradient3 is set only when gradient2 is. The colours of a gradient bubble are
  all distinct. The animated flag is set only with 3 or 4 colours.
- Wallpaper colour count: 2, 3 or 4 = 2 + (wallpaper3 != 0) + (wallpaper4 != 0); wallpaper4 is set only
  when wallpaper3 is, and the colours are distinct. 2 colours are drawn as a linear gradient at
  `rotation`; 3 or 4 as Telegram's motion gradient, which ignores the rotation (it is stored anyway).
- No record has a pattern: every entry was validated as a plain gradient.
- Flag bit 1 (`patternMotion`, set on about half the records) has **no visible effect** with Telegram's
  code: `createBackgroundDrawable` uses the accent's `patternMotion` only when a pattern wallpaper file
  exists (`getPathToWallpaper()` is null for an empty slug); for a plain gradient the parallax follows
  the theme's own `ThemeInfo.isMotion` setting. It is stored so the app could apply it (for example by
  setting the theme's motion setting from it), which would be a Java-side decision; it does not affect
  readability.
- Within a theme no two records share an accent colour, and none uses a built-in preset accent colour.

### Applying an entry

This is exactly what the simulator validated (`style_sim.to_accent`, accent id 101):

```java
Theme.ThemeInfo theme = Theme.getTheme(themeKey);      // "Blue", "Arctic Blue", "Day", "Dark Blue", "Night"
Theme.ThemeAccent a = ...;  // a runtime accent of that theme: id > 100 (++lastAccentId), e.g. from getAccent(true)
a.accentColor = accent;
a.accentColor2 = 0;
a.myMessagesAccentColor = bubble;
a.myMessagesGradientAccentColor1 = bubbleGradient1;    // == bubble for a solid bubble
a.myMessagesGradientAccentColor2 = bubbleGradient2;    // 0 when unused
a.myMessagesGradientAccentColor3 = bubbleGradient3;    // 0 when unused
a.myMessagesAnimated = (flags & 1) != 0;
a.backgroundOverrideColor = wallpaper1;                // int -> long, as ThemePreviewActivity assigns colours
a.backgroundGradientOverrideColor1 = wallpaper2;
a.backgroundGradientOverrideColor2 = wallpaper3 != 0 ? wallpaper3 : 0x100000000L;
a.backgroundGradientOverrideColor3 = wallpaper4 != 0 ? wallpaper4 : 0x100000000L;
a.backgroundRotation = rotation;
a.patternSlug = "";
a.patternIntensity = 0f;
a.patternMotion = (flags & 2) != 0;                    // no visible effect without a pattern (see above)
a.pattern = null;
a.overrideWallpaper = null;                            // getAccent(true) copies the current one; drop it
```

- The accent must be a runtime accent (`PaletteFix.isRuntimeAccent`: id above 100 and `info == null`):
  the palette fix's on-accent rule and out-bubble text guard only run for runtime accents, and the
  entries are only readable with them.
- Unused wallpaper slots take `0x100000000L`, the "remove this key" value `setAccentColorOptions` uses,
  not 0 (0 would keep a base-theme value; the bundled themes have none today, but that is what was
  validated).
- Parsing cost: read the 24-byte header and the directory, then read or skip to the one record needed.
  The asset is compressed in the APK (no `noCompress` entry), so use `AssetManager.open()`, not
  `openFd()`; skipping to the last record inflates at most about 0.8 MB.
- Suggested pick: the day style uniformly over all records of the day themes (directory entries without
  bit 0, in directory order), the night style likewise over the night themes, so every entry is equally
  likely and the base theme follows from the entry. If the table can change in a later release, keep
  the chosen colours (the accent is persisted by Telegram's own accent storage) or store the header's
  crc32 with the index, so an update does not silently restyle an install.

### Readability rule

Each entry is evaluated by the simulator (`sim/engine.py` port of `refreshThemeColors`,
`sim/readability.py` 99 pairs) on this tree's Theme.java, ThemeColors.java and bundled `.attheme` files
plus overlay A, with the accent as a runtime accent (id 101). The simulator's solver stops exactly on
its thresholds, so the table is solved against thresholds with headroom:

| Pair class | WCAG / project threshold | Table threshold |
|---|---|---|
| text (incl. date-pill text) | 4.5 | **4.6** |
| non-text (icons, marks, fills) | 3.0 | **3.1** |
| bubble vs wallpaper | 1.15 | **1.19** |

Exception: **palette-limited pairs** are held only to the plain threshold, because no style can give them
headroom; the palette fix has to. **So the table does not meet the 4.6 / 3.1 headroom on these pairs**:
they are between 4.500 and 4.54:1 (3.034:1 for the composer icons) on the light themes whatever the
style, and between 4.500 and about 4.8:1 on Night. They are found per base theme
(`style_table.palette_limited`), over a fixed probe of accents (24 hues x 3 chromas x 9 lightnesses):

- pairs whose contrast moves by less than 10 % of their threshold over the probe and falls below the table
  threshold for some of it. Overlay A sized these neutral greys at exactly the WCAG threshold;
- the digits on the muted unread badge (`chats_muted_badge_text`) while they fall below the table
  threshold for some probe accent: the palette fix fills that badge from a per-theme table sized at 4.5:1,
  and the style only decides which of its two entries is used.

Both rules follow the palette: when the palette fix gives a pair headroom for every probe accent (greys
at 4.6:1, composer icons at 3.1:1, a muted-badge table sized at 4.6:1), the pair stops being
palette-limited and the generator holds it to the table threshold; regenerate the table then. On Night
the accent tint moves some of these pairs (`in_time`, `in_views`, `in_file_info` up to about 4.8:1), but
holding just them to 4.6 makes the solver reject orange and magenta accents (the 30-60 and 300-330 degree
hue ranges lose about half their entries) while every entry still keeps `list_gray_text2` near 4.50, so
they stay palette-limited until the palette has headroom.

| Base theme | Palette-limited pairs (range over the table's entries) |
|---|---|
| Blue, Arctic Blue, Day | list_gray_text, list_gray_text2, chats_preview, chats_date, actionbar_subtitle, in_time, in_file_info, in_views, composer_hint, pinned_text, settings_footnote (text, constant 4.500-4.540 whatever the style); composer_icons (non-text, constant 3.034); chats_muted_badge_text (4.513, or 11.47 with near-black digits) |
| Dark Blue | settings_footnote (4.520), chats_muted_badge_text (4.502) |
| Night | list_gray_text, list_gray_text2, chats_preview, chats_date, actionbar_subtitle, in_time, in_file_info, in_views, composer_hint, pinned_text, chats_attach_label (4.500-4.752, moving at most 0.2 with the accent tint); settings_footnote (4.507); chats_muted_badge_text (4.501) |

Smallest margins in the current table (contrast / WCAG threshold):

| Base theme | text | non-text | bubble vs wallpaper | palette-limited |
|---|---|---|---|---|
| Blue | 1.0222 (picker_badge_text 4.600) | 1.0738 (in_media_button 3.221) | 1.0367 (1.192) | 1.0001 (chats_date 4.500), non-text 1.0112 (composer_icons 3.034) |
| Arctic Blue | 1.0222 (service_text_lite 4.600) | 1.2035 (unread_badge 3.611) | 1.0350 (1.190) | 1.0001 (chats_date 4.500), non-text 1.0112 |
| Day | 1.0222 (filled_button_text 4.600) | 1.2046 (in_media_button 3.614) | 1.0350 (1.190) | 1.0001 (list_gray_text 4.500), non-text 1.0112 |
| Dark Blue | 1.0223 (list_accent_text6 4.600) | 1.1005 (composer_icons 3.302) | 1.0351 (1.190) | 1.0004 (chats_muted_badge_text 4.502) |
| Night | 1.0222 (list_accent_text6 4.600) | 1.2234 (composer_icons 3.670) | 1.0348 (1.190) | 1.0001 (list_gray_text2 4.500) |

The model works on 8-bit colours exactly as the app computes them, but it is a model: only a device
build confirms the result.

### Generation

`python3 multigram/tools/make_style_table.py` (about 30 s on 4 cores; `--procs N`, `--report r.json` for
statistics, `--check` to compare with the committed asset). It is deterministic: the same tree gives the
same bytes on every run and for any `--procs`.

- Table seed `multigram-style-table-1`; candidate `k` of base theme `T` is seeded with the string
  `multigram-style-table-1/T/k` (SHA-256, first 8 bytes big-endian, SplitMix64).
- Each candidate runs the simulator's seeded OKLCH solver (accent: free hue, chroma 0.07-0.17,
  lightness solved; bubble: 1-4 colours near the accent hue, light or dark; wallpaper: 2 (25 %), 3 (20 %)
  or 4 (55 %) colours near the accent hue or its complement, lightness solved; rotation and the animated
  and motion flags drawn), up to 12 attempts, against the thresholds above, with the wallpaper always
  evaluated without a pattern.
- Candidates are taken in order of `k`. A candidate is kept when it passes, its record round-trips to
  the same 99 contrasts, and its accent colour is new for that theme, until 4,096 per theme.
- The generator gives up rather than run on when a theme's yield collapses (no entry from its first 256
  candidates, a yield below 20 % after 1,024, or more candidates than 4,096 / 20 % + 256; `--min-yield`
  changes the 20 %). It then prints the stages and pairs that failed most often and exits with status 4.
  Today's yield is 94 to 99 %.

Current table: 4,096 entries per base theme, 20,480 in all, every accent-hue range of 30 degrees
represented (288-387 entries per range and theme); bubbles 1/2/3/4 colours about 30/30/15/25 %, about
20 % animated, on the day themes about 55 % light (dark text); wallpapers 2/3/4 colours about
25/20/55 %; the motion flag on for about half.

### Checks

`bash multigram/tools/check.sh` (CI runs it after the compile) runs:

1. `palette_fix_check.py`, when the tree has it (the MultiGram branch): `PaletteFix.java`, its hooks and
   the theme sources apply exactly `multigram/palette-fix/overlay_A.json`. The table is validated
   against that file, so this is what ties the validation to the Java code the app runs.
2. `check_style_table.py`: the format rules above, every record; theme keys must be bundled base themes
   of this tree with the right night flag. Self-tests: the parser must recognise every form of the
   out-text guard (stock, `|| id > 100`, and the palette fix's exact line) with the rest of Theme.java
   parsed the same; 250 entries evaluated with overlay A applied by the simulator and with overlay A
   already written into the sources (Theme.java parsed with the palette fix's guard line) must give
   identical results; 25 entries are also compared against the simulator's full (non-lazy) port. Then
   all 20,480 entries are re-evaluated on the current sources: any pair below its WCAG threshold
   **fails** the check; a pair that is still readable but lost the table's headroom is a warning; a note
   counts the entries whose palette-limited pairs are below the headroom (today all of them). `--sample N`
   checks N entries per theme instead of all.
3. `make_style_table.py --check`: whether this tree would regenerate the same asset. A difference is only
   a warning (the theme sources changed since the table was made; the entries still passed step 2). A
   collapsed yield (exit status 4, see "Generation") **fails**: the table could not be regenerated.

**With or without the palette fix in the tree.** The simulator detects whether the sources already carry
overlay A (the palette fix's out-text guard in `fillAccentColors`,
`if (!isMyMessagesGradientColorsNear || org.telegram.messenger.multigram.PaletteFix.isRuntimeAccent(this))`,
or every overlay value present):

- not yet (a plain Forkgram tree): it applies overlay A itself: ThemeColors defaults, `.attheme` values,
  accent exclusions, the on-accent hook and the out-text guard;
- already there (the MultiGram branch): it takes the ThemeColors and `.attheme` values from the tree (so
  an upstream change to them is seen) and adds only the parts that live in Java code the parser does
  not read: the accent exclusions, the on-accent hook, the out-text guard. It takes those from
  `overlay_A.json`; `palette_fix_check.py` (step 1) checks that `PaletteFix.java` matches it. The app
  also applies the on-accent rule to the voice-record glyphs and the send-button glyphs, which overlay A
  does not; that only raises contrast, and the model has no pair for those glyphs.

Every part of overlay A assigns an absolute value or adds to a set, so applying it to a tree that
already has it changes nothing; the self-test checks that on every run. The 12 on-accent ThemeColors
defaults, which the palette fix keeps stock, make no difference because the hook sets those keys for
every runtime accent.

`--overlay apply|in-tree` forces either mode; `TG_REPO=/path/to/checkout` models another tree.

### Replaying onto a new Forkgram release

Run `bash multigram/tools/check.sh`. If it fails, or warns that entries lost headroom, regenerate the
table with `make_style_table.py`, re-run the check and commit the new asset (the header's crc32 changes).
If a pair the style cannot move fell below its threshold, regenerating does not help (the generator
stalls and names the pair): the palette fix has to change first. If the simulator cannot parse the new
Theme.java or ThemeColors.java, it says so; update `sim/tgsrc.py`.
