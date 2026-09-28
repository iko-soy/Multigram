# MultiGram

MultiGram is Forkgram (https://github.com/forkgram/TelegramAndroid) plus a small stack of MultiGram changes.

| Branch | What it holds |
|---|---|
| `forkgram` | Snapshots of Forkgram's `dev` branch, one commit per Forkgram release (the `.github` folder is left out). |
| `multigram` | The app: the latest `forkgram` snapshot plus the MultiGram commits on top. Build this branch. |
| `main` | This README, the automation that keeps `multigram` in step with Forkgram, and helper scripts. |

The sync also uses `multigram-next` (the next `multigram`, while it is being checked) and tags
the `multigram` it replaces as `multigram-before-<version>`.

[PATCH.md](https://github.com/iko-soy/Multigram/blob/docs/PATCH.md) on the `docs` branch says what
to do after a Telegram update when the sync needs a hand, and lists every MultiGram change with
the exact code, so the stack can be re-applied by hand.

## Build

**Actions > Build MultiGram > Run workflow**, ref `multigram`. It compiles the Java and Kotlin
code (a few minutes). Tick **APK** to also build a release APK; it compiles the native code
too, so it takes much longer, and the APK is attached to the run as `multigram-apk`.

## Secrets

Set these in **Settings > Secrets and variables > Actions**:

- `MULTIGRAM_APP_ID` and `MULTIGRAM_APP_HASH`: your own API id and hash from
  https://my.telegram.org (API development tools). Without them the APK cannot log in.
- Signing (optional): `MULTIGRAM_KEYSTORE_BASE64` (your release keystore, `base64 -w0 release.keystore`),
  `MULTIGRAM_KEYSTORE_PASSWORD`, `MULTIGRAM_KEY_ALIAS` and `MULTIGRAM_KEY_PASSWORD` (if it differs
  from the store password). Without them the APK is signed with Forkgram's public test key
  (`TMessagesProj/config/test.keystore`), which is fine for testing but lets anyone sign an
  "update" for it. Keep the same key for every build you give out, or phones can't update. The
  rebrand toolkit can make a key for you (see "Signing and updates" in `multigram/rebrand/README.md`).

## How the sync works

The **Sync with Forkgram** workflow runs every 6 hours (and by hand):

1. If Forkgram's `dev` has a new tip (Forkgram rebases `dev` onto every Telegram release, so each
   new tip is a release candidate), it adds a snapshot commit to `forkgram`: that tree without
   `.github`, with `Forkgram-Commit`, `Forkgram-Version` and `Telegram-Base` lines in the message.
2. It replays the MultiGram commits (`forkgram..multigram`) onto the snapshot as `multigram-next`
   (`git rebase --onto`).
3. It compiles `multigram-next` with the Build MultiGram workflow.
4. If that passes, it tags the old `multigram` as `multigram-before-<version>`, moves `multigram`
   to `multigram-next`, deletes `multigram-next` and closes the sync issue.
5. On a conflict or a failed compile it opens an issue labelled `forkgram-sync` (or comments on the
   open one) with the details; `multigram` stays as it was.

It never replaces a `multigram-next` that has commits it did not make (your fix, say): it then
changes nothing, not even `forkgram`, and says so on the issue until you run **use_next** or
delete `multigram-next`. It records the `multigram-next` it built last in the ref
`refs/multigram-sync/next`. Keep `multigram` linear (rebase, do not merge): the replay flattens
merges, so a merge commit with changes of its own stops the sync.

Run it by hand with **force** to rebuild `multigram-next` without a new release (to test the
pipeline, or to retry), or with **use_next** to compile and promote a `multigram-next` you fixed
yourself. **use_next** checks that `multigram-next` still has every commit on `multigram` (a
commit pushed to `multigram` after you started the fix would otherwise be lost); tick
**allow_drop** as well if it leaves some out on purpose.

The work is done by `scripts/sync-forkgram.sh` (see `--help`). It also runs locally without
pushing anything: from a checkout of `main`, `bash scripts/sync-forkgram.sh --remote origin`
leaves the results in your local `forkgram` and `multigram-next` branches.
`bash scripts/selftest-sync.sh` tests it against fake repositories.

rerere (git's memory of conflict fixes) only knows the fixes recorded in the clone it runs in.
It helps when you redo a rebase or run the script in your own clone; the scheduled sync starts
from a fresh clone every time, so it reports a conflict again until `multigram` carries the fix.

## When the sync issue opens

The issue has the exact commands; in short:

**Conflict.** Replay the stack yourself, fix the files, push the result to `multigram-next`:

```sh
git fetch origin
git switch -C multigram-next origin/multigram
git config rerere.enabled true     # reuses your fixes if you redo this rebase here
git rebase origin/forkgram
# fix the files git names, then: git add <files> && git rebase --continue (repeat)
git push --force origin multigram-next
```

**Compile failure.** Fix the build on top of `multigram-next` and fold the fix into the commit it
belongs to:

```sh
git fetch origin
git switch -C multigram-next origin/multigram-next
# edit, then, once per MultiGram commit your fix touches (name only that commit's files):
git commit --fixup=<the MultiGram commit it belongs to> -- <its files>
GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash origin/forkgram
git push --force origin multigram-next
```

Then **Actions > Sync with Forkgram > Run workflow** with **use_next** ticked: it compiles
`multigram-next` and, if that passes, moves `multigram` to it and closes the issue. If the
compile failed because of a runner or network hiccup, **Re-run failed jobs** on the run page
is enough. Until then the sync leaves your `multigram-next` alone; if you give up on it, delete
it (`git push origin --delete multigram-next`) and the next sync starts over from `multigram`.

## Patches

`bash scripts/export-patches.sh --base origin/forkgram --head origin/multigram` writes the stack
as numbered patches to `multigram-patches/`, with `APPLY.txt` saying how to apply them onto a
plain Forkgram checkout (`git am -3`).

## What is on the multigram branch

- `multigram/rebrand/`: the rebrand toolkit that gives a build its own name, applicationId,
  launcher icon and signing key (instructions in its `README.md`).
- `multigram/hide-search-bar/`: the "Hide chat list search" option in Fork Client Settings >
  Chat list view (off by default), which removes the search bar and search icon from the chat list.
- `multigram/`: the other MultiGram tools and notes, such as the per-install random style and
  its palette check; the app code is in
  `TMessagesProj/src/main/java/org/telegram/messenger/multigram/`.

## Repository settings

- `main` must be the default branch: scheduled workflows only run from it.
- The workflows ask for the token permissions they need, so the default workflow permissions
  can stay read-only.
- Issues must be enabled: the sync reports on an issue labelled `forkgram-sync`.
- If you protect `forkgram`, `multigram`, `multigram-next` or `multigram-before-*` tags with
  branch protection or rulesets, let GitHub Actions push and force-push them.
