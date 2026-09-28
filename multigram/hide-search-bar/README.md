# Hide chat list search

Telegram 12 shows a search field (`FragmentSearchField`, 48 dp, `DialogsActivity.SEARCH_FIELD_HEIGHT`) under the
chat list header, and a search icon in the header once that field has scrolled away. "Hide chat list search", a
toggle in Fork Client Settings > Chat list view right after Forkgram's Disable Global Search (off by default),
removes both: the chat list lays out as stock does once the bar has scrolled away, minus the 48 dp the bar reserves,
so the first chat sits right under the header (or the folder tabs), and the header search icon never shows. The
chat list itself then offers no way into search. Forkgram's Disable Global Search is unrelated: it only drops server
results from search.

This build is the **"no search" variant**, the one the owner chose. The other design, the "search icon" variant,
hid only the bar and let the stock header icon open search (see "Considered and not done"). The two differ by one
hook (21), the two strings and the check.

The header icon needs its own hook because stock shows it whenever the bar is invisible, not only in search mode:
`checkUi_searchFieldVisibility` ends with `animatorSearchButtonVisible.setValue(alpha <= 0.01f, true)`, which drives
`checkUi_itemSearchVisibility`, and `FragmentFloatingButton.setAnimatedVisibility` makes the icon VISIBLE whenever
its factor is above 0. With the bar's alpha from scrolling held at 0 (hook 18), stock would swap the icon in at
rest; hook 21 zeroes the icon's factor instead.

With the option off every hook returns the stock value it replaced, so the chat list is exactly stock.

Code: `org.telegram.messenger.multigram.HideSearchBar`. Check: `multigram/tools/hide_search_bar_check.py`, which
`multigram/tools/check.sh` runs.

## Scope

In scope (no bar and no header search icon while the option is on): every `DialogsActivity` with the default
dialogs type, no `onlySelect` argument, no delegate and no search string (`isMainDialogList()`). That is the main
chat list with its folder tabs, the Archive, community lists, and the plain list `BackButtonMenu` opens.

Out of scope (stock bar and stock search always): dialog pickers (forward, share from another app, bot share, Save
to Gallery exceptions and every other `onlySelect` or non-default `dialogsType` screen; every `new DialogsActivity(`
call site that picks a chat sets one of the two) and the `#hashtag` / link search screens, which set a search
string.

The scope of a list is decided once, at its first use, because a picker may reset its delegate later
(`isMainDialogList()` would then turn true). To keep community lists stock, add `&& !f.isCommunity()` to
`HideSearchBar.inScope` (one line; the comment there says so).

## What still opens search

The option removes the chat list's own ways into search: the bar and the header icon. It does not block search
itself. These entries are left stock on purpose, and each still opens search in the chat list, with the field
appearing in the header while searching:

- **The Downloads item** in the main list's header. It shows only while files are downloading or there are
  downloads you have not looked at yet, and it opens search on the Downloads tab.
- **`tg://search?query=...` links.** They open search in the chat list with the query filled in.
- **The search icon of the forum topics column** (a forum opened beside the chat list). It calls `performClick()`
  on the list's header icon, and `performClick()` runs the click listener even while the icon is hidden. That
  search is scoped to the forum.

Also left stock: the music player's search by performer (a tap on the performer's name). As in stock, it does
nothing when the account has 10 chats or fewer. When the top screen is an in-scope list, that is an open Archive, an
open community list or the plain list `BackButtonMenu` opens, it opens search in that list, with the field in its
header. Otherwise, Chats included (there the top screen is the main tabs screen, not the list), it opens its own
search screen: a list with a search string, so out of scope and fully stock, bar included. Pickers and `#hashtag`
screens keep their stock search bar.

Why they stay: each is something the user asked for (a download, a link, a tap on a search icon), not the chat list
offering search on its own. Blocking them needs about 4 more hooks in busier code (`showSearch`, `canToggleSearch`
while not expanded, the Downloads item, `TopicsFragment`), and blocking `showSearch` alone would leave
`searching = true` with no search screen. The check fails if any of the three entries above stops opening search,
so an update that changes one gets this section reviewed.

