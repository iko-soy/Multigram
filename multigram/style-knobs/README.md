# Style knobs: per-install shapes and chat list layout

The per-install random style (`multigram/random-style/README.md`) gives every install its own colours. The style
knobs use the same seed for the shapes and the chat list: how round the message bubbles, service pills, reaction
chips, buttons and settings cards are, whether the floating action button is a circle or a rounded square, the
two- or three-line chat list, and where the wallpaper gradient starts. Every value is a shape or layout that the
app already supports; nothing changes behaviour, and accessibility settings (text size) are never touched.
Avatars keep their shape (see "Considered and not done").

Code: `org.telegram.messenger.multigram.StyleKnobs`. Check: `multigram/tools/style_knobs_check.py`, which
`multigram/tools/check.sh` runs. Research: `random-style/style-knobs.json` in the project files (safe ranges,
guardrails).

## The knobs

Each knob has its own stream, `RandomStyle.deriveSeed(seed, "<knob>")`, so adding a knob never changes the others.
An index into the knob's table is `(stream >>> 1) % length`, so every table entry is equally likely.

| Knob (stream name) | Values | Stock | Setting the user already has | Hook |
|---|---|---|---|---|
| `bubble-radius` | 8, 10, 12, 14 or 17 dp | 17 | Chat Settings, Message corners slider (0-17) | mainconfig `bubbleRadius`, written at start; `ThemeActivity` Reset |
| `chat-list-density` | two lines (3 in 5) or three lines (2 in 5); two lines on screens under 640 dp or with text size 19+ | two lines | Chat Settings, Chat list view | mainconfig `useThreeLinesLayout`, written at start |
| service pill (no own stream) | corner `clamp(round(bubble radius x 0.65), 4, 11)` dp; inner corners 8 and 6 dp scaled with it, at least 3 dp; the pill's size and its 8 dp side padding stay stock | 11 / 8 / 6 dp | follows the bubble radius slider | `ChatActionCell`, 4 lines |
| `reaction-chip-shape` | pill (1 in 2), or a rounded rectangle of `clamp(round(bubble radius x 0.6), 6, 10)` dp, never above the pill | pill | follows the slider | `ReactionsLayoutInBubble`, 2 lines |
| `cta-button-radius` | `clamp(round(bubble radius x 50, 75 or 100 %), 6, 12)` dp | 8 dp | follows the slider; `setRound()` and `setRoundRadius()` callers keep their values | `ButtonWithCounterView`, 2 lines; `GradientButtonWithCounterView` keeps stock 8 dp, 1 line |
| `fab-shape` | circle (1 in 2) or a rounded square of 14, 16 or 18 dp; the small button above it takes the same shape (radius x 36/48) | circle | none | `FragmentFloatingButton`, 4 lines |
| `settings-cards` | card corner 12, 14, 16 or 20 dp (inset stays 12 dp) | 16 dp | none | the default `setSections()` overloads of `RecyclerListView` and `UniversalRecyclerView`, 2 lines each |
| `wallpaper-phase` | starting phase 0-7 of the chat wallpaper gradient (`deriveSeed & 7`) | 0 | none | `Theme.reloadWallpaper`, 1 line |

Why these ranges (from the research's guardrails):

- **Bubble radius** stays at 8 or more: below that, grouped media corners look broken. 17 is the slider's
  maximum, so Chat Settings can always show the value.
- **Service pills, reaction chips and buttons follow the bubble radius**, so a square-ish style is square-ish
  everywhere, and a radius the user sets on the slider drives them through the same formulas. The pill corner
  never exceeds stock 11 dp, so a one-line pill never self-intersects; the inner corners never exceed the outer
  one. `ChatActionCell` derives the pill's side padding from the corner (`corner - cornerOffset`, stock
  11 - 3 = 8 dp), so the hook also moves `cornerOffset` with the corner: the pill keeps its stock size and padding
  and only its corners change. Reaction chips stay at 6 dp or more next to the emoji, and saved-message tags keep their notched shape.
  Button radii stay at most 12 dp: half of the smallest common button height and below the 24 dp corners of
  bottom sheets. The boost sheet's gradient button draws its gradient and shimmer at a fixed 8 dp, so it keeps
  stock 8 dp. Colours are not changed.
