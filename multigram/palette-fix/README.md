# Palette fix (overlay A)

Stock Telegram colours already fail WCAG contrast on many text/background pairs. MultiGram gives every
install a generated accent, and those accents are only readable on top of this fix. The values come from
the colour-engine simulator (research folder `random-style/palette-fix`, overlay A); `overlay_A.json` here
is a copy of that spec.

## What changes

| Part | Where | Applies to |
|---|---|---|
| 11 `ThemeColors` defaults (grey secondary texts) | `ThemeColors.createDefaultColors()`, each line marked `MultiGram: contrast fix, was ...` | every theme without its own value, including Blue preset 99 |
| 36 lines in the five bundled `.attheme` files | `assets/{bluebubbles,darkblue,arctic,day,night}.attheme` | those themes, every accent |
| 13 accent-exclusion keys (neutral greys, `windowBackgroundGray`) | `PaletteFix.addAccentExclusions`, called from Theme's static initializer | every non-default accent of the five themes |
| On-accent rule: 12 marks on accent fills become white or `#050505`, whichever contrasts more; muted unread badge gets a per-theme neutral fill | `PaletteFix.applyToCurrentColors` / `applyToColorMap` | runtime accents only (see below); per-chat themes while a runtime accent is active |
| Not in overlay A: a 13th pair, the voice-record glyphs (`chat_messagePanelVoicePressed` on `chat_messagePanelVoiceBackground`), and the send-button glyphs, which upstream draws in hard-coded white | `PaletteFix` `ON_ACCENT`; `ChatActivityEnterView.SendButton.updateColors` via `getGlyphColorOnFill` | while a runtime accent is active |
| Out-bubble black/white text block also for runtime accents | `Theme.ThemeAccent.fillAccentColors`: `if (!isMyMessagesGradientColorsNear \|\| PaletteFix.isRuntimeAccent(this))` | runtime accents only |
| Bundled `.attheme` copies are refreshed after an app update | `Theme.getAssetFile` via `PaletteFix.isStaleAssetCopy` | every bundled theme |

**Runtime accents** (`PaletteFix.isRuntimeAccent`): id > 100 and no server theme behind the accent
(`accent.info == null`), or a server theme this user created (`info.creator`, a custom accent the user
shared). That is MultiGram's generated accents and accents made in the theme editor. Telegram's own
server themes (the Chat Settings carousel, `account.getThemes`) and cloud themes installed from someone
else's link also get ids above 100, but they carry their `TL_theme` in `accent.info` and stay stock.
Stock presets have ids up to 99; id 100 is a custom accent migrated from very old app versions and
counts as stock. On top of that, `isActiveFor` is false for Monet themes and, on Blue, for an accent
with the default accent colour (`Theme.getColor` serves the stock defaults for it anyway).

**Per-chat themes** (`EmojiThemes.createColors`, accents in `ThemeInfo.chatAccentsByThemeId`) get the
rule when the global rule is active and the map is for the current light/dark mode. So a themed chat
looks exactly as in Forkgram for a user on a stock accent, and gets readable marks on the chat theme's
own fills for a user on a generated style. The map `createColors` returns is complete (it fills every
key from `Theme.getDefaultColors()`), so a themed chat never falls back to the global colours.

The 12 on-accent `ThemeColors` defaults keep their stock value (white): the rule sets them at run time, so
stock accents look exactly as in Forkgram. Monet themes define all 11 changed keys themselves and have no
accents, so they are unaffected.

## Hooks in upstream files (small, every changed line marked `MultiGram:`)

- `Theme.java`: the `isRuntimeAccent(this)` guard in `fillAccentColors`; `addAccentExclusions` after
  the last `themeAccentExclusionKeys.add`; `applyToCurrentColors` at the end of `refreshThemeColors`
  (after the calculated table/article colours); `applyToColorMap` in `ThemeAccent.saveToFile`
  (exported themes); `isStaleAssetCopy` in `getAssetFile`, which otherwise re-copies a bundled
  `.attheme` only when its size changes (the arctic and bluebubbles edits keep the size).
- `EmojiThemes.createColors`, `PeerColorActivity`, `ChannelColorActivity`, `MessageEntityView`:
  `applyToColorMap` right after `fillAccentColors`, so chat-theme and preview colour maps follow the
  rule as described above.
- `Components/ChatActivityEnterView.SendButton.updateColors` (a field, five lines in `updateColors`
  and the loading-arc colour in `onDraw`): the glyph, star price, counter digits and loading arc drawn
  on the send button's fill use `PaletteFix.getGlyphColorOnFill(fill)` while the global rule is
  active. This covers the chat composer (new design, `chat_messagePanelSend`) and the old-design send
  buttons of the attach, share, forward, gift and photo-viewer sheets (`getFillColor()`).
- `Stories/DarkThemeResourceProvider.getColor`: keys the provider does not override go through
  `PaletteFix.getOverrideFallbackColor`, so a mark whose fill the provider overrides (for example the
  group-call checkbox) is recomputed for that fill instead of taking the global one.

Not hooked, on purpose: `EmojiThemes.getPreviewColors` (only bubble, button and wallpaper colours),
static `EmojiThemes.getPreviewColors(ThemeInfo)` (no callers), `Stories/recorder/PreviewView`
(wallpaper only), `ThemePreviewDrawable` (no on-accent marks drawn).

## Replaying onto a new Forkgram release

Locate every hook by content, not line number. Then run:

    python3 multigram/tools/palette_fix_check.py --base <new forkgram snapshot>

It checks the values against `overlay_A.json`, the key tables in `PaletteFix.java`, that each hook is
present once, and that nothing else in `ThemeColors.java` or the `.attheme` files changed. If upstream
changed a stock value that the overlay replaces, re-run the simulator before accepting it.
