# Per-install random style

Every fresh MultiGram install gets its own day and night style: a random 64-bit seed picks one day entry and one
night entry from the bundled style table (`assets/multigram_styles.bin`, see `multigram/tools/README.md`). Each
entry becomes a local accent on its base theme, and the pair is selected before the first frame is drawn.
"Shuffle my style" in Chat Settings draws a new seed and style, with Undo for a few seconds. "Reset to defaults"
also returns to the install's generated style. The style never leaves the device.

Code: `org.telegram.messenger.multigram.RandomStyle` (logic), `RandomStyleUi` (Chat Settings row and messages),
`StyleTable` (asset reader). Strings: `res/values/multigram_strings.xml`. Check:
`multigram/tools/random_style_check.py`, which `multigram/tools/check.sh` runs.

## Lifecycle

| Stage | Where | What it does |
|---|---|---|
| A | `ApplicationLoader.onCreate`, before `NativeLoader.initNativeLibs` and before anything touches `Theme` | Runs once per install (while `state` is absent). An install that already has theme settings is marked `existing`. Otherwise it is marked `fresh`, creates the seed with `SecureRandom.nextLong()`, picks both entries and stores them with the table's CRC, then sets `pending`, or `failed` if the table cannot be read. |
| B | `Theme`'s static initializer, after the saved accents are loaded and before the auto-night settings are read and the first theme is applied | Always drops stale generated-accent records. On `pending` it first commits `failed`, so a crash cannot retry at every start. Then it creates the day and night accents (`getAccent(true)` on the entry's base theme, so the first free id is 101 or above), saves them with `saveThemeAccents(..., upload = false, migration = true)`, selects the night theme, writes mainconfig `theme` / `nighttheme` and the themeconfig selection keys, sets `applied` and returns the day theme for Theme to apply. Any exception leaves the stock style. |
| Shuffle | "Shuffle my style" row in Chat Settings, under the colour themes | Uses a new seed, then creates the new pair. It removes the previous generated accents unless the user edited them (see "Unedited" below), saves with upload off and applies the pair (see below). A failure changes nothing and shows an error bulletin. |
| Undo | "Undo" on the bulletin shown after a Shuffle (5 seconds) | Offered only when the generated style was showing before the Shuffle; any other theme stays in the theme list anyway. Brings back the previous seed and style (recreated with new accent ids) and removes the shuffled pair unless edited. Memory only: gone when the bulletin closes. |
| Reset | Chat Settings menu, "Reset to defaults" | Stock Chat Settings resets only text size and bubble radius here: its colour branch (back to Blue) runs only where the old theme list exists, which Chat Settings no longer has. MultiGram adds the colours: an install with a generated style returns to it (same colours, new accent ids). It leaves the colours alone when the day, night or showing theme is a custom, cloud or Monet theme, and for installs without a generated style. |

**Unedited** means exactly as the style made it: the same colours, no pattern, and no chat background of its own.
"Change chat background" attaches the background to the current accent, and deleting an accent deletes its
background, so an accent with a background of its own is kept like any edited one.

**Applying a shuffle, undo or reset** keeps the user's auto-night mode and respects which variant is showing:

- Day theme showing: the day style is animated in (`needSetDayNightTheme`, the stock path). The night style is recorded silently as the night theme.
- Night theme showing through auto-night: the night style is animated in as night. The day style becomes the day theme for the next switch (`Theme.setCurrentDayTheme`, mainconfig `theme`).
- A dark theme picked manually as the day theme: it stays dark with the new night style, and the day/night toggle switches to the new day style (themeconfig `lastDayTheme`).

The generated accents are applied exactly as `multigram/tools/README.md` ("Applying an entry") says:

- they are runtime accents (id above 100, `info == null`), so the palette fix applies;
- `accentColor2 = 0`;
- unused wallpaper slots take `0x100000000L`;
- `patternSlug = ""`, with no pattern object and no override wallpaper.

## Preferences