- **Chat list**: only the two stock layouts, never row heights or text sizes.
- **Floating action button**: shape only; the size, colour keys and the 48 dp touch target stay stock. Its shadow
  follows the background (`ViewOutlineProvider.BACKGROUND`, which for the stock circle is the same oval as
  before), so shadow and ripple always match the shape.
- **Settings cards**: corner radius only; the inset and shadows stay stock (shadows are a debug-menu setting and
  depend on the palette's card contrast). `UniversalRecyclerView` (the main Settings screen, Forkgram settings,
  Business, Stars and others) overrides the default overloads with its own 16 dp, so it has the same hook.

## Lifecycle

| When | What happens |
|---|---|
| Every start, `ApplicationLoader.onCreate` right after `RandomStyle.onApplicationCreate` (before Theme and the first frame) | Installs without a seed stop here: every hook returns its stock value. Otherwise the stored values are loaded (a fresh install derives and stores them), and the two settings are written into mainconfig where they are still ours (below), then copied into `SharedConfig`'s fields. The copy matters on large screens (sw600dp: tablets, unfolded foldables): there `AndroidUtilities`' static initialiser, which runs earlier in `onCreate`, calls `isTablet()`, which reads `SharedConfig.forceDisableTabletMode`, so `SharedConfig` has already loaded mainconfig and its later `loadConfig()` does nothing. On phones the copy loads `SharedConfig` at this point, from the values just written. Normal starts write nothing. |
| Shuffle, Undo | `RandomStyle` calls `StyleKnobs.onStyleApplying(seed)` right before it shows the style, because the theme switch that follows applies synchronously and reloads the wallpaper. A new seed re-derives every knob. The bubble radius and chat list layout change at once where they are ours, and so do the shapes read when drawing or laying out: message bubbles, reaction chips, service pills as they are laid out again, and the floating button (it redraws its background on the theme update). The next wallpaper load starts at the new phase. Chat Settings rebinds its text size preview, radius slider and chat list picker (`ThemeActivity.refreshStyleKnobRows`), and a bind hook updates those cells, visible or kept off screen (`RandomStyleUi.bindStyleKnobRow`). The theme switch does not rebuild screens, so button and settings card corners, which a screen reads when it builds them, change when each screen is next opened. |
| Reset to defaults (Chat Settings) | The bubble radius goes to the install's radius instead of stock 17 (`StyleKnobs.resetBubbleRadius`) and follows the style again. When the colours are reset too, the wallpaper restarts at the install's phase. Text size is reset by stock code as before. |

**Ours.** A stock setting is written only while it still has the value StyleKnobs last gave it (recorded in its
own file) or, before StyleKnobs ever set it, its stock default. So:

- a fresh install gets its values before the first frame, on phones and large screens alike;
- a value the user picks (slider, chat list picker) is kept by Shuffle and Undo; if they later pick the value
  StyleKnobs gave, it follows the style again;
- an existing install that presses Shuffle gets new values for the settings still at their stock defaults and
  keeps the others;
