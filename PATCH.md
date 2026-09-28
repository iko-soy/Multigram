# MultiGram patch guide

This guide says how to keep MultiGram working after Telegram, and then Forkgram, release an update.

MultiGram is Forkgram plus seven commits of its own. Usually the automatic sync moves those commits onto each new Forkgram release by itself. When it cannot, this guide tells you what to do. It also lists every place where MultiGram edits a Forkgram file, with the exact text, so that you can put each change back by hand.

## 1. About this document

### 1.1 Stamp

| | |
|---|---|
| Written for | `multigram` at ff868b3ea4 |
| Built on | Forkgram 12.10.6 (Forkgram commit b994e1446e), which is Telegram 12.10.5 (DrKLO commit dc780e81e, "update to 12.10.5 (7105)") |
| Forkgram snapshot | `forkgram` at 4543767655 |
| Sync scripts | `main` at da0cc7c548 |
| Date | 2026-09-28 |

Line numbers, counts and outputs in this guide are from that state. When you use it after an update, expect line numbers to have moved. Every hook is therefore described by its content, not only by its line. Section 11 says how to bring this guide up to date.

Output marked "example output" comes from a test with a made-up Forkgram release. Its commit hashes do not exist in the real repository.

### 1.2 Words used here

| Word | Meaning in this guide |
|---|---|
| Upstream | The code MultiGram builds on: Forkgram, which is Telegram's Android app (DrKLO/Telegram) plus Forkgram's own changes. |
| Snapshot | A commit on the `forkgram` branch that holds one Forkgram release, without its `.github` folder. |
| Stack | The seven MultiGram commits on top of the snapshot. Together with the snapshot they form the `multigram` branch. |
| Hook | A small edit in an upstream file that calls MultiGram code. Most hooks are one line that ends with `// MultiGram: ...`. |
| New file | A file the stack adds. It never conflicts, but it can stop compiling when an upstream name it uses changes. |
| Replay | Moving the stack onto a new snapshot with `git rebase`. |
| Conflict | A place where git cannot combine an upstream change with a MultiGram change by itself. |
| rerere | Git's "reuse recorded resolution": it remembers how you fixed a conflict and repeats the fix, but only in the same clone. |
| Worktree | An extra working folder of the same clone, made with `git worktree add`, with its own branch checked out. |
| CI | "Continuous integration": here, the GitHub Actions workflows that compile and check each candidate. |
| Static initializer | Java code in a `static { ... }` block. It runs once, when the class is first used. `Theme`'s static initializer loads the themes at app start. |
| ARGB | A colour as four bytes: alpha (opacity), red, green, blue, written `0xAARRGGBB` or `#AARRGGBB`. `.attheme` files store it as a signed decimal number. |
| Accent | The main colour of a theme. A **runtime accent** is one made on the device (MultiGram's generated style, or a colour picked with the colour wheel). Its id is above 100, and it either has no server theme or has one the user created (`accent.info.creator`, for example a custom accent the user shared). |
| Contrast, WCAG | How readable a colour is on its background, as a ratio from 1 : 1 to 21 : 1. The usual minimum (the WCAG guideline) is 4.5 : 1 for text and 3 : 1 for icons. |
| Overlay A | The palette fix's list of colour changes, in `multigram/palette-fix/overlay_A.json`. |
| Simulator | Python code in `multigram/tools/sim/` that recomputes Telegram's theme colours without Android. It makes overlay A and checks the style table. |
| Seed | A random number stored once per install. The random style and the shapes are derived from it. |
| Knob | One shape or layout choice derived from the seed, such as the bubble corner radius. |
| use_next | An input of the sync workflow. It means "take my fixed `multigram-next` as it is, compile it, and promote it". |

### 1.3 Branches

| Branch or tag | What it holds |
|---|---|
| `forkgram` | One snapshot commit per Forkgram release. |
| `multigram` | The latest snapshot plus the stack. This is the app. |
| `main` | README, the workflows and the scripts in `scripts/`. |
| `multigram-next` | The next `multigram`, while it is being checked or fixed. |
| `multigram-before-<version>` | A tag on each `multigram` the sync replaced. |
| `docs` | This guide. |

### 1.4 What you need

- A clone of `iko-soy/Multigram` with the right to push branches and run workflows.
- git, bash, and Python 3.9 or later. The MultiGram tools use only Python's standard library.
- For a local compile only: JDK 17 and the Android SDK. The CI has both, so you can skip this.
- Optional: the GitHub CLI `gh`. The `gh` commands in this guide were not run while writing it.

### 1.5 How a hook is described

Section 8 describes each of the 84 hooks in the same way:

- **File** and **Where**: the file, the class and method, and (for upstream files) the line where the text starts in Forkgram 12.10.6.
- **Find this**: text to search for. It is copied from the file, so a plain text search finds it. For K1, for K18 to K24 and for H22 it is the text as an earlier stack commit left the file, so it has no Forkgram line number.
- **Change it to**: the change as a diff, copied from the stack commit. Lines starting with `-` go, lines starting with `+` are added, and the other lines are context that stays.
- **Why**: what the hook does.
- **If the code moved**: how to find the right place when the text above is gone.

## 2. After a Telegram update: what to do

1. Open the repository's **Issues** and look for an open issue labelled `forkgram-sync`.
2. Open **Actions > Sync with Forkgram** and look at the latest run.
3. Pick the row that matches:

| What you see | What it means | Go to |
|---|---|---|
| No open issue. The last run is green, and `multigram` sits on the new snapshot (see the command below). | The stack moved by itself. | Build an APK and test it (10.4, 10.5). Also re-derive the palette values once (8.2.5, a few seconds): a colour change upstream can make them too weak without any conflict. |
| An issue "Forkgram sync needs a hand" that says the stack "does not apply" | A conflict: git could not replay one of the commits. | Section 5 |
| An issue that says "the compile check failed", and the failed step is **Compile** | The Java code no longer compiles. | Section 6 |
| The same, but the failed step is **Run MultiGram tool checks** | `check.sh` found a problem. A line `hide-search-bar: ... unreviewed use of the bar height` asks you to review one upstream line, not to fix a bug. | 10.2; for `unreviewed use of the bar height`, 8.5.5 |
| The rebase conflicts in many places, or Forkgram moved or rewrote the code around the hooks | Replaying is not practical. | Section 7, with section 8 for each hook |
| Forkgram released, but there is no run and no issue | The schedule has not run yet, or Forkgram's `dev` branch has not moved. | Section 4.3 (run the sync by hand) |
| The issue or the run says `next-edited` | A fix of yours on `multigram-next` is waiting. The sync did not replace it. | 4.2 |
| The issue or the run says `behind` | `multigram` is still on an older snapshot, because an earlier sync could not move it. | 4.2: run the sync with **force**. If it conflicts, section 5. |
| Telegram has released, but Forkgram has not moved for months | Forkgram has slowed down or stopped. | 4.5 |
| You want to build on plain Telegram instead of Forkgram | | Section 9 |

To see which Forkgram release `multigram` is built on:

```sh
git fetch origin
git log -1 --format=%B origin/forkgram
git merge-base --is-ancestor origin/forkgram origin/multigram && echo "multigram is on the latest snapshot"
```

## 3. The stack at a glance

### 3.1 The seven commits

| Commit | What it does | Upstream files touched | New files | How it is checked |
|---|---|---|---|---|
| d457ac74ae Add the rebrand toolkit | A build-time tool that gives a build its own name, app id, icons, signing key and account type. A stock build is unchanged. | 4: `AppIconsSelectorCell.java`, `DialogsActivity.java`, `ForkSettingsActivity.java`, `TMessagesProj_App/build.gradle` (+9 −3 lines; hooks R1–R5) | 7 | `multigram/rebrand/selftest.py` (run by `check.sh` since 4780eb095b). No script checks the four Java hooks: use the `git grep` in 10.3. |
| 5b53859682 Fix palette contrast for generated accents | Makes grey texts readable (contrast 4.5 : 1), and makes marks on accent fills readable for runtime accents. | 13: `Theme.java`, `ThemeColors.java`, `EmojiThemes.java`, `ChannelColorActivity.java`, `ChatActivityEnterView.java`, `MessageEntityView.java`, `PeerColorActivity.java`, `DarkThemeResourceProvider.java` (+30 −18 lines), and 5 `.attheme` files (36 values); hooks P1–P18 | 4 | `multigram/tools/palette_fix_check.py`; the simulator (8.2.5) |
| cddd62df98 Add the style table and its generator | A precomputed table of 20,480 readable colour styles, and the Python tools that make and check it. Also creates `check.sh`. | none | 17 | `check_style_table.py`, `make_style_table.py --check` |
| 27d32d57b4 Give each install its own random style | Each fresh install picks a day and a night style from the table. Adds "Shuffle my style" to Chat Settings. Generated styles are never uploaded. | 7: `ApplicationLoader.java`, `MessagesController.java`, `Theme.java`, `AlertsCreator.java`, `DefaultThemesPreviewCell.java`, `ThemeActivity.java`, `ThemePreviewActivity.java` (+16 lines; hooks S1–S15) | 6. It also changes `check.sh` and `multigram/tools/README.md`. | `multigram/tools/random_style_check.py` |
| 3b941c01de Randomise shapes and chat list layout per install | Derives corner radii, the chat list layout and the wallpaper phase from the install's seed. | 10: `ApplicationLoader.java`, `Theme.java`, `ThemeActivity.java`, `ChatActionCell.java`, `FragmentFloatingButton.java`, `GradientButtonWithCounterView.java`, `ReactionsLayoutInBubble.java`, `RecyclerListView.java`, `UniversalRecyclerView.java`, `ButtonWithCounterView.java` (+23 −16 lines; hooks K1–K17) | 3. It also changes `RandomStyle.java` and `RandomStyleUi.java` (hooks K18–K22), `check.sh` (K23), and two READMEs. | `multigram/tools/style_knobs_check.py` |
| 4780eb095b Run the rebrand self-test in the CI checks | Adds the rebrand self-test to `check.sh`. | none | none. It changes `check.sh` (K24). | `check.sh` itself |
| ff868b3ea4 Add an option to remove the chat list search bar | "Hide chat list search" in Fork Client Settings removes the search bar and the header search icon from the chat list (the "no search" variant, 8.5.1). Off by default, and then exactly stock. The commit title and the name `HideSearchBar` (class, setting key, string names) come from the first design, which hid only the bar (8.5.4). | 2: `DialogsActivity.java`, `ForkSettingsActivity.java` (+21 −16 lines; hooks H1–H21) | 3. It also changes `check.sh` (H22), `multigram_strings.xml` (two strings) and `multigram/tools/README.md`. | `multigram/tools/hide_search_bar_check.py` |

In total the stack adds 40 new files and touches 30 upstream files:

- 25 Java or Gradle files: 99 added lines (3 of them blank) and 53 removed lines. Most removed lines are replaced by a changed copy.
- 5 `.attheme` files: 36 changed values.

93 of the added lines carry the word `MultiGram`. The other six are the 3 blank lines, and 3 lines whose `// MultiGram:` comment sits on the line above them (hooks R2, R3 and R5).

### 3.2 Why the order matters

Keep the seven commits in this order. Later commits build on earlier ones:

- 27d32d57b4 needs 5b53859682: `RandomStyle` uses `PaletteFix.LAST_STOCK_ACCENT_ID`, and generated styles are only readable with the palette fix.
- 27d32d57b4 needs cddd62df98: it reads the style table asset, and it adds a step to `check.sh`, which cddd62df98 creates.
- 3b941c01de needs 27d32d57b4: `StyleKnobs` uses `RandomStyle`, hook K1 sits on the line after hook S1, and the commit changes `RandomStyle.java` and `RandomStyleUi.java`.
- 4780eb095b needs d457ac74ae (the self-test) and cddd62df98 (`check.sh`).
- ff868b3ea4 needs 27d32d57b4, which creates `multigram_strings.xml`, and cddd62df98, which creates `check.sh` and `multigram/tools/README.md`. Its `check.sh` block sits between the knobs block (3b941c01de) and the self-test block (4780eb095b), and its README lines follow the knobs lines (3b941c01de), so it goes last. Its hooks in `DialogsActivity.java` and `ForkSettingsActivity.java` do not depend on the other commits: they apply to plain Forkgram too.
- The file `overlay_A.json` exists twice: `multigram/palette-fix/overlay_A.json` (from 5b53859682) and `multigram/tools/sim/palette-fix/overlay_A.json` (from cddd62df98). The two copies must stay byte-identical. No script checks this; the `cmp` line in 5.4 does.

## 4. The automatic sync, briefly

The full description is in `README.md` on `main` ("How the sync works" and "When the sync issue opens"), and in `bash scripts/sync-forkgram.sh --help`. This section is a summary.

### 4.1 What it does

The workflow **Sync with Forkgram** (`.github/workflows/sync-forkgram.yml` on `main`) runs every 6 hours, at 23 minutes past the hour (`cron: '23 */6 * * *'`, UTC). You can also start it by hand. It has four jobs:

1. **sync** runs `scripts/sync-forkgram.sh`. It reads the tip of Forkgram's `dev` branch. If the tip is new, it adds a snapshot commit to `forkgram`. Then it replays the stack onto the new snapshot as `multigram-next`, with `git rebase --onto`. It pushes `forkgram` and `multigram-next` in one push.
2. **compile** runs the workflow **Build MultiGram** on `multigram-next`: the Java compile and `check.sh` (see 10.1).
3. **promote** runs only if the compile passed. It tags the old `multigram` as `multigram-before-<version>`, moves `multigram` to `multigram-next`, and deletes `multigram-next`.
4. **report** (`scripts/sync-report.py`) opens, updates or closes the issue labelled `forkgram-sync`. The issue title is "Forkgram sync needs a hand (Forkgram <version>)". It holds the exact commands for the case at hand.

A new snapshot's commit message names its source in the lines `Source:`, `Forkgram-Commit:`, `Forkgram-Version:` and `Telegram-Base:`. The last one is left out when the sync cannot find Telegram's "update to ..." commit in Forkgram's history.

### 4.2 What each outcome means

The sync script ends by printing `status=<value>`.

| Status | What it means | What you do |
|---|---|---|
| `up-to-date` | Nothing new. | Nothing. |
| `candidate` | The stack was replayed onto the new snapshot. The compile job runs next. | Wait for the run to finish. |
| `promoted` (promote job) | `multigram` moved to the new release. The old tip is tagged `multigram-before-<version>`. | Build an APK and test it (10.4, 10.5). |
| `unchanged` (promote job) | `multigram` already was the candidate. `multigram-next` was deleted. | Nothing. |
| `conflict` (exit status 2) | A stack commit does not apply. `forkgram` has the new snapshot, and `multigram` is unchanged. | Section 5. |
| A failed compile job | The stack applied, but the compile or `check.sh` failed. `multigram-next` holds the candidate. | Section 6. |
| `next-edited` | `multigram-next` has commits the sync did not make (your fix). The sync changed nothing. | Run the workflow with **use_next**, or delete the branch (`git push origin --delete multigram-next`). |
| `behind` | No new release, but `multigram` is still on an older snapshot, because an earlier problem was never fixed. | Finish the fix and run **use_next**, or run with **force** to retry. |
| `error` | Something else: Forkgram unreachable, a rejected push, a `.github` folder in the stack, or a merge commit with changes of its own. | Read the message on the issue, fix the cause, run again. |

Keep `multigram` linear: rebase, never merge. The replay flattens merges, and a merge commit with changes of its own stops the sync.

### 4.3 Running the sync by hand

In the browser: **Actions > Sync with Forkgram > Run workflow**. The inputs:

| Input | Use it when |
|---|---|
| (none) | You want an extra run now, for example right after a Forkgram release. |
| **force** | You want to rebuild `multigram-next` although Forkgram has no new release: to retry after a failed compile, or to test the pipeline. |
| **use_next** | You fixed `multigram-next` yourself. The run compiles it and, if that passes, promotes it. It first checks that `multigram-next` carries every commit on `multigram`, matched by author and subject, or by patch content. |
| **allow_drop** | Only with **use_next**: your `multigram-next` leaves out some commits on purpose. |

The same from a terminal (not run while writing this guide):

```sh
gh workflow run sync-forkgram.yml -R iko-soy/Multigram --ref main -f use_next=true
gh workflow run sync-forkgram.yml -R iko-soy/Multigram --ref main -f force=true
gh run list -R iko-soy/Multigram --workflow sync-forkgram.yml -L 5
gh run rerun <run-id> -R iko-soy/Multigram --failed
```

The last command is the same as the **Re-run failed jobs** button. Use it when a run failed because of a runner or network problem.

### 4.4 Running the sync locally

This uses your clone's rerere memory (5.6). Run it from a checkout of `main`. It refuses to run while `forkgram` or `multigram-next` is checked out in any worktree.

```sh
git fetch origin
git switch main
bash scripts/sync-forkgram.sh --remote origin
```

That leaves the results in your local `forkgram` and `multigram-next` branches. Add `--push` to push them too. Sections 5 to 7 start from `origin/forkgram`, so use `--push` when you go on to them. After a local `--push`, start the workflow with **use_next**, not **force**: a forced run starts from a fresh clone without your rerere memory, and would hit the same conflict again.

To test the sync scripts themselves against fake repositories:

```sh
bash scripts/selftest-sync.sh
```

On `main` da0cc7c548 it ended with `183 passed, 0 failed` after about 10 seconds.

### 4.5 When Forkgram stops

Forkgram follows Telegram with a delay. If Telegram has released and Forkgram's `dev` branch has not moved for months, compare the `Telegram-Base` line of `git log -1 --format=%B origin/forkgram` with the newest "update to ..." commit at https://github.com/DrKLO/Telegram. Then choose one of these:

- **Stay on the last snapshot.** Nothing to do. The scheduled sync reports `up-to-date` until Forkgram moves again.
- **Follow another fork.** The sync script reads its source from the environment variables `FORKGRAM_URL` and `FORKGRAM_BRANCH` (defaults `https://github.com/forkgram/TelegramAndroid` and `dev`), or from the options `--url` and `--branch`. It takes the version from `APP_VERSION_NAME` in the source's `gradle.properties`. On Actions, add both variables to the `env:` of the **Sync** step in `.github/workflows/sync-forkgram.yml` on `main`, then run the workflow. The workflow does not set them today.
- **Move to plain Telegram.** Read section 9 first. The sync can take Telegram itself as the source, in the same way.

To see what the sync makes of another source before you change the workflow, run it locally from a checkout of `main` (4.4), without `--push`:

```sh
bash scripts/sync-forkgram.sh --remote origin --url https://github.com/DrKLO/Telegram --branch master
```

On 2026-09-27, with DrKLO's `master` at dc780e81e, it made a snapshot titled `Forkgram 12.10.5 snapshot` (the script says "Forkgram" whatever the source) with a correct `Telegram-Base` line. Then it ended with `status=conflict` at commit 1 of 6 (the stack had six commits then): the three conflicts of 9.1. With any new source, expect to settle conflicts with section 5 or 7. Afterwards update the stamp (11.2).

This trial run leaves its snapshot in your local `forkgram` branch, and a trial `multigram-next` if the replay went through. A later local sync that finds nothing new does not reset them. Never push them: 5.1 pushes your local `forkgram`. Put `forkgram` back with `git branch -f forkgram origin/forkgram`. If there is a trial `multigram-next`, delete it with `git branch -D multigram-next`.

## 5. Fixing a conflicting replay

Use this section when the sync issue says the stack "does not apply". The issue names the commit that stopped and the files involved.

### 5.1 Replay the stack by hand

The new snapshot must be on `origin/forkgram`. After a sync on Actions it is. If you ran the sync locally (4.4) without `--push`, push the snapshot first with `git push origin forkgram`.

```sh
git fetch origin
git switch -C multigram-next origin/multigram
git config rerere.enabled true
git rebase origin/forkgram
```

The third line switches on rerere for this clone (5.6). Git replays the seven commits one by one. It stops at the first one that conflicts and names the files. If git answers `Current branch multigram-next is up to date.`, `origin/forkgram` is still the old snapshot: `git log -1 --format=%B origin/forkgram` shows which release it holds.

`git switch -C` resets a local `multigram-next`. If yours holds work you have not pushed and want to keep, rename it first: `git branch -m multigram-next my-fix`.

The issue shows a longer form, `git rebase --onto <new snapshot> <old snapshot>`. It does the same thing, because each new snapshot is a child of the previous one.

### 5.2 Read and fix a conflict

Example output, from a test with a made-up Forkgram 12.10.7 that changed the line under hook S2:

```text
Rebasing (1/7)Rebasing (2/7)Rebasing (3/7)Rebasing (4/7)Auto-merging TMessagesProj/src/main/java/org/telegram/messenger/MessagesController.java
CONFLICT (content): Merge conflict in TMessagesProj/src/main/java/org/telegram/messenger/MessagesController.java
error: could not apply 27d32d57b4... Give each install its own random style
```

The file then contains this (example output; the first line inside the markers is the made-up Forkgram change):

```text
<<<<<<< HEAD
        if (themeInfo == null || accent == null) {
=======
        if (org.telegram.messenger.multigram.RandomStyle.isUploadBlocked(themeInfo, accent)) return; // MultiGram: a generated style never leaves the device
        if (themeInfo == null) {
>>>>>>> 27d32d57b4 (Give each install its own random style)
            return;
        }
```

How to read it:

- Between `<<<<<<< HEAD` and `=======` is the **new Forkgram** code.
- Between `=======` and `>>>>>>>` is the **old Forkgram** code with the MultiGram hook in it.
- Never take the MultiGram side as a whole. It would bring back Forkgram's old code.
- Git also reports a conflict when Forkgram only changed a line next to a hook, as here.

How to fix it depends on the hook. Its "Change it to" block in section 8 shows which kind it is:

- **The hook only adds lines** (the block has no `-` line), as S2 here. Keep Forkgram's new code and put the MultiGram line back where the hook's "Where" says. If Forkgram added a line at the same spot, the hook's "Where" and "If the code moved" say which comes first. For example, P11 goes after every calculated-colour call, and S10 goes directly after `themeListRow2 = rowCount++;`.
- **The hook replaces an upstream line** (the block has a `-` line), as R2 to R4, P1 to P6, P8, P12, P14, P15, P18, K3 to K7, K9 to K14, K16, H1 to H10, H14 to H18 and H21. Take Forkgram's new line and make the MultiGram change to it again. Keep only that one line, not both. For example, if Forkgram changed the default title from `"Fork Client"` to `"Forkgram"`, R2 becomes `getString("forkCustomTitle", org.telegram.messenger.multigram.Rebrand.defaultTitle("Forkgram"))`. For the colour lines of P1 to P6, 5.3 says what to do.
- Delete the three marker lines.

Four hooked files end without a final newline: `assets/arctic.attheme`, `assets/day.attheme`, `ui/Components/RecyclerListView.java` and `ui/PeerColorActivity.java`. Keep it that way. Many editors add one when they save (in vim, `:set nofixendofline` stops that). Check with `git diff`: it must not show the last line as changed. An added newline makes `palette_fix_check.py --base` report `unexpected arctic.attheme change: <last line>`, and `style_knobs_check.py --base` report `added line without a "MultiGram:" marker: }`.

The fixed text in this example:

```text
        if (org.telegram.messenger.multigram.RandomStyle.isUploadBlocked(themeInfo, accent)) return; // MultiGram: a generated style never leaves the device
        if (themeInfo == null || accent == null) {
```

To see which hooks the stopped commit puts in a file, run `git show REBASE_HEAD -- <file>`. Section 8 explains each hook, and 5.3 says what a conflict in each file usually means.

When a file is fixed:

```sh
git add <file>
git rebase --continue
```

Repeat until git prints `Successfully rebased and updated refs/heads/multigram-next.` To give up and go back, run `git rebase --abort`.

### 5.3 What a conflict in each file usually means

| File | Hooks | A conflict here usually means |
|---|---|---|
| `ui/Cells/AppIconsSelectorCell.java` | R1 | Forkgram changed how the app icon list is built. Put the filter call after the list is filled. |
| `ui/DialogsActivity.java` | R2, H1–H18, H21 | Forkgram changed the chat list title code (R2), or the code of the chat list's header, padding, scrolling, action mode or search field (the H hooks). For R2, wrap every literal default of `forkCustomTitle` again. For an H hook, take Forkgram's new line and make the hook's small change in it again: most only wrap `SEARCH_FIELD_HEIGHT` inside a `dp(...)` (8.5.6). H21 goes on the `factor0` line of `checkUi_itemSearchVisibility`, not on the identical line above it. Then run `hide_search_bar_check.py`: it also names every new use of the bar height. |
| `ui/ForkSettingsActivity.java` | R3, R4, H19, H20 | Forkgram changed its own settings screen. Wrap the custom title defaults again. Put the "Hide chat list search" row back right after the Disable Global Search row (H19), and its click hook right after `final int id = item.id;` in `onClick` (H20). If the file was renamed, git reports it as deleted: find the new file with `git grep -n '"forkCustomTitle"'`. |
| `TMessagesProj_App/build.gradle` | R5 | Forkgram added lines at the end of the file. Keep them, and keep the `apply from:` line last. |
| `ui/ActionBar/ThemeColors.java` | P1 | Forkgram changed a stock colour next to, or on, one of the 11 grey lines. Take MultiGram's line for the 11 keys that carry `// MultiGram: contrast fix`, and Forkgram's line for every other key. The simulator is not in the tree at this stop (it comes with cddd62df98), so re-derive the values after the rebase (5.4). |
| `assets/*.attheme` (5 files) | P2–P6 | Forkgram changed a colour of a bundled theme. As for ThemeColors: MultiGram's value for the keys of P2 to P6, Forkgram's for all others, and re-derive after the rebase. |
| `ui/ActionBar/EmojiThemes.java` | P7 | Forkgram changed how per-chat themes build their colours. Put the call back after `fillAccentColors`, in `createColors` only. |
| `ui/ActionBar/Theme.java` | P8–P12, S3, S4, K2 | Forkgram changed the theme engine. Keep the new code and put each hook back at the same logical place. Then diff the engine methods, because the simulator copies them (8.3.6), and re-derive the palette values (8.2.5). |
| `ui/ChannelColorActivity.java`, `ui/PeerColorActivity.java`, `ui/Components/Paint/Views/MessageEntityView.java` | P13, P17, P16 | The screen's preview colour code changed. Put the call back after `fillAccentColors`. |
| `ui/Components/ChatActivityEnterView.java` | P14, P15 | The send button's drawing code changed. Every mark drawn on the button's fill must use `multigramGlyphColor` when it is not 0. |
| `ui/Stories/DarkThemeResourceProvider.java` | P18 | The dark provider's colour lookup changed. Its fallback must go through `getOverrideFallbackColor`. |
| `messenger/ApplicationLoader.java` | S1, K1 | Forkgram changed the app start. S1 and K1 must still run after `applicationContext` is set and before anything loads `Theme`. |
| `messenger/MessagesController.java` | S2 | Forkgram changed the theme upload. The guard must stay the first statement of `saveThemeToServer`. |
| `ui/Components/AlertsCreator.java` | S5 | The "create theme" dialog changed. The call goes right after the fragment check. |
| `ui/DefaultThemesPreviewCell.java` | S6 | The theme strip changed. The call stays the first statement of `updateDayNightMode()`. |
| `ui/ThemePreviewActivity.java` | S7 | The accent editor changed. The call stays right after the editor gets its accent. |
| `ui/ThemeActivity.java` | S8–S15, K15–K17 | Chat Settings changed: rows, menus or the list adapter. Put each hook back by its landmark (the rows, the reset menu, the click listener, the view types). `random_style_check.py` and `style_knobs_check.py` check the placement. |
| `ui/Cells/ChatActionCell.java` | K3, K4 | The service pill drawing changed. Wrap the corner constants again, and keep the offset in step. |
| `ui/Components/FragmentFloatingButton.java` | K5–K7 | The floating button changed. Route its background, outline and small-button radius through `StyleKnobs` again. |
| `ui/Components/Premium/boosts/GradientButtonWithCounterView.java` | K8 | The gradient button changed. Keep `setRoundRadius(8)` at the end of its constructor. |
| `ui/Components/Reactions/ReactionsLayoutInBubble.java` | K9, K10 | Reaction chip drawing changed. Both radius lines must use the same function. |
| `ui/Components/RecyclerListView.java`, `ui/Components/UniversalRecyclerView.java` | K11, K12 | The settings card code changed. Wrap the default radius in every default `setSections` overload. |
| `ui/Stories/recorder/ButtonWithCounterView.java` | K13, K14 | The shared button changed. The field and the constructor must both use `radiusDp`. |

All Java paths above start with `TMessagesProj/src/main/java/org/telegram/`, and the `.attheme` files are in `TMessagesProj/src/main/assets/`.

The stack's new files never conflict: they do not exist in Forkgram.

### 5.4 Finish and hand it back

When the rebase is done, check the result. These are the checks the CI runs, plus stricter versions:

```sh
bash multigram/tools/check.sh
python3 multigram/tools/palette_fix_check.py --base origin/forkgram
python3 multigram/tools/random_style_check.py --base origin/forkgram
python3 multigram/tools/style_knobs_check.py --base origin/forkgram
python3 multigram/tools/hide_search_bar_check.py --base origin/forkgram
git grep -n -e 'multigram\.Rebrand\.' -e 'multigram/rebrand/rebrand.gradle' -- TMessagesProj TMessagesProj_App
git grep -n '"forkCustomTitle"' -- TMessagesProj/src/main/java
cmp multigram/palette-fix/overlay_A.json multigram/tools/sim/palette-fix/overlay_A.json && echo "overlay copies identical"
```

- `check.sh` must end with `== all MultiGram checks passed` (about 1 to 3 minutes; section 10.2 explains each part).
- Each of the four Python checks must print one line ending in `OK`. With `--base`, `random_style_check.py`, `style_knobs_check.py` and `hide_search_bar_check.py` also require the `MultiGram:` marker on every non-blank line the stack adds to their hooked files, and `palette_fix_check.py` checks that `ThemeColors.java` and the `.attheme` files change only the keys of overlay A.
- The first `git grep` must print 5 lines (hooks R1 to R5). Only R5 is also checked by a script (the rebrand self-test in `check.sh`).
- The second `git grep` lists every use of the title setting. On ff868b3ea4 it prints 4 lines. Each line that reads the setting must pass its default through `Rebrand.defaultTitle(` or use `defaultValue` (R2 to R4). A doubled line here means a conflict was fixed by keeping both sides.
- The `cmp` must print `overlay copies identical`. If it does not, copy `multigram/palette-fix/overlay_A.json` over the other copy and fold that into "Add the style table and its generator" (6.3).

If the conflict was in `ThemeColors.java`, an `.attheme` file or `Theme.java`, also re-derive the palette values (8.2.5).

Then push, and let the sync compile and promote your branch:

```sh
git push --force origin multigram-next
```

Open **Actions > Sync with Forkgram > Run workflow**, tick **use_next**, and run it. If the compile passes, `multigram` moves to your branch and the issue closes.

### 5.5 Leaving a commit out

If Forkgram now does what a MultiGram commit did, run `git rebase --skip` when git stops at that commit. The commit is then left out. Tick **allow_drop** as well as **use_next** when you run the workflow, or it refuses a branch that lacks a commit.

The automatic replay drops a commit by itself when it becomes empty because Forkgram took the same change. The closing note on the issue lists such commits.

The last commit, "Add an option to remove the chat list search bar", can be left out as a whole. No other commit needs it. If Telegram rewrites the chat list header so that its hooks no longer fit, and you do not want to port them now, skip it the same way and tick **allow_drop**. The option, its check and its `check.sh` block all go with it, so also leave out the `hide_search_bar_check.py` line of 5.4. Anyone who had the option on gets the stock chat list back.

### 5.6 rerere: git's memory of your fixes

With `rerere.enabled`, git records how you fixed each conflict. If you redo the same rebase in the same clone, git fills in the same fix. It still stops, and you still run `git add` and `git rebase --continue`. To have git stage its replayed fixes by itself, also run `git config rerere.autoUpdate true`.

rerere only knows the fixes recorded in the clone where you made them. The scheduled sync starts from a fresh clone every time. So it reports the same conflict again until `multigram` carries your fix. That is why you push `multigram-next` and run **use_next**.

### 5.7 Using patches instead of a rebase

You can also export the stack as patch files and apply them to any Forkgram checkout. From a checkout of `main`:

```sh
git fetch origin
bash scripts/export-patches.sh --base origin/forkgram --head origin/multigram
```

It writes seven numbered `.patch` files and `APPLY.txt` to the folder `multigram-patches/`. `APPLY.txt` says how to clone the matching Forkgram release and apply them with `git am -3`. The `-3` lets git merge like a rebase when the text around a hook changed.

When a patch conflicts, git stops. The markers read `<<<<<<< HEAD` (Forkgram) and `>>>>>>> <commit subject>`. Fix the file as in 5.2, then:

```sh
git add <file>
git am --continue
```

Other commands: `git am --skip` leaves a patch out, `git am --abort` goes back, and `git am --show-current-patch=diff` shows the patch that failed. To export again into the same folder, add `--force` to `export-patches.sh`.

A shallow clone (`--depth 1`) of a newer Forkgram release lacks the old files that `-3` needs. Git then fails with `Repository lacks necessary blobs to fall back on 3-way merge.` Fetch the release the patches were made on into the same clone, and start again:

```sh
git am --abort
git fetch --depth 1 origin tag 12.10.6.0
git am -3 /path/to/multigram-patches/*.patch
```

The tag is the Forkgram version the patches were exported from, plus `.0`.

## 6. Fixing a compile failure

Use this section when the sync issue says "the compile check failed". The stack applied, and the candidate is on `multigram-next`.

### 6.1 Find what failed

Open the run page linked from the issue. In the job **Compile Java and Kotlin**, see which step failed:

- **Compile**: a Java or Kotlin error. Read on.
- **Run MultiGram tool checks**: `check.sh` failed. See 10.2.
- A step failed with a network or runner error: press **Re-run failed jobs**. Nothing else is needed.

From a terminal (not run while writing this guide):

```sh
gh run view <run-id> -R iko-soy/Multigram --log-failed
```

The Java compiler prints each error as `<file>:<line>: error: <message>`. Search the log for `error:`.

### 6.2 Common errors

| The error mentions | Likely cause | Fix |
|---|---|---|
| `cannot find symbol` and `isMonet()` in `PaletteFix.java` or `RandomStyle.java` | Forkgram renamed or removed `Theme.ThemeInfo.isMonet()`. | Use the new name, or drop the Monet condition. The calls are at `PaletteFix.java` lines 165 and 225, and `RandomStyle.java` lines 449 and 624. |
| `cannot find symbol` and a `key_...` name | Telegram renamed or removed a colour key in `Theme.java`. | Rename it everywhere MultiGram names it, with and without the `key_` prefix (see below the table). The `git grep` below the table finds every place. Most keys of overlay A are in `PaletteFix.java`, both `overlay_A.json` copies, `overlay_B.json` and the simulator (`sim/readability.py`, `sim/canvas.py`, two in `sim/engine.py`). A few keys are also in `style_table.py`, `style_knobs_check.py`, `RandomStyleUi.java` or a README. Fix the simulator first: until then `canvas.py --build` stops with a Python `KeyError` naming the old key. Then re-derive the palette (8.2.5). |
| `reference to getColor is ambiguous` in `PaletteFix.java` | Upstream added another `Theme.getColor` with three arguments. | Change `Theme.getColor(key, null, true)` at `PaletteFix.java` line 316 to `Theme.getColor(key, (boolean[]) null, true)`. |
| `getAccent`, `saveThemeAccents`, `deleteThemeAccent` or a `ThemeAccent` field in `RandomStyle.java` | Telegram changed the accent API. | Read the new methods and adjust `RandomStyle` (8.3.6). |
| `SharedConfig.bubbleRadius`, `useThreeLinesLayout` or `setUseThreeLinesLayout` in `StyleKnobs.java` | Telegram renamed a chat setting. | Use the new names (8.4.6). |
| `duplicate case label` in `ThemeActivity.java` | Upstream now binds one of the three knob row types itself. | Call `bindStyleKnobRow` from upstream's `case` and remove hook K17's line. |
| `cannot find symbol` and `DEFAULT` in `Rebrand.java` | Forkgram renamed `LauncherIconController.LauncherIcon.DEFAULT`. | Point `Rebrand.filterLauncherIcons` at the new default icon entry (R1). |
| `cannot find symbol` and `setMultiline` in `HideSearchBar.java` | Forkgram removed `UItem.setMultiline`, which it added to Telegram's `UItem`. | Build the row the way Forkgram now builds its own Chat list rows, next to H19. |
| `cannot find symbol` for a variable or method used in a hook line, such as `applyingTheme`, `accent`, `sparseIntArray` or `getMaxScrollYOffsetWithoutSearch` | Upstream renamed a local variable, field or method. | Use the new name in the hook line. Keep the `// MultiGram:` comment. If a check script matches that line exactly, update its pattern too. |
| `cannot find symbol` for any other method, class or field, in a file under `org/telegram/messenger/multigram/` | Upstream renamed or removed a name that a new file uses. The "Upstream names it relies on" columns of 8.1.2, 8.2.2, 8.3.2, 8.4.2 and 8.5.2 list these names. | Find the new name, and fix every use (see below the table). `check.sh` does not find this; only the compile does. |
| A Gradle message that starts with `[rebrand]` | `rebrand.gradle` found a problem. | See the list of messages in 8.1.5. |
| A Gradle error that the task `buildNativeDeps` does not exist | Forkgram renamed or removed its native build task. The compile command skips it with `-x :TMessagesProj:buildNativeDeps`. | Update `.github/workflows/build.yml` on `main`. |

**When upstream renamed a name.** To see what became of it, search the upstream changes since the snapshot `multigram` is built on. The first command below prints each changed line that holds the old name, with three lines around it, so the new line next to a removed one shows too. The second lists every place MultiGram uses the old name, in the new files and the tools:

```sh
git diff $(git merge-base origin/multigram origin/forkgram) origin/forkgram -- TMessagesProj/src/main/java | grep -C 3 '<old name>'
git grep -n -w '<old name>' -- TMessagesProj/src/main/java/org/telegram/messenger/multigram multigram
```

For a colour key, search for both spellings, as in `git grep -n -w -e key_chat_inViews -e chat_inViews -- TMessagesProj/src/main/java/org/telegram/messenger/multigram multigram`: the Java code uses the `key_` prefix, the theme files and some tools do not.

A rename can hit files of several stack commits. For example, a rename of `Theme.getActiveTheme()` hits `PaletteFix.java` (5b53859682) and `RandomStyle.java` and `RandomStyleUi.java` (27d32d57b4). Fold each file into its own commit (6.3).

### 6.3 Fold the fix into the commit it belongs to

The fix must go into the stack commit it belongs to, not on top as an eighth commit. A "fixup" commit and an automatic rebase do that.

**1. Get the branch.** Coming from 6.1 (a failed compile on Actions), start from the candidate the sync pushed:

```sh
git fetch origin
git switch -C multigram-next origin/multigram-next
```

Skip these two commands if you are already on your own `multigram-next` (from section 5, or from 7.5). `git switch -C` would replace your local branch, and everything on it you have not pushed, with the remote one.

**2. Find the commit each change belongs to.** This lists the seven commits with their short hashes:

```sh
git log --oneline origin/forkgram..multigram-next
```

Each file, and each line, belongs to the commit that added it. For a file the stack adds: `git log --format='%h %s' --diff-filter=A origin/forkgram..multigram-next -- <file>`. For line `n` of any file: `git blame -s -L n,n HEAD -- <file>` (with `HEAD`, it reads the committed file, so it also works after you have edited the line). The tables in 3.1 and 7.2 help too.

A fix can belong to several commits. For example, a rename in upstream code can hit `PaletteFix.java` (5b53859682) and `RandomStyle.java` (27d32d57b4).

**3. Make one fixup commit per stack commit.** Name the files. Do not use `git commit -a`: it puts every edited file into one fixup, so changes land in the wrong commit, and the rebase can stop with the `CONFLICT (modify/delete)` described at the end of this step. The sync issue and `README.md` on `main` give the same per-commit command.

```sh
git commit --fixup=<hash of commit A> -- <files of commit A>
git commit --fixup=<hash of commit B> -- <files of commit B>
GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash origin/forkgram
```

If one file needs changes for two commits (`Theme.java` holds hooks of three), edit the lines of one commit, run its `git commit --fixup`, then edit the lines of the next.

`--fixup` makes a commit titled `fixup! <subject>`. `--autosquash` melts it into the commit with that subject. `GIT_SEQUENCE_EDITOR=:` accepts the plan without opening an editor. Afterwards the branch has seven commits again, with the same subjects and authors: `git log --oneline origin/forkgram..multigram-next` shows them.

If the rebase stops with `CONFLICT (modify/delete): <file> deleted in HEAD and modified in ... (fixup! ...)`, a fixup holds a file that its commit does not have yet. Run `git rebase --abort`, then `git reset HEAD~1` for one fixup commit (`HEAD~2` for two, and so on). That removes the fixup commits and keeps your edits in the files. Then make the fixups again, one per commit.

**4. Hand it back.** Coming from 7.5, go on with 7.6 instead. Otherwise push:

```sh
git push --force origin multigram-next
```

Then open **Actions > Sync with Forkgram > Run workflow** and tick **use_next**.

### 6.4 Compiling locally

This is what the CI runs. It was not run while writing this guide, because it needs JDK 17 and the Android SDK:

```sh
git submodule update --init --depth 1 TMessagesProj/lib/jlatexmath TMessagesProj_Modules/media
./gradlew --no-daemon --stacktrace -x :TMessagesProj:buildNativeDeps :TMessagesProj:compileReleaseJavaWithJavac :TMessagesProj_App:compileAfatReleaseJavaWithJavac
bash multigram/tools/check.sh
```

Gradle finds the SDK through `ANDROID_HOME` or a `local.properties` file with `sdk.dir=<path>`. The CI also appends `org.gradle.jvmargs=-Xmx6g -XX:MaxMetaspaceSize=1g` to `gradle.properties`. Do that if Gradle runs out of memory, but do not commit it.

## 7. Re-applying the stack by hand

Use this section when a rebase is not practical: many conflicts, or files that Forkgram moved or rewrote. You start from the new snapshot and add MultiGram's changes again.

The result must again be seven commits with the same subjects and authors. Then the sync's **use_next** accepts it.

If a rebase from section 5 is still running, stop it first with `git rebase --abort`: git refuses to switch branches during a rebase.

### 7.1 Get the base

The new Forkgram release must be on `forkgram` first. The sync pushes the new snapshot even when the replay conflicts, so after a sync run it is there. If no sync has run, run it locally from a checkout of `main` (4.4) with `--push`.

Then:

```sh
git fetch origin
git switch -C multigram-next origin/forkgram
OLD=origin/multigram
OLDSNAP=$(git merge-base $OLD origin/forkgram)
git log -1 --format=%B origin/forkgram
```

- `OLD` is the stack you re-apply. A tag `multigram-before-<version>` works too.
- `OLDSNAP` is the old snapshot that `OLD` sits on.
- The last command shows which Forkgram release you are on.
- `git switch -C` resets a local `multigram-next`, as in 5.1.

The next steps use these two shell variables. If you open a new terminal, set them again.

### 7.2 Copy all new files

One command copies all 40 files the stack adds, as they are on `OLD`:

```sh
git checkout $OLD -- multigram TMessagesProj/src/main/java/org/telegram/messenger/multigram \
  TMessagesProj/src/main/res/values/multigram_rebrand.xml TMessagesProj/src/main/res/values/multigram_strings.xml \
  TMessagesProj/src/main/assets/multigram_styles.bin
git reset -q
```

`git reset -q` un-stages the files but leaves them in place, so the checks of 7.4 can run from the start. Do not commit these copies: they are the versions of `OLD`, and 7.3 copies each commit's own files again at that commit's version. `git status --short` now shows 5 untracked entries: the 2 folders and the 3 single files.

None of these paths exists in Forkgram 12.10.6. If a future Forkgram adds a file with one of these names, `git checkout` would overwrite it. This command must print nothing:

```sh
git ls-tree -r --name-only origin/forkgram -- multigram TMessagesProj/src/main/java/org/telegram/messenger/multigram TMessagesProj/src/main/res/values/multigram_rebrand.xml TMessagesProj/src/main/res/values/multigram_strings.xml TMessagesProj/src/main/assets/multigram_styles.bin
```

The 40 files:

| # | Path | Added by | Section |
|---|---|---|---|
| 1 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/Rebrand.java` | d457ac74ae | 8.1 |
| 2 | `TMessagesProj/src/main/res/values/multigram_rebrand.xml` | d457ac74ae | 8.1 |
| 3 | `multigram/rebrand/.gitignore` | d457ac74ae | 8.1 |
| 4 | `multigram/rebrand/README.md` | d457ac74ae | 8.1 |
| 5 | `multigram/rebrand/generate_rebrand.py` | d457ac74ae | 8.1 |
| 6 | `multigram/rebrand/rebrand.gradle` | d457ac74ae | 8.1 |
| 7 | `multigram/rebrand/selftest.py` | d457ac74ae | 8.1 |
| 8 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/PaletteFix.java` | 5b53859682 | 8.2 |
| 9 | `multigram/palette-fix/README.md` | 5b53859682 | 8.2 |
| 10 | `multigram/palette-fix/overlay_A.json` | 5b53859682 | 8.2 |
| 11 | `multigram/tools/palette_fix_check.py` | 5b53859682 | 8.2 |
| 12 | `TMessagesProj/src/main/assets/multigram_styles.bin` | cddd62df98 | 8.3 |
| 13 | `multigram/tools/.gitignore` | cddd62df98 | 8.3 |
| 14 | `multigram/tools/README.md` | cddd62df98 | 8.3 |
| 15 | `multigram/tools/check.sh` | cddd62df98 | 8.3 |
| 16 | `multigram/tools/check_style_table.py` | cddd62df98 | 8.3 |
| 17 | `multigram/tools/make_style_table.py` | cddd62df98 | 8.3 |
| 18 | `multigram/tools/sim/README.md` | cddd62df98 | 8.3 |
| 19 | `multigram/tools/sim/canvas.py` | cddd62df98 | 8.3 |
| 20 | `multigram/tools/sim/detmath.py` | cddd62df98 | 8.3 |
| 21 | `multigram/tools/sim/detmath_tables.py` | cddd62df98 | 8.3 |
| 22 | `multigram/tools/sim/engine.py` | cddd62df98 | 8.3 |
| 23 | `multigram/tools/sim/palette-fix/overlay_A.json` | cddd62df98 | 8.3 |
| 24 | `multigram/tools/sim/palette-fix/overlay_B.json` | cddd62df98 | 8.3 |
| 25 | `multigram/tools/sim/readability.py` | cddd62df98 | 8.3 |
| 26 | `multigram/tools/sim/style_sim.py` | cddd62df98 | 8.3 |
| 27 | `multigram/tools/sim/tgsrc.py` | cddd62df98 | 8.3 |
| 28 | `multigram/tools/style_table.py` | cddd62df98 | 8.3 |
| 29 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyle.java` | 27d32d57b4 | 8.3 |
| 30 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyleUi.java` | 27d32d57b4 | 8.3 |
| 31 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/StyleTable.java` | 27d32d57b4 | 8.3 |
| 32 | `TMessagesProj/src/main/res/values/multigram_strings.xml` | 27d32d57b4 | 8.3 |
| 33 | `multigram/random-style/README.md` | 27d32d57b4 | 8.3 |
| 34 | `multigram/tools/random_style_check.py` | 27d32d57b4 | 8.3 |
| 35 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/StyleKnobs.java` | 3b941c01de | 8.4 |
| 36 | `multigram/style-knobs/README.md` | 3b941c01de | 8.4 |
| 37 | `multigram/tools/style_knobs_check.py` | 3b941c01de | 8.4 |
| 38 | `TMessagesProj/src/main/java/org/telegram/messenger/multigram/HideSearchBar.java` | ff868b3ea4 | 8.5 |
| 39 | `multigram/hide-search-bar/README.md` | ff868b3ea4 | 8.5 |
| 40 | `multigram/tools/hide_search_bar_check.py` | ff868b3ea4 | 8.5 |

### 7.3 Put the hooks back, commit by commit

Work through the seven commits in order. For each one: copy the commit's own files at that commit's version, put its hooks into the upstream files, and commit with the same message and author.

**The quick way: a loop.** This loop does that for every commit. For each upstream file it tries the commit's change with `git apply -3`, which merges the way a rebase does. It stops at the first commit with a file it cannot patch cleanly, and names the files.

```sh
START=$OLDSNAP
for C in $(git rev-list --reverse $START..$OLD); do
  echo "== $(git log -1 --format='%h %s' $C)"
  new=$(git diff-tree --no-commit-id -r --name-only --diff-filter=A $C)
  own=$(git diff-tree --no-commit-id -r --name-only --diff-filter=M $C -- multigram TMessagesProj/src/main/java/org/telegram/messenger/multigram)
  up=$(git diff-tree --no-commit-id -r --name-only --diff-filter=M $C -- . ':!multigram' ':!TMessagesProj/src/main/java/org/telegram/messenger/multigram')
  if [ -n "$new$own" ]; then git checkout $C -- $new $own; fi
  todo=
  for f in $up; do
    git diff $C^ $C -- $f | git apply -3 --index || todo="$todo $f"
  done
  if [ -n "$todo" ]; then
    echo "STOPPED at $C. Put the hooks of these files in by hand:$todo"
    break
  fi
  git commit --quiet -C $C
done
```

`git commit -C $C` reuses the commit's message, author and date. That is what **use_next** matches on.

This was tested on 2026-09-28, with the seven commits, against the made-up Forkgram release of 5.2. The loop stopped at 27d32d57b4 on `MessagesController.java`. After the fix below, all seven new commits had exactly the same content as the rebase in section 5 gave.

**When the loop stops:**

1. Look at each file it names.
   - If it contains conflict markers, fix it as in 5.2. Here the markers read `<<<<<<< ours` (new Forkgram) and `>>>>>>> theirs` (old Forkgram with the hook).
   - If git printed `Resolved '<file>' using previous resolution`, rerere (5.6) has already put in a fix you made earlier in this clone, for example during a section 5 attempt. The file has no markers but still counts as unmerged. Read the fix with `git diff HEAD -- <file>` before you `git add` it. rerere repeats values, not the `overlay_A.json` that went with them, so if the file is `ThemeColors.java` or an `.attheme` file, run `python3 multigram/tools/palette_fix_check.py --base origin/forkgram` before you commit. If it reports `expected <value>`, write the value it expects: that is the value of this commit's `overlay_A.json`. 7.5 re-derives the palette afterwards and adopts new values then.
   - If it is unchanged, git could not place the change at all. Put the hooks in by hand, with section 8. `git show $C -- <file>` shows what the commit changed.
2. Commit the stopped commit:

   ```sh
   git add <the files>
   git commit -C $C
   ```

3. Continue after it. Set `START` to the commit that stopped, and paste the loop again from its second line:

   ```sh
   START=$C
   ```

**By hand, without the loop.** First list the seven commits you re-apply, with their hashes:

```sh
git log --reverse --format='%h %s' $OLDSNAP..$OLD
```

Use these hashes as `<commit>` below, not the hashes printed in this guide. Those are the commits of `multigram` ff868b3ea4, and every sync rebases the stack, so after the next sync they are old versions (still reachable through the `multigram-before-<version>` tags, so git would not complain). Then, for each commit in that order (the table in 7.7 shows what each one holds):

1. List what it touches: `git diff-tree --no-commit-id -r --name-status <commit>`.
2. Copy the MultiGram files it adds or changes, at its version:

   ```sh
   git checkout <commit> -- $(git diff-tree --no-commit-id -r --name-only <commit> -- multigram TMessagesProj/src/main/java/org/telegram/messenger/multigram TMessagesProj/src/main/res/values/multigram_rebrand.xml TMessagesProj/src/main/res/values/multigram_strings.xml TMessagesProj/src/main/assets/multigram_styles.bin)
   ```

   This copies only the paths the commit has. Naming a path by hand that the commit does not have yet (say `multigram_styles.bin` for d457ac74ae) makes `git checkout` copy nothing at all.
3. Put its hooks into the upstream files. Section 8 lists them in order. Mind the four files without a final newline (5.2).
4. `git add` the upstream files and run `git commit -C <commit>`.

### 7.4 Use the checks as a to-do list

The check scripts name every missing or misplaced hook. Run them at any point:

```sh
python3 multigram/tools/palette_fix_check.py --base origin/forkgram
python3 multigram/tools/random_style_check.py --base origin/forkgram
python3 multigram/tools/style_knobs_check.py --base origin/forkgram
python3 multigram/tools/hide_search_bar_check.py --base origin/forkgram
git grep -n -e 'multigram\.Rebrand\.' -e 'multigram/rebrand/rebrand.gradle' -- TMessagesProj TMessagesProj_App
cmp multigram/palette-fix/overlay_A.json multigram/tools/sim/palette-fix/overlay_A.json && echo "overlay copies identical"
```

With all 40 files copied but no hooks in place, a test tree gave 59, 27, 35 and 61 problems from the four checks, and the rebrand self-test failed one check (`TMessagesProj_App/build.gradle applies rebrand.gradle`). When everything is back:

- each check prints a single line ending in `OK`;
- the `git grep` prints 5 lines, one for each of R1 to R5;
- the `cmp` prints `overlay copies identical` (see 5.4 if not).

Each problem line says what is wrong, for example `the upload guard is not the first statement of saveThemeToServer`.

### 7.5 Regenerate and check derived data

Two things are derived from upstream sources and may need a refresh. Do this after 7.3, on your local `multigram-next`:

1. **The palette values** (overlay A). Re-derive them from the new plain snapshot with the simulator (8.2.5, step 2). If they change, adopt them as "To adopt a new overlay" in 8.2.5 says. Its last step names the commit each file goes into.
2. **The style table** (`multigram_styles.bin`). Run `bash multigram/tools/check.sh`. If it asks for a new table, run `python3 multigram/tools/make_style_table.py` (8.3.5). The new file goes into "Add the style table and its generator".

To fold a change into its commit, follow 6.3 from its step 2. Skip its step 1: your seven commits exist only on your local branch until 7.6, and `git switch -C multigram-next origin/multigram-next` would throw them away.

Nothing else is derived. The rebrand output is generated at build time and never committed. The knob values are computed on the device.

### 7.6 Compile

Push the branch and run the compile check on it (10.1), or compile locally (6.4):

```sh
git push --force origin multigram-next
```

### 7.7 Check the seven commits

The new commits must match the old ones in author, date and subject:

```sh
diff <(git log --reverse --format='%an %ad %s' $OLDSNAP..$OLD) <(git log --reverse --format='%an %ad %s' origin/forkgram..multigram-next) && echo "same seven commits"
```

| # | Subject (keep it exactly) | Hooks | Section |
|---|---|---|---|
| 1 | Add the rebrand toolkit | R1–R5 | 8.1 |
| 2 | Fix palette contrast for generated accents | P1–P18 | 8.2 |
| 3 | Add the style table and its generator | none (new files only) | 8.3 |
| 4 | Give each install its own random style | S1–S15 | 8.3 |
| 5 | Randomise shapes and chat list layout per install | K1–K17 (K18–K23 come with the copied files) | 8.4 |
| 6 | Run the rebrand self-test in the CI checks | none (K24 comes with the copied `check.sh`) | 8.4 |
| 7 | Add an option to remove the chat list search bar | H1–H21 (H22 comes with the copied `check.sh`) | 8.5 |

### 7.8 Hand it to the sync

Push (7.6), then run **Actions > Sync with Forkgram** with **use_next**.

If **use_next** refuses with "multigram-next does not carry N of multigram's commit(s)", then someone pushed to `multigram` after you started, or a subject or author changed. Add the missing commit with `git cherry-pick <commit>`, or tick **allow_drop** if you left it out on purpose.

## 8. The changes, one by one

Each part below has the same six subsections: what and why, new files, hooks, data, how to regenerate and verify, and gotchas.

### 8.1 Rebrand toolkit (d457ac74ae)

#### 8.1.1 What and why

The rebrand toolkit gives a build its own identity: application id, app name, launcher, splash and notification icons, signing key, and Android account type. It is meant for builds you give to other people. A stock build (no rebrand) behaves exactly like Forkgram.

It works at build time:

1. You run `python3 multigram/rebrand/generate_rebrand.py --seed <any text>`. The seed makes the identity repeatable.
2. The generator writes a resource overlay to `multigram/rebrand/generated/res` and settings to `multigram/rebrand/rebrand.properties`. Both are git-ignored.
3. It also edits three upstream files in place, because the account type is a Java literal that no overlay can replace: `ContactsController.java`, `res/xml/auth.xml` and `res/xml/sync_contacts.xml`. It keeps backups and adds a marker comment. These edits are never committed.
4. `rebrand.gradle` reads the properties and sets the application id, signing, version and resource folders.
5. `python3 multigram/rebrand/generate_rebrand.py --clean` puts everything back byte for byte.

The committed upstream changes are small: four Java hooks of one code line each (R2 and R3 also put a comment line above theirs) and one Gradle line. Three Java hooks replace Forkgram's default chat list title "Fork Client" with the app's own name in a rebranded build. One hides the other launcher icons.

#### 8.1.2 New files

| Path | Purpose | Upstream names it relies on |
|---|---|---|
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/Rebrand.java` | The only runtime code. `isActive()` reads the flag `multigram_rebrand_active`. `defaultTitle(stock)` returns the app's own `AppName` in a rebranded build and `stock` otherwise. `filterLauncherIcons(list)` keeps only the default icon in a rebranded build. | `ApplicationLoader.applicationContext`, `FileLog.e(Throwable)`, `R.string.AppName`, `LauncherIconController.LauncherIcon.DEFAULT` |
| `TMessagesProj/src/main/res/values/multigram_rebrand.xml` | Declares `bool/multigram_rebrand_active` as false. The generated overlay sets it to true. | None. It must stay in the `TMessagesProj` library, because `Rebrand.java` compiles against that module's `R`. |
| `multigram/rebrand/.gitignore` | Keeps `generated/`, `rebrand.properties` (it holds key passwords) and `__pycache__/` out of git. | None |
| `multigram/rebrand/README.md` | User documentation: quick start, what changes, icons, account type, signing and updates. | Documentation only. It names Forkgram's icons, strings and ids; correct it if they change. |
| `multigram/rebrand/generate_rebrand.py` | The generator (Python standard library, plus `keytool` for the key). Makes the identity from the seed, writes the overlay and properties, patches the account type, and `--clean` undoes it all. | The resource folders `TMessagesProj/src/*/res` and `TMessagesProj_App/src/*/res`; the icon, splash and string names in 8.1.4; the account type in the three files above |
| `multigram/rebrand/rebrand.gradle` | Gradle glue, applied by hook R5. In stock mode it only fails the build if a rebrand marker was left behind. In rebrand mode it sets the id, signing, version and resources, and feeds the new app name to Telegram's string tasks. | The `android {}` block of `TMessagesProj_App/build.gradle`; the stock ids `org.forkclient.messenger` and `org.forkgram.messenger`; the `generate*TelegramStrings` tasks of class `org.telegram.tasks.TelegramStringsTask` with the properties `stringsXml` and `localizationFiles` |
| `multigram/rebrand/selftest.py` | End-to-end test without an Android SDK. It copies the tracked sources into a throwaway git repository, runs the generator with two seeds, checks every output, and checks that `--clean` restores the tree. | `git`; the exact R5 line; the three account-type files; exactly 5 account-type literals in `ContactsController.java` |

#### 8.1.3 Hooks

##### R1. Hide the other launcher icons in a rebranded build

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Cells/AppIconsSelectorCell.java`

**Where:** Class `AppIconsSelectorCell`, method `updateIconsVisibility()`. The new line goes right after the icon list is filled. In Forkgram 12.10.6 the text below starts at line 153.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        availableIcons.addAll(Arrays.asList(LauncherIconController.LauncherIcon.values()));
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     private void updateIconsVisibility() {
         availableIcons.clear();
         availableIcons.addAll(Arrays.asList(LauncherIconController.LauncherIcon.values()));
+        org.telegram.messenger.multigram.Rebrand.filterLauncherIcons(availableIcons); // MultiGram: a rebranded build offers only its own icon
         if (MessagesController.getInstance(currentAccount).premiumFeaturesBlocked()) {
             for (int i = 0; i < availableIcons.size(); i++) {
                 if (availableIcons.get(i).premium) {
```

**Why:** Chat Settings has an app icon row that lists every launcher icon. The other icons are Forkgram's and Telegram's logos. In a rebranded build, `Rebrand.filterLauncherIcons` keeps only `DEFAULT`, the icon whose files the rebrand replaces. In a stock build it does nothing.

**If the code moved:** Put the call right after the list that feeds the picker is filled from `LauncherIconController.LauncherIcon.values()`, and before anything reads the list (the premium filter, `notifyDataSetChanged`, the scroll loop). Find candidates with `git grep -n "LauncherIcon.values()" -- TMessagesProj/src/main/java`. Leave two other users alone: `LauncherIconController` (it switches every icon alias on and off, so it must see all of them) and `PremiumAppIconsPreviewView` (the Premium screen, left as it is on purpose). If Forkgram renames `DEFAULT`, or points another entry at the `icon_01_*` files, update `Rebrand.filterLauncherIcons`.


##### R2. Chat list title: default to the rebranded app name

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `createView(Context)`, in the last `else` branch that sets up the main chat list title (no folder, no community). In Forkgram 12.10.6 the text below starts at line 3512.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                actionBar.setTitle(MessagesController.getGlobalMainSettings().getString("forkCustomTitle", "Fork Client"));
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 SpannableStringBuilder ssb = new SpannableStringBuilder(getString(R.string.AppName));
                 ssb.setSpan(new ImageSpan(logoDrawable), 0, ssb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                 actionBar.setTitle(ssb, statusDrawable);
-                actionBar.setTitle(MessagesController.getGlobalMainSettings().getString("forkCustomTitle", "Fork Client"));
+                // MultiGram: a rebranded build's default title is its own app name.
+                actionBar.setTitle(MessagesController.getGlobalMainSettings().getString("forkCustomTitle", org.telegram.messenger.multigram.Rebrand.defaultTitle("Fork Client")));
                 actionBar.setTitleLongClickListener(v -> {
                     boolean mainTabsHidden = !UserConfig.getInstance(currentAccount).getMainTabsHiddenFork();
                     UserConfig.getInstance(currentAccount).setMainTabsHiddenFork(mainTabsHidden);
```

**Why:** Forkgram shows the setting `forkCustomTitle` as the chat list title, with the fixed default "Fork Client". With the hook, a rebranded build shows its own app name when the user has not set a title. A stock build still shows "Fork Client". The comment sits on its own line above the hook.

**If the code moved:** Find every place that reads the title setting: `git grep -n '"forkCustomTitle"' -- TMessagesProj/src/main/java`. Wrap each literal default in `org.telegram.messenger.multigram.Rebrand.defaultTitle(<the stock text>)`. If Forkgram changes the default text, pass the new text, so stock builds stay identical to Forkgram. If Forkgram drops the custom title and shows `R.string.AppName` as text, no hook is needed: the rebrand already renames `AppName`.

**On plain Telegram (DrKLO):** Forkgram only. Plain Telegram has no `forkCustomTitle`: it draws the `telegram_logo_2` picture over `R.string.AppName` (the line just above the hook), so renaming `AppName` does not change what is shown. See section 9.


##### R3. Fork Client Settings: show the same default title

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ForkSettingsActivity.java`

**Where:** Class `ForkSettingsActivity`, method `fillSettings(ArrayList<UItem>)`: the "Custom title" row (`ID_CUSTOM_TITLE`). In Forkgram 12.10.6 the text below starts at line 547.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        items.add(UItem.asSettingsCell(ID_CUSTOM_TITLE, LocaleController.getString(R.string.EditAdminRank), prefs().getString("forkCustomTitle", "Fork Client")));
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             items.add(UItem.asButtonCheck(ID_HIDE_BOTTOM_BUTTON, LocaleController.getString(R.string.HideBottomButton), LocaleController.getString(R.string.HideBottomButtonInfo))
                 .setChecked(pref("hideBottomButton", false)).setMultiline(true));
         }
-        items.add(UItem.asSettingsCell(ID_CUSTOM_TITLE, LocaleController.getString(R.string.EditAdminRank), prefs().getString("forkCustomTitle", "Fork Client")));
+        // MultiGram: a rebranded build's default title is its own app name.
+        items.add(UItem.asSettingsCell(ID_CUSTOM_TITLE, LocaleController.getString(R.string.EditAdminRank), prefs().getString("forkCustomTitle", org.telegram.messenger.multigram.Rebrand.defaultTitle("Fork Client"))));
         items.add(UItem.asShadow(null));
 
         items.add(UItem.asHeader(LocaleController.getString(R.string.AvatarShape)));
```

**Why:** The row shows the current title as its value. Without a saved title, a rebranded build now shows its own app name here too, the same as the chat list. A stock build still shows "Fork Client".

**If the code moved:** This is the settings row that shows the `forkCustomTitle` value. Wrap its literal default in `Rebrand.defaultTitle(<stock text>)`. It must agree with R2 and R4.

**On plain Telegram (DrKLO):** Forkgram only: `ForkSettingsActivity.java` does not exist in plain Telegram.


##### R4. Custom title dialog: same default

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ForkSettingsActivity.java`

**Where:** Class `ForkSettingsActivity`, method `showCustomTitleDialog(View)`, first line. In Forkgram 12.10.6 the text below starts at line 1154.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        final String defaultValue = "Fork Client";
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     private void showCustomTitleDialog(View view) {
-        final String defaultValue = "Fork Client";
+        final String defaultValue = org.telegram.messenger.multigram.Rebrand.defaultTitle("Fork Client"); // MultiGram: rebranded default
         org.telegram.messenger.forkgram.ForkDialogs.createFieldAlert(
             getContext(),
             LocaleController.getString(R.string.EditAdminRank),
```

**Why:** The dialog fills its text field with the saved title or `defaultValue`, and an empty answer saves `defaultValue`. In a rebranded build both now use the app's own name, so clearing the field never brings "Fork Client" back.

**If the code moved:** Find the dialog that saves the title: `git grep -n 'putString("forkCustomTitle"' -- TMessagesProj/src/main/java`. Whatever default it shows or saves must come from `Rebrand.defaultTitle(<stock text>)`.

**On plain Telegram (DrKLO):** Forkgram only.


##### R5. Apply the rebrand Gradle script

**File:** `TMessagesProj_App/build.gradle`

**Where:** The very end of the file, after the closing brace of the `android { }` block. In Forkgram 12.10.6 the text below starts at line 330.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```groovy
        checkReleaseBuilds false
    }
}
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         checkReleaseBuilds false
     }
 }
+
+// MultiGram: build-time rebrand, a no-op unless multigram/rebrand/rebrand.properties exists.
+apply from: "${rootDir}/multigram/rebrand/rebrand.gradle"
```

**Why:** This connects the toolkit to the app module. It must come after the module's own `android { }` block, so that the rebrand's application id, signing, version and resource folder replace the module's values. Without `multigram/rebrand/rebrand.properties` (a stock build) the script only checks that no rebrand patch was left behind in three source files.

**If the code moved:** Keep one `apply from:` line at the very end of the app module's build script, after `android { }`. If upstream adds lines after `android { }`, put this line after them. If the app module is renamed, or `settings.gradle` gets another app module, hook that module; the paths inside `rebrand.gradle` start at the repository root. `selftest.py` looks for this exact text.

**On plain Telegram (DrKLO):** Conflicts: plain Telegram's file ends with `apply plugin: 'com.google.gms.google-services'`. Keep both lines.


#### 8.1.4 Data

Nothing derived is committed. The generator looks for these upstream names. If Forkgram renames one, the generator or the self-test says so.

| What | Names in Forkgram 12.10.6 | Where the name is set |
|---|---|---|
| App name strings | `AppName`, `AppNameBeta`, `AppNameFdroid` in `values/strings.xml` (lines 177 to 179) and 10 translations; also `AppNameBeta` ("Fork Client Test") in `TMessagesProj_App/src/forkTest/res/values/strings.xml`, which the generator scans too | `APP_NAME_STRINGS` in `generate_rebrand.py` |
| Icons | 12 entries: mipmap `ic_launcher`, `ic_launcher_round`, `icon_01_launcher`, `icon_01_launcher_round`, `icon_01_launcher_adaptive`, `icon_01_launcher_sa`, `icon_01_foreground_sa`; drawable `icon_01_background_sa`, `ic_launcher_dr`, `splash_fork_320`, `tg_splash_320`, `notification`. That is 54 files today. | `ICON_TARGETS` in `generate_rebrand.py` |
| Account type in Java | 5 literals `"org.telegram.messenger"` in `TMessagesProj/src/main/java/org/telegram/messenger/ContactsController.java` | `JAVA_EXPECTED_LITERALS` in `generate_rebrand.py`, and `== 5` at `selftest.py` line 270 |
| Account type in XML | `android:accountType="${applicationId}"`, once each in `res/xml/auth.xml` and `res/xml/sync_contacts.xml` | `STOCK_XML_ACCOUNT_TYPE` in `generate_rebrand.py` |
| Stock application ids | `org.forkclient.messenger`, and `org.forkgram.messenger` for F-Droid builds | `stockIds` in `rebrand.gradle` |
| Default chat list title | `"Fork Client"` | The argument of `Rebrand.defaultTitle(...)` in hooks R2, R3 and R4 |

#### 8.1.5 Regenerate and verify

**The self-test.** Run it from the root of a checkout that is not rebranded. It takes about 30 seconds, and needs `git` (and `keytool` for the signing checks):

```sh
python3 multigram/rebrand/selftest.py
```

It passes when no line starts with `FAIL` and the last line is `PASSED: 0 failure(s)` (exit status 0). Besides the `ok` lines it prints the throwaway folder, an indented "Rebrand identity" block per seed and blank lines. An excerpt of a passing run on ff868b3ea4 (the temporary path differs each time):

```text
throwaway tree: /tmp/rebrand-selftest-n2jxoni1/tree
ok    TMessagesProj_App/build.gradle applies rebrand.gradle
ok    seed A: generator succeeds
ok    seed A: no warnings
ok    seed A: overlay covers all 54 upstream icon files in the same folders
ok    seed A: account type dev.quietshoal.app in Java (5x) and both XML files
ok    --clean: git status clean (incl. ignored files), files byte-identical
ok    --clean twice is harmless

PASSED: 0 failure(s)
```

- A `FAIL` line ends the run with `FAILED: N failure(s)` and exit status 1. The line names the check.
- Exit status 2 with `This tree is rebranded; run generate_rebrand.py --clean first.` means the tree you ran it from has `generated/` or `rebrand.properties`.
- Without `keytool` it prints `note: keytool not found, signing checks skipped` just before the final `PASSED` or `FAILED` line.
- The counts (54 icon files and so on) come from the tree. They may change when Forkgram adds or drops icon sizes.

**The hooks.** No script checks the four Java hooks. This must print 5 lines:

```sh
git grep -n -e 'multigram\.Rebrand\.' -e 'multigram/rebrand/rebrand.gradle' -- TMessagesProj TMessagesProj_App
```

On ff868b3ea4 they are `AppIconsSelectorCell.java:154`, `DialogsActivity.java:3513`, `ForkSettingsActivity.java:548` and `:1157`, and `TMessagesProj_App/build.gradle:335`.

Every use of the title setting must pass through `Rebrand.defaultTitle`. This lists them:

```sh
git grep -n '"forkCustomTitle"' -- TMessagesProj/src/main/java
```

**A real identity, in a scratch worktree.** Never do this in the checkout you commit from (see 8.1.6):

```sh
git fetch origin
git worktree add --detach /tmp/mg-rebrand origin/multigram
cd /tmp/mg-rebrand
python3 multigram/rebrand/generate_rebrand.py --seed patch-doc-demo
```

On 2026-09-27 it printed, among other lines:

```text
  applicationId  dev.cleargrove.im  (Gradle adds the build type suffix, e.g. .beta)
  app name       Willowbirch
                   TMessagesProj/src/main/java/org/telegram/messenger/ContactsController.java: 5 literal(s)
```

Success means: exit status 0, no `WARNING:` line, and exactly `5 literal(s)`. A line like `N literal(s) (expected 5: check the file)` is a problem, even without the word WARNING. `git status --porcelain` then shows the three patched files as modified, and `generated/` holds 74 files.

To undo it and remove the worktree:

```sh
python3 multigram/rebrand/generate_rebrand.py --clean
cd -
git worktree remove /tmp/mg-rebrand
```

`--clean` prints `Rebrand removed: stock identity restored (3 source file(s) put back).` and `The generated signing key was deleted with it.` `cd -` goes back to the checkout you started from.

**Gradle messages.** These come from reading `rebrand.gradle`, not from a build. A rebranded build prints lines that start with `[rebrand] :TMessagesProj_App:`. A stock build prints no `[rebrand]` line. The messages that point to a problem:

| Message starts with | Kind | Meaning |
|---|---|---|
| `[rebrand] :TMessagesProj_App: no generate*TelegramStrings task found` | warning | Telegram's build code (`buildSrc`) changed, and the in-app strings keep the stock name. Update `rebrand.gradle`. |
| `[rebrand] account type ... is not in place in ...` | error | A half-patched tree. Run the generator again, or `--clean`. |
| `[rebrand] no active rebrand (multigram/rebrand/rebrand.properties), but these files still carry a rebrand's account type` | error | `rebrand.properties` was deleted without `--clean`. See 8.1.6. |
| `[rebrand] signing keystore ... not found` | error | The key file named in `rebrand.properties` is missing. Put it back. |

**On the APK and a device** (needs the Android build tools):

- `aapt2 dump badging <file>.apk | grep -E '^package:|application-label'` shows the new package and label.
- `apksigner verify --print-certs <file>.apk` shows the key fingerprint the generator printed.
- On the device: the launcher, splash and notification icons are the generated ones; the chat list title is the app name; the app icon picker offers one icon; after login with contact sync, **Settings > Accounts** lists an account with the app's name.

#### 8.1.6 Gotchas

- **Never commit, rebase, pull or switch to a new Forkgram while a rebrand is active.** The three patched files show as modified. Run `--clean` first and generate again afterwards.
- **`--clean` deletes `rebrand.properties` and the generated key.** Note the seed and options first. The identity comes back from the same seed, but the key does not. Keep a key for real users outside the repository (`--keystore PATH`), or phones cannot install your updates.
- **Deleting `generated/` by hand** leaves the three files patched, and `--clean` refuses. Fix it with `git checkout -- TMessagesProj/src/main/java/org/telegram/messenger/ContactsController.java TMessagesProj/src/main/res/xml/auth.xml TMessagesProj/src/main/res/xml/sync_contacts.xml`, then run `--clean`. **Deleting only `rebrand.properties`** makes Gradle refuse (`[rebrand] no active rebrand ...`, see 8.1.5), because the three files still carry the rebrand's account type. `--clean` still puts them back.
- **If the generator stops with an error** such as `unexpected <dir>/<name>.xml: update ICON_TARGETS`, a partial `generated/` stays behind. Run `--clean` before building. The self-test refuses to start while `generated/` exists.
- **The account type count.** The generator replaces every `"org.telegram.messenger"` literal in `ContactsController.java`. If upstream adds that literal for another purpose, it would be replaced too. When the count is no longer 5, read each use, then change `JAVA_EXPECTED_LITERALS` and `selftest.py` line 270 together.
- **Keep each Java hook one line, with the full name** `org.telegram.messenger.multigram.Rebrand`. No import is added, so upstream changes to the import list never conflict.
- **`Rebrand.defaultTitle` reads `AppName` through Android, not through `LocaleController`**, because cloud language packs carry Telegram's name. This works because Telegram's string task keeps `AppName` as a real resource (`GENERATED_EXCLUSIONS` in `buildSrc/src/main/kotlin/org/telegram/tasks/TelegramStringsTask.kt`). If that list changes, the title may come out wrong.
- **The stock title "Fork Client" appears in three hooks.** If Forkgram changes it, change all three.
- **The `[rebrand] ... app name added to N TelegramStrings task(s)` message** counts tasks by name only. If `buildSrc` renames the task class or its properties, the message still appears but the in-app strings keep "Fork Client". Check `TelegramBuildAppPlugin.kt` and `TelegramStringsTask.kt` after an update.
- **Forkgram's `auth.xml` and `sync_contacts.xml` say `${applicationId}`**; plain Telegram says `org.telegram.messenger`. If Forkgram switches, the generator warns and the self-test fails `seed A: no warnings`. Update `STOCK_XML_ACCOUNT_TYPE`.
- **`filterLauncherIcons` keeps only `DEFAULT`.** Do not filter `LauncherIconController`'s own loops (they switch every icon on and off) or `PremiumAppIconsPreviewView` (the Premium screen).
- **The self-test copies only files git tracks.** `git add` a new upstream file before you trust its result.
- **Two build variants of one identity** (for example `.beta` and `.web`) share the account type, so only one of them can hold the account on a phone.

### 8.2 Palette fix (5b53859682)

#### 8.2.1 What and why

Stock Telegram already fails the contrast minimum on many grey texts. MultiGram also gives every install a generated accent colour, which can be very light. This commit fixes both. It has four parts:

1. **Static values.** 11 grey default colours in `ThemeColors.java` and 36 grey values in the five bundled themes (Blue, Dark Blue, Arctic Blue, Day, Night) move to the nearest lightness that passes 4.5 : 1. 13 neutral keys join the list of keys the accent tint skips, so an accent cannot pull them back. Monet themes are not touched.
2. **The on-accent rule** (new class `PaletteFix`). For runtime accents only, marks drawn on accent fills become white or near-black `#050505`, whichever is more readable. These marks include the floating pencil, unread digits, button texts, checkmarks and the send glyph. Stock presets, server themes, other people's cloud themes and Monet look exactly as in Forkgram.
3. **Outgoing bubble texts.** For runtime accents, the code that picks black or white texts for outgoing bubbles always runs.
4. **Bundled theme refresh.** The app re-copies a bundled theme file after an app update, because two edited files kept their size.

All values come from overlay A, which the simulator makes from plain Forkgram (8.2.5).

#### 8.2.2 New files

| Path | Purpose | Upstream names it relies on |
|---|---|---|
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/PaletteFix.java` | All the runtime logic; upstream files only call it. It holds the rule, the contrast maths, and data tables that must equal overlay A (8.2.4). A runtime accent is `accent.id > 100 && (accent.info == null \|\| accent.info.creator)`. | `Theme.getColor(int)`, `Theme.getColor(int, boolean[], boolean)`, `getFallbackKeys()`, `getDefaultColor(int)`, `getActiveTheme()`, `DEFALT_THEME_ACCENT_ID` (upstream's spelling); `ThemeAccent.id`, `info`, `parentTheme`, `accentColor`; `ThemeInfo.isMonet()` (Forkgram only), `isDark()`, `getKey()`, `firstAccentIsDefault`, `themeAccentsMap`, `chatAccentsByThemeId`; 45 `Theme.key_*` colour keys; `ApplicationLoader.applicationContext`; Android's `PackageInfo.lastUpdateTime` |
| `multigram/palette-fix/overlay_A.json` | The specification: 23 defaults, 36 theme values, 13 exclusions, the on-accent pairs and the muted badge table. Colours are unsigned 32-bit ARGB. A second, identical copy is in `multigram/tools/sim/palette-fix/`. | The key names (with the `key_` prefix), the five `.attheme` file names, and the theme names "Blue", "Arctic Blue", "Day", "Dark Blue", "Night" |
| `multigram/tools/palette_fix_check.py` | Checks the tree against overlay A: the values, the tables in `PaletteFix.java`, and 12 hook lines (each exactly once). With `--base REV` it also rejects any other change to `ThemeColors.java` and the 7 `.attheme` files. Prints `palette-fix: OK`. | The file paths of the hooked files; the formats `defaultColors[key_X] = ...;` and `name=<decimal>`; the exact hook texts including their comments |
| `multigram/palette-fix/README.md` | Human documentation: what changes, what a runtime accent is, the hooks, and what is not hooked on purpose. | Documentation only |

#### 8.2.3 Hooks

##### P1. ThemeColors: 11 grey default colours

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/ThemeColors.java`

**Where:** Class `ThemeColors`, method `createDefaultColors()`. Eleven `defaultColors[...] = ...;` lines, each changed in place. The values are listed in table 8.2.4.

**Find this** (the method that holds the lines; it occurs once in the file, at line 20 in Forkgram 12.10.6):

```java
    public static int[] createDefaultColors() {
```

**Then find these 11 lines** (each occurs once in the file):

```java
        defaultColors[key_windowBackgroundWhiteGrayText] = 0xff808384;
        defaultColors[key_windowBackgroundWhiteGrayText2] = 0xff82868a;
        defaultColors[key_windowBackgroundWhiteGrayText4] = 0xff808080;
        defaultColors[key_actionBarDefaultSubtitle] = 0xff79817e;       // key_windowBackgroundWhiteGrayText
        defaultColors[key_chats_message] = 0xff75787A;
        defaultColors[key_chats_date] = 0xff848688;
        defaultColors[key_chat_inViews] = 0xffa1aab3;
        defaultColors[key_chat_inTimeText] = 0xffa1aab3;
        defaultColors[key_chat_inFileInfoText] = 0xffa1aab3;
        defaultColors[key_chat_messagePanelHint] = 0xff858a84;
        defaultColors[key_chat_topPanelMessage] = 0xff767e7c;
```

**Change them to** (`-` is the Forkgram line, `+` the MultiGram line):

```diff
-        defaultColors[key_windowBackgroundWhiteGrayText] = 0xff808384;
-        defaultColors[key_windowBackgroundWhiteGrayText2] = 0xff82868a;
+        defaultColors[key_windowBackgroundWhiteGrayText] = 0xff757778; // MultiGram: contrast fix, was 0xff808384
+        defaultColors[key_windowBackgroundWhiteGrayText2] = 0xff73777b; // MultiGram: contrast fix, was 0xff82868a
-        defaultColors[key_windowBackgroundWhiteGrayText4] = 0xff808080;
+        defaultColors[key_windowBackgroundWhiteGrayText4] = 0xff6f6e6e; // MultiGram: contrast fix, was 0xff808080
-        defaultColors[key_actionBarDefaultSubtitle] = 0xff79817e;       // key_windowBackgroundWhiteGrayText
+        defaultColors[key_actionBarDefaultSubtitle] = 0xff717876;       // key_windowBackgroundWhiteGrayText; MultiGram: contrast fix, was 0xff79817e
-        defaultColors[key_chats_message] = 0xff75787A;
+        defaultColors[key_chats_message] = 0xff747779; // MultiGram: contrast fix, was 0xff75787A
-        defaultColors[key_chats_date] = 0xff848688;
+        defaultColors[key_chats_date] = 0xff757778; // MultiGram: contrast fix, was 0xff848688
-        defaultColors[key_chat_inViews] = 0xffa1aab3;
+        defaultColors[key_chat_inViews] = 0xff6f7780; // MultiGram: contrast fix, was 0xffa1aab3
-        defaultColors[key_chat_inTimeText] = 0xffa1aab3;
+        defaultColors[key_chat_inTimeText] = 0xff6f7780; // MultiGram: contrast fix, was 0xffa1aab3
-        defaultColors[key_chat_inFileInfoText] = 0xffa1aab3;
+        defaultColors[key_chat_inFileInfoText] = 0xff6f7780; // MultiGram: contrast fix, was 0xffa1aab3
-        defaultColors[key_chat_messagePanelHint] = 0xff858a84;
+        defaultColors[key_chat_messagePanelHint] = 0xff737873; // MultiGram: contrast fix, was 0xff858a84
-        defaultColors[key_chat_topPanelMessage] = 0xff767e7c;
+        defaultColors[key_chat_topPanelMessage] = 0xff717877; // MultiGram: contrast fix, was 0xff767e7c
```

**Why:** These are the stock default colours. The default Blue theme uses them directly, and every theme without its own value inherits them. The stock greys reach only 2.36 to 4.45 : 1 contrast against their backgrounds. The new values reach 4.50 to 4.54 : 1 with the same hue. Each changed line ends with `// MultiGram: contrast fix, was <old value>`.

**If the code moved:** Match each line by its key, not by its value. If Forkgram changed the stock value of one of these keys, the replay conflicts on that line. Keep MultiGram's line to finish the replay (5.3), but not for good: re-derive the values from the new plain Forkgram with the simulator (8.2.5), use the value it gives (or drop the line if the key now passes), and update the `was 0x...` comment. If a key is renamed, see the `key_...` row of 6.2. The 12 "on-accent" keys in `overlay_A.json` (for example `key_chats_actionIcon`) must **not** be copied here: the app keeps them stock white on purpose.


##### P2. assets/arctic.attheme: grey values of the "Arctic Blue" theme

**File:** `TMessagesProj/src/main/assets/arctic.attheme`

**Where:** Bundled theme "Arctic Blue". `key=value` lines anywhere in the file; order does not matter. Values are signed decimal colours (ARGB). The values are listed in table 8.2.4.

**Then find these 4 lines** (each occurs once in the file):

```properties
actionBarDefaultSubtitle=-7630182
chat_topPanelMessage=-8354167
chat_inFileInfoText=-6182221
windowBackgroundWhiteGrayText=-7629665
```

**Change them to** (`-` is the Forkgram line, `+` the MultiGram line):

```diff
-actionBarDefaultSubtitle=-7630182
+actionBarDefaultSubtitle=-9341057
-chat_topPanelMessage=-8354167
+chat_topPanelMessage=-9275526
-chat_inFileInfoText=-6182221
+chat_inFileInfoText=-9472128
-windowBackgroundWhiteGrayText=-7629665
+windowBackgroundWhiteGrayText=-9472126
```

**Why:** These greys fail the 4.5 : 1 contrast minimum on the "Arctic Blue" theme in stock Forkgram. The file keeps its size (9041 bytes), so users who update need hook P12 to see the new values.

**If the code moved:** Find each line by its key. If the stock value of a line changed upstream (a replay conflict), or the key disappeared, re-derive the values with the simulator (8.2.5). Write values in decimal: the checker does not read `#hex`.


##### P3. assets/bluebubbles.attheme: grey values of the "Blue" theme

**File:** `TMessagesProj/src/main/assets/bluebubbles.attheme`

**Where:** Bundled theme "Blue". `key=value` lines anywhere in the file; order does not matter. Values are signed decimal colours (ARGB). The values are listed in table 8.2.4.

**Then find these 4 lines** (each occurs once in the file):

```properties
actionBarDefaultSubtitle=-8156010
windowBackgroundWhiteGrayText=-7565423
windowBackgroundWhiteGrayText2=-7565423
windowBackgroundWhiteGrayText4=-7565423
```

**Change them to** (`-` is the Forkgram line, `+` the MultiGram line):

```diff
-actionBarDefaultSubtitle=-8156010
+actionBarDefaultSubtitle=-9472127
-windowBackgroundWhiteGrayText=-7565423
+windowBackgroundWhiteGrayText=-9144455
-windowBackgroundWhiteGrayText2=-7565423
+windowBackgroundWhiteGrayText2=-9144455
-windowBackgroundWhiteGrayText4=-7565423
+windowBackgroundWhiteGrayText4=-9671056
```

**Why:** These greys fail the 4.5 : 1 contrast minimum on the "Blue" theme in stock Forkgram. The file keeps its size (6073 bytes), so users who update need hook P12 to see the new values.

**If the code moved:** Find each line by its key. Match by key: the old value `-7565423` is on 9 lines in this file. Only the three P3 keys that have it change; the others (for example `windowBackgroundWhiteGrayText3`) stay unchanged. If the stock value of a line changed upstream (a replay conflict), or the key disappeared, re-derive the values with the simulator (8.2.5). Write values in decimal: the checker does not read `#hex`.


##### P4. assets/darkblue.attheme: grey values of the "Dark Blue" theme

**File:** `TMessagesProj/src/main/assets/darkblue.attheme`

**Where:** Bundled theme "Dark Blue". `key=value` lines anywhere in the file; order does not matter. Values are signed decimal colours (ARGB). The values are listed in table 8.2.4.

**Then find these 12 lines** (each occurs once in the file):

```properties
chat_messagePanelHint=1859907583
actionBarDefaultSubtitle=2111566591
chat_topPanelMessage=1859974399
chat_inFileInfoText=-8812137
windowBackgroundWhiteGrayText=-8549479
chats_message=-8549479
chats_date=-9207925
chat_inViews=-8812137
windowBackgroundWhiteGrayText2=1878130175
windowBackgroundWhiteGrayText4=-931296359
chat_inTimeText=-645885536
chats_attachMessage=-8548712
```

**Change them to** (`-` is the Forkgram line, `+` the MultiGram line):

```diff
-chat_messagePanelHint=1859907583
+chat_messagePanelHint=-1763971073
-actionBarDefaultSubtitle=2111566591
+actionBarDefaultSubtitle=-1831079169
-chat_topPanelMessage=1859974399
+chat_topPanelMessage=-1814235905
-chat_inFileInfoText=-8812137
+chat_inFileInfoText=-7035469
-windowBackgroundWhiteGrayText=-8549479
+windowBackgroundWhiteGrayText=-7562327
-chats_message=-8549479
+chats_message=-7562327
-chats_date=-9207925
+chats_date=-7431514
-chat_inViews=-8812137
+chat_inViews=-7035469
-windowBackgroundWhiteGrayText2=1878130175
+windowBackgroundWhiteGrayText2=-2081292801
-windowBackgroundWhiteGrayText4=-931296359
-chat_inTimeText=-645885536
+windowBackgroundWhiteGrayText4=-209876071
+chat_inTimeText=-7035724
-chats_attachMessage=-8548712
+chats_attachMessage=-6710887
```

**Why:** These greys fail the 4.5 : 1 contrast minimum on the "Dark Blue" theme in stock Forkgram.

**If the code moved:** Find each line by its key. Keep `chats_attachMessage` a pure grey (red = green = blue) if you re-derive it: the key is accent blue on the light themes, so it cannot join the exclusion list, and a pure grey is never re-tinted. If the stock value of a line changed upstream (a replay conflict), or the key disappeared, re-derive the values with the simulator (8.2.5). Write values in decimal: the checker does not read `#hex`.


##### P5. assets/day.attheme: grey values of the "Day" theme

**File:** `TMessagesProj/src/main/assets/day.attheme`

**Where:** Bundled theme "Day". `key=value` lines anywhere in the file; order does not matter. Values are signed decimal colours (ARGB). The values are listed in table 8.2.4.

**Then find these 6 lines** (each occurs once in the file):

```properties
actionBarDefaultSubtitle=-8814210
chat_topPanelMessage=-9011588
chat_inFileInfoText=-7565679
windowBackgroundWhiteGrayText=-8354940
chat_inViews=-274882397
chat_inTimeText=-7105127
```

**Change them to** (`-` is the Forkgram line, `+` the MultiGram line):

```diff
-actionBarDefaultSubtitle=-8814210
+actionBarDefaultSubtitle=-9340810
-chat_topPanelMessage=-9011588
+chat_topPanelMessage=-9340809
-chat_inFileInfoText=-7565679
+chat_inFileInfoText=-9671312
-windowBackgroundWhiteGrayText=-8354940
+windowBackgroundWhiteGrayText=-9078920
-chat_inViews=-274882397
+chat_inViews=-9736591
-chat_inTimeText=-7105127
+chat_inTimeText=-9671311
```

**Why:** These greys fail the 4.5 : 1 contrast minimum on the "Day" theme in stock Forkgram.

**If the code moved:** Find each line by its key. If the stock value of a line changed upstream (a replay conflict), or the key disappeared, re-derive the values with the simulator (8.2.5). Write values in decimal: the checker does not read `#hex`.


##### P6. assets/night.attheme: grey values of the "Night" theme

**File:** `TMessagesProj/src/main/assets/night.attheme`

**Where:** Bundled theme "Night". `key=value` lines anywhere in the file; order does not matter. Values are signed decimal colours (ARGB). The values are listed in table 8.2.4.

**Then find these 10 lines** (each occurs once in the file):

```properties
chat_messagePanelHint=1694498815
actionBarDefaultSubtitle=1945301746
chat_topPanelMessage=1694498815
chat_inFileInfoText=-9013641
windowBackgroundWhiteGrayText=1862270975
chats_date=-8882056
chat_inViews=-8881024
windowBackgroundWhiteGrayText2=1862139391
windowBackgroundWhiteGrayText4=-9803158
chat_inTimeText=-8552575
```

**Change them to** (`-` is the Forkgram line, `+` the MultiGram line):

```diff
-chat_messagePanelHint=1694498815
+chat_messagePanelHint=1979711487
-actionBarDefaultSubtitle=1945301746
+actionBarDefaultSubtitle=-2131561742
-chat_topPanelMessage=1694498815
+chat_topPanelMessage=1962934271
-chat_inFileInfoText=-9013641
+chat_inFileInfoText=-7763573
-windowBackgroundWhiteGrayText=1862270975
+windowBackgroundWhiteGrayText=1962934271
-chats_date=-8882056
+chats_date=-8289920
-chat_inViews=-8881024
+chat_inViews=-8025458
-windowBackgroundWhiteGrayText2=1862139391
+windowBackgroundWhiteGrayText2=1962802687
-windowBackgroundWhiteGrayText4=-9803158
-chat_inTimeText=-8552575
+windowBackgroundWhiteGrayText4=-9079692
+chat_inTimeText=-7894388
```

**Why:** These greys fail the 4.5 : 1 contrast minimum on the "Night" theme in stock Forkgram.

**If the code moved:** Find each line by its key. Match by key: the old value `1694498815` is on 8 lines in this file. Only `chat_messagePanelHint` and `chat_topPanelMessage` change; the other six (for example `chat_messagePanelIcons`) stay unchanged. If the stock value of a line changed upstream (a replay conflict), or the key disappeared, re-derive the values with the simulator (8.2.5). Write values in decimal: the checker does not read `#hex`.


##### P7. Per-chat themes: apply the on-accent rule

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/EmojiThemes.java`

**Where:** Class `EmojiThemes`, method `createColors(int currentAccount, int index)`, inside `if (accent != null) {`, after the gift-theme block and before `} else {`. In Forkgram 12.10.6 the text below starts at line 429.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public SparseIntArray createColors(int currentAccount, int index) {
```

The context lines of the change below occur twice in the file. Use the copy after this line (it begins at line 472 in Forkgram 12.10.6, inside `createColors`), not the one in `getPreviewColors` (line 397).

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             if (isGiftTheme() && accent.parentTheme != null && accent.parentTheme.isLight()) {
                 accent.resetAccentColorsForMyMessagesGiftThemeLight(currentColors);
             }
+            org.telegram.messenger.multigram.PaletteFix.applyToColorMap(themeInfo, accent, currentColors); // MultiGram: on-accent contrast rule
         } else {
             currentColors = currentColorsNoAccent;
         }
```

**Why:** This builds the colour map of a per-chat theme (emoji or gift theme). With the hook, marks drawn on accent fills in a themed chat stay readable while the user's own accent is a runtime accent. With a stock accent the chat looks as in Forkgram.

**If the code moved:** Anchor on the method `createColors`, not on the block: the same `if (accent != null) { ... resetAccentColorsForMyMessagesGiftThemeLight ... }` block also exists in `getPreviewColors`, which is deliberately **not** hooked (it only draws a small preview). The call goes after `fillAccentColors` and the gift-theme fix, and before the map is completed with fallbacks and returned.


##### P8. Out-bubble text: always recompute for runtime accents

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme.ThemeAccent`, method `fillAccentColors(SparseIntArray, SparseIntArray)`: the condition of the block that picks black or white texts for outgoing bubbles. In Forkgram 12.10.6 the text below starts at line 679.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            if (!isMyMessagesGradientColorsNear) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                     }
                 }
             }
-            if (!isMyMessagesGradientColorsNear) {
+            if (!isMyMessagesGradientColorsNear || org.telegram.messenger.multigram.PaletteFix.isRuntimeAccent(this)) { // MultiGram: runtime accents (generated/custom) always get readable black/white out-bubble texts
                 if (myMessagesGradientAccentColor1 != 0) {
                     int textColor;
                     int subTextColor;
```

**Why:** Upstream picks readable black or white outgoing-bubble texts only when the custom bubble colour is not close to the theme's own bubble. A generated light bubble can be close to Blue's bubble and then keeps stock texts that fail contrast. For runtime accents the block now always runs.

**If the code moved:** Wherever `fillAccentColors` decides whether to recompute out-bubble text colours, make runtime accents always take the recompute path. Keep the line exactly as it is: `palette_fix_check.py` matches it, and the simulator (`tgsrc.py`, `style_table.py`) looks for this exact guard to know the palette fix is in the tree.


##### P9. Exported accent themes carry the rule

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme.ThemeAccent`, method `saveToFile()`, right after `fillAccentColors(...)`. In Forkgram 12.10.6 the text below starts at line 1041.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            SparseIntArray currentColorsNoAccent = getThemeFileValues(null, parentTheme.assetName, null);
            SparseIntArray currentColors = currentColorsNoAccent.clone();
            fillAccentColors(currentColorsNoAccent, currentColors);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             SparseIntArray currentColorsNoAccent = getThemeFileValues(null, parentTheme.assetName, null);
             SparseIntArray currentColors = currentColorsNoAccent.clone();
             fillAccentColors(currentColorsNoAccent, currentColors);
+            org.telegram.messenger.multigram.PaletteFix.applyToColorMap(parentTheme, this, currentColors); // MultiGram: on-accent contrast rule
 
             String wallpaperLink = null;
 
```

**Why:** An accent saved as an `.attheme` file carries the same readable marks the user sees. Stock accents export unchanged.

**If the code moved:** Wherever an accent's colour map is built for export, apply the rule after `fillAccentColors` and before the map is written.


##### P10. Keep 13 neutral keys out of the accent tint

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme`, static initializer: after the last `themeAccentExclusionKeys.add(...)` and before `themes = new ArrayList<>();`. In Forkgram 12.10.6 the text below starts at line 3886.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        themeAccentExclusionKeys.add(key_stories_circle_closeFriends2);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         themeAccentExclusionKeys.add(key_stories_circle_dialog2);
         themeAccentExclusionKeys.add(key_stories_circle_closeFriends1);
         themeAccentExclusionKeys.add(key_stories_circle_closeFriends2);
+        org.telegram.messenger.multigram.PaletteFix.addAccentExclusions(themeAccentExclusionKeys); // MultiGram: neutral greys stay readable under any accent
 
 
         themes = new ArrayList<>();
```

**Why:** `fillAccentColors` shifts the hue of most colours towards the accent. Keys in `themeAccentExclusionKeys` are skipped. The hook adds 13 neutral keys (the 11 greys, `windowBackgroundGray` and `chat_messagePanelIcons`), so an accent cannot tint them back below the contrast minimum.

**If the code moved:** Call it once, after upstream has filled `themeAccentExclusionKeys` and before any theme is loaded (still in the static initializer, after the `key_*` fields exist). If upstream turns the set into another type, change the parameter type of `PaletteFix.addAccentExclusions`.


##### P11. The global hook: apply the rule to the app's colours

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme`, method `refreshThemeColors(boolean bg, boolean messages)`: after the calculated table and article colours, before `reloadWallpaper` and `applyCommonTheme`. In Forkgram 12.10.6 the text below starts at line 6107.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        applyCalculatedArticleCodeColors(currentColorsNoAccent, currentColors, currentTheme.isDark());
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         }
         applyCalculatedTableColors(currentColorsNoAccent, currentColors, currentTheme.isDark());
         applyCalculatedArticleCodeColors(currentColorsNoAccent, currentColors, currentTheme.isDark());
+        org.telegram.messenger.multigram.PaletteFix.applyToCurrentColors(currentTheme, accent, currentColors); // MultiGram: on-accent contrast rule
         if (!messages) {
             boolean async = !(LaunchActivity.getLastFragment() instanceof ChatActivity);
             reloadWallpaper(async);
```

**Why:** This is the main hook. It decides whether the current theme and accent get the rule, and remembers the answer for hooks P14 to P18. When the rule is on, it sets the marks drawn on accent fills (the floating pencil, unread digits, checkmarks, button texts) to white or near-black `#050505`, whichever reads better, and gives the muted unread badge a matching fill.

**If the code moved:** It must run every time the global colour map is rebuilt: after the accent tint and all calculated colours, and before `applyCommonTheme`, `applyDialogsTheme` and `applyChatTheme` copy colours into paints. The local variable `accent` must be in scope; pass `null` if upstream removes it.


##### P12. Re-copy bundled themes after an app update

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme`, method `getAssetFile(String assetName)`: the condition that decides whether to copy the asset again. In Forkgram 12.10.6 the text below starts at line 7251.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        if (!file.exists() || size != 0 && file.length() != size) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             size = 0;
             FileLog.e(e);
         }
-        if (!file.exists() || size != 0 && file.length() != size) {
+        if (!file.exists() || size != 0 && file.length() != size || org.telegram.messenger.multigram.PaletteFix.isStaleAssetCopy(file)) { // MultiGram: also re-copy after an app update (same-size .attheme edits)
             try (InputStream in = ApplicationLoader.applicationContext.getAssets().open(assetName)) {
                 AndroidUtilities.copyFile(in, file);
             } catch (Exception e) {
```

**Why:** The app reads bundled themes from a copy in its files folder, and upstream refreshes that copy only when the asset's size changes. `arctic.attheme` and `bluebubbles.attheme` keep their size, so without this hook users who update would keep the old greys. `isStaleAssetCopy` returns true at most once per file per app start, when the copy is older than the app update.

**If the code moved:** Wherever a bundled asset is copied to storage and reused, also refresh it after an app update. If upstream starts reading assets directly (no copy), drop this hook.


##### P13. Channel colour screen

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ChannelColorActivity.java`

**Where:** Class `ChannelColorActivity`, method `updateThemeColors()`, inside `if (accent != null) {`, right after `fillAccentColors`. In Forkgram 12.10.6 the text below starts at line 2582.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                accent.fillAccentColors(themeColors, currentColors);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             Theme.ThemeAccent accent = themeInfo.getAccent(false);
             if (accent != null) {
                 accent.fillAccentColors(themeColors, currentColors);
+                org.telegram.messenger.multigram.PaletteFix.applyToColorMap(themeInfo, accent, currentColors); // MultiGram: on-accent contrast rule
             }
         }
         dividerPaint.setColor(Theme.getColor(Theme.key_divider, resourceProvider));
```

**Why:** This screen builds its own colour map for its previews. With the hook, the previews match what the app shows.

**If the code moved:** Put the call right after `fillAccentColors` wherever a screen builds its own colour map to draw UI. After an update run `git grep -n 'fillAccentColors(' -- TMessagesProj/src/main/java ':!TMessagesProj/src/main/java/org/telegram/messenger/multigram'`. Today it prints 11 lines: the method itself and 10 calls. (Without the last pathspec it prints a 12th line on a MultiGram tree: a comment in `PaletteFix.java`.) Six calls are hooked (P7, P9, P11, P13, P16, P17). Four are left alone on purpose: `EmojiThemes.getPreviewColors` (twice), `ThemePreviewDrawable` and `Stories/recorder/PreviewView`. Decide for any new call.


##### P14. Send button: loading arc colour

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/ChatActivityEnterView.java`

**Where:** Inner class `ChatActivityEnterView.SendButton`, method `onDraw(Canvas)`, inside `if (loadingShown > 0) {`. In Forkgram 12.10.6 the text below starts at line 15512.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                    loadingPaint.setColor(0xFFFFFFFF);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 }
                 canvas.clipPath(path);
                 if (loadingShown > 0) {
-                    loadingPaint.setColor(0xFFFFFFFF);
+                    loadingPaint.setColor(multigramGlyphColor != 0 ? multigramGlyphColor : 0xFFFFFFFF); // MultiGram: was 0xFFFFFFFF
                     loadingPaint.setAlpha((int) (0xFF * loadingShown));
                     final float R = dp(8.66f);
                     AndroidUtilities.rectTmp.set(right - w / 2.0f - R, cy - R, right - w / 2.0f + R, cy + R);
```

**Why:** The progress arc drawn on the send button's fill uses the same readable colour as the icon. `multigramGlyphColor` is the field added in P15; 0 means "keep stock white".

**If the code moved:** Any mark that `SendButton` draws in fixed white on its accent fill should use `multigramGlyphColor` when it is not 0. `palette_fix_check.py` does not check this line; check it by hand.


##### P15. Send button: glyph colour on the fill

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/ChatActivityEnterView.java`

**Where:** Inner class `ChatActivityEnterView.SendButton`: a new field after `private int drawableColor;`, and method `updateColors()`. In Forkgram 12.10.6 the text below starts at line 15674.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        private int drawableColor;

        public void updateColors() {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         }
 
         private int drawableColor;
+        private int multigramGlyphColor; // MultiGram: glyph colour on the fill for generated styles, 0 = stock
 
         public void updateColors() {
-            int color = isNewDesignSendButton ? Color.WHITE : Theme.getColor(Theme.key_chat_messagePanelSend, resourcesProvider);
-            if (color != drawableColor) {
+            int glyph = org.telegram.messenger.multigram.PaletteFix.getGlyphColorOnFill(isNewDesignSendButton ? Theme.getColor(Theme.key_chat_messagePanelSend, resourcesProvider) : shouldDrawBackground() ? getFillColor() : 0); // MultiGram: readable glyph on generated accent fills
+            int color = isNewDesignSendButton ? (glyph != 0 ? glyph : Color.WHITE) : Theme.getColor(Theme.key_chat_messagePanelSend, resourcesProvider); // MultiGram: was Color.WHITE for the new design
+            if (color != drawableColor || glyph != multigramGlyphColor) { // MultiGram: was color != drawableColor
                 drawableColor = color;
+                multigramGlyphColor = glyph; // MultiGram
                 drawable.setColorFilter(new PorterDuffColorFilter(color, PorterDuff.Mode.SRC_IN));
                 int c = Theme.getColor(Theme.key_glass_defaultIcon, resourcesProvider);
                 inactiveDrawable.setColorFilter(new PorterDuffColorFilter(Color.argb(0xb4, Color.red(c), Color.green(c), Color.blue(c)), PorterDuff.Mode.SRC_IN));
-                drawableInverse.setColorFilter(new PorterDuffColorFilter(Theme.getColor(Theme.key_chat_messagePanelVoicePressed, resourcesProvider), PorterDuff.Mode.SRC_IN));
+                drawableInverse.setColorFilter(new PorterDuffColorFilter(glyph != 0 ? glyph : Theme.getColor(Theme.key_chat_messagePanelVoicePressed, resourcesProvider), PorterDuff.Mode.SRC_IN)); // MultiGram: was the voicePressed colour only
+                count.setTextColor(glyph != 0 && !isNewDesignSendButton ? glyph : 0xFFFFFFFF); // MultiGram: counter digits on the fill (old design)
+                priceText.setTextColor(glyph != 0 ? glyph : 0xFFFFFFFF); // MultiGram: star price on the fill
             }
             if (isNewDesignSendButton) {
                 backgroundPaint.setColor(Theme.getColor(Theme.key_chat_messagePanelSend, resourcesProvider));
```

**Why:** Upstream draws the send button's glyph in fixed white on the accent fill. While the rule is on, `getGlyphColorOnFill` returns white or `#050505` for that fill (0 otherwise, which keeps stock). The glyph, the inverse glyph, the old-design counter digits and the star price follow it. The extra `|| glyph != multigramGlyphColor` makes a style change repaint even when `color` did not change.

**If the code moved:** In the send button's colour update, compute the glyph colour from the colour of the fill it sits on, and use it for every mark drawn on that fill. It relies on these `SendButton` members: `isNewDesignSendButton`, `shouldDrawBackground()`, `getFillColor()`, `drawable`, `drawableInverse`, `count`, `priceText`, `resourcesProvider`. The checker looks only at the `int glyph = ...` and `drawableInverse...` lines; check the rest by hand.


##### P16. Message-in-story preview

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/Paint/Views/MessageEntityView.java`

**Where:** Class `MessageEntityView`, method `setupTheme(StoryEntry)`, inside `if (accent != null) {`, right after `fillAccentColors`. In Forkgram 12.10.6 the text below starts at line 1399.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                accent.fillAccentColors(themeColors, currentColors);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             Theme.ThemeAccent accent = themeInfo.getAccent(false);
             if (accent != null) {
                 accent.fillAccentColors(themeColors, currentColors);
+                org.telegram.messenger.multigram.PaletteFix.applyToColorMap(themeInfo, accent, currentColors); // MultiGram: on-accent contrast rule
             }
         }
 
```

**Why:** The message shown inside a story builds its own colour map. With the hook, its marks follow the rule exactly when the app's colours do.

**If the code moved:** As for P13.


##### P17. Profile colour screen

**File:** `TMessagesProj/src/main/java/org/telegram/ui/PeerColorActivity.java`

**Where:** Class `PeerColorActivity`, method `updateThemeColors()`, inside `if (accent != null) {`, right after `fillAccentColors`. In Forkgram 12.10.6 the text below starts at line 1496.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            accent.fillAccentColors(themeColors, currentColors);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         Theme.ThemeAccent accent = themeInfo.getAccent(false);
         if (accent != null) {
             accent.fillAccentColors(themeColors, currentColors);
+            org.telegram.messenger.multigram.PaletteFix.applyToColorMap(themeInfo, accent, currentColors); // MultiGram: on-accent contrast rule
         }
 
         if (namePage != null && namePage.messagesCellPreview != null) {
```

**Why:** The name and profile colour screen builds its own colour map for its message previews. With the hook, they match the app.

**If the code moved:** As for P13.


##### P18. Stories and calls: marks on overridden fills

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Stories/DarkThemeResourceProvider.java`

**Where:** Class `DarkThemeResourceProvider`, method `getColor(int key)`: the last `return`, for keys the provider does not override. In Forkgram 12.10.6 the text below starts at line 205.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        return Theme.getColor(key);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         if (!debugUnknownKeys.contains(key)) {
             debugUnknownKeys.add(key);
         }
-        return Theme.getColor(key);
+        return org.telegram.messenger.multigram.PaletteFix.getOverrideFallbackColor(sparseIntArray, key); // MultiGram: was Theme.getColor(key); marks on fills overridden here stay readable
     }
 
     Drawable msgOutMedia;
```

**Why:** This provider (used by stories and group calls) replaces some fills, such as `dialogRoundCheckBox`, but not the marks drawn on them. While the rule is on, the app's mark colour was chosen for the app's fill. For a mark whose fill this provider replaces, PaletteFix picks white or `#050505` again for the replaced fill. Every other key still returns `Theme.getColor(key)`.

**If the code moved:** In resource providers that replace some colours and fall back to the global theme, send the fallback through `getOverrideFallbackColor`. `sparseIntArray` is the provider's map today; rename it in the call if upstream renames the field.


#### 8.2.4 Data

The values below are taken from the repository. The contrast columns come from the simulator's report (`overlay_A_rows.json`), rebuilt on Forkgram 12.10.6. Each is measured against the key's background in that theme.

**`ThemeColors.java` defaults** (hook P1; used by the Blue theme and inherited by every theme without its own value):

| Key | Forkgram 12.10.6 | MultiGram | Contrast before → after |
|---|---|---|---|
| `windowBackgroundWhiteGrayText` | `0xff808384` | `0xff757778` | 3.82 → 4.50 |
| `windowBackgroundWhiteGrayText2` | `0xff82868a` | `0xff73777b` | 3.67 → 4.51 |
| `windowBackgroundWhiteGrayText4` | `0xff808080` | `0xff6f6e6e` | 3.50 → 4.51 |
| `actionBarDefaultSubtitle` | `0xff79817e` | `0xff717876` | 4.00 → 4.52 |
| `chats_message` | `0xff75787A` | `0xff747779` | 4.45 → 4.51 |
| `chats_date` | `0xff848688` | `0xff757778` | 3.65 → 4.50 |
| `chat_inViews` | `0xffa1aab3` | `0xff6f7780` | 2.36 → 4.54 |
| `chat_inTimeText` | `0xffa1aab3` | `0xff6f7780` | 2.36 → 4.54 |
| `chat_inFileInfoText` | `0xffa1aab3` | `0xff6f7780` | 2.36 → 4.54 |
| `chat_messagePanelHint` | `0xff858a84` | `0xff737873` | 3.52 → 4.50 |
| `chat_topPanelMessage` | `0xff767e7c` | `0xff717877` | 4.16 → 4.51 |

**Bundled themes** (hooks P2 to P6). The files store signed decimal numbers; the "As colours" column shows the same values as `#AARRGGBB`.

**`arctic.attheme`** (theme "Arctic Blue")

| Key | Forkgram 12.10.6 | MultiGram | As colours | Contrast before → after |
|---|---|---|---|---|
| `actionBarDefaultSubtitle` | `-7630182` | `-9341057` | #FF8B929A → #FF71777F | 3.15 → 4.52 |
| `chat_topPanelMessage` | `-8354167` | `-9275526` | #FF808689 → #FF72777A | 3.69 → 4.53 |
| `chat_inFileInfoText` | `-6182221` | `-9472128` | #FFA1AAB3 → #FF6F7780 | 2.36 → 4.54 |
| `windowBackgroundWhiteGrayText` | `-7629665` | `-9472126` | #FF8B949F → #FF6F7782 | 3.07 → 4.53 |

**`bluebubbles.attheme`** (theme "Blue")

| Key | Forkgram 12.10.6 | MultiGram | As colours | Contrast before → after |
|---|---|---|---|---|
| `actionBarDefaultSubtitle` | `-8156010` | `-9472127` | #FF838C96 → #FF6F7781 | 3.41 → 4.53 |
| `windowBackgroundWhiteGrayText` | `-7565423` | `-9144455` | #FF8C8F91 → #FF747779 | 3.25 → 4.51 |
| `windowBackgroundWhiteGrayText2` | `-7565423` | `-9144455` | #FF8C8F91 → #FF747779 | 3.25 → 4.51 |
| `windowBackgroundWhiteGrayText4` | `-7565423` | `-9671056` | #FF8C8F91 → #FF6C6E70 | 2.88 → 4.54 |

**`darkblue.attheme`** (theme "Dark Blue")

| Key | Forkgram 12.10.6 | MultiGram | As colours | Contrast before → after |
|---|---|---|---|---|
| `chat_messagePanelHint` | `1859907583` | `-1763971073` | #6EDBEFFF → #96DBEFFF | 3.49 → 4.52 |
| `actionBarDefaultSubtitle` | `2111566591` | `-1831079169` | #7DDBF2FF → #92DBF2FF | 4.12 → 4.51 |
| `chat_topPanelMessage` | `1859974399` | `-1814235905` | #6EDCF4FF → #93DCF4FF | 3.57 → 4.54 |
| `chat_inFileInfoText` | `-8812137` | `-7035469` | #FF798997 → #FF94A5B3 | 3.83 → 4.54 |
| `windowBackgroundWhiteGrayText` | `-8549479` | `-7562327` | #FF7D8B99 → #FF8C9BA9 | 4.33 → 4.53 |
| `chats_message` | `-8549479` | `-7562327` | #FF7D8B99 → #FF8C9BA9 | 4.33 → 4.53 |
| `chats_date` | `-9207925` | `-7431514` | #FF737F8B → #FF8E9AA6 | 3.70 → 4.50 |
| `chat_inViews` | `-8812137` | `-7035469` | #FF798997 → #FF94A5B3 | 3.83 → 4.54 |
| `windowBackgroundWhiteGrayText2` | `1878130175` | `-2081292801` | #6FF1FDFF → #83F1FDFF | 3.95 → 4.51 |
| `windowBackgroundWhiteGrayText4` | `-931296359` | `-209876071` | #C87D8B99 → #F37D8B99 | 3.48 → 4.52 |
| `chat_inTimeText` | `-645885536` | `-7035724` | #D98091A0 → #FF94A4B4 | 3.49 → 4.50 |
| `chats_attachMessage` | `-8548712` | `-6710887` | #FF7D8E98 → #FF999999 | 4.46 → 4.53 |

**`day.attheme`** (theme "Day")

| Key | Forkgram 12.10.6 | MultiGram | As colours | Contrast before → after |
|---|---|---|---|---|
| `actionBarDefaultSubtitle` | `-8814210` | `-9340810` | #FF79817E → #FF717876 | 4.00 → 4.52 |
| `chat_topPanelMessage` | `-9011588` | `-9340809` | #FF767E7C → #FF717877 | 4.16 → 4.51 |
| `chat_inFileInfoText` | `-7565679` | `-9671312` | #FF8C8E91 → #FF6C6D70 | 2.88 → 4.54 |
| `windowBackgroundWhiteGrayText` | `-8354940` | `-9078920` | #FF808384 → #FF757778 | 3.82 → 4.50 |
| `chat_inViews` | `-274882397` | `-9736591` | #EF9DA0A3 → #FF6B6E71 | 2.17 → 4.50 |
| `chat_inTimeText` | `-7105127` | `-9671311` | #FF939599 → #FF6C6D71 | 2.63 → 4.53 |

**`night.attheme`** (theme "Night")

| Key | Forkgram 12.10.6 | MultiGram | As colours | Contrast before → after |
|---|---|---|---|---|
| `chat_messagePanelHint` | `1694498815` | `1979711487` | #64FFFFFF → #75FFFFFF | 3.67 → 4.52 |
| `actionBarDefaultSubtitle` | `1945301746` | `-2131561742` | #73F2F2F2 → #80F2F2F2 | 3.98 → 4.50 |
| `chat_topPanelMessage` | `1694498815` | `1962934271` | #64FFFFFF → #74FFFFFF | 3.72 → 4.53 |
| `chat_inFileInfoText` | `-9013641` | `-7763573` | #FF767677 → #FF89898B | 3.56 → 4.50 |
| `windowBackgroundWhiteGrayText` | `1862270975` | `1962934271` | #6EFFFFFF → #74FFFFFF | 4.25 → 4.56 |
| `chats_date` | `-8882056` | `-8289920` | #FF787878 → #FF818180 | 4.02 → 4.51 |
| `chat_inViews` | `-8881024` | `-8025458` | #FF787C80 → #FF858A8E | 3.84 → 4.51 |
| `windowBackgroundWhiteGrayText2` | `1862139391` | `1962802687` | #6EFDFDFF → #74FDFDFF | 4.20 → 4.50 |
| `windowBackgroundWhiteGrayText4` | `-9803158` | `-9079692` | #FF6A6A6A → #FF757474 | 3.88 → 4.51 |
| `chat_inTimeText` | `-8552575` | `-7894388` | #FF7D7F81 → #FF878A8C | 4.02 → 4.52 |

**Keys the accent tint skips** (hook P10, `PaletteFix.addAccentExclusions`). The order does not matter.

| # | Key |
|---|---|
| 1 | `key_windowBackgroundGray` |
| 2 | `key_windowBackgroundWhiteGrayText` |
| 3 | `key_windowBackgroundWhiteGrayText2` |
| 4 | `key_chats_message` |
| 5 | `key_chats_date` |
| 6 | `key_actionBarDefaultSubtitle` |
| 7 | `key_chat_inTimeText` |
| 8 | `key_chat_inFileInfoText` |
| 9 | `key_chat_messagePanelHint` |
| 10 | `key_windowBackgroundWhiteGrayText4` |
| 11 | `key_chat_topPanelMessage` |
| 12 | `key_chat_inViews` |
| 13 | `key_chat_messagePanelIcons` |

**Marks and the fills they sit on** (`PaletteFix.Keys.ON_ACCENT`). While the rule is on, each mark becomes white or `#FF050505` for its fill. The order must match overlay A, with the extra voice pair last.

| # | Mark (content key) | Fill it sits on |
|---|---|---|
| 1 | `key_chats_actionIcon` | `key_chats_actionBackground` |
| 2 | `key_chats_unreadCounterText` | `key_chats_unreadCounter` |
| 3 | `key_featuredStickers_buttonText` | `key_featuredStickers_addButton` |
| 4 | `key_checkboxSquareCheck` | `key_checkboxSquareBackground` |
| 5 | `key_dialogRoundCheckBoxCheck` | `key_dialogRoundCheckBox` |
| 6 | `key_chat_goDownButtonCounter` | `key_chat_goDownButtonCounterBackground` |
| 7 | `key_dialogCheckboxSquareCheck` | `key_dialogCheckboxSquareBackground` |
| 8 | `key_chat_attachCheckBoxCheck` | `key_chat_attachCheckBoxBackground` |
| 9 | `key_chat_inMediaIcon` | `key_chat_inLoader` |
| 10 | `key_chat_inContactIcon` | `key_chat_inContactBackground` |
| 11 | `key_picker_badgeText` | `key_picker_badge` |
| 12 | `key_dialogFloatingIcon` | `key_dialogFloatingButton` |
| 13 | `key_chat_messagePanelVoicePressed` | `key_chat_messagePanelVoiceBackground` (extra pair, only in `PaletteFix.java`) |

**Muted unread badge** (`PaletteFix.MUTED_FILL`). While the rule is on, the badge (`key_chats_unreadCounterMuted`) gets a neutral fill that suits the digit colour. Four keys normally borrow the badge colour: `key_avatar_backgroundArchived`, `key_chats_archivePinBackground`, `key_chats_archivePullDownBackground` and `key_checkboxDisabled` (`MUTED_PINS`). Before it changes the badge, the rule writes their current colour explicitly, so they keep their look.

| Theme | Badge fill with white digits | Badge fill with near-black digits |
|---|---|---|
| Blue | `#FF73777B` | `#FFBEC3C7` |
| Arctic Blue | `#FF73777B` | `#FFBEC3C7` |
| Day | `#FF73777B` | `#FFBEC3C7` |
| Dark Blue | `#FF3E5263` | `#FF63798B` |
| Night | `#FF454545` | `#FF777676` |

#### 8.2.5 Regenerate and verify

**1. Check the tree** (a few seconds). From the root of a checkout:

```sh
python3 multigram/tools/palette_fix_check.py
python3 multigram/tools/palette_fix_check.py --base origin/forkgram
```

Success prints one line, `palette-fix: OK`, and exit status 0. A failure prints one line per problem, then `palette-fix: FAILED, N problem(s)`, and exit status 1. Two real problem lines, from a test copy with one value changed and one hook line deleted:

```text
palette-fix: ThemeColors key_chat_topPanelMessage = ['0xff717878'], expected 0xff717877
palette-fix: hook 'PaletteFix\\.applyToColorMap\\(themeInfo, accent, currentColors\\); // MultiGram:' found 0 times in TMessagesProj/src/main/java/org/telegram/ui/PeerColorActivity.java
```

`--base` must name the snapshot the tree is built on. On the MultiGram tree, `--base dc780e81e` (plain Telegram) reports 1450 false problems, because Forkgram's Monet theme files then count as changes.

This check compares the tree with overlay A. It cannot tell whether overlay A still suits the new Forkgram. The simulator does that.

**2. Re-derive the values from the new Forkgram** (about 3 seconds). The simulator treats the tree it reads as stock, so give it the plain new snapshot, never the MultiGram tree:

```sh
rm -rf /tmp/fk-new /tmp/overlay-new
mkdir -p /tmp/fk-new /tmp/overlay-new
git archive origin/forkgram TMessagesProj/src/main/java/org/telegram/ui/ActionBar TMessagesProj/src/main/assets | tar -x -C /tmp/fk-new
cd multigram/tools/sim
TG_REPO=/tmp/fk-new CANVAS_OUT=/tmp/overlay-new python3 canvas.py --build > /tmp/overlay-new/build.log
grep '^VARIANT A' /tmp/overlay-new/build.log
cmp /tmp/overlay-new/overlay_A.json ../../palette-fix/overlay_A.json && cmp /tmp/overlay-new/overlay_A.json palette-fix/overlay_A.json && echo "overlay A unchanged"
cd ../../..
```

- The first line clears what an earlier update left there. `tar` only adds files, so files Forkgram has since deleted would stay and be modelled.
- The simulator needs only `ui/ActionBar` and the assets, so `git archive` of those two folders is enough.
- Always set `CANVAS_OUT`. Without it, `--build` overwrites the committed `multigram/tools/sim/palette-fix/overlay_A.json` and `overlay_B.json`.
- On Forkgram 12.10.6 it prints `VARIANT A (1.8 s): 23 defaults, 36 attheme lines, 13 exclusions`, and both `cmp` commands find no difference.

If `overlay A unchanged` appears, there is nothing to do. If not, see what changed:

```sh
diff <(python3 -m json.tool --sort-keys multigram/palette-fix/overlay_A.json) <(python3 -m json.tool --sort-keys /tmp/overlay-new/overlay_A.json)
```

`/tmp/overlay-new/build.log` and `overlay_A_rows.json` explain each value: theme, key, old and new colour, contrast before and after, and the source file and line.

To adopt a new overlay:

1. Copy `/tmp/overlay-new/overlay_A.json` over **both** `multigram/palette-fix/overlay_A.json` and `multigram/tools/sim/palette-fix/overlay_A.json`.
2. Write the new values into `ThemeColors.java` and the `.attheme` files, and the new tables into `PaletteFix.java`. `palette_fix_check.py` lists every line that differs, with the expected value. Remember the `// MultiGram: contrast fix, was <old value>` comments in `ThemeColors.java`.
3. Run `python3 multigram/tools/palette_fix_check.py --base origin/forkgram` until it says OK.
4. Regenerate the style table (8.3.5), because it is checked against overlay A.
5. Fold the changes in with one fixup per commit (6.3): `multigram/palette-fix/overlay_A.json`, `ThemeColors.java`, the `.attheme` files and `PaletteFix.java` into "Fix palette contrast for generated accents"; `multigram/tools/sim/palette-fix/overlay_A.json` and a new `multigram_styles.bin` into "Add the style table and its generator".

**3. Residual check on the finished tree.** Run the simulator on the MultiGram tree itself:

```sh
mkdir -p /tmp/overlay-in-tree
cd multigram/tools/sim
TG_REPO=$(git rev-parse --show-toplevel) CANVAS_OUT=/tmp/overlay-in-tree python3 canvas.py --build | grep '^VARIANT A'
cd ../../..
```

On ff868b3ea4 it prints `VARIANT A (1.7 s): 12 defaults, 0 attheme lines, 13 exclusions` (the time varies). The 12 defaults are the on-accent marks the app keeps white on purpose. Any `.attheme` line, or a 13th default, means a grey below 4.5 : 1.

**4. Measure generated accents** on the plain new Forkgram from step 2:

```sh
cd multigram/tools/sim
TG_REPO=/tmp/fk-new python3 canvas.py --measure 200 --variant A --procs 4
cd ../../..
```

On 12.10.6 the line `pass rate (generated, all pairs)` shows `100.00%` for all five themes, and `residual failing pairs` shows `(none)`. Use `--measure 5000` before a release.

**On a device:** with a stock preset accent, only grey secondary texts differ from Forkgram. With a light runtime accent (pick light yellow with the colour wheel), marks on accent fills turn near-black: the chat list pencil, unread digits, Join buttons, checkboxes, the send button. With a dark accent they stay white. To test hook P12, install a build from before this commit, select Arctic Blue, then install the new build over it: the darker greys must appear without clearing data.

#### 8.2.6 Gotchas

- **Only 11 of the 23 defaults in overlay A go into `ThemeColors.java`.** The other 12 are the on-accent marks. Overlay A stores them as `#FF050505` (the rule applied to the Blue theme inside the simulator), but the app keeps them stock white and sets them at run time. Copying them would turn every stock user's pencil and badge digits near-black. The check flags it.
- **The values sit right at the minimum** (4.50 to 4.56 : 1). An upstream change to a background, bubble or the accent maths causes no conflict, but can push a grey below 4.5 : 1. Re-derive the overlay after every update (step 2 above). As a second line of defence, `check_style_table.py` re-checks every generated style on the new sources.
- **If upstream changes the stock value of a replaced line**, the replay conflicts on that line. Do not just keep MultiGram's value: re-derive it, or drop the line if the new stock value passes. Update the `was 0x...` comment.
- **The simulator only exists from cddd62df98.** When you re-apply 5b53859682 alone, run the simulator from a full MultiGram checkout with `TG_REPO` pointing at the tree to model.
- **The checker matches hook lines exactly, including their comments.** Reformatting a hook line fails the check. But it checks only 2 of the 9 MultiGram lines in `ChatActivityEnterView.java` (the `int glyph = ...` line and the `drawableInverse` line), and it does not check whether hooks sit in the right method. Check the rest by hand (10.3).
- **Order matters in `PaletteFix`.** `Keys.ON_ACCENT` and `MUTED_PINS` must follow overlay A's order. The exclusions are compared as a set.
- **`Theme.key_*` values are counted at run time** (`colorsCount++`), not compile-time constants. They cannot be used in `switch` statements, and `PaletteFix` reads them through a lazy holder class (`Keys`).
- **`getColor(key, null, true)`** becomes ambiguous if upstream adds another three-argument `getColor`. Cast the `null` to `(boolean[])`.
- **`isActiveFor` copies the private `ThemeInfo.isDefaultMainAccent()`.** If upstream changes that method, change the copy.
- **Accent ids.** The rule depends on these conventions: presets have ids up to 99, the migrated old custom accent is 100, new accents get 101 and up, server and cloud accents carry a `TL_theme` in `accent.info`, and chat-theme accents have small ids. If upstream changes them, stock accents could get the rule, or generated ones could lose it.
- **`EmojiThemes` has two identical `fillAccentColors` blocks.** Hook only the one in `createColors`, not the one in `getPreviewColors`.
- **Hook P11's place matters:** after the accent tint and all computed colours, before the colours are copied into paints.
- **Value-only edits to bundled themes reach users only through hook P12**, because upstream re-copies a theme file only when its size changes.
- **Theme files use signed decimals without the `key_` prefix.** Overlay A uses unsigned numbers with the prefix. For a value with the top bit set, subtract 2^32. Write decimals; the checker ignores `#hex`. Match lines by key, because the same old value can occur on several lines.
- **`chats_attachMessage` on Dark Blue is a pure grey (`#FF999999`) on purpose.** The key is accent-coloured on the light themes, so it cannot join the global exclusion list, and a pure grey is never tinted. `chat_messagePanelIcons` is excluded without a value change. Do not tidy either.
- **New calls of `fillAccentColors`** are not found automatically. After an update, run the `git grep` of P13. On ff868b3ea4 it prints 11 lines: the method itself and 10 calls, 6 of them hooked (P7, P9, P11, P13, P16, P17). Decide for any new call.

### 8.3 Style table and random style (cddd62df98 and 27d32d57b4)

#### 8.3.1 What and why

These two commits give every fresh install its own day and night colour style.

The colours are not made on the device. Commit **cddd62df98** adds a precomputed table, `TMessagesProj/src/main/assets/multigram_styles.bin`. It holds 4,096 styles for each of the five bundled themes (Blue, Arctic Blue, Day, Dark Blue, Night), 20,480 in all. A style is an accent colour, 1 to 4 outgoing bubble colours and a wallpaper gradient of 2 to 4 colours, without a pattern. The commit also adds the Python tools that make the table and check that every style is readable. They include the simulator. This commit touches no upstream file.

Commit **27d32d57b4** adds the Java side and 15 hooks in 7 upstream files:

- **Stage A** (hook S1, at app start): a fresh install gets a random seed, which picks one day and one night style. The choice is stored in the preferences file `rebrand_style`.
- **Stage B** (hook S3, while the `Theme` class starts): the two styles become local accents (ids 101 and up, no pattern) and are selected before the first frame.
- **Chat Settings**: a "Shuffle my style" row with Undo. "Reset to defaults" returns to the generated style.
- **Privacy**: generated accents are never uploaded, shared or turned into cloud themes.

Installs that existed before are never restyled automatically.

#### 8.3.2 New files

| Path | Purpose | Upstream names it relies on |
|---|---|---|
| `TMessagesProj/src/main/assets/multigram_styles.bin` | The style table, format version 1: 819,384 bytes, 20,480 records. Made by `make_style_table.py`; never edit it by hand. The same sources always give the same bytes. | The theme keys "Blue", "Arctic Blue", "Day", "Dark Blue", "Night" and their night flag; `Theme.java`, `ThemeColors.java` and the five `.attheme` files it was checked against; the `ThemeAccent` fields each record fills |
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/StyleTable.java` | Reads and fully verifies the table (magic, version, sizes, directory, CRC-32). `get(night, n)` returns the n-th day or night style. It never touches `Theme`, so it is safe before `Theme` exists. | `AssetManager.open()` (not `openFd()`, because the asset is compressed) |
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyle.java` | The logic: Stage A, Stage B, Shuffle, Undo, Reset, the privacy records, and the seed API that the knobs use. | `Theme.getActiveTheme()`, `getCurrentTheme()`, `getCurrentNightTheme()`, `setCurrentNightTheme()`, `getTheme(String)`, `saveThemeAccents(...)` (5- and 6-argument forms), `deleteThemeAccent(...)`, `selectedAutoNightType`; `ThemeInfo.getAccent(boolean)`, `themeAccents`, `themeAccentsMap`, `prevAccentId`, `currentAccentId`, `overrideWallpaper`, `assetName`, `isDark()`, `getKey()`, `isMonet()` (Forkgram only); the `ThemeAccent` colour fields; `NotificationCenter.needSetDayNightTheme`; the preference files `themeconfig` and `mainconfig`; `PaletteFix.LAST_STOCK_ACCENT_ID` |
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyleUi.java` | The Chat Settings side: the Shuffle row, Undo, the custom theme tile refresh, and the "stays on this device" messages. | `TextCell`, `BulletinFactory`, `EmojiThemes.createPreviewCustom(int)` and its tile emoji, `ChatThemeBottomSheet.ChatThemeItem`, `R.drawable.menu_random`, `R.raw.info`, `Utilities.globalQueue` |
| `TMessagesProj/src/main/res/values/multigram_strings.xml` | Five English strings, `MultiGram*`. They are read with `Context.getString`, never through `LocaleController`. | Telegram's build turns only `strings.xml` files into its translation assets, so this separate file stays a plain resource. The names must not clash with other strings. |
| `multigram/random-style/README.md` | Design document: lifecycle, preference keys, privacy, the hook table, and a 15-item device checklist. | Documentation only |
| `multigram/tools/random_style_check.py` | Checks the 15 hooks and where they sit, that the feature makes no server calls and saves without upload, the strings, the asset, and the backup policy. Prints `random-style: OK`. | The landmark lines of each hook; `forkgram/SettingsBackup.kt` and its `ALLOWED_PREFS` (Forkgram only: the check crashes without this file); `BackupAgent.java`; `android:backupAgent=".BackupAgent"` in the manifest |
| `multigram/tools/README.md` | The table format, how an entry is applied, the readability rule, generation, the checks, and "Replaying onto a new Forkgram release". | Documentation only |
| `multigram/tools/.gitignore` | Ignores `__pycache__/`, `*.pyc` and `sim/cache/`. | None |
| `multigram/tools/check.sh` | The checks CI runs after the compile (10.2). | bash and python3 |
| `multigram/tools/make_style_table.py` | Makes the table. `--check` only compares. Exit status: 0 written or identical, 3 different, 4 stalled, 1 error. | Everything `style_table.py` and the simulator read |
| `multigram/tools/check_style_table.py` | Checks the table's format and the readability of every entry on this tree's theme sources. Exit status 0 on PASS, 1 on FAIL. | Same as the simulator; `TG_REPO` to model another checkout |
| `multigram/tools/style_table.py` | Shared code: the binary format, the generator's settings, and how overlay A is applied. | overlay A; the palette fix's exact guard line in `fillAccentColors` (hook P8) |
| `multigram/tools/sim/tgsrc.py` | Reads the theme engine's inputs straight from the Java and `.attheme` sources, and caches the result. Raises `... update the simulator` when a structure changed. | Many exact forms in `Theme.java` and `ThemeColors.java`: key declarations, fallbacks, exclusions, accent presets, `fillAccentColors`, `createDefaultWallpaper`, `createDefaultColors`, `createColorKeysMap` |
| `multigram/tools/sim/engine.py` | A port of Telegram's accent engine to Python. | The logic of `fillAccentColors`, `changeColorAccent`, `getAccentColor`, `useBlackText`, `changeBrightness` and others, as in Telegram 12.10.5. A change inside these methods is **not** detected; see 8.3.6. |
| `multigram/tools/sim/readability.py` | The 99 readability pairs and the contrast maths. | Colour key names; models of the bubble, wallpaper and service message drawing |
| `multigram/tools/sim/style_sim.py`, `multigram/tools/sim/canvas.py`, `multigram/tools/sim/detmath.py`, `multigram/tools/sim/detmath_tables.py` | The style generator, the overlay builder and measurer (`canvas.py`), and portable maths that keep results identical on every machine. | None beyond the files above |
| `multigram/tools/sim/palette-fix/overlay_A.json`, `multigram/tools/sim/palette-fix/overlay_B.json` | overlay A (a copy, used when the modelled tree has none) and the rejected variant B. | Must stay byte-identical to `multigram/palette-fix/overlay_A.json` |
| `multigram/tools/sim/README.md` | How the simulator works and what it reads. | Documentation only |

27d32d57b4 also adds the random style step to `check.sh` and a two-line note about it to `multigram/tools/README.md`.

#### 8.3.3 Hooks

##### S1. Stage A: pick this install's style at first start

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/ApplicationLoader.java`

**Where:** Class `ApplicationLoader`, method `onCreate()`: right after the second `if (applicationContext == null) { applicationContext = getApplicationContext(); }`, before `NativeLoader.initNativeLibs(...)`. In Forkgram 12.10.6 the text below starts at line 368.

**Find this** (its first line occurs twice in the file, the whole block once; text from Forkgram 12.10.6):

```java
            applicationContext = getApplicationContext();
        }

        NativeLoader.initNativeLibs(ApplicationLoader.applicationContext);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         if (applicationContext == null) {
             applicationContext = getApplicationContext();
         }
+        org.telegram.messenger.multigram.RandomStyle.onApplicationCreate(applicationContext); // MultiGram: per-install style seed, before anything touches Theme
 
         NativeLoader.initNativeLibs(ApplicationLoader.applicationContext);
 
```

**Why:** It runs on every start but does its work only once per install. An install that already has theme settings is marked `existing` and never restyled. A fresh install gets a random seed and picks one day and one night entry from the style table. It never throws.

**If the code moved:** It must run in `Application.onCreate` after `applicationContext` is set, and **before anything loads the `Theme` class**. Theme's static initializer writes a theme setting on every start; after that, every fresh install would count as `existing` and silently get no style. Keep it the first MultiGram line in `onCreate`: K1 goes directly below it. The lines `applicationContext = getApplicationContext();` and `NativeLoader.initNativeLibs(` each occur twice in the file; the 4-line block shown occurs once. `random_style_check.py` checks the order.


##### S2. Never upload a generated style

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/MessagesController.java`

**Where:** Class `MessagesController`, method `saveThemeToServer(Theme.ThemeInfo, Theme.ThemeAccent)`: the first statement. In Forkgram 12.10.6 the text below starts at line 9131.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public void saveThemeToServer(Theme.ThemeInfo themeInfo, Theme.ThemeAccent accent) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     public void saveThemeToServer(Theme.ThemeInfo themeInfo, Theme.ThemeAccent accent) {
+        if (org.telegram.messenger.multigram.RandomStyle.isUploadBlocked(themeInfo, accent)) return; // MultiGram: a generated style never leaves the device
         if (themeInfo == null) {
             return;
         }
```

**Why:** Every theme or accent upload passes through this method. A generated accent, or an edit or copy of one, is never uploaded.

**If the code moved:** Put it at the very start of whatever method builds the theme file and uploads a local accent. If upstream splits the upload into several methods, guard each one. The check requires it to be the first statement of `saveThemeToServer`.


##### S3. Stage B: turn the picked entries into accents before the first frame

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme`, static initializer: after the saved accents are loaded and the old-accent migration is committed, before the auto-night setting is read. In Forkgram 12.10.6 the text below starts at line 4279.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                oldEditorNew.commit();
            }

            selectedAutoNightType = preferences.getInt("selectedAutoNightType", Build.VERSION.SDK_INT >= 29 ? AUTO_NIGHT_TYPE_SYSTEM : AUTO_NIGHT_TYPE_NONE);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 oldEditor.commit();
                 oldEditorNew.commit();
             }
+            applyingTheme = org.telegram.messenger.multigram.RandomStyle.onThemeInit(applyingTheme); // MultiGram: a fresh install gets its generated style before the first frame
 
             selectedAutoNightType = preferences.getInt("selectedAutoNightType", Build.VERSION.SDK_INT >= 29 ? AUTO_NIGHT_TYPE_SYSTEM : AUTO_NIGHT_TYPE_NONE);
             autoNightScheduleByLocation = preferences.getBoolean("autoNightScheduleByLocation", false);
```

**Why:** On a fresh install this creates the day and night accents from the picked entries (new ids from 101 up, no pattern), saves them without uploading, selects them and returns the day theme. The stock code then applies it, so the first frame already shows the style. On every start it also tidies its records of generated accents.

**If the code moved:** Place it inside the static initializer where all of these hold: (1) every bundled theme's accents are loaded (the loop with `String accents = themeConfig.getString("accents_" + info.assetName, null);`) and the old-accent migration is committed; (2) the local `applyingTheme` was read from the `theme` setting; (3) `selectedAutoNightType` is not read yet, and neither `currentDayTheme = applyingTheme;` nor the first `applyTheme(applyingTheme, false, false, switchToTheme == 2);` has run. If the local variable is renamed, assign the result to the new name. The check tests this order with the landmark patterns in `order(THEME, ...)` inside `check_placement()` of `random_style_check.py`. If upstream changes one of those landmark lines, the check fails although the hook is right (10.2).


##### S4. A setter for the private day theme

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme`, between `getCurrentTheme()` and `getCurrentNightTheme()`: a new one-line method and a blank line. In Forkgram 12.10.6 the text below starts at line 6448.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public static ThemeInfo getCurrentNightTheme() {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         return currentDayTheme != null ? currentDayTheme : defaultTheme;
     }
 
+    public static void setCurrentDayTheme(ThemeInfo theme) { currentDayTheme = theme; } // MultiGram: "Shuffle my style" sets the day theme while the night theme is showing
+
     public static ThemeInfo getCurrentNightTheme() {
         return currentNightTheme;
     }
```

**Why:** `currentDayTheme` is private. When Shuffle, Undo or Reset runs while the night theme is showing, MultiGram records the new day style here for the next switch to day.

**If the code moved:** Anywhere in class `Theme`. The check requires this exact line with 4 spaces of indentation. If upstream renames the field, keep the method's name and point it at the new field. Then change the old field name in two patterns of `multigram/tools/random_style_check.py`, both in "Give each install its own random style": the S4 entry in `HOOKS`, and the landmark `currentDayTheme = applyingTheme;` in `check_placement()`. Git often replays this hook without a conflict after such a rename, because the rename changes only other lines. Then only the check or the compile shows it.


##### S5. "Create new theme" refuses the generated style

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/AlertsCreator.java`

**Where:** Class `AlertsCreator`, method `createThemeCreateDialog(BaseFragment, int, Theme.ThemeInfo, Theme.ThemeAccent)`: right after the `fragment == null` check. In Forkgram 12.10.6 the text below starts at line 8296.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public static void createThemeCreateDialog(BaseFragment fragment, int type, Theme.ThemeInfo switchToTheme, Theme.ThemeAccent switchToAccent) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         if (fragment == null || fragment.getParentActivity() == null) {
             return;
         }
+        if (org.telegram.messenger.multigram.RandomStyleUi.interceptThemeCreate(fragment, switchToAccent)) return; // MultiGram: a cloud theme cannot start from the generated style
         Context context = fragment.getParentActivity();
         final EditTextBoldCursor editText = new EditTextBoldCursor(context);
         editText.setBackground(null);
```

**Why:** Creating a cloud theme would upload the accent's colours. For a generated accent the dialog is replaced by a short message that the style stays on this device.

**If the code moved:** At the start of the flow that creates a cloud theme from an accent, after the fragment check (the call shows a message on the fragment). The check requires it directly after `if (fragment == null || fragment.getParentActivity() == null) { return; }`.


##### S6. Rebuild the custom theme tile after Shuffle

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DefaultThemesPreviewCell.java`

**Where:** Class `DefaultThemesPreviewCell`, method `updateDayNightMode()`: the first statement. In Forkgram 12.10.6 the text below starts at line 352.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public void updateDayNightMode() {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     public void updateDayNightMode() {
+        org.telegram.messenger.multigram.RandomStyleUi.refreshCustomTile(adapter.items, parentFragment.getCurrentAccount()); // MultiGram: Shuffle, Undo and Reset replace the accents the custom tile points to
         if (currentType == ThemeActivity.THEME_TYPE_BASIC || currentType == TYPE_CUSTOM_LIST) {
             themeIndex = !Theme.isCurrentThemeDay() ? 2 : 0;
         } else {
```

**Why:** Chat Settings shows a strip of colour themes with a custom tile (the palette emoji). Shuffle, Undo and Reset replace the accents that tile points to; this rebuilds the tile so it never applies a deleted accent.

**If the code moved:** Call it wherever the strip refreshes after a theme change. It finds the tile by the emoji that `EmojiThemes.createPreviewCustom` sets; if upstream changes that emoji, change `RandomStyleUi.CUSTOM_TILE_EMOJI` too. The check requires it as the first line of `updateDayNightMode`.


##### S7. The accent editor marks copies of the generated style

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemePreviewActivity.java`

**Where:** Class `ThemePreviewActivity`, constructor, branch `if (screenType == SCREEN_TYPE_ACCENT_COLOR)`, right after the accent is obtained. In Forkgram 12.10.6 the text below starts at line 562.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            accent = applyingTheme.getAccent(!edit);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
 
         if (screenType == SCREEN_TYPE_ACCENT_COLOR) {
             accent = applyingTheme.getAccent(!edit);
+            org.telegram.messenger.multigram.RandomStyle.onAccentCopied(applyingTheme, accent, !edit); // MultiGram: a copy of the generated style stays on this device too
             if (accent != null) {
                 useDefaultThemeForButtons = false;
                 backupAccentColor = accent.accentColor;
```

**Why:** The accent editor either edits the current accent or creates a copy. If the source is a generated accent, the result is marked too, so it also stays on the device.

**If the code moved:** Right after the editor gets its accent and before anything can save or upload it. The check requires it on the line directly after `accent = applyingTheme.getAccent(!edit);`.


##### S8. Chat Settings: a field for the new row

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, the row index fields. In Forkgram 12.10.6 the text below starts at line 223.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    private int createNewThemeRow;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     private int editThemeRow;
     @Keep
     private int createNewThemeRow;
+    private int shuffleStyleRow = -1; // MultiGram: "Shuffle my style"
     private int lastShadowRow;
     @Keep
     private int stickersRow;
```

**Why:** The row index of "Shuffle my style". It is -1 when the row is not shown.

**If the code moved:** Any field position works. Keep the initial value -1, because only the Chat Settings branch of `updateRows` sets it.


##### S9. Chat Settings: reset the row index

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, method `updateRows(boolean)`: the block that sets every row index to -1. In Forkgram 12.10.6 the text below starts at line 607.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        createNewThemeRow = -1;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         themePreviewRow = -1;
         editThemeRow = -1;
         createNewThemeRow = -1;
+        shuffleStyleRow = -1; // MultiGram: "Shuffle my style"
 
         appIconHeaderRow = -1;
         appIconSelectorRow = -1;
```

**Why:** Resets the row every time the rows are rebuilt, so other screens that share this class never show it.

**If the code moved:** With the other `xxxRow = -1;` lines at the top of the method that counts the rows.


##### S10. Chat Settings: place the row under the colour themes

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, method `updateRows(boolean)`, branch `else if (currentType == THEME_TYPE_BASIC)` (Chat Settings), after the colour theme strip. In Forkgram 12.10.6 the text below starts at line 663.

**Find this** (its first line occurs twice in the file, the whole block once; text from Forkgram 12.10.6):

```java
            themeListRow2 = rowCount++;
            themeInfoRow = rowCount++;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             themeHeaderRow = rowCount++;
 
             themeListRow2 = rowCount++;
+            shuffleStyleRow = rowCount++; // MultiGram: under the colour themes
             themeInfoRow = rowCount++;
 
             bubbleRadiusHeaderRow = rowCount++;
```

**Why:** Shows "Shuffle my style" directly under the colour theme strip.

**If the code moved:** In the branch that builds Chat Settings (`THEME_TYPE_BASIC`), right after the row that holds the theme strip. `themeListRow2 = rowCount++;` also occurs in the themes browser branch; do not use that one. The 2-line block shown occurs once. The check requires `themeListRow2 = rowCount++;` directly followed by `shuffleStyleRow = rowCount++;`.


##### S11. Sharing refuses the generated style

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, method `didReceivedNotification(int, int, Object...)`, branch `NotificationCenter.needShareTheme`, after the `isPaused` check. In Forkgram 12.10.6 the text below starts at line 910.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        } else if (id == NotificationCenter.needShareTheme) {
            if (getParentActivity() == null || isPaused) {
                return;
            }
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             if (getParentActivity() == null || isPaused) {
                 return;
             }
+            if (org.telegram.messenger.multigram.RandomStyleUi.interceptShare(this, (Theme.ThemeAccent) args[1])) return; // MultiGram: the generated style stays on this device
             sharingTheme = (Theme.ThemeInfo) args[0];
             sharingAccent = (Theme.ThemeAccent) args[1];
             sharingProgressDialog = new AlertDialog(getParentActivity(), AlertDialog.ALERT_TYPE_SPINNER);
```

**Why:** Sharing an accent needs an upload, which S2 refuses. Without this hook a spinner would wait forever. The hook shows the "stays on this device" message instead.

**If the code moved:** At the start of the handler that begins sharing a theme or accent (the one that stores `sharingTheme` and `sharingAccent` and shows the spinner), before the spinner. `args[1]` is the accent.


##### S12. "Reset to defaults" also resets the colours

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, action bar menu handler, `} else if (id == reset_settings) {`: the last statement of the confirm button's lambda. In Forkgram 12.10.6 the text below starts at line 1041.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                                Theme.reloadWallpaper(true);
                            }
                        }
                    });
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                                 Theme.reloadWallpaper(true);
                             }
                         }
+                        org.telegram.messenger.multigram.RandomStyle.resetToGeneratedStyle(); // MultiGram: also reset the colours, to this install's generated style (the branch above needs the theme list, which Chat Settings lacks)
                     });
                     builder1.setNegativeButton(getString("Cancel", R.string.Cancel), null);
                     AlertDialog alertDialog = builder1.create();
```

**Why:** Stock "Reset to defaults" in Chat Settings resets only text size and bubble radius. This returns the colours to the install's generated style. It does nothing when the install has no generated style, or when a custom, cloud or Monet theme is involved.

**If the code moved:** Make it the last statement of the confirm handler, **outside** the `if (themesHorizontalListCell != null) { ... }` block (that cell is null in Chat Settings). K16 edits another line in the same lambda.


##### S13. A tap on the row runs Shuffle

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, method `createView(Context)`: the first statement of the list's item click listener. In Forkgram 12.10.6 the text below starts at line 1105.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        listView.setOnItemClickListener((view, position, x, y) -> {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         frameLayout.addView(listView, LayoutHelper.createFrame(LayoutHelper.MATCH_PARENT, LayoutHelper.MATCH_PARENT));
         actionBar.setAdaptiveBackground(listView);
         listView.setOnItemClickListener((view, position, x, y) -> {
+            if (position == shuffleStyleRow) { org.telegram.messenger.multigram.RandomStyleUi.shuffle(ThemeActivity.this); return; } // MultiGram: "Shuffle my style"
             if (position == enableAnimationsRow) {
                 SharedPreferences preferences = MessagesController.getGlobalMainSettings();
                 boolean animations = preferences.getBoolean("view_animations", true);
```

**Why:** A tap runs Shuffle: a new seed and style, applied at once, with an Undo message when the generated style was showing.

**If the code moved:** First statement of the click listener of ThemeActivity's main list. The check requires that position.


##### S14. Draw the row

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Inner class `ThemeActivity.ListAdapter`, method `onBindViewHolder`, `case TYPE_TEXT_PREFERENCE:`, after `cell.heightDp = 48;`. In Forkgram 12.10.6 the text below starts at line 2668.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                case TYPE_TEXT_PREFERENCE: {
                    TextCell cell = (TextCell) holder.itemView;
                    cell.heightDp = 48;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 case TYPE_TEXT_PREFERENCE: {
                     TextCell cell = (TextCell) holder.itemView;
                     cell.heightDp = 48;
+                    if (position == shuffleStyleRow) { org.telegram.messenger.multigram.RandomStyleUi.bindShuffleRow(cell); break; } // MultiGram: "Shuffle my style"
                     if (position == backgroundRow) {
                         cell.setSubtitle(null);
                         cell.setColors(Theme.key_windowBackgroundWhiteBlueText4, Theme.key_windowBackgroundWhiteBlueText4);
```

**Why:** Binds the row like "Change chat background": blue text, the dice icon `R.drawable.menu_random`, and the label `R.string.MultiGramShuffleStyle`.

**If the code moved:** In the binding of the view type that creates a `TextCell` for "Change chat background". The `break` leaves the `switch` case.


##### S15. Give the row its view type

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Inner class `ThemeActivity.ListAdapter`, method `getItemViewType(int)`: the first statement. In Forkgram 12.10.6 the text below starts at line 2732.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            if (position == scheduleFromRow || position == distanceRow ||
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
 
         @Override
         public int getItemViewType(int position) {
+            if (position == shuffleStyleRow) return TYPE_TEXT_PREFERENCE; // MultiGram: "Shuffle my style"
             if (position == scheduleFromRow || position == distanceRow ||
                     position == scheduleToRow || position == scheduleUpdateLocationRow ||
                     position == contactsReimportRow || position == contactsSortRow ||
```

**Why:** Gives the row the `TextCell` view type, so the adapter creates and binds it.

**If the code moved:** The file has two `getItemViewType(int position)` methods (in `ThemeAccentsListAdapter` and in `ListAdapter`). Use the one whose body starts with `if (position == scheduleFromRow`.


#### 8.3.4 Data

**The table file.** All numbers are big-endian. Size = 24 + 32 × themes + 40 × records.

| Part | Size | Content |
|---|---|---|
| Header | 24 bytes | magic `MGST`, version 1, header size 24, theme count, directory entry size 32, record size 40, a zero, record count, CRC-32 of everything after the header |
| Directory | 32 bytes per theme | theme key (20 bytes, UTF-8, padded with zeros), flags (bit 0 = night), first record, record count |
| Record | 40 bytes | 9 colours (accent, bubble, bubble gradient 1 to 3, wallpaper 1 to 4), rotation (a multiple of 45), flags (bit 0 animated bubble gradient, bit 1 pattern motion), a zero. Bubble gradient 2 and 3 and wallpaper 3 and 4 are 0 when unused; bubble gradient 1 equals the bubble for a plain bubble. |

The themes are, in order: Blue, Arctic Blue and Day (day), then Dark Blue and Night (night). On ff868b3ea4 the CRC-32 is `884B1657`. `StyleTable.java` accepts only this version and these sizes. A format change means changing `style_table.py`, `StyleTable.java` and `multigram/tools/README.md` together.

**The pick.** Day index = `(mix64(seed + 1 × 0x9E3779B97F4A7C15) >>> 1) % day count`, and the night index uses 2 in place of 1.

**Preferences file `rebrand_style`:** `state`, `fresh`, `seed`, `version`, `table_crc`, `day_theme`, `night_theme`, `day_style`, `night_style` (80 hex digits each), `day_index`, `night_index`, `day_accent`, `night_accent`, `generated`. The file `themeconfig` also gets `multigram_generated_accents`.

#### 8.3.5 Regenerate and verify

From the root of a checkout:

```sh
bash multigram/tools/check.sh
python3 multigram/tools/random_style_check.py --base origin/forkgram
python3 multigram/tools/check_style_table.py
python3 multigram/tools/make_style_table.py --check
```

- `random_style_check.py` prints `random-style: OK`. A failure lists each problem, then `random-style: FAILED, N problem(s)`.
- `check_style_table.py` ends with `style table check: PASS (0 failures, 0 warnings, ...)`. Lines starting with `note:` are expected.
- `make_style_table.py --check` ends with `identical to .../multigram_styles.bin`.

**When to make a new table.** Run `check.sh` after every update, once the palette fix and this unit are back:

| `check.sh` says | Meaning | What to do |
|---|---|---|
| `FAIL: <theme>: N entries are unreadable on the current theme sources` | The new sources pushed some styles below the minimum. | Make a new table. If the generator then stalls, the palette fix must change first. |
| `WARNING: <theme>: N entries lost the generator's headroom but still pass WCAG` | The styles still pass, but with less margin. | Make a new table when convenient. |
| `WARNING: make_style_table.py would now generate a different table` (exit status 3) | The theme sources changed since the table was made. CI still passes. | Make a new table when convenient. |
| `FAIL: the style table can no longer be generated on these theme sources (see STALLED above).` (exit status 4) | A colour the styles cannot move fell below its minimum. A new table cannot help. | Fix the palette first (8.2.5). |
| `... update the simulator` | The simulator cannot read the new `Theme.java` or `ThemeColors.java`. | Update `multigram/tools/sim/tgsrc.py`. |
| A Python traceback that ends in `KeyError: 'key_...'` | Upstream renamed a colour key that the simulator names. | Rename it in the simulator and the other MultiGram files (6.2, the `key_...` row). |

To make a new table (about 40 seconds on 4 cores):

```sh
python3 multigram/tools/make_style_table.py
bash multigram/tools/check.sh
```

Then fold the new `multigram_styles.bin` into "Add the style table and its generator" with a fixup (6.3). Installed phones keep the styles they stored. Only later Shuffles draw from the new table.

**Preview a new Forkgram before replaying.** This checks 64 styles per theme against the plain new snapshot (the folder `/tmp/fk-new` from step 2 of 8.2.5). It models that tree, but reads the table from this checkout:

```sh
TG_REPO=/tmp/fk-new python3 multigram/tools/check_style_table.py --sample 64
```

On Forkgram 12.10.6 it ended with `style table check: PASS (0 failures, 0 warnings, 4.5 s)`.

**On a device** (the full list is "Device test checklist" in `multigram/random-style/README.md`):

1. Fresh install (or `adb shell pm clear <applicationId>`): the first frame already shows a non-stock accent and a plain gradient wallpaper, with no flash of the Blue theme. With a dark system theme (Android 10 and later), the night style shows.
2. Chat Settings shows "Shuffle my style" under the colour themes. A tap changes the colours at once and offers Undo.
3. Menu > "Reset to defaults" brings the install's generated style back.
4. Share, or "Create new theme", on the generated accent shows the "stays on this device" message and no spinner.
5. Installing over an existing install changes nothing.
6. On a debuggable build, `adb shell run-as <applicationId> cat shared_prefs/rebrand_style.xml` shows `state` (`applied` for a fresh install, `existing` for an old one), a `seed`, and two styles of 80 hex digits.

#### 8.3.6 Gotchas

- **Order.** The palette fix must be in the tree first: `RandomStyle` uses `PaletteFix.LAST_STOCK_ACCENT_ID`, and the styles are readable only with the palette fix. The knobs (3b941c01de) come after.
- **Stage A must run before anything loads `Theme`.** `Theme` writes to `themeconfig` on every start, and any key there marks the install as existing. If upstream starts to touch `Theme` earlier, every fresh install silently gets no style. Nothing crashes, so test a fresh install on a device.
- **Stage B has three order rules** inside `Theme`'s static initializer: after all bundled accents are loaded (so new ids start at 101), before `selectedAutoNightType` is read, and before the first `applyTheme(...)`. `random_style_check.py` checks this order.
- **`ThemeActivity.java` has two lines `themeListRow2 = rowCount++;` and two `getItemViewType` methods.** The row goes in the Chat Settings branch, and the view type in `ListAdapter`'s method (S10, S15).
- **The Reset hook (S12) goes after the `if (themesHorizontalListCell != null) { ... }` block**, not inside it: that cell is null in Chat Settings.
- **Every hook is one line ending in `// MultiGram: ...`**, apart from the blank line after S4. The check's placement patterns are strict. If upstream reformats the code around a hook, update `check_placement()` in `random_style_check.py` too.
- **Never merge the binary table in a conflict.** Take either side, finish the source changes, run `make_style_table.py`, and commit its output.
- **The simulator copies Telegram's accent maths by hand.** `tgsrc.py` fails loudly when a structure it reads changes, but a change of logic inside a method passes silently. After each update, read the upstream changes to these files and look for edits inside the engine methods listed in 8.3.2:

  ```sh
  git diff $(git merge-base origin/multigram origin/forkgram) origin/forkgram -- TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java TMessagesProj/src/main/java/org/telegram/ui/ActionBar/ThemeColors.java TMessagesProj/src/main/java/org/telegram/ui/ActionBar/MessageDrawable.java TMessagesProj/src/main/java/org/telegram/messenger/AndroidUtilities.java
  ```

  The `merge-base` is the snapshot `multigram` is built on. That works until `multigram` moves to the new release. Afterwards, put `multigram-before-<version>` in place of `origin/multigram`, with the new release as `<version>`: promote puts that tag on the old tip (4.1).

- **Exit status 4 (stalled)** cannot be fixed by making a new table. Exit status 3 and the headroom warning only mean the table is older than the sources.
- **Forkgram-only dependencies:** `ThemeInfo.isMonet()`, and `forkgram/SettingsBackup.kt`, which the check reads. Never add `rebrand_style` to `ALLOWED_PREFS` or to `BackupAgent`: by design a seed must not follow the user to another device (see "Backup and settings export" in `multigram/random-style/README.md`).
- **The custom theme tile** is found by its emoji (`RandomStyleUi.CUSTOM_TILE_EMOJI`, which must equal what `EmojiThemes.createPreviewCustom` sets). If upstream changes the emoji, the refresh silently does nothing.
- **`addAccent` relies on `ThemeInfo.getAccent(true)`**: it increments `lastAccentId`, copies the current accent and sets `prevAccentId`. If upstream changes that method, re-check `addAccent`, `removeAccent` and `onAccentCopied` in `RandomStyle.java`.
- **Stage B uses the 6-argument `saveThemeAccents`**, so that no notifications fire inside the static initializer. Every call in the feature must pass `false` for upload; the check enforces it.
- **The five theme names are built into the table.** If upstream renames, adds or removes a bundled theme, the checks fail and Stage B leaves the stock style. Update `DAY_THEMES` and `NIGHT_THEMES` in `style_table.py`, and make a new table.
- **Copying `RandomStyle.java` or `RandomStyleUi.java` from the tip** brings the knob calls with it. Re-apply the knobs (8.4) too, or the build fails on `StyleKnobs`.
- **Testing the first start** needs a fresh install or cleared data. An update over an old build only tests the "existing" path. An Android backup restore counts as a fresh install.
- **The simulator's cache** (`multigram/tools/sim/cache/`) is keyed by the source files. If you change `tgsrc.py`'s parsing, raise `PARSER_VERSION` or delete the cache folder.

### 8.4 Style knobs and CI self-test (3b941c01de and 4780eb095b)

#### 8.4.1 What and why

Commit **3b941c01de** adds `StyleKnobs`. It uses the install's seed from the random style to pick shapes and a chat list layout, using only options the app already has. Each knob gets its own random numbers from `RandomStyle.deriveSeed(seed, "<knob name>")`, so adding a knob never changes the others. The values are stored in the preferences file `rebrand_style_knobs` together with the seed. So an app update never restyles an install; only a new seed (Shuffle or Undo) derives them again.

Installs without a seed keep every stock value, because each hook returns the stock value it is given. Two knobs are real Forkgram settings (`bubbleRadius` and `useThreeLinesLayout`). They are written only while they still hold the stock value or the value `StyleKnobs` last wrote, so a user's own choice is never overwritten.

Commit **4780eb095b** adds the rebrand self-test to `check.sh`. A Forkgram release that moves what the rebrand generator changes then fails the sync's compile job, instead of breaking the next rebrand.

#### 8.4.2 New files

| Path | Purpose | Upstream names it relies on |
|---|---|---|
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/StyleKnobs.java` | The whole feature: derives, stores and loads the knob values, writes the two settings, and holds the functions the hooks call. None of them throws, and each returns the stock value when there is no seed. | `SharedConfig.bubbleRadius`, `useThreeLinesLayout`, `fontSize`, `setUseThreeLinesLayout(boolean)`; the `mainconfig` keys `bubbleRadius`, `useThreeLinesLayout`, `fons_size`; `AndroidUtilities.dp(float)`; `Theme.createSimpleSelectorCircleDrawable` and `createSimpleSelectorRoundRectDrawable`; `RandomStyle.hasSeed()`, `getSeed()`, `deriveSeed(long, String)` |
| `multigram/style-knobs/README.md` | Design document: the knobs, why each range is safe, the lifecycle, the hooks, and a 10-item device checklist. | Documentation only |
| `multigram/tools/style_knobs_check.py` | Checks every knob hook (exact text, count, marker, full class name), that the stock lines are gone, the placement, and that `StyleKnobs` writes only its own settings and stays in safe ranges. Prints `style-knobs: OK`. | The paths of the 10 hooked files; the exact stock arguments and indentation of each hooked line; `public void onCreate() {` and `NativeLoader.initNativeLibs(` in `ApplicationLoader`; `reloadWallpaper` and `previousPhase = 0;` in `Theme`; `} else if (id == reset_settings) {` in `ThemeActivity` |

3b941c01de also changes MultiGram's own `RandomStyle.java` and `RandomStyleUi.java` (hooks K18 to K22), `check.sh` (K23), `multigram/random-style/README.md` and `multigram/tools/README.md`. 4780eb095b changes only `check.sh` (K24).

#### 8.4.3 Hooks

K1 to K17 are in upstream files. K18 to K24 are in MultiGram's own files. Section 7 copies those files from each commit, so there their lines are already in place. Use the K18 to K24 blocks to review a file, or to rebuild one by hand.

##### K1. Start: derive and apply this install's knobs

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/ApplicationLoader.java`

**Where:** Class `ApplicationLoader`, method `onCreate()`: directly below S1.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```java
        org.telegram.messenger.multigram.RandomStyle.onApplicationCreate(applicationContext); // MultiGram: per-install style seed, before anything touches Theme
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             applicationContext = getApplicationContext();
         }
         org.telegram.messenger.multigram.RandomStyle.onApplicationCreate(applicationContext); // MultiGram: per-install style seed, before anything touches Theme
+        org.telegram.messenger.multigram.StyleKnobs.onApplicationCreate(applicationContext); // MultiGram: per-install shapes and chat list layout, before SharedConfig and Theme read them
 
         NativeLoader.initNativeLibs(ApplicationLoader.applicationContext);
 
```

**Why:** Runs on every start. Installs without a seed return at once. Otherwise it loads (or, on a fresh install, derives) the knob values, writes the bubble radius and chat list layout settings where they still hold MultiGram's or the stock value, and copies them into `SharedConfig`. On tablets `SharedConfig` is loaded before this point, so the copy is needed there.

**If the code moved:** Early in `Application.onCreate`, after `applicationContext` is set and after S1 (which creates the seed), before `Theme` or anything that draws. `style_knobs_check.py` requires it on the line directly after S1 and before `NativeLoader.initNativeLibs(`.

**On plain Telegram (DrKLO):** Applies only on top of S1, because S1's line is its context.


##### K2. Wallpaper gradient starts at this install's phase

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ActionBar/Theme.java`

**Where:** Class `Theme`, method `reloadWallpaper(boolean async)`: after the `if/else` that takes `previousPhase` from the old wallpaper, before `wallpaper = null;`. In Forkgram 12.10.6 the text below starts at line 9268.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            previousPhase = ((MotionBackgroundDrawable) wallpaper).getPhase();
        } else {
            previousPhase = 0;
        }
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         } else {
             previousPhase = 0;
         }
+        previousPhase = org.telegram.messenger.multigram.StyleKnobs.wallpaperPhase(previousPhase, wallpaper instanceof MotionBackgroundDrawable); // MultiGram: the gradient starts at this install's phase, not always at 0
         wallpaper = null;
         themedWallpaper = null;
         loadWallpaper(async);
```

**Why:** The generated gradient starts at the install's phase (0 to 7) when there is no old gradient to continue: the first load after start, and once after Shuffle, Undo or Reset. Otherwise the stock behaviour stays, so sending messages still turns the gradient.

**If the code moved:** Find where the new wallpaper's starting phase is taken from the old wallpaper (`previousPhase`, later passed to `setPhase` in `loadWallpaper`). The hook must see the **old** wallpaper, so it goes before `wallpaper = null`. It belongs in `reloadWallpaper`, not `loadWallpaper`: `LaunchActivity` calls `loadWallpaper` directly, and that returns early when a wallpaper is already loaded.


##### K3. Service pill: outer and inner corners

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Cells/ChatActionCell.java`

**Where:** Class `ChatActionCell`, method `drawBackground(Canvas, boolean)`, inside `if (invalidatePath) {`, where the path around service and date pills is built. In Forkgram 12.10.6 the text below starts at line 3341.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            final int corner = dp(11);
            final int cornerIn = dp(8);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             backgroundRight = 0;
             lineWidths.clear();
             final int count = textLayout == null ? 0 : textLayout.getLineCount();
-            final int corner = dp(11);
-            final int cornerIn = dp(8);
+            final int corner = org.telegram.messenger.multigram.StyleKnobs.servicePillRadius(dp(11)); // MultiGram: pill corners follow this install's bubble radius
+            final int cornerIn = org.telegram.messenger.multigram.StyleKnobs.servicePillRadius(dp(8)); // MultiGram: scaled with the corner
 
             int prevLineWidth = 0;
             for (int a = 0; a < count; a++) {
```

**Why:** Pill corners follow the install's bubble radius: about 0.65 of it, between 4 and 11 dp, never above stock, so pills never cross themselves. It follows the live slider value, but only on installs with a seed.

**If the code moved:** Find the code that builds the rounded path around service messages and date pills (outer corner 11 dp, inner corners 8 and 6 dp, offset 3 dp). Wrap each corner constant in `servicePillRadius(stock)` and keep K4 in step.


##### K4. Service pill: keep the stock side padding

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Cells/ChatActionCell.java`

**Where:** Same method and block as K3, just before `final int cornerRest = corner - cornerOffset;`. In Forkgram 12.10.6 the text below starts at line 3370.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            final int cornerOffset = dp(3);
            final int cornerInSmall = dp(6);
            final int cornerRest = corner - cornerOffset;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             int x = getMeasuredWidth() / 2;
             int previousLineBottom = 0;
 
-            final int cornerOffset = dp(3);
-            final int cornerInSmall = dp(6);
+            final int cornerOffset = org.telegram.messenger.multigram.StyleKnobs.servicePillCornerOffset(dp(3), corner, dp(11)); // MultiGram: keeps the stock side padding (corner - cornerOffset) when the corner is smaller
+            final int cornerInSmall = org.telegram.messenger.multigram.StyleKnobs.servicePillRadius(dp(6)); // MultiGram: scaled with the corner
             final int cornerRest = corner - cornerOffset;
 
             lineHeights.clear();
```

**Why:** The pill's side padding is `corner - cornerOffset` (8 dp in stock). The new offset keeps that padding when the corner is smaller, so the pill keeps its stock size. A negative offset (corner under 8 dp) is intended.

**If the code moved:** Change the offset together with the corner. Changing only the corner makes the text touch the pill's edge.


##### K5. Floating button: shadow follows the shape

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/FragmentFloatingButton.java`

**Where:** Class `FragmentFloatingButton`, constructor, `if (!isSubButton)` block. In Forkgram 12.10.6 the text below starts at line 73.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            setOutlineProvider(ViewOutlineProviderImpl.BOUNDS_OVAL);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
 
         ScaleStateListAnimator.apply(this);
         if (!isSubButton) {
-            setOutlineProvider(ViewOutlineProviderImpl.BOUNDS_OVAL);
+            setOutlineProvider(android.view.ViewOutlineProvider.BACKGROUND); // MultiGram: the shadow follows the background, a circle or this install's rounded square (stock: BOUNDS_OVAL)
             setTranslationZ(dpf2(0.5f));
         }
 
```

**Why:** The shadow follows the background: a circle (as in stock) or the install's rounded square.

**If the code moved:** Wherever the main chat list button sets its outline, make the outline follow the background. The `ViewOutlineProviderImpl` import becomes unused; leave it.


##### K6. Floating button: the small button above it

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/FragmentFloatingButton.java`

**Where:** Class `FragmentFloatingButton`, method `updateColors()`, branch `if (isSubButton)`. In Forkgram 12.10.6 the text below starts at line 160.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            int rad = dp(18);
            int pressedColor = Theme.getColor(Theme.key_listSelector, resourcesProvider);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             invalidate();
 
-            int rad = dp(18);
+            int rad = org.telegram.messenger.multigram.StyleKnobs.floatingSubButtonRadius(dp(18)); // MultiGram: same shape as the main button
+            iBlur3Background.setRadius(rad); // MultiGram: the constructor's dp(18), updated after a Shuffle
             int pressedColor = Theme.getColor(Theme.key_listSelector, resourcesProvider);
             setBackground(Theme.createInsetRoundRectDrawable(pressedColor, rad, dp(6)));
```

**Why:** The small button gets the main button's shape, scaled by 36/48. Its blurred background (radius set once in the constructor) is updated here, so a Shuffle changes it without rebuilding the view.

**If the code moved:** Apply the same radius to the selector and to `iBlur3Background`, somewhere that runs again on a theme change. It relies on `BlurredBackgroundDrawable.setRadius(float)`.


##### K7. Floating button: circle or rounded square

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/FragmentFloatingButton.java`

**Where:** Class `FragmentFloatingButton`, method `updateColors()`, the `else` branch (main button). In Forkgram 12.10.6 the text below starts at line 166.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            setBackground(Theme.createSimpleSelectorCircleDrawable(dp(48),
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             imageView.setColorFilter(Theme.getColor(Theme.key_chats_actionIcon, resourcesProvider), PorterDuff.Mode.SRC_IN);
             progressView.setProgressColor(Theme.getColor(Theme.key_chats_actionIcon, resourcesProvider));
-            setBackground(Theme.createSimpleSelectorCircleDrawable(dp(48),
+            setBackground(org.telegram.messenger.multigram.StyleKnobs.floatingButtonBackground(dp(48), // MultiGram: a circle or this install's rounded square (stock: Theme.createSimpleSelectorCircleDrawable)
                 Theme.getColor(Theme.key_featuredStickers_addButton, resourcesProvider),
                 Theme.getColor(Theme.key_featuredStickers_addButtonPressed, resourcesProvider)
```

**Why:** Returns the stock circle or a rounded square (14, 16 or 18 dp) with the same colours. It runs on every theme update, so Shuffle changes it at once.

**If the code moved:** Find where the main floating button's round background is created (a 48 dp circle with `key_featuredStickers_addButton`) and route it through `floatingButtonBackground(size, color, pressedColor)`.


##### K8. Premium gradient button keeps 8 dp corners

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/Premium/boosts/GradientButtonWithCounterView.java`

**Where:** Class `GradientButtonWithCounterView`, constructor: the last statement. In Forkgram 12.10.6 the text below starts at line 28.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        flickerDrawable.repeatProgress = 4f;
    }
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         flickerDrawable.animationSpeedScale = 1.2f;
         flickerDrawable.drawFrame = false;
         flickerDrawable.repeatProgress = 4f;
+        setRoundRadius(8); // MultiGram: stock 8dp corners, which the gradient and shimmer below are drawn with (StyleKnobs.ctaRadiusDp would change only the background and ripple)
     }
 
     @Override
```

**Why:** This button draws its gradient and shimmer with a fixed 8 dp corner. Without this line its inherited background (K13) would not match the gradient.

**If the code moved:** Any subclass of `ButtonWithCounterView` that draws its own shape at a fixed radius needs `setRoundRadius(<that radius>)` at the end of its constructor. Check with `git grep -n 'extends ButtonWithCounterView'`. Today: `FoundStickerPackButton` calls `setRound()` and is fine; `UpdateReactionsButton` draws nothing of its own; `StickerCutOutBtn` keeps its own 8 dp selector while its loading shimmer follows the knob (not handled; check on a device).


##### K9. Reactions: particle clip

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/Reactions/ReactionsLayoutInBubble.java`

**Where:** Inner class `ReactionsLayoutInBubble.ReactionButton`, method `drawOverlay(...)`: the particle clip. In Forkgram 12.10.6 the text below starts at line 997.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            AndroidUtilities.rectTmp.set(x, y, x + width, y + height);
            float rad = height / 2f;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             if (!LiteMode.isEnabled(LiteMode.FLAG_ANIMATED_EMOJI_REACTIONS) || !LiteMode.isEnabled(LiteMode.FLAG_PARTICLES)) return false;
 
             AndroidUtilities.rectTmp.set(x, y, x + width, y + height);
-            float rad = height / 2f;
+            float rad = org.telegram.messenger.multigram.StyleKnobs.reactionChipRadius(height / 2f); // MultiGram: pill or this install's rounded chip
 
             particles.bounds.set(AndroidUtilities.rectTmp);
             particles.bounds.inset(-dp(4), -dp(4));
```

**Why:** Selection particles are clipped to the same chip shape as K10 draws.

**If the code moved:** The line `float rad = height / 2f;` occurs twice in the file. This one follows `rectTmp.set(x, y, x + width, y + height)`. Both must use the same radius.


##### K10. Reactions: chip shape

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/Reactions/ReactionsLayoutInBubble.java`

**Where:** Inner class `ReactionsLayoutInBubble.ReactionButton`, method `draw(...)`: the chip background. In Forkgram 12.10.6 the text below starts at line 1109.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                canvas.scale(bounceScale, bounceScale, x + w / 2f, y + height / 2f);
            }
            float rad = height / 2f;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 canvas.save();
                 canvas.scale(bounceScale, bounceScale, x + w / 2f, y + height / 2f);
             }
-            float rad = height / 2f;
+            float rad = org.telegram.messenger.multigram.StyleKnobs.reactionChipRadius(height / 2f); // MultiGram: pill or this install's rounded chip
             if (getDrawServiceShaderBackground() > 0 && !drawBgOnlyIfChosen) {
                 Paint paint1 = Theme.getThemePaint(Theme.key_paint_chatActionBackground, resourcesProvider);
                 Paint paint2 = Theme.getThemePaint(Theme.key_paint_chatActionBackgroundDarken, resourcesProvider);
```

**Why:** Returns the stock pill radius, or a rounded chip of about 0.6 of the bubble radius (6 to 10 dp). Saved-message tags keep their notched shape.

**If the code moved:** Find where the reaction chip under messages gets its corner radius (stock: half its height) and wrap it in `reactionChipRadius(stock)`.


##### K11. Settings cards: corner radius (RecyclerListView)

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/RecyclerListView.java`

**Where:** Class `RecyclerListView`, the default overloads `setSections()` and `setSections(boolean topPadding)`. In Forkgram 12.10.6 the text below starts at line 3309.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public void setSections() {
        setSections(dp(12), dp(16), false);
    }
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     public void setSections() {
-        setSections(dp(12), dp(16), false);
+        setSections(dp(12), org.telegram.messenger.multigram.StyleKnobs.sectionRadius(dp(16)), false); // MultiGram: this install's card corners
     }
     public void setSections(boolean topPadding) {
-        setSections(dp(12), dp(16), topPadding);
+        setSections(dp(12), org.telegram.messenger.multigram.StyleKnobs.sectionRadius(dp(16)), topPadding); // MultiGram: this install's card corners
     }
     public void setSections(int padding, float roundRadius, boolean topPadding) {
         setSections(
```

**Why:** Sets the default corner radius of settings cards to 12, 14, 16 or 20 dp (stock 16). A screen reads it when it builds its list, so after a Shuffle each screen changes the next time it opens.

**If the code moved:** Wrap the default card radius in `sectionRadius(stock)`. Calls that pass their own radius are left alone (there are none today). Find new copies with `git grep -n 'setSections(dp(12), dp(16)'`.


##### K12. Settings cards: corner radius (UniversalRecyclerView)

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Components/UniversalRecyclerView.java`

**Where:** Class `UniversalRecyclerView`, its own copies of the two default `setSections` overloads. In Forkgram 12.10.6 the text below starts at line 430.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public void setSections() {
        setSections(dp(12), dp(16), false);
    }
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     public void setSections() {
-        setSections(dp(12), dp(16), false);
+        setSections(dp(12), org.telegram.messenger.multigram.StyleKnobs.sectionRadius(dp(16)), false); // MultiGram: this install's card corners, as in RecyclerListView
     }
     public void setSections(boolean topPadding) {
-        setSections(dp(12), dp(16), topPadding);
+        setSections(dp(12), org.telegram.messenger.multigram.StyleKnobs.sectionRadius(dp(16)), topPadding); // MultiGram: this install's card corners, as in RecyclerListView
     }
     public void setSections(int padding, float roundRadius, boolean topPadding) {
         super.setSections(
```

**Why:** `UniversalRecyclerView` repeats both default overloads with its own `dp(16)`. It is used by the main Settings screen, Forkgram's settings and others, so hooking `RecyclerListView` alone is not enough.

**If the code moved:** Every class that repeats the default overloads with a fixed radius needs the same change. `git grep -n 'setSections(dp(12), dp(16)'` should print nothing on a finished tree.


##### K13. Buttons: default corner radius

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Stories/recorder/ButtonWithCounterView.java`

**Where:** Class `ButtonWithCounterView`, the field `radiusDp`. In Forkgram 12.10.6 the text below starts at line 44.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    private int radiusDp = 8;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
 
     private Theme.ResourcesProvider resourcesProvider;
 
-    private int radiusDp = 8;
+    private int radiusDp = org.telegram.messenger.multigram.StyleKnobs.ctaRadiusDp(8); // MultiGram: this install's button corners (explicit setRoundRadius/setRound still win)
 
     private final Paint paint;
     public final AnimatedTextView.AnimatedTextDrawable text;
```

**Why:** The default corner radius of the filled buttons in sheets and many screens: 50, 75 or 100 % of the bubble radius, between 6 and 12 dp. Buttons that call `setRound()` or `setRoundRadius(n)` keep their values.

**If the code moved:** Find the default corner radius of this shared button. It must stay a field initialiser (or be set before the constructor's first `setBackground`), so the constructor's background uses it too.


##### K14. Buttons: the constructor uses the field

**File:** `TMessagesProj/src/main/java/org/telegram/ui/Stories/recorder/ButtonWithCounterView.java`

**Where:** Class `ButtonWithCounterView`, constructor, `if (filled)`. In Forkgram 12.10.6 the text below starts at line 115.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            setBackground(Theme.createRoundRectDrawable(dp(8), backgroundColor = Theme.getColor(Theme.key_featuredStickers_addButton, resourcesProvider)));
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         addView(rippleView, LayoutHelper.createFrame(LayoutHelper.MATCH_PARENT, LayoutHelper.MATCH_PARENT));
 
         if (filled) {
-            setBackground(Theme.createRoundRectDrawable(dp(8), backgroundColor = Theme.getColor(Theme.key_featuredStickers_addButton, resourcesProvider)));
+            setBackground(Theme.createRoundRectDrawable(dp(radiusDp), backgroundColor = Theme.getColor(Theme.key_featuredStickers_addButton, resourcesProvider))); // MultiGram: radiusDp (stock: dp(8), the same default)
         }
 
         paint = new Paint(Paint.ANTI_ALIAS_FLAG);
```

**Why:** The constructor had a fixed `dp(8)` instead of the field. Using `radiusDp` makes the first background match the ripple and loading shimmer. Stock behaviour is the same, because the stock default is 8.

**If the code moved:** Any place in this class that draws the default shape with a literal 8 instead of `radiusDp` needs the same change.


##### K15. Chat Settings: rebind the rows the knobs change

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`: a new public one-line method (and a blank line) before `setBubbleRadius(int, boolean)`. In Forkgram 12.10.6 the text below starts at line 463.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    private boolean setBubbleRadius(int size, boolean layout) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         updateRows(true);
     }
 
+    public void refreshStyleKnobRows() { if (listAdapter != null) { for (int row : new int[] {textSizeRow, bubbleRadiusRow, chatListRow}) { if (row >= 0) listAdapter.notifyItemChanged(row); } } } // MultiGram: Shuffle and Undo change the bubble radius and chat list layout these rows show (StyleKnobs); the rebind updates their cells (onBindViewHolder)
+
     private boolean setBubbleRadius(int size, boolean layout) {
         if (size != SharedConfig.bubbleRadius) {
             SharedConfig.bubbleRadius = size;
```

**Why:** After Shuffle and Undo, `RandomStyleUi` calls this. It asks the list to rebind the text size preview, the message corners slider and the chat list picker, so they show the new radius and layout.

**If the code moved:** It must be public (it is called from another package). It relies on the fields `textSizeRow`, `bubbleRadiusRow`, `chatListRow` and `listAdapter`. Place it anywhere in the outer class; the check wants the one-line form.


##### K16. "Reset to defaults" uses this install's radius

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Class `ThemeActivity`, the `reset_settings` confirm lambda (the same lambda as S12). In Forkgram 12.10.6 the text below starts at line 1013.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                        if (setBubbleRadius(17, true)) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                         if (setFontSize(AndroidUtilities.isTablet() ? 18 : 16)) {
                             changed = true;
                         }
-                        if (setBubbleRadius(17, true)) {
+                        if (setBubbleRadius(org.telegram.messenger.multigram.StyleKnobs.resetBubbleRadius(17), true)) { // MultiGram: this install's radius, not always 17
                             changed = true;
                         }
                         if (changed) {
```

**Why:** Reset returns the bubble radius to the install's value instead of 17, and marks it as MultiGram's again. With no seed it returns 17.

**If the code moved:** Find the Chat Settings reset of the bubble radius to 17 and pass 17 through `resetBubbleRadius`. The check requires it inside the `} else if (id == reset_settings) {` branch.


##### K17. Chat Settings: bind the three knob rows

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ThemeActivity.java`

**Where:** Inner class `ThemeActivity.ListAdapter`, method `onBindViewHolder(RecyclerView.ViewHolder, int)`: the first case of the `switch`. In Forkgram 12.10.6 the text below starts at line 2471.

**Find this** (its first line occurs twice in the file, the whole block once; text from Forkgram 12.10.6):

```java
        public void onBindViewHolder(RecyclerView.ViewHolder holder, int position) {
            switch (holder.getItemViewType()) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         @Override
         public void onBindViewHolder(RecyclerView.ViewHolder holder, int position) {
             switch (holder.getItemViewType()) {
+                case TYPE_TEXT_SIZE: case TYPE_BUBBLE_RADIUS: case TYPE_CHAT_LIST: org.telegram.messenger.multigram.RandomStyleUi.bindStyleKnobRow(holder.itemView); break; // MultiGram: these cells read the bubble radius and chat list layout only when created or measured; Shuffle and Undo change them (StyleKnobs)
                 case TYPE_TEXT_SETTING: {
                     TextSettingsCell cell = (TextSettingsCell) holder.itemView;
                     if (position == nightThemeRow) {
```

**Why:** In stock these three view types are never bound: their cells read the settings only when created or measured. This brings a visible cell up to date after Shuffle or Undo.

**If the code moved:** `TYPE_TEXT_SIZE`, `TYPE_BUBBLE_RADIUS` and `TYPE_CHAT_LIST` are private to `ListAdapter`, so the line must be inside `ListAdapter`. The file has two `onBindViewHolder` methods; the 2-line block shown occurs once. If a future version adds its own `case` for one of these types, call `bindStyleKnobRow` from that case instead: duplicate case labels do not compile.


##### K18. RandomStyle.shuffle: apply the knobs before the switch

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyle.java`

**Where:** MultiGram's own file. Method `shuffle(Context)`, just before `show(pair);`.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```java
            undo = previous;
            show(pair);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 previous.shuffledSeed = seed;
             }
             undo = previous;
+            StyleKnobs.onStyleApplying(seed); // before the theme switch, which reloads the wallpaper at once
             show(pair);
             notifyListeners(seed, REASON_SHUFFLE);
             return true;
```

**Why:** Derives every knob from the new seed and applies the two settings before the theme switch. The switch reloads the wallpaper at once, so K2 must already see the new phase.

The commit also adds two lines to the class description at the top of the file, after the list item that ends in `(stock Chat Settings only resets text size and bubble radius).</li>`:

```diff
+ *   <li>{@link StyleKnobs} (shapes and chat list layout from the same seed) is updated right before Shuffle, Undo and
+ *       Reset show the style, because the theme switch reloads the wallpaper synchronously; listeners run after.</li>
```

**If the code moved:** Keep the call directly before `show(pair);`; `style_knobs_check.py` checks it. A `RandomStyle.Listener` would be too late, because listeners run after `show`.


##### K19. RandomStyle.undoShuffle: same

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyle.java`

**Where:** MultiGram's own file. Method `undoShuffle()`, just before `show(pair);`.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```java
            putPair(editor, pair).commit();
            show(pair);
            notifyListeners(u.seed, REASON_UNDO);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             putStyle(editor, DAY, u.day, u.dayIndex);
             putStyle(editor, NIGHT, u.night, u.nightIndex);
             putPair(editor, pair).commit();
+            StyleKnobs.onStyleApplying(u.seed);
             show(pair);
             notifyListeners(u.seed, REASON_UNDO);
             return true;
```

**Why:** Undo restores the previous seed, and the knobs follow it.

**If the code moved:** Directly before `show(pair);`, with the restored seed `u.seed`.


##### K20. RandomStyle.resetToGeneratedStyle: same

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyle.java`

**Where:** MultiGram's own file. Method `resetToGeneratedStyle()`, just before `show(pair);`.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```java
            putPair(p.edit(), pair).commit();
            show(pair);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 return false;
             }
             putPair(p.edit(), pair).commit();
+            StyleKnobs.onStyleApplying(p.getLong(KEY_SEED, 0));
             show(pair);
             notifyListeners(p.getLong(KEY_SEED, 0), REASON_RESET);
             return true;
```

**Why:** Reset keeps the seed; this applies the two settings again and restarts the wallpaper at the install's phase.

**If the code moved:** Directly before `show(pair);`, with `p.getLong(KEY_SEED, 0)`.


##### K21. RandomStyleUi: imports

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyleUi.java`

**Where:** MultiGram's own file. The import block.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```java
import android.os.SystemClock;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
 package org.telegram.messenger.multigram;
 
 import android.os.SystemClock;
+import android.view.View;
+import android.view.ViewGroup;
 
 import org.telegram.messenger.ApplicationLoader;
 import org.telegram.messenger.FileLog;
+import org.telegram.messenger.MessageObject;
 import org.telegram.messenger.R;
+import org.telegram.messenger.SharedConfig;
 import org.telegram.messenger.Utilities;
 import org.telegram.ui.ActionBar.BaseFragment;
 import org.telegram.ui.ActionBar.EmojiThemes;
 import org.telegram.ui.ActionBar.Theme;
+import org.telegram.ui.Cells.ChatListCell;
+import org.telegram.ui.Cells.ChatMessageCell;
 import org.telegram.ui.Cells.TextCell;
+import org.telegram.ui.Cells.ThemePreviewMessagesCell;
 import org.telegram.ui.Components.BulletinFactory;
 import org.telegram.ui.Components.ChatThemeBottomSheet;
+import org.telegram.ui.Components.RadioButton;
 import org.telegram.ui.DialogsActivity;
+import org.telegram.ui.ThemeActivity;
 
+import java.util.ArrayList;
 import java.util.List;
 
 /**
```

**Why:** Imports for K22.

**If the code moved:** MultiGram's own file: copy it from the commit. The upstream classes these imports name are listed in K22.


##### K22. RandomStyleUi: refresh after Shuffle and Undo, and the bind helper

**File:** `TMessagesProj/src/main/java/org/telegram/messenger/multigram/RandomStyleUi.java`

**Where:** MultiGram's own file. Method `shuffle(BaseFragment)` (two calls), and three new methods before the javadoc of the `DefaultThemesPreviewCell.updateDayNightMode` hook.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```java
        if (fragment != null && RandomStyle.canUndoShuffle()) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             }
             return;
         }
+        refreshStyleKnobRows(fragment);
         if (fragment != null && RandomStyle.canUndoShuffle()) {
             BulletinFactory.of(fragment).createUndoBulletin(str(R.string.MultiGramStyleShuffled), () -> {
                 if (!RandomStyle.undoShuffle()) {
                     BulletinFactory.of(fragment).createErrorBulletin(str(R.string.MultiGramUndoFailed)).show();
+                } else {
+                    refreshStyleKnobRows(fragment);
                 }
             }, null).show();
         }
     }
 
+    /**
+     * Shuffle and Undo may change the bubble radius and the chat list layout ({@link StyleKnobs}); Chat Settings
+     * rebinds the rows that show them ({@link #bindStyleKnobRow}).
+     */
+    private static void refreshStyleKnobRows(BaseFragment fragment) {
+        try {
+            if (fragment instanceof ThemeActivity) {
+                ((ThemeActivity) fragment).refreshStyleKnobRows();
+            }
+        } catch (Throwable e) {
+            FileLog.e(e);
+        }
+    }
+
+    /**
+     * ThemeActivity.ListAdapter.onBindViewHolder hook for the text size preview, the message corners slider and the
+     * chat list picker. Their cells read the bubble radius and chat list layout only when created (the picker's
+     * radio buttons) or measured (the slider's position, the preview's bubbles), and binding them does nothing in
+     * stock, so after Shuffle or Undo ({@link ThemeActivity#refreshStyleKnobRows}) a visible row, or one kept
+     * off screen, would still show the old values. This brings the cell in line with SharedConfig the way the
+     * stock slider does: the preview messages are laid out again, the cell is measured again, and the picker's
+     * radio buttons are re-checked. A cell never laid out was just created from the current values and is left
+     * alone, and so is every cell while the install has no style knobs. Never throws.
+     */
+    public static void bindStyleKnobRow(View itemView) {
+        try {
+            if (itemView == null || !StyleKnobs.isActive() || itemView.getWidth() == 0) {
+                return;
+            }
+            if (itemView instanceof ChatListCell) {
+                // Its two options in order (two lines, three lines), each with one radio button; a button animates
+                // only while attached, and does nothing when it already shows the value.
+                List<RadioButton> buttons = new ArrayList<>();
+                collect(itemView, RadioButton.class, buttons);
+                if (buttons.size() == 2) {
+                    buttons.get(0).setChecked(!SharedConfig.useThreeLinesLayout, true);
+                    buttons.get(1).setChecked(SharedConfig.useThreeLinesLayout, true);
+                }
+            } else {
+                List<ThemePreviewMessagesCell> previews = new ArrayList<>();
+                collect(itemView, ThemePreviewMessagesCell.class, previews);
+                for (ThemePreviewMessagesCell preview : previews) {
+                    ChatMessageCell[] cells = preview.getCells();
+                    for (int i = 0; cells != null && i < cells.length; i++) {
+                        MessageObject message = cells[i] == null ? null : cells[i].getMessageObject();
+                        if (message != null) {
+                            message.resetLayout();
+                            cells[i].requestLayout();
+                        }
+                    }
+                }
+                itemView.requestLayout(); // the corners slider takes its position from SharedConfig in onMeasure
+            }
+            itemView.invalidate();
+        } catch (Throwable e) {
+            FileLog.e(e);
+        }
+    }
+
+    /** Adds view and its descendants that are instances of type to out, depth first. */
+    private static <T> void collect(View view, Class<T> type, List<T> out) {
+        if (type.isInstance(view)) {
+            out.add(type.cast(view));
+        }
+        if (view instanceof ViewGroup) {
+            ViewGroup group = (ViewGroup) view;
+            for (int i = 0; i < group.getChildCount(); i++) {
+                collect(group.getChildAt(i), type, out);
+            }
+        }
+    }
+
     /**
      * DefaultThemesPreviewCell.updateDayNightMode hook. The custom tile of Chat Settings' theme strip is built once,
      * from themeconfig's lastDay/DarkCustomTheme(AccentId), but Shuffle, Undo and Reset replace the accents it points
```

**Why:** After Shuffle, and after a successful Undo, Chat Settings rebinds its three knob rows (K15). `bindStyleKnobRow` is the body of K17: it re-checks the chat list picker's radio buttons, lays the preview messages out again and re-measures the slider.

**If the code moved:** MultiGram's own file. The check requires exactly two `refreshStyleKnobRows(fragment);` calls. Upstream names it relies on: `ThemeActivity.refreshStyleKnobRows` (K15), `BaseFragment`, `ChatListCell` (two options, one `RadioButton` each, in the order two lines, three lines), `RadioButton.setChecked(boolean, boolean)`, `ThemePreviewMessagesCell.getCells()`, `ChatMessageCell.getMessageObject()`, `MessageObject.resetLayout()`, and the slider cell reading `SharedConfig.bubbleRadius` in `onMeasure`. If `ChatListCell` gains a third option, the `buttons.size() == 2` guard makes this do nothing; adjust it.


##### K23. check.sh: run the knobs check

**File:** `multigram/tools/check.sh`

**Where:** MultiGram's own file. After the random style block.

**Find this** (it occurs once in the file; text from the file as commit 27d32d57b4 left it):

```sh
  python3 multigram/tools/random_style_check.py
fi
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
   python3 multigram/tools/random_style_check.py
 fi
 
+if [ -f multigram/tools/style_knobs_check.py ]; then
+  # Per-install shapes and chat list layout: hooks and their placement, owned settings only, safe ranges.
+  echo "== style knobs: hooks, owned settings and safe ranges"
+  python3 multigram/tools/style_knobs_check.py
+fi
+
 echo "== style table: format and readability on the current theme sources"
 python3 multigram/tools/check_style_table.py
 
```

**Why:** CI runs `style_knobs_check.py` on every build and every sync candidate.

**If the code moved:** Order does not matter. The `[ -f ... ]` guard lets older trees without the file pass.


##### K24. check.sh: run the rebrand self-test (commit 4780eb095b)

**File:** `multigram/tools/check.sh`

**Where:** MultiGram's own file. After the style knobs block, before the style table checks.

**Find this** (it occurs once in the file; text from the file as commit 3b941c01de left it):

```sh
  python3 multigram/tools/style_knobs_check.py
fi
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
   python3 multigram/tools/style_knobs_check.py
 fi
 
+if [ -f multigram/rebrand/selftest.py ]; then
+  # Rebrand toolkit: generate two identities on a scratch copy, check the output, then --clean back to the commit.
+  echo "== rebrand toolkit: self-test"
+  python3 multigram/rebrand/selftest.py
+fi
+
 echo "== style table: format and readability on the current theme sources"
 python3 multigram/tools/check_style_table.py
 
```

**Why:** Runs the rebrand self-test in CI. A Forkgram release that moves what the rebrand generator changes (the account type code, app name strings, launcher, splash or notification icons) then fails the sync's compile job, instead of breaking the next rebrand.

**If the code moved:** Order does not matter. The self-test copies part of the tree to a throwaway folder in the system temp folder and removes it afterwards. It needs `git`; `keytool` is optional.


#### 8.4.4 Data

The knob tables are Java constants in `StyleKnobs.java`. "r" is the bubble radius in dp.

| Knob (its name in `StyleKnobs.java`) | Values | Stock | What it drives | Hooks |
|---|---|---|---|---|
| `bubble-radius` | 8, 10, 12, 14, 17 dp | 17 | Setting `bubbleRadius` (Chat Settings > Message corners). "Reset to defaults" returns to it. | K1, K16, K18–K20 |
| `chat-list-density` | three lines in 2 of 5 cases, only when the screen's long side is at least 640 dp and the font size is below 19 | two lines | Setting `useThreeLinesLayout` (Chat Settings > chat list view) | K1, K18–K20 |
| (none: follows the live `bubbleRadius`) | outer corner round(r × 0.65), between 4 and 11 dp | 11 dp | Service and date pills | K3, K4 |
| `reaction-chip-shape` | pill, or rounded: round(r × 0.6), between 6 and 10 dp | pill | Reaction chips under messages | K9, K10 |
| `cta-button-radius` | 50, 75 or 100 % of r, between 6 and 12 dp | 8 dp | Default corners of filled buttons | K8, K13, K14 |
| `fab-shape` | circle (3 of 6 cases), or a rounded square of 14, 16 or 18 dp | circle | Chat list floating button, its shadow, and the small button above it (× 36/48) | K5–K7 |
| `settings-cards` | 12, 14, 16, 20 dp | 16 dp | Default corners of settings cards | K11, K12 |
| `wallpaper-phase` | 0 to 7 | continues the old phase | Where the generated wallpaper gradient starts | K2 |

**Preferences file `rebrand_style_knobs`:** `seed`, `version` (1), `bubble_radius`, `three_lines`, `reaction_pill`, `cta_scale`, `fab_radius`, `section_radius`, `wallpaper_phase`, and `set_bubble_radius` and `set_three_lines` (the values `StyleKnobs` last wrote).

#### 8.4.5 Regenerate and verify

Nothing is generated in this unit. To verify, from the root of a checkout:

```sh
python3 multigram/tools/style_knobs_check.py
python3 multigram/tools/style_knobs_check.py --base origin/forkgram
bash multigram/tools/check.sh
```

- Both checks print `style-knobs: OK`. With `--base`, every non-blank line added to the 10 hooked files must carry `MultiGram:`.
- A failure lists each problem, then `style-knobs: FAILED, N problem(s)`. For example, with K3's first line put back to stock: `style-knobs: TMessagesProj/src/main/java/org/telegram/ui/Cells/ChatActionCell.java: stock line 'final int corner = dp\\(11\\);' is back (the hook must replace it)`. Patterns are printed as Python strings, so each backslash shows doubled.
- `check.sh` runs the knobs check and the rebrand self-test, and ends with `== all MultiGram checks passed`. On ff868b3ea4 it took 1 minute 13 seconds on 4 cores.

**On a device** (the full list is "Device test checklist" in `multigram/style-knobs/README.md`). Knobs work only on installs with a seed: a fresh install, or an old install after "Shuffle my style".

1. `adb shell run-as <applicationId> cat shared_prefs/rebrand_style_knobs.xml` (debuggable build) shows the keys above.
2. From the first frame, on a phone and on a tablet, Chat Settings shows the install's corner radius and chat list layout.
3. With a small radius, pills have smaller corners but the stock size. Reactions are pills or rounded chips, with particles inside. Sheet buttons have 6 to 12 dp corners. The floating button is a circle or a rounded square, with a matching shadow. Settings cards have the install's corners. The wallpaper gradient starts at the same phase on every start.
4. Shuffle, then Undo: the preview, slider and chat list picker update at once. Move the slider, then Shuffle: your value stays. "Reset to defaults" brings back the install's radius, not 17.
5. Avatars keep Forkgram's own shape setting.

#### 8.4.6 Gotchas

- **Apply this unit after 27d32d57b4.** K1's context is S1's line, so K1 does not apply on plain Forkgram.
- **Keep every upstream hook one line**, with the full class name `org.telegram.messenger.multigram.StyleKnobs.` and the exact `// MultiGram: ` marker, at the stock indentation. The check matches these exactly, including leading spaces and stock arguments. The now unused import `ViewOutlineProviderImpl` in `FragmentFloatingButton.java` stays on purpose.
- **Start order.** `StyleKnobs.onApplicationCreate` must come after `RandomStyle.onApplicationCreate` and before anything draws. On tablets, `SharedConfig` is already loaded at that point, so `StyleKnobs` copies the two values into it. Without that copy, tablets show stock values until the next start.
- **K2 must read the old wallpaper,** so it goes before `wallpaper = null`, and in `reloadWallpaper`, not `loadWallpaper`.
- **K3 and K4 go together.** The pill's side padding is corner minus offset. Changing only the corner puts the text against the edge.
- **`ReactionsLayoutInBubble.java` has two identical lines `float rad = height / 2f;`.** Hook both (K9, K10).
- **`ButtonWithCounterView` needs both K13 and K14.** Subclasses that draw a fixed radius must opt out, as `GradientButtonWithCounterView` does (K8). Today: `FoundStickerPackButton` calls `setRound()` and is fine; `UpdateReactionsButton` draws nothing of its own; `StickerCutOutBtn` keeps its own 8 dp selector while its loading shimmer follows the knob (not handled; check it on a device). After an update, run `git grep -n 'extends ButtonWithCounterView'`.
- **`UniversalRecyclerView` repeats the `setSections` overloads.** Hooking only `RecyclerListView` misses the main Settings screen.
- **K17 must stay inside `ListAdapter`**, because the three view types are private to it. If upstream adds its own `case` for one of them, call `bindStyleKnobRow` from there instead: duplicate case labels do not compile. `refreshStyleKnobRows` (K15) must be public.
- **K18 to K20 must come right before `show(pair);`.** The theme switch reloads the wallpaper at once, so a listener would be too late.
- **Never rename a knob name** (the `KNOB_*` constants): that re-rolls the knob for every new seed. Keep the tables inside the check's ranges.
- **Nothing changes on an existing install until it presses Shuffle.** Test on a fresh install.
- **Never add Forkgram's avatar settings** (`avatarCorners`, `squareAvatars`) to the knobs. The check fails on them.
- **The rebrand self-test in `check.sh`** takes about a third of the script's time (about 26 seconds on 4 cores; `make_style_table.py --check` takes the most, about 30 seconds). It writes a temporary folder in the system temp folder (and removes it), and skips the signing checks without `keytool`.

### 8.5 Hide chat list search (ff868b3ea4)

#### 8.5.1 What and why

Commit **ff868b3ea4** adds the option "Hide chat list search". It is a switch in **Fork Client Settings > Chat list view**, right after Forkgram's "Disable Global Search", and it is off by default.

When it is on, the chat list has no search bar (the 48 dp field under the header) and no search icon in the header. Stock Telegram shows that icon once the bar has scrolled away; with the option on it never shows. The list is laid out as stock lays it out when the bar has scrolled away, minus the room the bar keeps, so the first chat sits right under the header or the folder tabs. This applies to the main chat list with its folders, the Archive, community lists, and the plain list that `BackButtonMenu` opens. The owner chose this "no search" variant. The other design, the "search icon" variant, hid only the bar; `multigram/hide-search-bar/README.md` says how to go back to it.

Some ways into search stay on purpose, because the user asks for each of them. They are left stock, and each shows the field in the header while searching:

- the Downloads item in the header (it shows while files download, or while there are downloads you have not looked at);
- `tg://search?query=...` links;
- the search icon of the forum topics column (a forum opened beside the chat list).

The music player's search by performer (a tap on the performer's name) is also left stock. From Chats it opens its own search screen, with the stock bar. From an open Archive or community list, or the list `BackButtonMenu` opens, it shows the field in that list's header. With 10 chats or fewer it does nothing, as in stock.

Dialog pickers (forward, share and the like) and `#hashtag` screens keep their stock bar. With the option on, three things are lost:

- the header icon's long-press shortcut to Saved Messages;
- the usual way from the chat list into Forkgram's hidden-account unlock (tap search, type the code). The unlock still works from any of the searches above;
- with Forkgram's option Hide the "All Chats" tab also on, that option's promise that chats outside folders "stay reachable through search and the archive". The chat list then offers no search to reach them.

When the option is off, every hook returns the stock value it replaced, so the chat list is exactly stock.

How it works. Each chat list reads the setting once, at first use, and keeps that value while it is on screen. When the list resumes (for example on the way back from Fork settings), hook H13 reads the setting again. If it changed, `HideSearchBar.refresh` first keeps each list's first chat in place, and then the list switches and redraws its header.

The upstream changes are 21 one-line hooks: 19 in `DialogsActivity.java` (H1 to H18, H21) and 2 in `ForkSettingsActivity.java` (H19, H20). 13 of them (H1 to H4, H6 to H10, H14 to H17) only put `HideSearchBar.restHeight(...)` around `SEARCH_FIELD_HEIGHT` inside the stock `dp(...)`.

#### 8.5.2 New files

| Path | Purpose | Upstream names it relies on |
|---|---|---|
| `TMessagesProj/src/main/java/org/telegram/messenger/multigram/HideSearchBar.java` | The whole feature. `hides(f)` says whether a list hides the bar and the icon. `restHeight(f, stock)` and `restAlpha(f, stock)` return `stock` while the option is off and 0 while it is on. `refresh(f, pages)` applies a changed setting in `onResume` (H13). `settingsRow()` and `onSettingsClick(item, view)` are the settings row (H19, H20). Each list keeps its value and its scope in a `WeakHashMap` keyed by the fragment. | `DialogsActivity.ViewPage` and its field `listView` (both public), `DialogsActivity.getType()`, `isMainDialogList()`, `DIALOGS_TYPE_DEFAULT`, the fragment argument `onlySelect`; `BaseFragment.getArguments()` and `getFragmentView()`; androidx `LinearLayoutManager` (`hasPendingScrollPosition`, `findFirstVisibleItemPosition`, `findViewByPosition`, `scrollToPositionWithOffset`); `UItem.asButtonCheck(int, CharSequence, CharSequence)`, `setChecked`, `setMultiline` (Forkgram only), the fields `id` and `checked`; `TextCheckCell.setChecked`, `NotificationsCheckCell.setChecked`; `MessagesController.getGlobalMainSettings()` (`mainconfig`); `ApplicationLoader.applicationContext`; `FileLog.e(Throwable)` |
| `multigram/hide-search-bar/README.md` | Design document: scope, what still opens search, what is lost, the lifecycle, the setting, the hook table (hooks 1 to 21 are H1 to H21 here), what was not done, a 14-item device checklist and known limitations. | Documentation only. It names upstream line numbers of `4780eb095b`. |
| `multigram/tools/hide_search_bar_check.py` | Checks the 21 hooks (exact text, indentation, count, marker), where each one sits, that the ways into search left stock still open search, that every other line of `DialogsActivity.java` that uses `SEARCH_FIELD_HEIGHT` is on a reviewed list, and that `HideSearchBar` writes one setting only. `--base REV` also requires the `MultiGram:` marker on every line the stack adds to the two hooked files. Prints `hide-search-bar: OK`. | In `DialogsActivity.java`: the 12 reviewed lines that use `SEARCH_FIELD_HEIGHT` (`REVIEWED`: 11 texts, because `childTop += dp(SEARCH_FIELD_HEIGHT);` occurs twice), the method signatures of the hooked methods, the stock line next to each hook, the icon's click listener, the Downloads item (`id == 3`) and `search(String query, boolean animated)`. In `ForkSettingsActivity.java`: `fillSettings`, `onClick`, the `ID_...` and `MENU_SEARCH` ids. `TopicsFragment.java` (`parentDialogsActivity.searchItem.performClick();`), `Components/FragmentSearchField.java`, and `forkgram/SettingsBackup.kt` with its `ALLOWED_PREFS` (Forkgram only, like `ForkSettingsActivity.java`). The check stops with `FileNotFoundError` if any file it reads is missing. |

ff868b3ea4 also adds two strings to `multigram_strings.xml` (8.5.4), a block to `check.sh` (H22), and three lines about the check to `multigram/tools/README.md`.

#### 8.5.3 Hooks

H1 to H21 are in upstream files. Their numbers are the numbers of the hook table in `multigram/hide-search-bar/README.md` and of `H` in `hide_search_bar_check.py`. So H21, the header icon, comes after the two settings hooks, although it is in `DialogsActivity.java`. H22 is in MultiGram's own `check.sh`. Section 7 copies that file from the commit, so there its lines are already in place.

The line numbers below are Forkgram's. The README's table uses the numbers of `4780eb095b`. There, lines of `DialogsActivity.java` after line 3512 are one higher (hook R2 adds a line), and so are lines of `ForkSettingsActivity.java` after line 547 (hook R3).

##### H1. Header: no room for a hidden bar

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `ContentView`, method `getActionBarFullHeight()`: the last line before `return (int) h;`. In Forkgram 12.10.6 the text below starts at line 881.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
            h += dp(SEARCH_FIELD_HEIGHT) * (1f - progressToActionMode) * (1f - searchAnimationProgress) * (1f - rightSlidingProgress);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 h += storiesHeight * (1f - searchAnimationProgress) * (1f - rightSlidingProgress) * (1f - progressToActionMode);
             }
             h += storiesOverscroll;
-            h += dp(SEARCH_FIELD_HEIGHT) * (1f - progressToActionMode) * (1f - searchAnimationProgress) * (1f - rightSlidingProgress);
+            h += dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)) * (1f - progressToActionMode) * (1f - searchAnimationProgress) * (1f - rightSlidingProgress); // MultiGram: no header band behind a hidden bar
 
             return (int) h;
         }
```

**Why:** This is the full height of the header: the action bar, the stories and the bar. The header background, the list's clip, the header shadow, the top of the topics column and the swipe area all follow it. `restHeight` returns `SEARCH_FIELD_HEIGHT` while the option is off, so the line is stock then. While it is on, it returns 0, and `dp(0)` is 0.

**If the code moved:** Find where the header height adds `dp(SEARCH_FIELD_HEIGHT)`, multiplied by the action mode, search and topics column factors. Put `org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)` in place of `SEARCH_FIELD_HEIGHT` inside the `dp(...)`, and leave the rest of the line as upstream has it. `hide_search_bar_check.py` requires the hook directly after `h += storiesOverscroll;` in `getActionBarFullHeight`.


##### H2. Action mode: lift the tabs by the visible header only

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `ContentView`, method `dispatchDraw(Canvas)`: the first argument of `tabsYOffset -= Math.min(`. In Forkgram 12.10.6 the text below starts at line 1059.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(SEARCH_FIELD_HEIGHT) + scrollYOffset,
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays). H2 and H3 are next to each other, so git shows them in one hunk, with both `-` lines first. The first `-` line and the first `+` line are H2:

```diff
             tabsYOffset = 0;
             storiesYOffset = 0;
             tabsYOffset -= Math.min(
-                dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(SEARCH_FIELD_HEIGHT) + scrollYOffset,
-                progressToActionMode * (dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(SEARCH_FIELD_HEIGHT))
+                dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)) + scrollYOffset, // MultiGram: action mode lifts the tabs by the visible header only
+                progressToActionMode * (dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT))) // MultiGram: same, for the full lift
             );
             storiesYOffset = tabsYOffset;
             if ((rightSlidingDialogContainer != null && rightSlidingDialogContainer.hasFragment())) {
```

**Why:** When chats are selected (action mode), the folder tabs move up over the stories and the bar, but never by more than the header shows. With the bar hidden there is no bar to cover, so the tabs move up by the stories only.

**If the code moved:** These are the two arguments of the `Math.min` that lifts `tabsYOffset` by `progressToActionMode`. Change `SEARCH_FIELD_HEIGHT` inside `dp(...)` in both, as the block shows. The check requires H2 and H3 directly after `tabsYOffset -= Math.min(`, in this order.


##### H3. Action mode: the same, for the full lift

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Same `Math.min(` as H2: its second argument, on the line below H2. In Forkgram 12.10.6 the text below starts at line 1060.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                progressToActionMode * (dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(SEARCH_FIELD_HEIGHT))
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added). H2's block shows this change with its context. H3 alone:

```diff
-                progressToActionMode * (dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(SEARCH_FIELD_HEIGHT))
+                progressToActionMode * (dp(hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT))) // MultiGram: same, for the full lift
```

**Why:** The lift as the action mode animation runs (`progressToActionMode` goes from 0 to 1). It must use the same height as H2.

**If the code moved:** See H2.


##### H4. Topics column: move the list up only by the header it covers

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `ContentView`, method `dispatchDraw(Canvas)`, in the branch `if ((rightSlidingDialogContainer != null && rightSlidingDialogContainer.hasFragment()))`: the line before `addH *= rightSlidingDialogContainer.openedProgress;`. In Forkgram 12.10.6 the text below starts at line 1086.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                addH += dp(SEARCH_FIELD_HEIGHT);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 if (hasStories) {
                     addH += dp(DialogStoriesCell.HEIGHT_IN_DP);
                 }
-                addH += dp(SEARCH_FIELD_HEIGHT);
+                addH += dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)); // MultiGram: the topics column moves the list up only by the header it covers
                 addH *= rightSlidingDialogContainer.openedProgress;
 
                 viewPages[0].setTranslationY(rightFragmentOffset - addH);
```

**Why:** When a forum opens in the topics column beside the list, the chat list moves up under the header by the stories and the bar. With the bar hidden it moves up by the stories only.

**If the code moved:** H4, H6 and H8 must use the same height: H4 moves the list up as the column opens, H6 measures the list taller by that amount, and H8 gives it back when the column closes. The check requires H4 directly before `addH *= rightSlidingDialogContainer.openedProgress;`.


##### H5. Search field: slide in from where a scrolled-away bar sits

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `ContentView`, method `dispatchDraw(Canvas)`, the `else` branch after H4: the first argument (the start) of the `lerp` that places `fragmentSearchField` while search opens. In Forkgram 12.10.6 the text below starts at line 1093.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                        scrollYOffset + tabsYOffset + storiesOverscroll - dp(4),
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             } else {
                 if (fragmentSearchField != null) {
                     fragmentSearchField.setTranslationY(lerp(
-                        scrollYOffset + tabsYOffset + storiesOverscroll - dp(4),
+                        scrollYOffset + tabsYOffset + storiesOverscroll - dp(4) - dp(SEARCH_FIELD_HEIGHT - org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)), // MultiGram: a hidden bar fades in where a scrolled-away stock bar does
                         -dp(SEARCH_FIELD_HEIGHT + (hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0)),
                         searchAnimationProgress
                     ));
```

**Why:** When search opens another way (Downloads, a link, the topics column's icon), the field slides from its place at rest up to the header row. With the bar hidden, it starts 48 dp higher, where a scrolled-away stock bar sits, so it fades in near its final place. While the option is off the new term is `dp(SEARCH_FIELD_HEIGHT - SEARCH_FIELD_HEIGHT)`, which is 0. The end of the slide (`-dp(SEARCH_FIELD_HEIGHT + ...)`, the next line) stays stock.

**If the code moved:** This is the start value of the field's slide into search. Subtract `dp(SEARCH_FIELD_HEIGHT - restHeight(...))` from it. The check requires the hook directly followed by the stock `-dp(SEARCH_FIELD_HEIGHT + (hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0)),` and then `searchAnimationProgress`.


##### H6. Topics column: measure the page taller by the same amount

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `ContentView`, method `onMeasure(int, int)`, branch `child instanceof ViewPage`, inside `if (rightSlidingDialogContainer.hasFragment())`: the last line, after the stories block. In Forkgram 12.10.6 the text below starts at line 1185.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                        h += dp(SEARCH_FIELD_HEIGHT);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                         if (hasStories) {
                             h += dp(DialogStoriesCell.HEIGHT_IN_DP);
                         }
-                        h += dp(SEARCH_FIELD_HEIGHT);
+                        h += dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)); // MultiGram: page measured taller by that same amount
                     }
                     h += actionModeAdditionalHeight;
                     if (actionBarColorAnimator == null) {
```

**Why:** With the topics column open, the chat list page is measured taller by the height H4 moves it up.

**If the code moved:** Same height as H4 and H8. The check requires the hook as the last statement of that `if`, right after `if (hasStories) { h += dp(DialogStoriesCell.HEIGHT_IN_DP); }` and before `h += actionModeAdditionalHeight;`.


##### H7. List padding: the first chat starts right under the header

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `DialogsRecyclerView`, method `onMeasure(int, int)`: inside `if (!actionModeFullyShowed) {`, after the stories padding. In Forkgram 12.10.6 the text below starts at line 2079.

**Find this** (without its indentation, the second line also matches the end of H8's line `offset += dp(SEARCH_FIELD_HEIGHT);`; the block as shown occurs once; text from Forkgram 12.10.6):

```java
            if (!actionModeFullyShowed) {
                t += dp(SEARCH_FIELD_HEIGHT);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 t += dp(DialogStoriesCell.HEIGHT_IN_DP);
             }
             if (!actionModeFullyShowed) {
-                t += dp(SEARCH_FIELD_HEIGHT);
+                t += dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)); // MultiGram: the first chat starts right under the header
             }
             additionalPadding = 0;
 
```

**Why:** This is the list's top padding, the room above the first chat. It is the hook that takes the bar's room away: with the bar hidden, the first chat starts right under the header or the folder tabs.

**If the code moved:** Find the padding the chat list keeps for the bar, next to the padding for the stories. The check requires the hook directly after `if (!actionModeFullyShowed) {`.


##### H8. Topics column: closing it gives back only the header it took

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Inner class `DialogsRecyclerView`, method `setAnimationSupportView(RecyclerListView, float, boolean, boolean)`: inside `if (backward) {`. In Forkgram 12.10.6 the text below starts at line 2368.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                        offset += dp(SEARCH_FIELD_HEIGHT);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                         offset += dp(DialogStoriesCell.HEIGHT_IN_DP);
                     }
                     if (backward) {
-                        offset += dp(SEARCH_FIELD_HEIGHT);
+                        offset += dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)); // MultiGram: closing the topics column gives back only the header it took
                         // offset += canShowFilterTabsView ? dp(50) : 0;
                     }
                     if (p >= 0) {
```

**Why:** When the topics column closes, the list scrolls back by the stories and the bar it lost. With the bar hidden, by the stories only.

**If the code moved:** Same height as H4 and H6. The check requires the hook directly after `if (backward) {`.


##### H9. Fling: stop at the first chat

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Method `createView(Context)`, the `LinearLayoutManager` each page gets (`viewPage.layoutManager = new LinearLayoutManager(context) {`), method `scrollVerticallyBy(int, RecyclerView.Recycler, RecyclerView.State)`: the `if` right after `int canScrollDy = -(view.getTop() - pTop) + viewsH;`. In Forkgram 12.10.6 the text below starts at line 4225.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                                    canScrollDy -= dp(SEARCH_FIELD_HEIGHT);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                                 }
                                 int canScrollDy = -(view.getTop() - pTop) + viewsH;
                                 if (!rightSlidingDialogContainer.hasFragment() && !(actionBar != null && actionBar.isActionModeShowed())) {
-                                    canScrollDy -= dp(SEARCH_FIELD_HEIGHT);
+                                    canScrollDy -= dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)); // MultiGram: a fling stops at the first chat, not past a hidden bar
                                 }
                                 if (hasStories && (viewPage.scroller.isRunning() || dialogStoriesCell.isExpanded()) && !rightSlidingDialogContainer.hasFragment() && !fixScrollYAfterArchiveOpened) {
                                     canScrollDy += dp(DialogStoriesCell.HEIGHT_IN_DP);
```

**Why:** When a fling towards the top would show a hidden Archive row, stock limits it so that it stops at the first chat. That limit takes off the bar's height. With the bar hidden it takes off nothing, so the fling still stops at the first chat, not past a bar that is not there, and the Archive stays hidden.

**If the code moved:** H9 and H10 must use the same height. The check requires H9 as the only statement of the stock `if` directly after `int canScrollDy = ...`.


##### H10. Fling: the pair of H9

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Same method as H9: the `if ((viewPage.scroller.isRunning() || dialogStoriesCell.isExpanded()) && ...)` right before `int positiveDy = Math.abs(dy);`. In Forkgram 12.10.6 the text below starts at line 4231.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                                    canScrollDy += dp(SEARCH_FIELD_HEIGHT);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                                     canScrollDy += dp(DialogStoriesCell.HEIGHT_IN_DP);
                                 }
                                 if ((viewPage.scroller.isRunning() || dialogStoriesCell.isExpanded()) && !rightSlidingDialogContainer.hasFragment() && !fixScrollYAfterArchiveOpened && !(actionBar != null && actionBar.isActionModeShowed())) {
-                                    canScrollDy += dp(SEARCH_FIELD_HEIGHT);
+                                    canScrollDy += dp(org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)); // MultiGram: pairs with the line above
                                 }
                                 int positiveDy = Math.abs(dy);
                                 if (canScrollDy < positiveDy) {
```

**Why:** While the stories scroll or are expanded, stock adds the bar's height back. It must be the height H9 takes away.

**If the code moved:** The check requires H10 as the only statement of that stock `if`, directly before `int positiveDy = Math.abs(dy);`.


##### H11. The header collapses by the stories only

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `getMaxScrollYOffset()`: a new first statement. In Forkgram 12.10.6 the text below starts at line 5742.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    private int getMaxScrollYOffset() {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     private int getMaxScrollYOffset() {
+        if (org.telegram.messenger.multigram.HideSearchBar.hides(this)) return getMaxScrollYOffsetWithoutSearch(); // MultiGram: the header collapses by the stories only
         if (hasStories) {
             return dp(DialogStoriesCell.HEIGHT_IN_DP) + dp(SEARCH_FIELD_HEIGHT);
         } else {
```

**Why:** This is how far the header can scroll away: in stock, the stories plus the bar. With the bar hidden, only the stories, which is stock's own `getMaxScrollYOffsetWithoutSearch()`. Without stories that is 0, so the header never moves. It also keeps stock's "snap the bar" code from running.

**If the code moved:** The first statement of the method that returns the header's maximum scroll. The check requires exactly that.


##### H12. Tabs and top panels take the bar's place

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `updateContextViewPosition()`: right after `totalOffset += storiesOverscroll;`. In Forkgram 12.10.6 the text below starts at line 6583.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        totalOffset += storiesOverscroll;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                     searchTabsHeight * searchAnimationProgress + tabsYOffset;
         }
         totalOffset += storiesOverscroll;
+        if (org.telegram.messenger.multigram.HideSearchBar.hides(this)) totalOffset -= dp(SEARCH_FIELD_HEIGHT) * (1f - searchAnimationProgress); // MultiGram: tabs and top panels take the bar's place at rest (their layout top in ContentView.onLayout still counts it)
 
         float searchVisibility = 0;
         if (fragmentSearchField != null && fragmentSearchField.getVisibility() == View.VISIBLE) {
```

**Why:** `ContentView.onLayout` places the folder tabs and the top panels (proxy, requests, suggestions) below the bar's place (`childTop += dp(SEARCH_FIELD_HEIGHT);`). That line is not hooked, because it also places the top panel in search mode. This hook moves them up by the bar's height at rest, and by nothing once search is open, so they sit right under the header.

**If the code moved:** The check requires the hook directly after `totalOffset += storiesOverscroll;`, and before `float fadeViewT = totalOffset;` and `filterTabsView.setTranslationY(` in the same method.


##### H13. Apply a changed setting when the list comes back

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `onResume()`: right after `super.onResume();`. In Forkgram 12.10.6 the text below starts at line 7084.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    public void onResume() {
        super.onResume();
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     @Override
     public void onResume() {
         super.onResume();
+        if (org.telegram.messenger.multigram.HideSearchBar.refresh(this, viewPages)) { setScrollY(Math.max(scrollYOffset, -getMaxScrollYOffset())); invalidateScrollY = true; checkUi_searchFieldVisibility(); checkUi_menuItems(); } // MultiGram: "Hide chat list search" changed while this list was paused: re-derive its header
         if (dialogStoriesCell != null) {
             dialogStoriesCell.onResume();
         }
```

**Why:** A list reads the setting at first use and keeps it while it is on screen. On resume, `HideSearchBar.refresh` reads it again. If this list's value changed, it keeps each page's first chat in place relative to the new padding, switches, and returns `true`. The line then limits the header's scroll to the new maximum, lets the next draw derive the scroll again (`invalidateScrollY`), and updates the field and the header icons. `checkUi_menuItems()` reaches H21, so the icon follows at once. When nothing changed, `refresh` returns `false` and changes nothing.

**If the code moved:** It must run before the loop in `onResume` that calls `notifyDataSetChanged()` on each page. After that call, stock skips its own re-anchoring of the list, and turning the option on would show 48 dp of a hidden Archive row (turning it off would leave the list 48 dp scrolled). The check requires the hook directly after `super.onResume();` and before `.notifyDataSetChanged()`.


##### H14. Leaving action mode: give back only the header it took

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `hideActionMode(boolean)`: right before `float finalTranslateListHeight = translateListHeight;`. In Forkgram 12.10.6 the text below starts at line 9109.

**Find this** (the first line's text also occurs, indented deeper, at H16; the whole block occurs once; text from Forkgram 12.10.6):

```java
        translateListHeight = Math.max(0, dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) + scrollYOffset);
        float finalTranslateListHeight = translateListHeight;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 viewPages[i].listView.cancelClickRunnables(true);
             }
         }
-        translateListHeight = Math.max(0, dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) + scrollYOffset);
+        translateListHeight = Math.max(0, dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)) + scrollYOffset); // MultiGram: leaving action mode gives back only the header it took
         float finalTranslateListHeight = translateListHeight;
         actionBarColorAnimator = ValueAnimator.ofFloat(progressToActionMode, 0);
         actionBarColorAnimator.addUpdateListener(valueAnimator -> {
```

**Why:** How far the list moves back down as action mode ends. H14 to H17 must use the same height; together they keep entering and leaving action mode free of jumps.

**If the code moved:** H14 and H15 stay in `hideActionMode`. The check requires H14 directly before `float finalTranslateListHeight = translateListHeight;`.


##### H15. Leaving action mode: the pair of H14

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Method `hideActionMode(boolean)`, in `onAnimationEnd(Animator)` of the animator's listener: right before `viewPages[0].setTranslationY(0);`. In Forkgram 12.10.6 the text below starts at line 9135.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                scrollAdditionalOffset = -(dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) - finalTranslateListHeight);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                 invalidateScrollY = true;
                 fixScrollYAfterArchiveOpened = true;
                 fragmentView.invalidate();
-                scrollAdditionalOffset = -(dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) - finalTranslateListHeight);
+                scrollAdditionalOffset = -(dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)) - finalTranslateListHeight); // MultiGram: pairs with translateListHeight
                 viewPages[0].setTranslationY(0);
                 for (int i = 0; i < viewPages.length; i++) {
                     if (viewPages[i] != null) {
```

**Why:** The scroll correction at the end of the animation. It must match H14.

**If the code moved:** The check requires H15 inside `hideActionMode`, directly before `viewPages[0].setTranslationY(0);`.


##### H16. Entering action mode: lift the list by the visible header only

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `showOrUpdateActionMode(long, View)`: right before `if (translateListHeight != 0) {`. In Forkgram 12.10.6 the text below starts at line 10238.

**Find this** (the first line's text also occurs, indented less, at H14; the whole block occurs once; text from Forkgram 12.10.6):

```java
            translateListHeight = Math.max(0, dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) + scrollYOffset);
            if (translateListHeight != 0) {
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                     viewPages[i].listView.cancelClickRunnables(true);
                 }
             }
-            translateListHeight = Math.max(0, dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) + scrollYOffset);
+            translateListHeight = Math.max(0, dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)) + scrollYOffset); // MultiGram: action mode lifts the list by the visible header only
             if (translateListHeight != 0) {
                 actionModeAdditionalHeight = (int) translateListHeight;
                 fragmentView.requestLayout();
```

**Why:** How far the list moves up as chats are selected. It matches H2 and H3, which move the tabs.

**If the code moved:** H16 and H17 stay in `showOrUpdateActionMode`. The check requires H16 directly before `if (translateListHeight != 0) {`.


##### H17. Entering action mode: the pair of H16

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Method `showOrUpdateActionMode(long, View)`, in `onAnimationEnd(Animator)` of the animator's listener: right before `viewPages[0].setTranslationY(0);`. In Forkgram 12.10.6 the text below starts at line 10265.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
                    scrollAdditionalOffset = dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) - finalTranslateListHeight;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
                     actionBarColorAnimator = null;
                     actionModeAdditionalHeight = 0;
                     actionModeFullyShowed = true;
-                    scrollAdditionalOffset = dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + SEARCH_FIELD_HEIGHT) - finalTranslateListHeight;
+                    scrollAdditionalOffset = dp((hasStories ? DialogStoriesCell.HEIGHT_IN_DP : 0) + org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)) - finalTranslateListHeight; // MultiGram: pairs with translateListHeight
                     viewPages[0].setTranslationY(0);
                     for (int i = 0; i < viewPages.length; i++) {
                         if (viewPages[i] != null) {
```

**Why:** The scroll correction at the end of the animation. It must match H16.

**If the code moved:** The check requires H17 inside `showOrUpdateActionMode`, directly before `viewPages[0].setTranslationY(0);`.


##### H18. No bar at rest

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `checkUi_searchFieldVisibility()`: the line that sets `alphaByScrollOffset`. In Forkgram 12.10.6 the text below starts at line 14235.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        final float alphaByScrollOffset = 1f - MathUtils.clamp((-scrollYOffset - maxScrollWithoutSearch) / dp(SEARCH_FIELD_HEIGHT), 0, 1);
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
         }
 
         final int maxScrollWithoutSearch = getMaxScrollYOffsetWithoutSearch();
-        final float alphaByScrollOffset = 1f - MathUtils.clamp((-scrollYOffset - maxScrollWithoutSearch) / dp(SEARCH_FIELD_HEIGHT), 0, 1);
+        final float alphaByScrollOffset = org.telegram.messenger.multigram.HideSearchBar.restAlpha(this, 1f - MathUtils.clamp((-scrollYOffset - maxScrollWithoutSearch) / dp(SEARCH_FIELD_HEIGHT), 0, 1)); // MultiGram: no bar at rest; the field shows only while searching
 
         final float actionModeVisible = Math.max(progressToActionMode, animatorActionModeVisible.getFloatValue());
         final float searchFieldVisible = animatorSearchVisible.getFloatValue();
```

**Why:** This method is the only code that sets the field's alpha and visibility. `restAlpha` keeps the stock value while the option is off. While it is on, the bar's alpha from scrolling is 0, so the field shows only while searching (`animatorSearchVisible` then keeps it visible). The method's last line would then show the header icon, as stock does once the bar has scrolled away. H21 stops that.

**If the code moved:** Wrap the whole stock value of `alphaByScrollOffset` in `org.telegram.messenger.multigram.HideSearchBar.restAlpha(this, ...)`. The check requires the hook in `checkUi_searchFieldVisibility`, together with the stock `fragmentSearchField.setVisibility(alpha > 0 ? View.VISIBLE : View.GONE);` and `animatorSearchButtonVisible.setValue(alpha <= 0.01f, true);`, and with that method's own `factor0` line left stock (see H21).


##### H19. Fork Client Settings: the row

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ForkSettingsActivity.java`

**Where:** Class `ForkSettingsActivity`, method `fillSettings(ArrayList<UItem>)`, section "Chat list view": right after the "Disable Global Search" row. In Forkgram 12.10.6 the text below starts at line 576.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
        items.add(UItem.asButtonCheck(ID_DISABLE_GLOBAL_SEARCH, LocaleController.getString(R.string.DisableGlobalSearch), LocaleController.getString(R.string.DisableGlobalSearchInfo))
            .setChecked(pref("disableGlobalSearch", false)).setMultiline(true));
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
             .setChecked(pref("disableThumbsInDialogList", false)).setMultiline(true));
         items.add(UItem.asButtonCheck(ID_DISABLE_GLOBAL_SEARCH, LocaleController.getString(R.string.DisableGlobalSearch), LocaleController.getString(R.string.DisableGlobalSearchInfo))
             .setChecked(pref("disableGlobalSearch", false)).setMultiline(true));
+        items.add(org.telegram.messenger.multigram.HideSearchBar.settingsRow()); // MultiGram: "Hide chat list search" row, right after Disable Global Search
         items.add(UItem.asButtonCheck(ID_HIDE_CONTACTS_IN_DIALOGS, LocaleController.getString(R.string.HideContactsInDialogs), LocaleController.getString(R.string.HideContactsInDialogsInfo))
             .setChecked(pref("hideContactsInDialogs", false)).setMultiline(true));
         items.add(UItem.asButtonCheck(ID_ENABLE_LAST_SEEN_DOTS, LocaleController.getString(R.string.EnableLastSeenDots), LocaleController.getString(R.string.EnableLastSeenDotsInfo))
```

**Why:** Adds the row "Hide chat list search" with its info line. `settingsRow()` builds it the way Forkgram builds its own Chat list rows, with id 9101.

**If the code moved:** Keep the row right after the Disable Global Search row. If that row moves or goes, put it in the same section. The check requires the hook in `fillSettings`, directly after `.setChecked(pref("disableGlobalSearch", false)).setMultiline(true));`.

**On plain Telegram (DrKLO):** Forkgram only: `ForkSettingsActivity.java` does not exist in plain Telegram (9.2, item 7).


##### H20. Fork Client Settings: the switch

**File:** `TMessagesProj/src/main/java/org/telegram/ui/ForkSettingsActivity.java`

**Where:** Class `ForkSettingsActivity`, method `onClick(UItem, View, int, float, float)`: right after `final int id = item.id;`. In Forkgram 12.10.6 the text below starts at line 744.

**Find this** (it occurs once in the file; text from Forkgram 12.10.6):

```java
    private void onClick(UItem item, View view, int position, float x, float y) {
        final int id = item.id;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
 
     private void onClick(UItem item, View view, int position, float x, float y) {
         final int id = item.id;
+        if (org.telegram.messenger.multigram.HideSearchBar.onSettingsClick(item, view)) return; // MultiGram: "Hide chat list search" toggle
 
         if (id == ID_HIDE_SENSITIVE_DATA) {
             toggle("hideSensitiveData", item, view);
```

**Why:** Handles a tap on the row: it flips the value, saves it with `commit`, and checks the cell, as Forkgram's private `toggle()` does. For every other row it returns `false`, so Forkgram's own rows work as before.

**If the code moved:** The first statement after the click handler of the settings screen reads the row's id. The check requires the hook directly after `final int id = item.id;` at the start of `onClick`.

**On plain Telegram (DrKLO):** Forkgram only.


##### H21. No header search icon either

**File:** `TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java`

**Where:** Class `DialogsActivity`, method `checkUi_itemSearchVisibility()`: its first line. In Forkgram 12.10.6 the text below starts at line 14319.

**Find this** (its second line occurs twice in the file, the whole block once; text from Forkgram 12.10.6):

```java
    private void checkUi_itemSearchVisibility() {
        final float factor0 = isSupportSearch() ? 1 : 0;
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
     }
 
     private void checkUi_itemSearchVisibility() {
-        final float factor0 = isSupportSearch() ? 1 : 0;
+        final float factor0 = isSupportSearch() && !org.telegram.messenger.multigram.HideSearchBar.hides(this) ? 1 : 0; // MultiGram: "no search": no header search icon either
         final float factor1 = animatorSearchButtonVisible.getFloatValue();
         final float factor2 = 1f - getRightSlidingProgress();
         final float factor3 = 1f - animatorDoneButtonVisible.getFloatValue();
```

**Why:** The header icon's visibility is the product of four factors. Stock shows the icon whenever the bar is invisible, and H18 keeps the bar invisible at rest. With `factor0` at 0 while the option is on, the icon never shows in the chat list. This one line is what makes this the "no search" variant.

**If the code moved:** Change the factor that says whether this list supports search, in the method that sets `searchItem`'s visibility. Leave the identical line in `checkUi_searchFieldVisibility` alone: there it decides whether the field can show at all, also while searching (8.5.6). The check requires the hook as the only `factor0` of `checkUi_itemSearchVisibility`, as its first line, directly followed by the stock `factor1` line, and the stock `factor0` line exactly once, in `checkUi_searchFieldVisibility`.


##### H22. check.sh: run the check

**File:** `multigram/tools/check.sh`

**Where:** MultiGram's own file. After the style knobs block, before the rebrand self-test block (K24).

**Find this** (it occurs once in the file; text from the file as commit 4780eb095b left it):

```sh
  python3 multigram/tools/style_knobs_check.py
fi
```

**Change it to** (lines starting with `-` go, lines starting with `+` are added, the rest stays):

```diff
   python3 multigram/tools/style_knobs_check.py
 fi
 
+if [ -f multigram/tools/hide_search_bar_check.py ]; then
+  # "Hide chat list search": hooks and their placement, every bar-height use reviewed, one owned setting.
+  echo "== hide search bar: hooks, reviewed bar-height uses and owned setting"
+  python3 multigram/tools/hide_search_bar_check.py
+fi
+
 if [ -f multigram/rebrand/selftest.py ]; then
   # Rebrand toolkit: generate two identities on a scratch copy, check the output, then --clean back to the commit.
   echo "== rebrand toolkit: self-test"
```

**Why:** CI runs `hide_search_bar_check.py` on every build and every sync candidate.

**If the code moved:** Order does not matter. The `[ -f ... ]` guard lets older trees without the file pass.


#### 8.5.4 Data

Nothing is generated or derived.

| What | Value | Where it is set |
|---|---|---|
| The setting | Key `multigramHideSearchBar` in `mainconfig` (`MessagesController.getGlobalMainSettings()`, the file of Forkgram's own Chat list rows). A boolean, default `false`, written only by the row, with `commit`. | `HideSearchBar.KEY` |
| The row's id | 9101: above 0, so the search inside Fork settings finds the row, and clear of Forkgram's ids (1 to 100). The check compares it with every `ID_...` and `MENU_SEARCH` in `ForkSettingsActivity.java`. | `HideSearchBar.ROW_ID` |
| Scope | Lists with the default dialogs type, without the `onlySelect` argument, for which `isMainDialogList()` is true (no delegate, no search string), decided once per list | `HideSearchBar.inScope`. To keep community lists stock, add `&& !f.isCommunity()`; a comment there says so. |
| Bar height | `SEARCH_FIELD_HEIGHT = 48` (dp), unchanged | Stock `DialogsActivity` |

Forkgram's settings export (`forkgram/SettingsBackup.kt`) exports and imports all of `mainconfig`, so the setting comes along. The Android backup agent does not back up `mainconfig`.

The two strings, in `TMessagesProj/src/main/res/values/multigram_strings.xml` (English only, read with `Context.getString`):

```xml
    <string name="MultiGramHideSearchBar">Hide chat list search</string>
    <string name="MultiGramHideSearchBarInfo">Remove the search bar and the search icon from the chat list.</string>
```

The resource names and the key keep the name `HideSearchBar` of the first design. Only the texts changed.

#### 8.5.5 Regenerate and verify

Nothing is generated in this unit. To verify, from the root of a checkout:

```sh
python3 multigram/tools/hide_search_bar_check.py
python3 multigram/tools/hide_search_bar_check.py --base origin/forkgram
bash multigram/tools/check.sh
```

- Both checks print `hide-search-bar: OK`, in under a second. With `--base`, every non-blank line the stack adds to `DialogsActivity.java` and `ForkSettingsActivity.java` must carry `MultiGram:`, or follow a `// MultiGram:` comment line (the form of R2 and R3).
- A failure lists each problem, then `hide-search-bar: FAILED, N problem(s)`, with exit status 1. For example, with H7 put back to stock:

  ```text
  hide-search-bar: hook '^                t \\+= dp\\(org\\.telegram\\.messenger\\.multigram\\.HideSearchBar\\.restHeight\\(DialogsActivity\\.this, SEARCH_FIELD_HEIGHT\\)\\); // MultiGram: ' found 0 times in TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java (expected 1)
  hide-search-bar: TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java: unreviewed use of the bar height (a new upstream use, or a stock line a hook replaced): t += dp(SEARCH_FIELD_HEIGHT);
  hide-search-bar: TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java: the list padding hook must directly follow "if (!actionModeFullyShowed) {"
  hide-search-bar: FAILED, 3 problem(s)
  ```

  Patterns are printed as Python strings, so each backslash shows doubled.
- `check.sh` prints `== hide search bar: hooks, reviewed bar-height uses and owned setting` and `hide-search-bar: OK` between the style knobs check and the rebrand self-test, and ends with `== all MultiGram checks passed`. On ff868b3ea4 it took 1 minute 13 seconds on 4 cores.

**When the check reports `unreviewed use of the bar height`.** An update added or changed a line of `DialogsActivity.java` that uses `SEARCH_FIELD_HEIGHT`, or a hook line lost its marker. Read the line in context and decide:

- If the line is part of the room the bar keeps at rest (list padding, header height, a scroll limit), hook it like the others, with `restHeight` inside its `dp(...)`, and add it to `H` and `LAYOUT` in the check.
- Otherwise add its text, without indentation, to `REVIEWED` in the check, with the number of times it occurs.

The message `reviewed line ... found N times (expected M)` means upstream removed or doubled a reviewed line: review it the same way and fix the count. Fold the change into "Add an option to remove the chat list search bar" (6.3).

**On a device** (the full list is "Device test checklist" in `multigram/hide-search-bar/README.md`, 14 items):

1. With the option off (the default), the chat list is exactly stock: the bar at rest and hiding on scroll, the header icon once the bar has scrolled away, search from both, and the icon's long-press opening Saved Messages. Compare it with a Forkgram build.
2. Turn the option on in **Fork Client Settings > Chat list view** and go back to Chats: no bar, no gap and no search icon, with the first chat right under the header or the folder tabs. With a hidden Archive, no strip of the Archive row shows. Check the Archive, a folder and a community list too.
3. Search still opens from the Downloads item (while a file downloads), from a `tg://search?query=` link and from the forum topics column's search icon. The field fades in in the header, and closing search brings back the list with no bar and no icon.
4. Action mode, stories (collapse, expand, fling) and the topics column cause no jump.
5. Pickers (forward, share from another app) keep their stock bar.
6. Turn the option off and go back: the bar is back at rest, with the first chat under it. The header search icon may show and fade out over about a third of a second (350 ms). Stock does the same when the bar scrolls back in, so this is expected.

#### 8.5.6 Gotchas

- **Most hooks change one word inside an existing `dp(...)`.** 13 of them (H1 to H4, H6 to H10, H14 to H17) only put `org.telegram.messenger.multigram.HideSearchBar.restHeight(DialogsActivity.this, SEARCH_FIELD_HEIGHT)` in place of `SEARCH_FIELD_HEIGHT`. The rest of each line is upstream's text. So when upstream edits one of these lines, for example to add a factor or rename a variable, git reports a conflict on the whole line. Take Forkgram's new line and make the same one-word change in it again. Never keep MultiGram's side: it would bring back the old line. Then run the check: it matches each hook line exactly, and it also finds a stock line that came back.
- **Keep the call inside `dp(...)`.** `restHeight` works in dp and returns 0 while the option is on, and `dp(0)` is 0. Do not move it outside (`restHeight(..., dp(SEARCH_FIELD_HEIGHT))`) or write 48: the check matches the exact text.
- **Two identical `factor0` lines.** `final float factor0 = isSupportSearch() ? 1 : 0;` is in `checkUi_searchFieldVisibility` (it decides whether the field can show at all) and, lower down, in `checkUi_itemSearchVisibility` (the header icon). H21 changes only the second one. An editor's search, or a `sed` that takes the first match, changes the wrong one. Search opened from Downloads or a link would then show no field, and the icon would come back. The check reports it with four problems: the stock line must stay exactly once in `checkUi_searchFieldVisibility`, and the hook must be the first line of `checkUi_itemSearchVisibility`. A search for the text alone finds other near-twins too: H14 and H16 differ only in their indentation, and `t += dp(SEARCH_FIELD_HEIGHT);` (H7) also matches the end of H8's line. Use the blocks of 8.5.3, which occur once.
- **`this` or `DialogsActivity.this`.** Every `restHeight` hook passes `DialogsActivity.this`, which works everywhere. Most of them sit in inner classes (`ContentView`, `DialogsRecyclerView`, the page's `LinearLayoutManager`, animator listeners), where `this` would be the inner object and would not compile. H11, H12, H13, H18 and H21 pass `this`, because they sit in `DialogsActivity`'s own methods. Keep each as its block shows: the check matches the text.
- **Hooks that must pair up:** H2 and H3; H4, H6 and H8 (topics column); H9 and H10 (fling); H14 to H17 (action mode). Change one, change its partners.
- **H13 must come before `onResume`'s `notifyDataSetChanged()`.** See H13.
- **Deliberately not hooked:** the `SEARCH_FIELD_HEIGHT = 48` declaration (`javac` copies the constant into other classes, and it also sets how far the field slides in search), `FragmentSearchField.java` (shared with other screens; the check fails if it names MultiGram), the tabs' layout line in `ContentView.onLayout` (H12 compensates), and a few cosmetic lines. The README lists them all. `REVIEWED` in the check holds each of these lines of `DialogsActivity.java`; the check tests `FragmentSearchField.java` separately.
- **The ways into search that stay are checked.** If an update stops the icon's click listener, the Downloads item or `search(String, boolean)` from calling `showSearch`, or `TopicsFragment` stops calling `searchItem.performClick()`, the check fails. Then review "What still opens search" in the README, and update the README and the check together.
- **The topics column's icon opens search through the hidden header icon.** `performClick()` runs the click listener even while the icon is hidden. Never block that listener: it would also break the topics column's search.
- **Scope is decided once per list,** at first use, because a picker may reset its delegate later. Pickers and `#hashtag` screens are out of scope and keep the stock bar.
- **Forkgram-only dependencies:** `ForkSettingsActivity.java` (the row), `UItem.setMultiline` (in `settingsRow()`), and `forkgram/SettingsBackup.kt`, which the check reads.
- **The strings are English only.** They are read with `Context.getString`, not `LocaleController`, like the other MultiGram strings.
- **To go back to the "search icon" variant** (bar hidden, icon shown), follow "Considered and not done" in the README: undo H21, and change the two strings and the check.

## 9. Plain Telegram (DrKLO)

This section says what happens if you put the stack on Telegram's own code (DrKLO/Telegram) instead of Forkgram. It was tested by applying the seven exported patches (5.7) with `git am -3`, one at a time, to DrKLO dc780e81e ("update to 12.10.5 (7105)"), the Telegram base of Forkgram 12.10.6.

### 9.1 What applies

| Commit | Applies? | Conflicts | Forkgram-only dependencies |
|---|---|---|---|
| d457ac74ae rebrand | No: `git am -3` stops with three conflicts. The new files and hook R1 go in without trouble. | `DialogsActivity.java` (hook R2: Forkgram's custom title code does not exist); `ForkSettingsActivity.java` (the file does not exist); `TMessagesProj_App/build.gradle` (DrKLO's file ends with `apply plugin: 'com.google.gms.google-services'`: keep both lines) | `forkCustomTitle` and `ForkSettingsActivity`; the generator's icon names and file types |
| 5b53859682 palette | Yes, cleanly. `palette_fix_check.py` passes. | none | `ThemeInfo.isMonet()` in `PaletteFix.java`: a compile error |
| cddd62df98 style table | Yes, cleanly. The table checks pass, and `make_style_table.py --check` finds the table identical. | none | none: `ThemeColors.java` and the five `.attheme` files are the same in both |
| 27d32d57b4 random style | Yes, cleanly. Every hook lands where the check expects it. | none | `ThemeInfo.isMonet()` in `RandomStyle.java` (a compile error); `random_style_check.py` crashes because `forkgram/SettingsBackup.kt` is missing |
| 3b941c01de knobs | Yes, cleanly. `style_knobs_check.py` passes. | none | none |
| 4780eb095b CI | Yes, cleanly. | none | Indirect: `check.sh` stops at the random style check, and the rebrand self-test fails on DrKLO's icons (9.2, item 2). |
| ff868b3ea4 hide search | No: `git am -3` stops on one file. The new files and the 19 `DialogsActivity.java` hooks go in cleanly, where the check expects them. | `ForkSettingsActivity.java` (the file does not exist: hooks H19 and H20) | `UItem.setMultiline` in `HideSearchBar.java` (a compile error); `hide_search_bar_check.py` crashes because `ForkSettingsActivity.java` and `forkgram/SettingsBackup.kt` are missing (9.2, item 7) |

So the text applies almost completely, but the result does not build or pass `check.sh` as it is.

### 9.2 What would have to change

1. **Rebrand hooks.** The rule of 5.2 does not fit these conflicts, because the MultiGram side holds Forkgram code that Telegram does not have. 9.4 gives the commands.
   - Drop hooks R3 and R4: `ForkSettingsActivity.java` does not exist. `git am -3` leaves Forkgram's whole file in the tree anyway (`deleted in HEAD and modified in Add the rebrand toolkit`). Remove it; it does not compile on DrKLO.
   - Drop hook R2 as it is: DrKLO has no `forkCustomTitle`. The HEAD side of the conflict is empty, and the other side is R2 plus Forkgram's own title code. Keep DrKLO's side. Putting R2 back would even replace Telegram's logo title with the text "Fork Client" in a stock build. DrKLO's chat list title draws the picture `telegram_logo_2` over the text of `R.string.AppName` (`DialogsActivity.java` line 3517 in dc780e81e). Renaming `AppName` therefore does not change what is shown. A rebranded build would need a new hook after `actionBar.setTitle(ssb, statusDrawable);` (line 3519) that shows `Rebrand.defaultTitle(getString(R.string.AppName))` as plain text when `Rebrand.isActive()`. `Rebrand.defaultTitle` reads `AppName` through Android, as 8.1.6 requires. That hook has not been written or tested.
   - In `TMessagesProj_App/build.gradle`, keep DrKLO's `apply plugin` line and add the `apply from:` line (R5) after it.
2. **Rebrand generator** (`multigram/rebrand/generate_rebrand.py` and `selftest.py`). DrKLO has no `icon_01_*` icons and no `splash_fork_320`. Its default icon uses `icon_foreground_sa` (PNG files) and `icon_background_sa` (a `<shape>` XML file). Its `ic_launcher_dr` and `notification` are `.webp` files, where Forkgram has `.png`. The self-test fails with `error: unexpected drawable-hdpi/ic_launcher_dr.webp: update ICON_TARGETS in multigram/rebrand/generate_rebrand.py`, prints more `FAIL` lines, and then stops with a Python traceback (`KeyError: 'REBRAND_KEYSTORE'`) instead of a `FAILED` line.
   - Editing `ICON_TARGETS` is not enough. `write_overlay()` writes only PNG files, adaptive icon XML and splash XML, and stops with `unexpected ...: update ICON_TARGETS` on anything else, such as the `.webp` icons or `icon_background_sa.xml`. Either teach `write_overlay()` those formats, or leave those three icons out of `ICON_TARGETS`; a rebranded build then keeps Telegram's account icon, notification icon and icon background.
   - `selftest.py` must change with it: it looks for `notification.png` (line 247) and requires the "same file type and pixel size as upstream".
   - DrKLO's `auth.xml` and `sync_contacts.xml` say `org.telegram.messenger`, so change `STOCK_XML_ACCOUNT_TYPE` too.
   - A test with only `ic_launcher`, `ic_launcher_round`, `icon_foreground_sa` and `tg_splash_320` in `ICON_TARGETS`, and the new account type, ended with `FAILED: 4 failure(s)`: `seed A: no warnings` (the google-services warning of item 6) and three times `0 notification icons are white on transparent`.
3. **Monet.** Replace `theme.isMonet()` at `PaletteFix.java` lines 165 and 225 and `RandomStyle.java` lines 449 and 624 with `false`. DrKLO has no Monet themes.
4. **`random_style_check.py`.** Make the `SettingsBackup.kt` part optional. DrKLO has no settings export. The Android backup part applies as it is.
5. **API id and hash.** DrKLO sets `APP_ID = 4` and Telegram's `APP_HASH` in `BuildVars.java`, and ignores the `APP_ID` and `APP_HASH` Gradle properties that the APK job writes. Forkgram copies them from `BuildConfig` (`BuildVars.java` lines 66 and 67). On DrKLO, edit `BuildVars.java` or port Forkgram's way.
6. **Application id and Firebase.** DrKLO's id is `org.telegram.messenger`, the official app's id. A rebrand, or at least a new id, is required. DrKLO applies the google-services plugin in two modules: `TMessagesProj/build.gradle` (line 253) and `TMessagesProj_App/build.gradle` (line 208). Both `google-services.json` files list only `org.telegram.messenger`, `.beta` and `.web`. For a new id, put a `google-services.json` from your own Firebase project that lists `<id>`, `<id>.beta` and `<id>.web` in `TMessagesProj_App/`, or delete the `apply plugin` line of `TMessagesProj_App/build.gradle`. While that line is there, the rebrand generator warns about it (item 2).
7. **Hide chat list search** (patch 7). Its 19 hooks in `DialogsActivity.java` apply cleanly, but its settings row (H19, H20) belongs in `ForkSettingsActivity.java`, which plain Telegram does not have. Without a row nothing turns the option on, and with the option off the hooks behave as stock. So either leave patch 7 out (`git am --skip`, 9.4), or keep it and:
   - Remove `.setMultiline(true)` from `HideSearchBar.settingsRow()`. `UItem.setMultiline` exists only in Forkgram, so the file does not compile otherwise.
   - Give the row a new home in Telegram's own settings screens. This has not been written or tested.
   - In `hide_search_bar_check.py`, make the parts that read `ForkSettingsActivity.java` and `forkgram/SettingsBackup.kt` optional: the check stops with `FileNotFoundError` on the first. Also add `"maxScrollYOffset = dp(SEARCH_FIELD_HEIGHT);": 1` to `REVIEWED`: DrKLO's `DialogsActivity.java` has one more use of the bar height (line 4580 in dc780e81e), in scroll code that never runs, because `applyScrollY` is set to `false` just before it. With these changes the rest of the check passes on DrKLO.

### 9.3 Build differences

- **`-x :TMessagesProj:buildNativeDeps`** in `build.yml` must go: the task exists only in Forkgram (`TMessagesProj/build.gradle` line 282), and Gradle rejects excluding a task that does not exist. DrKLO links prebuilt native libraries from `TMessagesProj/jni/prebuild/`.
- **Modules.** DrKLO's `settings.gradle` also includes `:TMessagesProj_AppHuawei`, `:TMessagesProj_AppHockeyApp`, `:TMessagesProj_AppStandalone` and `:TMessagesProj_AppTests`, and its root `build.gradle` adds Huawei and Firebase build plugins.
- **Flavors.** The flavor `afat`, the tasks `compileAfatReleaseJavaWithJavac` and `assembleAfatRelease`, and the APK output folder exist in both.
- **Signing.** DrKLO signs every build type with `TMessagesProj/config/release.keystore`, a public key whose passwords are in its `gradle.properties` (`RELEASE_STORE_PASSWORD=android`, `RELEASE_KEY_ALIAS=androidkey`, `RELEASE_KEY_PASSWORD=android`). It ignores Forkgram's `RELEASE_KEYSTORE_FILE`, but reads the other three properties. So with the `MULTIGRAM_KEYSTORE_*` secrets set (10.4), the APK job passes your passwords for DrKLO's keystore, which they do not open. Without the secrets, the APK is signed with DrKLO's public key. Port Forkgram's `signingConfigs` in `TMessagesProj_App/build.gradle`, which read `RELEASE_KEYSTORE_FILE`.
- The APK job's extra tools (meson, nasm, rust targets) serve Forkgram's native build and are probably not needed for DrKLO. This was not tested.

### 9.4 How to try it

```sh
git clone --recursive --shallow-submodules https://github.com/DrKLO/Telegram.git
cd Telegram
git fetch --depth 1 https://github.com/forkgram/TelegramAndroid.git tag 12.10.6.0
git switch -c multigram dc780e81ed1261c369c27870e8e0999a1eb0b600
git am -3 /path/to/multigram-patches/0001-*.patch
```

- The start point of `git switch` is the commit this section was tested on: the `Telegram-Base` line of the snapshot the patches were made on (`git log -1 --format=%B origin/forkgram`). DrKLO's `master` moves on; on any other commit, expect other conflicts and line numbers than in 9.1 and 9.2.
- The `git fetch` of Forkgram's release gives `git am -3` the old file versions it needs. Use the tag that `APPLY.txt` names (the Forkgram version plus `.0`).

Patch 1 stops with three conflicts (9.1). Settle them as 9.2 item 1 says:

```sh
git rm -q TMessagesProj/src/main/java/org/telegram/ui/ForkSettingsActivity.java
git checkout --ours TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java
sed -i -e '/^<<<<<<< /d' -e '/^=======$/d' -e '/^>>>>>>> /d' TMessagesProj_App/build.gradle
git add TMessagesProj/src/main/java/org/telegram/ui/DialogsActivity.java TMessagesProj_App/build.gradle
git am --continue
git am -3 /path/to/multigram-patches/000[2-7]-*.patch
```

- `git rm` drops R3 and R4 with Forkgram's file. `git checkout --ours` keeps DrKLO's `DialogsActivity.java`, without R2. The `sed` deletes the three marker lines, the only conflict in `build.gradle`: DrKLO's `apply plugin` line stays first and R5 follows.
- Patches 2 to 6 then apply without conflicts.
- Patch 7 stops once more, with `CONFLICT (modify/delete)` on `ForkSettingsActivity.java`, because that file is gone. `git am` calls it patch 0006, because it counts the patches of this run. Its `DialogsActivity.java` part merges cleanly.

Settle patch 7 in one of two ways. To leave the option out, run `git am --skip`. To keep its chat list hooks without the settings row (9.2, item 7):

```sh
git rm -q TMessagesProj/src/main/java/org/telegram/ui/ForkSettingsActivity.java
git am --continue
```

Then make changes 2 to 6 of 9.2, and change 7 if you kept patch 7, and commit them. Without change 3 the Java code does not compile, nor without change 7 when patch 7 is kept. To check the result:

```sh
python3 multigram/tools/palette_fix_check.py --base dc780e81e
python3 multigram/tools/style_knobs_check.py --base dc780e81e
python3 multigram/tools/random_style_check.py --base dc780e81e
python3 multigram/tools/hide_search_bar_check.py --base dc780e81e
git grep -n -e 'multigram\.Rebrand\.' -e 'multigram/rebrand/rebrand.gradle' -- TMessagesProj TMessagesProj_App
```

- The first two print `OK` right after the patches. `random_style_check.py` stops with `FileNotFoundError` on `SettingsBackup.kt` until change 4 is done; then it prints `OK` too. If you kept patch 7, `hide_search_bar_check.py` stops with `FileNotFoundError` on `ForkSettingsActivity.java` until change 7 is done; then it prints `OK` too.
- The `git grep` prints 2 lines here (R1 and R5), not the 5 of 5.4.
- `bash multigram/tools/check.sh` stops at the random style check until change 4 is done, at the hide search bar check until change 7 is done (if you kept patch 7), and at the rebrand self-test until change 2 is done and the google-services `apply plugin` line of `TMessagesProj_App/build.gradle` is gone (change 6). While that line is there, the self-test fails `seed A: no warnings`.

## 10. Verifying

### 10.1 The compile check on Actions

In the browser: **Actions > Build MultiGram > Run workflow**. Leave "Use workflow from" on `main`, because the workflow file lives there. Type the branch to build in **ref**: `multigram-next` for a fix, `multigram` otherwise. Tick **APK** only for a release build (10.4).

From a terminal (not run while writing this guide):

```sh
gh workflow run build.yml -R iko-soy/Multigram --ref main -f ref=multigram-next
gh run list -R iko-soy/Multigram --workflow build.yml -L 5
gh run watch <run-id> -R iko-soy/Multigram
gh run view <run-id> -R iko-soy/Multigram --log-failed
```

The job **Compile Java and Kotlin**:

1. checks out the ref, and fetches the two submodules the Java code needs (`TMessagesProj/lib/jlatexmath` and `TMessagesProj_Modules/media`);
2. sets up Java 17 (Temurin) and Gradle;
3. compiles the Java and Kotlin code of both modules, without the native code (step **Compile**);
4. runs `bash multigram/tools/check.sh` if the file exists (step **Run MultiGram tool checks**).

Past runs took about 8 to 9 minutes: about 4.5 minutes to compile and about 3 minutes for the checks (from the Actions history, not measured again for this guide). The sync's compile job calls this same workflow.

### 10.2 check.sh

`bash multigram/tools/check.sh` needs only bash and python3. On ff868b3ea4 it took 1 minute 13 seconds on 4 cores locally, and about 3 minutes on CI (3 minutes 7 seconds in run 36467179859). It stops at the first failure. Each part prints a header line that starts with `==`:

| Header | What it checks | Passes with | A failure usually means |
|---|---|---|---|
| `== palette fix: ...` | `palette_fix_check.py`: colour values, `PaletteFix.java` tables, the 12 palette hook lines | `palette-fix: OK` | A palette hook is missing or doubled, or upstream changed a colour that overlay A replaces. See 8.2.5. |
| `== random style: ...` | `random_style_check.py`: the 15 hooks and their places, privacy, strings, backup policy | `random-style: OK` | A random style hook is missing or in the wrong place. A Python `FileNotFoundError` means Forkgram moved `forkgram/SettingsBackup.kt`. A line `<file>: <X> not found after <Y>` can also mean that upstream changed a line the check uses as a landmark (`check_placement()` in `random_style_check.py`): if the hook still sits where its "If the code moved" says, update that pattern. See 8.3.5. |
| `== style knobs: ...` | `style_knobs_check.py`: the knob hooks, stock lines gone, safe ranges | `style-knobs: OK` | A knob hook is missing, a stock line came back, or upstream reformatted a hooked line. Placement failures can also come from a changed landmark (8.4.2 lists them in `style_knobs_check.py`). See 8.4.5. |
| `== hide search bar: ...` | `hide_search_bar_check.py`: the 21 hooks and their places, the ways into search left stock, every other use of the bar height, the one setting and its row | `hide-search-bar: OK` | A hook is missing or moved, a stock line came back, or upstream added or changed a line that uses `SEARCH_FIELD_HEIGHT` (`unreviewed use of the bar height`). A placement failure can also come from a changed landmark next to a hook (8.5.2). A Python `FileNotFoundError` means Forkgram moved a file the check reads. See 8.5.5. |
| `== rebrand toolkit: self-test` | `selftest.py`: two generated identities and `--clean` | `PASSED: 0 failure(s)` | Forkgram renamed or re-encoded an icon, string or account type literal the generator targets. The error names it, for example `update ICON_TARGETS`. See 8.1.5. |
| `== style table: format and readability ...` | `check_style_table.py`: all 20,480 styles on this tree's theme sources | `style table check: PASS (...)` | Upstream colours changed so much that some styles are unreadable. Make a new table (8.3.5). |
| `== style table: does this tree regenerate the same asset?` | `make_style_table.py --check` | `identical to ...` | Status 3 prints a `WARNING` and passes: make a new table when convenient. Status 4 fails: fix the palette first. Any other status fails with `FAIL: make_style_table.py exited with status N`. |

The last line on success is `== all MultiGram checks passed`.

A fix to a check script goes into the commit that added the script (6.3): `random_style_check.py` into "Give each install its own random style", `style_knobs_check.py` into "Randomise shapes and chat list layout per install", `palette_fix_check.py` into "Fix palette contrast for generated accents", `hide_search_bar_check.py` into "Add an option to remove the chat list search bar".

### 10.3 Hooks no script checks

- The four rebrand Java hooks: run the `git grep` of 8.1.5 and expect 5 lines (with R5).
- Seven of the nine MultiGram lines in `ChatActivityEnterView.java` (P14, and all of P15 except the `int glyph = ...` and `drawableInverse` lines). Read them with `git grep -n MultiGram -- TMessagesProj/src/main/java/org/telegram/ui/Components/ChatActivityEnterView.java`. It must print 9 lines.
- The `check.sh` steps that run the checks (K23, K24, H22, and the random style step that 27d32d57b4 adds). If one is missing, its check silently does not run. `bash multigram/tools/check.sh` must print the seven `==` headers of the table in 10.2 before `== all MultiGram checks passed`.

### 10.4 Release APK

Run **Build MultiGram** with **APK** ticked (or add `-f apk=true` to the `gh` command). The job **Release APK** starts after the compile job and takes about 70 minutes, most of it for the native code; the whole run takes about 80 minutes ([run 36306473313](https://github.com/iko-soy/Multigram/actions/runs/36306473313), 2026-09-27). Its time limit is 300 minutes.

Secrets, in **Settings > Secrets and variables > Actions**:

| Secret | Needed? | What it is |
|---|---|---|
| `MULTIGRAM_APP_ID`, `MULTIGRAM_APP_HASH` | Yes | Your API id and hash from https://my.telegram.org. Without them the APK cannot log in. |
| `MULTIGRAM_KEYSTORE_BASE64` | For APKs you give to others | Your release keystore, as `base64 -w0 release.keystore`. |
| `MULTIGRAM_KEYSTORE_PASSWORD`, `MULTIGRAM_KEY_ALIAS` | With the keystore | The keystore password and the key's alias. |
| `MULTIGRAM_KEY_PASSWORD` | Only if it differs from the keystore password | The key's password. |

Without the keystore secrets the job signs the APK with Forkgram's public test key (`TMessagesProj/config/test.keystore`) and prints a warning. That is fine for testing, but anyone could sign an "update" for such an APK. Keep one key for every build you give out, or phones cannot update. The rebrand toolkit can make a key (see "Signing and updates" in `multigram/rebrand/README.md`).

The job adds 8 GB of swap and smaller Java memory settings, because runners for private repositories have about 8 GB of memory. It builds with `./gradlew :TMessagesProj_App:assembleAfatRelease`. The APK is attached to the run as the artifact `multigram-apk`. To download it from a terminal: `gh run download <run-id> -R iko-soy/Multigram -n multigram-apk`.

### 10.5 Device checklist

After each update:

1. **Update over the previous MultiGram build** (same key): it installs as an update, the style does not change, and "Shuffle my style" still works.
2. **Fresh install, light system theme:** the first frame already shows the day style, with no flash of the Blue theme. **Dark system theme:** the night style. Bubble corners and the chat list layout are right from the first frame.
3. **Chat Settings:** Shuffle, then Undo. The preview, radius slider and chat list picker update at once. "Reset to defaults" returns to the install's style and radius. The custom theme tile applies the current generated style.
4. **Sharing the generated accent** shows the "stays on this device" message and uploads nothing. "Create new theme" shows the message instead of the dialog.
5. **Shapes:** service and date pills, reaction chips, sheet buttons, the chat list floating button with its shadow, settings cards, and the wallpaper gradient's start phase.
6. **Readability:** grey texts, times in bubbles, the message field hint, and the send and voice glyphs on the accent, in day and night.
7. **Monet:** a selected Monet theme survives a restart. Shuffle replaces it with a generated style (by design). "Reset to defaults" leaves it alone.
8. **Rebranded build only:** app name, launcher, splash and notification icons, a single icon in the icon picker, the chat list title, and the account in **Settings > Accounts** with working contact sync.
9. **Tablet or unfolded foldable:** knob values from the first frame.
10. **Hide chat list search** (Fork Client Settings > Chat list view): off, the chat list is exactly stock. On, Chats, a folder and the Archive show no search bar and no search icon, and the first chat sits right under the header. The Downloads item, a `tg://search?query=` link and the forum topics column's search icon still open search. Pickers keep their bar. See 8.5.5.

The full lists are in `multigram/random-style/README.md` (15 items), `multigram/style-knobs/README.md` (10 items) and `multigram/hide-search-bar/README.md` (14 items).

## 11. Keeping this guide current

### 11.1 Check and refresh the hooks

**After every upstream update**, even one that replayed with no conflict, the "Find this" texts and the line numbers in section 8 can go stale. No check script looks at them, but this does. Run it in the folder that holds `PATCH.md` (the `docs` branch, 11.2), in a clone that has `origin/forkgram`:

```sh
python3 - origin/forkgram <<'EOF'
import re, subprocess, sys
rev = sys.argv[1]
if subprocess.run(['git', 'rev-parse', '--verify', '-q', rev + '^{commit}'], stdout=subprocess.DEVNULL).returncode:
    sys.exit('unknown revision: ' + rev)
doc = open('PATCH.md', encoding='utf-8').read()
for part in re.split(r'^##### ', doc, flags=re.M)[1:]:
    hook = part.split('.')[0]
    path = re.search(r'\*\*File:\*\* `([^`]+)`', part).group(1)
    if 'multigram' in path.split('/'):
        continue  # MultiGram's own files (K18 to K24, H22)
    show = subprocess.run(['git', 'show', rev + ':' + path], capture_output=True, text=True)
    if show.returncode:
        print(hook, path, 'is missing')
        continue
    src = show.stdout
    for kind, block in re.findall(r'\*\*(Find this|Then find these)[^\n]*\n\n```[a-z]*\n(.*?)```', part, re.S):
        for text in (block.splitlines() if kind.startswith('Then') else [block]):
            if src.count(text) != 1:
                print(hook, 'found', src.count(text), 'times:', ' '.join(text.split())[:60])
            elif kind == 'Find this':
                line = src[:src.index(text)].count('\n') + 1
                said = re.search(r'starts at line (\d+)', part)
                if said and int(said.group(1)) != line:
                    print(hook, 'now starts at line', line, 'not', said.group(1))
EOF
```

It prints one line for each hook text that no longer occurs exactly once, and one for each hook whose text now starts at another line than its "Where" says. On `forkgram` 4543767655 it prints a single line, because K1's text comes from the stack (1.5):

```text
K1 found 0 times: org.telegram.messenger.multigram.RandomStyle.onApplicationCr
```

Refresh every other hook it names with the commands at the end of this section.

**After the stack changes** (a fixup after an update, say), also compare these lists with section 3 and section 8. Run them from any checkout:

```sh
git fetch origin
git diff --stat --diff-filter=M origin/forkgram origin/multigram -- . ':!multigram' ':!TMessagesProj/src/main/java/org/telegram/messenger/multigram'
git diff --name-only --diff-filter=A origin/forkgram origin/multigram
git diff -U0 --diff-filter=M origin/forkgram origin/multigram -- . ':!multigram' ':!TMessagesProj/src/main/java/org/telegram/messenger/multigram'
```

1. The first command lists the upstream files the stack touches. On ff868b3ea4 it ends with `30 files changed, 135 insertions(+), 89 deletions(-)`: 99 and 53 lines in Java and Gradle files, plus 36 and 36 in the `.attheme` files.
2. The second lists the new files: 40 on ff868b3ea4.
3. The third shows every hook line with no context.

The code blocks of each hook come straight from git:

- "Change it to" is `git diff -U3 <commit>^ <commit> -- <file>` for the commit that adds the hook. The value lists P1 to P6 use `-U0`, which shows only the changed lines. When two hooks are so close that git shows them in one hunk, each block keeps only its own change and the stock lines around it (K6 and K7, H4 and H5, H9 and H10). H2 and H3 are on adjacent lines, so git prints both `-` lines before both `+` lines: H2's block shows that hunk as git prints it, and H3's block keeps only its own two lines.
- "Find this" is the matching text in `git show origin/forkgram:<file>`, and the line number in "Where" is its line there. For hooks in MultiGram's own files (K18 to K24 and H22), and for K1, which sits on the line after S1, it is the text in the file as the previous stack commit left it.

When a hook changes, refresh its blocks with these commands. Do not type code by hand.

### 11.2 Update the stamp

Change the table in 1.1:

- the `multigram` commit: `git rev-parse --short=10 origin/multigram`;
- the Forkgram version and commit, and the Telegram base: `git log -1 --format=%B origin/forkgram`;
- the `forkgram` and `main` commits;
- the date.

Then update the data that belongs to one version. Most of it is marked "on ff868b3ea4", "in Forkgram 12.10.6" or "today"; `grep -n -e 'ff868b3ea4' -e '12\.10\.6' -e '[Tt]oday' PATCH.md` finds those places. In short:

- the counts in 3.1, and the stat line and file count in 11.1;
- the "starts at line" of each hook (the script in 11.1 names the stale ones);
- line numbers in MultiGram's own files: 6.2 and 9.2 (`PaletteFix.java` 165, 225 and 316; `RandomStyle.java` 449 and 624), and `selftest.py` line 270 (8.1.4, 8.1.6);
- the problem counts in 7.4 (59, 27, 35 and 61), the line counts of the `git grep` commands in 5.4, 8.1.5, P13 and 8.2.6, and the seven `check.sh` headers of 10.3;
- 8.1.4 (string lines, 54 icon files), the old-value counts in P3 and P6, and the values and contrasts in 8.2.4;
- the expected outputs in 8.1.5, 8.2.5, 8.3.5 and 8.5.5, and the CRC in 8.3.4;
- the timings in 4.4, 8.1.5, 8.3.5, 8.4.5, 8.4.6, 8.5.5, 10.1 and 10.2;
- the DrKLO commit and line numbers in section 9.

This guide lives on the branch `docs`. If you keep a separate worktree for that branch, run these commands there instead of switching:

```sh
git switch docs
git add PATCH.md
git commit -m "Update PATCH.md for Forkgram <version>"
git push origin docs
```