`rebrand_style` (this feature's own file; never exported, backed up or uploaded):

| Key | Type | Meaning |
|---|---|---|
| `state` | string | `pending`, `applied`, `failed` or `existing` (see `RandomStyle.STATE_*`) |
| `fresh` | boolean | Stage A found no theme settings (the install was born with this feature) |
| `seed` | long | the current seed (changes on Shuffle); absent until the install has one |
| `version` | int | `RandomStyle.GENERATOR_VERSION` of the pick below |
| `table_crc` | int | CRC-32 of the table the entries came from |
| `day_theme`, `night_theme` | string | base theme key of the current day and night style |
| `day_style`, `night_style` | string | the entry, 80 hex digits (the 40-byte record); Reset uses these, not the table |
| `day_index`, `night_index` | int | the entry's index among the table's day or night entries |
| `day_accent`, `night_accent` | int | id of the accent created for it |
| `generated` | string | `"<theme key>\|<accent id>\|<tags>"` records joined with `;`: every accent that must stay on the device. Tags are joined with `,`: fingerprints of the accent's colours (CRC-32, 8 hex digits) or `*` (any colours) |

themeconfig (Telegram's theme file):

- `accents_*`, `accent_current_*`: the accents themselves, written by Theme's own storage.
- `lastDayTheme`, `lastDarkTheme`, `lastDayCustomTheme(AccentId)`, `lastDarkCustomTheme(AccentId)`: the selection, which the day/night toggle and the chat-theme sheet read.
- `multigram_generated_accents`: a copy of `generated`.

Records whose accent no longer exists are dropped after every Shuffle, Undo or Reset and at every start. At
start, before anything can upload, each record is also checked against the accent as saved: a `*` or matching
record is narrowed to the saved colours' fingerprint, and a record whose accent now has other colours is dropped.
That accent is a different one that got the same id, typically from a settings import.

**Pick (version 1).** With `mix64` the SplitMix64 finaliser and `gamma = 0x9E3779B97F4A7C15`:

- day index = `(mix64(seed + 1*gamma) >>> 1) % dayCount`;
- night index = `(mix64(seed + 2*gamma) >>> 1) % nightCount`.

Each index counts the day or night entries in directory order, so every entry is equally likely. The picked
entries are stored, so a later table update never restyles an install.

## Existing users

Stage A classifies the install once, before Theme has run. It counts as existing when:

- themeconfig has any key (Theme writes `remote_version` on every start); or
- mainconfig has `theme`, `nighttheme` or `selectedAutoNightType`.

Such an install is marked `existing`, with `fresh = false` and no seed. Nothing restyles it automatically.
Stage B only acts on `pending`, which only Stage A sets, and only on a fresh install. "Shuffle my style" works
for existing users too and gives them a seed. "Reset to defaults" stays stock for them until they have shuffled
once.

## Privacy

The seed and the `rebrand_style` file are never sent anywhere. The generated colours can only leave the device
through Telegram's theme upload, which is guarded.

**The guard.** `RandomStyle.isGenerated(accent)` is true when:

- the accent has no server theme (`info == null`);
- its id is above 100; and
- a record `"<theme>|<id>"` exists in `generated` or in themeconfig's copy, and it holds `*` or the fingerprint of
  the accent's current colours.

If reading the records fails, it answers true.

The records cover:

- the accents Stage B, Shuffle, Undo and Reset create, with their fingerprint;
- every later edit of them. Opening a generated accent in the accent editor (`ThemePreviewActivity`, via
  `onAccentCopied`) adds `*`. Saving it reaches `saveThemeToServer`, whose guard adds the new fingerprint. The next
  start narrows the record to the colours on disk;
- every copy made from them in the accent editor. The "+" in the accent list starts from the current accent, and
  `onAccentCopied` gives the copy a `*` record.

Accent ids are not unique across installs: a fresh install's first accent is 101 on its base theme, as is a
Forkgram user's first own accent. The fingerprint keeps an imported accent that got a generated accent's id from
being taken for it.

| Path | What would leave the device | Guard |
|---|---|---|
| `MessagesController.saveThemeToServer` (all callers below end here) | the accent as an `.attheme` file and a preview image (`account.uploadTheme`, then `createTheme`) | returns at once when `RandomStyle.isUploadBlocked` (the accent is generated) |
| Chat Settings → accent long-press → Share; toolbar Share (`ThemeActivity`) | upload, then a share link | upload blocked; the `needShareTheme` handler shows "stays on this device" instead of a spinner that would never finish (`RandomStyleUi.interceptShare`) |
| Accent editor → Share (`ThemePreviewActivity`, `openThemeCreate(true)`) | same | same (the editor closes, and ThemeActivity shows the message) |
| Accent editor → Save (`saveThemeAccents(..., upload = true)`) | upload of the edited accent or of a new accent | blocked; the edit or copy is marked generated (above) |
| Create new theme / theme from an accent (`AlertsCreator.createThemeCreateDialog`) | a cloud theme built from the accent's colours | refused with the message when the given accent is generated. With no accent given, it is refused when the current accent of the previous or active theme is generated. |
| Custom theme editor save (`Theme.saveCurrentTheme`), share of a custom theme | a custom `.attheme` | not a generated accent: custom themes are never created from a generated style (the create dialog above is the only way in) and are never touched |
| Applying a theme (`MessagesController.saveTheme` → `installTheme`) | `account.installTheme` with the dark flag only: a generated accent has no `info` (no theme id) and no pattern slug (no `installWallPaper`) | nothing to guard; this is the same request stock sends for any local accent without a pattern |
| Background preview share (`ThemePreviewActivity`, id 5) | a `t.me/bg` colour link | the theme background is a `FileWallpaper`, and that share button appears for it only in `DEBUG_PRIVATE_VERSION` builds |
| Pattern download (`PatternsLoader`) | a request naming the pattern slug | a generated accent has none |

The feature's own classes make no network calls. `random_style_check.py` fails if they call a server path or save
accents with upload on.

## Backup and settings export

- **Android backup.** The manifest names the key/value `BackupAgent`, which backs up only `saved_tokens` and
  `saved_tokens_login`, and there is no `fullBackupOnly`, so neither `rebrand_style` nor themeconfig is
  backed up. A restore from Android backup is therefore a fresh install with a new seed. `rebrand_style` must
  not be added: a seed must not follow the user to another device. The check fails if the agent mentions it,
  or if the manifest stops giving backup to the agent (re-check this policy then).
- **Forkgram settings export** (`forkgram/SettingsBackup.kt`). This exports mainconfig and themeconfig to a file
  the user picks. `rebrand_style` is deliberately not in `ALLOWED_PREFS`, so the seed stays on the install; the
  check enforces this. The generated colours do travel, as themeconfig accents, like any accent. Themeconfig's
  copy of the records travels with them, so an imported generated accent stays local-only on the target install.
  The target keeps its own seed; its Reset returns to its own style. The file is a user-made local file, not an
  upload. An imported accent with the same theme and id as one of the target's generated accents but other colours
  (for example a Forkgram user's own first accent, id 101) is not taken for it: the next start drops the target's
  record, so that accent can be shared as in stock.

## Interplay

- **Chat themes** (per-chat emoji and server themes) keep their precedence inside their chats. Nothing here
  touches `EmojiThemes` or the chat theme delegate. The palette fix gives chat themes its on-accent rule while
  a generated style is active (see `multigram/palette-fix/README.md`).
- **Monet** themes are never a base (the table has none, and `baseTheme` refuses them). A user on Monet keeps it
  until they press Shuffle.
- **Custom themes** (`.attheme`, cloud themes) are never modified or deleted. Shuffle, Undo and Reset only delete
  the previous generated pair, and only while it is unedited.
- **Chat Settings' theme strip.** Its custom tile (🎨) is built from themeconfig's `lastDay/DarkCustomTheme(AccentId)`,
  which Stage B, Shuffle, Undo and Reset set to the generated pair. A hook in
  `DefaultThemesPreviewCell.updateDayNightMode` rebuilds the tile when those keys have moved on, so it never points
  at a removed accent. It also picks up an accent chosen elsewhere in the meantime, which stock showed only after
  reopening the screen.
- **Auto-night.** Stage B and Shuffle never change `selectedAutoNightType`. On a fresh install it stays at the
  stock default: follow the system on API 29 and above, off below.
- **Bubble radius and chat list layout** are Forkgram settings this feature does not touch. The per-install
  shape knobs in `StyleKnobs` pick them from the same seed (see `multigram/style-knobs/README.md`). The avatar
  shape is left alone by both.
- User accents made from scratch, and stock presets, keep uploading and sharing as in stock.

## Hooks in upstream files

| File | Hook |
|---|---|
| `ApplicationLoader.java` `onCreate` | `RandomStyle.onApplicationCreate(applicationContext)` (Stage A) |
| `Theme.java` static initializer | `applyingTheme = RandomStyle.onThemeInit(applyingTheme)` (Stage B) |
| `Theme.java` | `setCurrentDayTheme(ThemeInfo)`, a one-line setter used when Shuffle runs while the night theme shows |
| `MessagesController.java` `saveThemeToServer` | `if (RandomStyle.isUploadBlocked(themeInfo, accent)) return;` as its first line |
| `AlertsCreator.java` `createThemeCreateDialog` | `if (RandomStyleUi.interceptThemeCreate(fragment, switchToAccent)) return;` after the null check |
| `ThemePreviewActivity.java` constructor | `RandomStyle.onAccentCopied(applyingTheme, accent, !edit)` right after `getAccent(!edit)` |
| `DefaultThemesPreviewCell.java` `updateDayNightMode` | `RandomStyleUi.refreshCustomTile(adapter.items, ...)` as its first line |
| `ThemeActivity.java` | `shuffleStyleRow`: field, reset, row after `themeListRow2`, and one line each opening the click listener, the `TYPE_TEXT_PREFERENCE` binding and `getItemViewType`; `interceptShare` opening the `needShareTheme` handler; `resetToGeneratedStyle()` ending the Reset handler |

Each hook is one inserted line, marked `// MultiGram:`; no upstream line is changed (the setter's blank separator
line aside). `random_style_check.py` checks each hook, its position and the marker on every line that names the
feature; `--base forkgram` also checks every added line of those files.

## API for other MultiGram features (knobs)

All static on `org.telegram.messenger.multigram.RandomStyle`. The methods are safe from Stage A on, and none
of them touches Theme:

```java
boolean hasSeed();              // the install has a seed (born with a style, or pressed Shuffle)
long getSeed();                 // current seed; 0 without one. Changes on Shuffle
boolean isFreshInstall();       // Stage A found no theme settings: this install was born with a generated style
String getState();              // STATE_PENDING / STATE_APPLIED / STATE_FAILED / STATE_EXISTING, null before Stage A
long deriveSeed(long seed, String knob); // independent, deterministic 64-bit value per knob name
StyleTable.Entry getStyle(boolean night); // the current day or night entry, or null
boolean hasGeneratedStyle();    // state applied and both entries stored
void addListener(RandomStyle.Listener l);    // onStyleChanged(long seed, int reason) on the UI thread, after
void removeListener(RandomStyle.Listener l); //   Shuffle (REASON_SHUFFLE), Undo (REASON_UNDO) or Reset (REASON_RESET)
```

A knob that must be decided before the first frame should run after `RandomStyle.onApplicationCreate`. Its
hook goes below this one in `ApplicationLoader.onCreate`. It should read `isFreshInstall()` and `getSeed()`,
derive its value with `deriveSeed(getSeed(), "<knob name>")`, and store the result in its own preferences.

Existing installs have no seed until they shuffle, so a knob should keep its stock value for them. On
`REASON_SHUFFLE` and `REASON_UNDO` a knob re-derives from the seed it is given (Undo restores the previous one). On
`REASON_RESET` the seed is unchanged. The listener runs after Chat Settings' own reset of font size and bubble
radius; the bubble radius that reset picks comes from `StyleKnobs.resetBubbleRadius`.

A knob whose value must be in place before the theme switch (the wallpaper is reloaded synchronously inside it)
cannot use a listener. `StyleKnobs.onStyleApplying(seed)` is called directly by Shuffle, Undo and Reset just
before they show the new pair; see `multigram/style-knobs/README.md`.

Not implemented here, left to the knobs work (research: `random-style/style-knobs.json`):

- **style-consumers-outside-theme** (notification accent). `getStyle(false).accent` is readable from the push
  path without loading Theme (StyleTable never touches it); remap it to the knob's OKLCH band there.

## Device test checklist

These need a device or emulator. The logic was exercised on the JVM with stubs, and CI only compiles.

1. Fresh install, system light: the first frame shows the day style (no Blue flash). Chat Settings shows the
   accent selected, and the chat list and bubbles look as the entry says.
2. Fresh install, system dark (API 29+): the first frame shows the night style.
3. Update over an existing Forkgram or MultiGram install: nothing changes. Shuffle then works.
4. Shuffle with the day theme showing, with the night theme showing through auto-night, with a manually picked
   dark theme, and with auto-night scheduled. Check the reveal animation and which variant shows afterwards,
   then toggle day/night and check the other variant.
5. Shuffle twice quickly: the one-second debounce and `DialogsActivity.switchingTheme` prevent overlap.
   Shuffle, then Undo on the bulletin (also during the colour animation): the previous style is back in the same
   variant. Shuffle twice, then Undo: the style of the second-to-last Shuffle comes back.
6. Edit the generated accent (Chat Settings → accent → edit), save, then Shuffle: the edited accent stays.
   Sharing it shows the "stays on this device" message, and no upload appears in the log. Restart and share
   again: still refused.
7. Pick a photo in "Change chat background" on the generated style, then Shuffle: the old accent and its
   background stay in the accent list.
8. After Shuffle, Undo and Reset, tap the 🎨 tile in Chat Settings' theme strip: it shows and applies the current
   generated style.
9. "+" in the accent list while on the generated accent, then Save: no upload. Share shows the message.
10. Create new theme while on the generated accent: the message, no dialog.
11. Reset to defaults: the generated style comes back. With a custom or Monet theme selected, only text size and
    bubble radius reset.
12. Chat with an emoji chat theme: it still wins inside that chat.
13. Monet: select a Monet theme, restart: it stays. Shuffle leaves Monet for the generated style.
14. Settings export and import into another install: the imported generated accents cannot be shared. Import a
    Forkgram export with an own accent on the fresh install's day base, restart: that accent can be shared.
15. Tablet layouts (both action bar layouts receive the theme animation).

## Known limitations

- Reset and Undo recreate the accents with new ids, and the old unedited ones are deleted.
- Chat Settings' menu offers "Reset to defaults" even when the install is already on its generated style.
- Deleting the custom theme in use still falls back to stock Blue (and Dark Blue as the night theme), as in stock
  (`Theme.deleteTheme`). "Reset to defaults" then returns to the generated style. Routing that fallback would
  need another Theme hook.
- Undo is offered only when the generated style was showing, and only until its bulletin closes.
- After a settings import, an accent imported with the same theme, id and colours as one of the target's own
  generated accents stays on the device too (the safe side). So does one imported while the target's accent
  editor had a generated accent open in the same session.
- The first start of a fresh install reads and checks the 800 KB table once on the main thread (Stage A, before
  Theme). Shuffle uses the cached table, which the Chat Settings row warms off the UI thread.