- a settings import (Forkgram's export carries mainconfig) brings values StyleKnobs did not record, so they are
  kept as the user's.

**Stable across updates.** The values are stored with the seed they came from, so an app update that changes a
table never restyles an install; only a new seed (Shuffle, Undo) re-derives them. A knob added by a later version
is missing from the file and is derived from its own stream once.

## Preferences

`rebrand_style_knobs` (this feature's own file). It holds values derived from the seed, not the seed's secrets;
like `rebrand_style`, it is in neither Android backup nor Forkgram's settings export (both are allow-lists).

| Key | Type | Meaning |
|---|---|---|
| `seed` | long | the seed the values below came from |
| `version` | int | `StyleKnobs.VERSION` that derived them |
| `bubble_radius`, `three_lines` | int, boolean | the values for the two stock settings |
| `reaction_pill`, `cta_scale`, `fab_radius`, `section_radius`, `wallpaper_phase` | boolean, int (%), int (dp, -1 circle), int (dp), int | the drawn knobs |
| `set_bubble_radius`, `set_three_lines` | as above | what StyleKnobs last wrote into (or found in) mainconfig: "ours" while the setting still has it |

mainconfig: `bubbleRadius`, `useThreeLinesLayout` (written only while ours). `fons_size` is only read (the chat
list guard). `avatarCorners` and `squareAvatars` are never read or written.

## Hooks in upstream files

Every hook is one line marked `// MultiGram:`; a changed stock line passes the stock value it had, so the hook
returns stock while the install has no seed (the bind hook and the gradient button's line do nothing then).

| File | Hook |
|---|---|
| `ApplicationLoader.java` `onCreate` | `StyleKnobs.onApplicationCreate(applicationContext)` right after RandomStyle's Stage A |
| `ActionBar/Theme.java` `reloadWallpaper` | `previousPhase = StyleKnobs.wallpaperPhase(previousPhase, wallpaper instanceof MotionBackgroundDrawable)` after the stock phase |
| `ThemeActivity.java` | Reset: `setBubbleRadius(StyleKnobs.resetBubbleRadius(17), true)`; one-line `refreshStyleKnobRows()` (`notifyItemChanged` on the text size, radius and chat list rows); in `ListAdapter.onBindViewHolder` one `case` line for those three view types that calls `RandomStyleUi.bindStyleKnobRow(holder.itemView)`. Chat Settings turns change animations off, so a changed visible row is rebound in place; one kept off screen is rebound when it is reused |
| `Cells/ChatActionCell.java` | `corner`, `cornerIn`, `cornerInSmall` = `StyleKnobs.servicePillRadius(dp(11 / 8 / 6))`; `cornerOffset = StyleKnobs.servicePillCornerOffset(dp(3), corner, dp(11))` |
| `Components/Reactions/ReactionsLayoutInBubble.java` | both `float rad = StyleKnobs.reactionChipRadius(height / 2f)` (chip and particle clip) |
| `Stories/recorder/ButtonWithCounterView.java` | `radiusDp = StyleKnobs.ctaRadiusDp(8)`; the constructor's background uses `dp(radiusDp)` instead of `dp(8)` |
| `Components/Premium/boosts/GradientButtonWithCounterView.java` | `setRoundRadius(8)` at the end of the constructor: its gradient and shimmer are drawn at a fixed 8 dp |
| `Components/FragmentFloatingButton.java` | outline `ViewOutlineProvider.BACKGROUND`; `StyleKnobs.floatingButtonBackground(dp(48), ...)`; sub-button `rad = StyleKnobs.floatingSubButtonRadius(dp(18))` and `iBlur3Background.setRadius(rad)` |
| `Components/RecyclerListView.java`, `Components/UniversalRecyclerView.java` | both default `setSections` overloads in each: `StyleKnobs.sectionRadius(dp(16))` |

MultiGram files: `RandomStyle` calls `StyleKnobs.onStyleApplying` in `shuffle`, `undoShuffle` and
`resetToGeneratedStyle`; `RandomStyleUi` calls `ThemeActivity.refreshStyleKnobRows` after Shuffle and Undo, and
`RandomStyleUi.bindStyleKnobRow` re-checks the chat list picker's radio buttons, lays the preview messages out
again and re-measures the row (the radius slider takes its position in `onMeasure`). It leaves a cell that was
never laid out alone: that cell was just created from the current values.
`style_knobs_check.py` checks every hook, its placement and marker, the settings StyleKnobs may write, and the
tables' ranges; `--base forkgram` also checks every added line of the hooked files.

## Considered and not done

| Knob | Why not |
|---|---|
| `avatar-shape` (Forkgram's Round, Rounded and Square) | The research's safe range is the circle until a forum-scaling hook ships (High effort). Forkgram's Rounded mode is not limited to avatars: `ImageReceiver.setRoundRadius` scales every image corner by 0.64, so round video messages show as rounded squares with a circular progress ring and snap back to a circle while playing, and photo corners in bubbles shrink. It also leaves user avatars in the chat header at 0.32 of the side against 0.24 for forum avatars, under the 0.12 gap the research asks for. Square erases the forum and community shape cue. The stream name stays reserved for a proper avatar knob. |
| FAB colour (`chats_actionBackground`) | A colour change needs the contrast checks of the colour work (the stock default of that key fails 3:1 against the white icon); shape only here. |
| `chat-list-badges` (counter badge radius) | Four draw sites in DialogCell plus the forum/folder `BubbleCounterPath`, FilterTabsView and GlassTabView counters would all need hooks for the badges to match; not a small hook. |
| Settings card shadows, inset | Shadows are a debug-menu setting and depend on card vs page contrast; the inset changes list layout. |
| `bubble-tail`, `overlay-roundness`, `folder-tabs-search`, `glass-chrome-look`, `settings-icon-tiles`, `header-style`, `controls` | Medium or High effort in the research: path changes, 9-patch replacements or several widget classes. |
| `story-ring`, `list-details`, `composer-panel` | Colour knobs: they belong with the palette work and its readability checks. |
| Text size, row heights | Accessibility and layout, never randomised. |

## Device test checklist

The logic was exercised on the JVM with stubs (fresh, existing, user override, Shuffle, Undo, Reset, restart,
settings import, stored values across a table change); CI only compiles.

1. Fresh install, on a phone and on a tablet or unfolded foldable: the bubble corners and chat list layout match
   `rebrand_style_knobs` from the first frame; Chat Settings shows the same radius and chat list choice.
2. Service messages and date pills with a small radius (8 or 10): one-line and multi-line pills (for example a
   long pinned-message notice) have clean corners and the same size and side padding as stock, and the
   floating date matches.
3. Reactions under a message, in a channel post and on media with the rounded style; selecting one (particles
   stay inside the chip); saved-message tags keep their shape.
4. Buttons in sheets (for example gift, boost or premium sheets) and screens using `ButtonWithCounterView`:
   corners, pressed ripple and the loading shimmer match; `setRound()` buttons stay pills; the boost reassign
   sheet's gradient button keeps 8 dp corners.
5. Chat list FAB and the stories button above it, rounded style: shadow, pressed ripple, the show/hide
   animation and the progress state; other screens with a floating button (contacts, calls, new group).
6. Settings screens with cards (Settings, Forkgram settings, Privacy, Data and storage, Chat Settings): corners
   and row selectors match from screen to screen.
7. Wallpaper: restart twice; the generated gradient starts at the same phase each time, sending messages still
   rotates it, and Shuffle restarts it at the new phase.
8. Shuffle and Undo in Chat Settings: the preview bubbles, radius slider (thumb and number) and chat list picker
   update at once, also when the preview or the picker was scrolled off screen at the time; the chat list
   switches between two and three lines. Settings cards and sheet buttons change when their screen is next
   opened.
9. Move the slider or pick a chat list layout, then Shuffle: the choice stays. Reset to defaults: the install's
   radius comes back.
10. Existing install (update): nothing changes until Shuffle; avatars keep Forkgram's setting.

## Known limitations

- After Shuffle or Undo, button and settings card corners change when each screen is next opened (the theme
  switch does not rebuild screens).
- Service pills already laid out keep their corners until the cell is laid out again (a chat reopened after
  Shuffle is rebuilt anyway).
- Screens that draw their own cards or buttons with fixed radii keep them; only the shared defaults follow.
- Stock Chat Settings keeps offering "Reset to defaults" while the radius differs from 17 (it already does
  while the generated accent is selected).