## What is lost with the option on

- **The icon's long-press shortcut to Saved Messages.** Saved Messages itself is unaffected.
- **The chat list route into Forkgram's hidden-account unlock** (stealth mode, no passcode: tap search, type the
  account's unlock code). The unlock itself is untouched: it runs in every `DialogsActivity`'s search text watcher
  (`HiddenAccountHelper.tryUnlockFromSearch`, gated only by `shouldUseSearchUnlock()`), so it still works from any
  search listed in "What still opens search", from any picker's search bar and from any `#hashtag` screen. Anyone
  who uses hidden accounts loses the usual way in and has to use one of those.
- **The promise in Hide the "All Chats" tab's info text** that chats outside folders "stay reachable through search
  and the archive": with both options on, the chat list offers no search to reach them.

## Lifecycle

| When | What happens |
|---|---|
| First use of a list (its `createView`) | The list latches the setting (and its scope) in a `WeakHashMap` keyed by the fragment. Every hook reads the latch, so a list never changes shape while it is on screen. |
| `onResume`, right after `super.onResume()` | `HideSearchBar.refresh` re-reads the setting. Nothing happens unless this list's latched value changes. When it does, it first re-anchors each page's first visible chat relative to the list padding, then switches the latch; the hook then clamps the header scroll to the new maximum, asks the next draw to derive it again from the list (`invalidateScrollY`), and re-derives the field's visibility and the header icons. |

**Why refresh re-anchors the lists itself.** Stock `DialogsRecyclerView.onMeasure` keeps the first chat's offset
from the padding when the padding changes, but not on this path: `onResume` calls `notifyDataSetChanged` on every
page, after which `findViewHolderForAdapterPosition` returns null and that re-anchor is skipped, and
`LinearLayoutManager` then anchors on the old child's absolute top. Turning the option on with a hidden Archive
would then show 48 dp of the Archive row under the header; turning it off would leave the list 48 dp scrolled.
`keepListOffset` does what the stock re-anchor does (`scrollToPositionWithOffset(pos, top - paddingTop)`) before the
notify, so the layout after it uses that pending position against the new padding.

**How the header icon follows a toggle.** Hook 13 ends with `checkUi_searchFieldVisibility(); checkUi_menuItems();`.
`checkUi_menuItems()` calls `checkUi_itemSearchVisibility()`, whose `factor0` (hook 21) reads the latch `refresh` has
just switched, and `setAnimatedVisibility` applies the result at once. Turning the option on hides the icon at
once. Turning it off brings the bar back at once, and the icon fades out over 350 ms: while the option was on the
bar's alpha was 0, so `animatorSearchButtonVisible` stands at 1, and `checkUi_searchFieldVisibility` now animates it
to 0. That is stock's own swap when the bar scrolls back in. Nothing else in the list makes the icon visible:
every other path (`checkUi_menuItems()`, the animators' `onFactorChanged`) goes through
`checkUi_itemSearchVisibility()` and so reads the same latch.

A change applies the moment Chats is shown again: back, swipe back, or the Chats tab when Fork settings was opened
from the Settings tab; each of them resumes the list before it is drawn. On a tablet, a list that stays resumed next
to settings applies the change at its next resume.

## Preferences

mainconfig (`MessagesController.getGlobalMainSettings()`, the file Forkgram's own Chat list rows use):

| Key | Type | Default | Meaning |
|---|---|---|---|
| `multigramHideSearchBar` | boolean | false | the option |

Written only by the row, with `commit` like Forkgram's `toggle()`. Forkgram's settings export (`SettingsBackup`)
exports and imports mainconfig as a whole, so the key comes along; the Android backup agent does not back up
mainconfig. The row's id is 9101: above 0, so Fork settings' in-screen search finds it, and clear of Forkgram's
row ids (1-100). The key, the class and the strings' resource names keep the `HideSearchBar` name of the first
design; only the row's text changed.

## Hooks in upstream files

Every hook is one line marked `// MultiGram:`. The changed stock lines swap only the stock token inside the original
`dp(...)` for `HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)`, which returns it unchanged
while the option is off (and `dp(0) == 0` while it is on). Line numbers are those of `4780eb095b`.

| # | File, place | Hook |
|---|---|---|
| 1 | `DialogsActivity` L881, `ContentView.getActionBarFullHeight` | header band height: `restHeight` (header band, list clip, shadow, right-pane top and swipe region follow it) |
| 2 | L1059, `tabsYOffset` | action mode lifts the tabs by the visible header only: `restHeight` |
| 3 | L1060 | same, for the full lift: `restHeight` |
| 4 | L1086, right pane `addH` | the topics column moves the list up only by the header it covers: `restHeight` |
| 5 | L1093, start term of the field's search slide | `- dp(SEARCH_FIELD_HEIGHT - restHeight(...))`: a hidden bar fades in where a scrolled-away stock bar does (end term L1094 stock) |
| 6 | L1185, `ContentView.onMeasure` | the page is measured taller by the same amount: `restHeight` |
| 7 | L2080, `DialogsRecyclerView.onMeasure` | the list's top padding: `restHeight` |
| 8 | L2368, `setAnimationSupportView`, `backward` branch | closing the topics column gives back only the header it took: `restHeight` |
| 9 | L4226, fling stop | a fling stops at the first chat, not past a hidden bar: `restHeight` |
| 10 | L4232 | pairs with 9: `restHeight` |
| 11 | after L5743, first statement of `getMaxScrollYOffset` | `if (hides(this)) return getMaxScrollYOffsetWithoutSearch();` the header collapses by the stories only |
| 12 | after L6584 `totalOffset += storiesOverscroll;` in `updateContextViewPosition` | `if (hides(this)) totalOffset -= dp(SEARCH_FIELD_HEIGHT) * (1f - searchAnimationProgress);` tabs and top panels take the bar's place at rest (their layout top, L1324 in `ContentView.onLayout`, still counts it) |
| 13 | after L7086 `super.onResume();` | `if (refresh(this, viewPages)) { setScrollY(...); invalidateScrollY = true; checkUi_searchFieldVisibility(); checkUi_menuItems(); }` |
| 14 | L9110, `hideActionMode` | leaving action mode gives back only the header it took: `restHeight` |
| 15 | L9136 | pairs with 14: `restHeight` |
| 16 | L10239, `showOrUpdateActionMode` | action mode lifts the list by the visible header only: `restHeight` |
| 17 | L10266 | pairs with 16: `restHeight` |
| 18 | L14236, `checkUi_searchFieldVisibility` | `alphaByScrollOffset = restAlpha(this, <stock>)`: no bar at rest, so the field shows only while searching |
| 19 | `ForkSettingsActivity` after L578 (Disable Global Search) | `items.add(HideSearchBar.settingsRow());` |
| 20 | `ForkSettingsActivity.onClick` after `final int id = item.id;` | `if (HideSearchBar.onSettingsClick(item, view)) return;` |
| 21 | `DialogsActivity` L14321, first line of `checkUi_itemSearchVisibility` | `factor0` also needs `!hides(this)`: no header search icon either ("no search" variant) |

Hook 21 in full:

```java
        final float factor0 = isSupportSearch() && !org.telegram.messenger.multigram.HideSearchBar.hides(this) ? 1 : 0; // MultiGram: "no search": no header search icon either
```

The same stock text, `final float factor0 = isSupportSearch() ? 1 : 0;`, is also at L14241 in
`checkUi_searchFieldVisibility`, where it decides whether the field shows at all. That copy stays stock. The check
requires it exactly once in the file, as the only `factor0` of that method, and hook 21 as the only `factor0` of
`checkUi_itemSearchVisibility`, its first line, directly followed by the stock `factor1` line. It counts the stock
lines of both methods on code with comments stripped, so a stock line an update comments out does not count.

**Deliberately not hooked** (the check keeps each bar-height line on a reviewed list, so an upstream change to any
use of the bar height fails the check until it is reviewed):

- the `SEARCH_FIELD_HEIGHT = 48` declaration (L300): `javac` inlines it into 4 other classes, and it also sets how
  far the field travels in search;
- L1324, the layout top of the tabs and top panels: it also anchors the top panel in search mode, so hook 12
  compensates instead;
- L1094, the end term of the search slide; L1636;
- L5707, the stock "bar snap": it cannot run once the maximum scroll equals the maximum without search;
- L7251, the top bulletin offset: it behaves as stock does when the bar is scrolled away;
- L7635, the search pager entry with stories: 48 dp low during a 200 ms fade;
- L14377, the glass capture area: performance only;
- the icon's click and long-press listeners, `showSearch`, the Downloads item, `search(query, animated)` and
  `TopicsFragment`: the entries in "What still opens search" stay stock on purpose;
- `FragmentSearchField.java`.

**State trace with the option on** (AB = action bar height, S = dp(81) with stories or 0, sy = `scrollYOffset`):
at rest the header band ends at AB+S and the list padding is AB+S (+ tabs and panels), tabs sit at AB+S+sy, and
the field and the header search icon are both GONE. Scrolling clamps sy to [-S, 0], so without stories the header
is fixed. A fling stops at the first chat and a hidden Archive stays hidden. When search is opened another way, the
field fades in where a scrolled-away stock bar does, and at `searchAnimationProgress == 1` everything matches stock,
because every rest term is multiplied by (1-p) or is a clamp (stock hides the icon in search mode too). Action mode
moves the list and tabs by S+sy (0 without stories) with no jump on either edge (hooks 14-17 pair up). The topics
column moves up by S times its progress and is measured with the same amount (hooks 4, 6, 8). Stories appearing or
disappearing stay consistent, because `getMaxScrollYOffset()` is S.

## Considered and not done

| Idea | Why not |
|---|---|
| The "search icon" variant: hide only the bar, and let the stock header icon (which stock shows whenever the bar is invisible) open search | The owner chose "no search". To go back: put hook 21's line back to stock; in the check, remove `H[21]` and its `LAYOUT` entry, make the stock `factor0` guard expect two copies in the file (still one, as code, in `checkUi_searchFieldVisibility`), and flip the `checkUi_itemSearchVisibility` placement check to require the stock `factor0` line and no `HideSearchBar`; reword the two strings so the title names only the bar and the info text points to the header icon; update this README. |
| A strict version that blocks every way into search | About 4 more hooks in busier code, and blocking `showSearch` alone leaves `searching = true` with no search screen. See "What still opens search". |
| Restart required | Not needed: each list latches the setting and switches it in `onResume`, before it is drawn. |
| An `attach` hook in `createView` to fix the scope | More upstream text in the busiest method; the first latch fixes the scope instead. |
| Hooking L1324, the constant or `FragmentSearchField` | L1324 also anchors the top panel in search mode; the constant is inlined into other classes and sets the search slide; the field class is shared with other screens. |
| Hooking L7251, L7635, L14377 | Cosmetic or performance only (see "Known limitations"). |
| An entry in the Settings screen's global search index (ProfileActivity) | Forkgram does not index its Chat list rows either (for example Hide the All Chats tab); the in-screen search of Fork settings finds the row. |
| Applying the change at once to a list visible next to settings on tablets | Needs a notification and a live re-layout of a visible list; it applies at the list's next resume. |

Open owner decision: whether community lists are in scope (default yes; see "Scope").

## Device test checklist

CI only compiles and runs the checks; everything below needs a device.

1. **Option off**, on a fresh install and again after turning it off: chat list, bar at rest and hiding on scroll,
   the header search icon appearing once the bar has scrolled away, search from the bar and from the icon, the
   icon's long-press opening Saved Messages, stories collapsing, action mode, Archive, topics column. Compare side
   by side with a stock Forkgram build.
2. **Turn it on**, then return to Chats in each of three ways: back, swipe back, and the Chats tab when settings was
   opened from the Settings tab.
   - Expected: no bar, no gap and no search icon in the header; the first chat sits directly under the header or
     folder tabs.
   - With a hidden Archive: no Archive strip shows.
   - Turn it off and return: the bar is back at rest, with the first chat under it; the search icon may fade out
     briefly, as it does in stock when the bar scrolls back in.
   - Repeat while scrolled halfway down the list.
3. **No search from the list** (option on):
   - No search icon at rest, while scrolled, at the bottom of a long list, after a fling, in every folder, in the
     Archive and in a community list.
   - Nothing in the header or the list opens search.
   - After leaving action mode, after closing the topics column and after coming back from a chat: still no icon.
4. **No stories**:
   - The header never moves.
   - The shadow appears when scrolled and goes at the top.
   - A fling to the top with a hidden Archive stops at the first chat.
   - Pull to reveal or open the Archive, with Open Archive on Pulldown both on and off.
5. **With stories**:
   - Collapse, expand, half-way snap, fling.
   - Collapsed story avatars sit next to the remaining header items, with no gap where the icon was, and are
     clipped before those items.
   - Stories appearing or disappearing causes no jump.
6. **Folder tabs** (also with Hide the All Chats tab and each folder tab style): switching folders by swiping; top
   panels (proxy, requests, suggestions) sit right under the header and move into place when search opens from
   Downloads or a link.
7. **Action mode** with and without stories, list at the top and scrolled: no jump entering or leaving; pin and
   archive several chats.
8. **Forum topics column**: it opens under the action bar and closes without a jump; its search icon still opens
   search scoped to the forum, the field appears in the header, and closing search brings back the list with no
   bar and no icon.
9. **Archive**, opened by pull and by the row: no bar and no icon; Hide Stories in Archive on and off. With the
   Archive open, the music player's search by performer shows the field in the Archive's header, with the Archive
   chip.
10. **A community list**: no bar and no icon. With the community list open, the music player's search by performer
    shows the field in the community list's header. (Stock instead if the owner excludes communities.)
11. **Pickers keep the stock bar and search**: forward, share from another app, bot share, Save to Gallery
    exceptions. A #hashtag screen keeps its stock search layout.
12. **What still opens search** (option on). Each time the field fades in in the header row, results show, and
    closing search (x or back) returns to the list with no bar and no icon:
    - the Downloads header item, while a file downloads (lands on the Downloads tab);
    - a `tg://search?query=` link, with Chats open and with the app in the background;
    - the forum topics column's search icon (item 8);
    - the music player's search by performer, with more than 10 chats: from Chats it opens its own search screen
      (stock layout, with its bar); from an open Archive or community list, see items 9 and 10; with 10 chats or
      fewer it does nothing, as in stock;
    - hidden-account unlock (stealth mode, no passcode): typing the code in one of these searches unlocks the
      account.
13. **Screens and themes**: tablet or unfolded device, landscape, split screen, liquid glass on and off, dark theme,
    a long custom title (it may use the room the icon took).
14. **Fork settings**:
    - The row "Hide chat list search" sits right after Disable Global Search, and the in-screen settings search
      finds it.
    - Export settings, turn the option off, import, restart: the option is on again.

## Known limitations

- Turning the option off: the header search icon fades out over 350 ms when Chats shows again (stock's own swap).
- Top bulletins keep stock's 48 dp margin.
- With stories, search results slide in from 48 dp below the list top.
- The glass capture area is 48 dp taller than needed.
- On tablets, a list visible beside settings applies the change at its next resume.
- The strings are English only.
