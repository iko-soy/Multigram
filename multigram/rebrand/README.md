# Rebrand toolkit

One command gives a MultiGram build its own identity: its own applicationId, app name,
launcher, splash-screen and notification icons, signing key and Android account type.
Another command puts the stock identity back, byte for byte.

This is white-label rebranding of your own build of open-source software (GPLv2). It
changes only this build's own identity and does not touch the network protocol, the app's
behaviour or its features. The names, ids and icons it generates come from neutral word
lists and plain geometric shapes. Values you pass yourself (`--app-name`,
`--application-id`, `--account-type`) are only checked against a short blocklist: names
containing "Telegram" (Telegram's API terms do not let third-party apps use it),
Forkgram's own names and a few other well-known apps' names, and ids in the platform's,
Telegram's and some well-known vendors' namespaces. Choosing a name and an id that belong
to you, and that do not imitate another app, is your responsibility.

| File | What it is |
| --- | --- |
| `generate_rebrand.py` | The generator (Python 3, standard library only; `keytool` from any JDK for the key). |
| `rebrand.gradle` | Gradle glue, applied at the end of `TMessagesProj_App/build.gradle`. |
| `selftest.py` | Checks the generator on a throwaway copy of the tree. |
| `generated/`, `rebrand.properties` | The generator's output. Git-ignored, never committed. |

The stack also carries `org.telegram.messenger.multigram.Rebrand` and the resource
`bool/multigram_rebrand_active` (false in `TMessagesProj/src/main/res/values/multigram_rebrand.xml`,
true in the generated overlay), for the few things that live in code (see below).

## Quick start

From the repository root:

```bash
# A new random identity (the seed is printed and stored, so it can be repeated)
python3 multigram/rebrand/generate_rebrand.py

# The same identity every time for one distribution
python3 multigram/rebrand/generate_rebrand.py --seed my-distribution-1

# Pin values; keep the signing key outside the repository so later builds can update it
python3 multigram/rebrand/generate_rebrand.py --seed my-distribution-1 \
    --app-name "Quiet Cove" --application-id net.example.quietcove \
    --keystore ~/keys/quietcove.keystore

# Build as usual (your own API credentials, see below)
./gradlew -PAPP_ID=12345 -PAPP_HASH=0123456789abcdef0123456789abcdef \
    :TMessagesProj_App:assembleAfatRelease

# Back to the stock identity (the only way: see "How it wires in")
python3 multigram/rebrand/generate_rebrand.py --clean
```

Other options: `--account-type VALUE` (default: the applicationId), `--no-account-type`
(leave the three account-type files alone), `--no-keystore` (sign with the module's own
signing config, see "Signing and updates"), `--version-name` and `--version-code`
(default: keep the tree's). The version override sets the APK's `versionName` /
`versionCode`, and that is what Telegram's servers see (the app reports it as its
`app_version` when it connects, and servers may gate features on it). The in-app version
string, Forkgram's update check and the update state compare against
`TMessagesProj`'s own `BuildConfig.VERSION_NAME`, which stays the tree's.

The identity (applicationId, app name, icon, account type) is deterministic per `--seed`,
and an override such as `--app-name` does not change the other values for that seed. The
signing key is not: each run without `--keystore` makes a new one. `rebrand.properties`
records the options of the run in `REBRAND_RERUN`, and Gradle's error messages quote them.

## What changes and what does not

| Changed per build | Left as it is |
| --- | --- |
| `applicationId` (Gradle still adds `.beta` / `.web` per build type) | Java/Kotlin packages and the `namespace` (`org.telegram.messenger.regular`) |
| App name: `AppName`, `AppNameBeta`, `AppNameFdroid` (launcher label, account label, bundled in-app strings) and the default title of the chat list | Network protocol, API endpoints, API id/hash handling, features |
| Launcher icon (adaptive and legacy PNGs), the Default/Adaptive previews in the in-app icon picker, the account/contacts icon | The version, unless you pass `--version-name` / `--version-code` |
| Android 12+ splash-screen icon (light and dark) and the status-bar notification icon | `com.android.contacts`, the system's sync authority |
| Signing key | The contact-row MIME types (`vnd.org.telegram.messenger.android.*`) |
| Android account type (contact sync) and its "Account settings" entry | |
| The in-app icon picker offers only the build's own icon | |

The applicationId and the code package are independent in Android, so the installed
package can differ from the source namespace without code changes.

## How it wires in

`TMessagesProj_App/build.gradle` ends with one hook:

```groovy
// MultiGram: build-time rebrand, a no-op unless multigram/rebrand/rebrand.properties exists.
apply from: "${rootDir}/multigram/rebrand/rebrand.gradle"
```

Without `rebrand.properties` (or without `REBRAND_ACTIVE=true` in it) the script changes
nothing and the module builds with Forkgram's identity, provided the tree is clean: it
stops the build if `ContactsController.java`, `auth.xml` or `sync_contacts.xml` still
carries a rebrand's patch (each patched file is marked with a
`MultiGram rebrand: patched by ...` comment, which the stock tree never has). That happens
when `rebrand.properties` is deleted by hand, so always undo a rebrand with `--clean`.

`TMessagesProj_App` is the only app module in `settings.gradle`, so it is the only one
hooked. With the file present the script, running after the module's own `android {}`
block (AGP 8.13):

- sets `defaultConfig.applicationId`, replacing `org.forkclient.messenger` (or
  `org.forkgram.messenger` with `F_DROID=1`). The build types' `applicationIdSuffix` still
  applies, so a normal release build installs as `<id>.beta`, as Forkgram's does, and an
  F-Droid build as `<id>`. The `forkTest` flavor, which has its own applicationId
  (`org.forkclient.messenger.test`), becomes `<id>.test` (with `F_DROID=1` too); its debug
  build adds `.beta` as before, `<id>.test.beta`.
- adds `generated/res` to the resources of every build type. Build-type resources win over
  the main and flavor source sets and over the `TMessagesProj` library, so the generated
  strings, icons and the rebrand flag replace the stock ones without duplicate-resource
  errors.
- adds the generated app names as the last input of `TelegramStringsTask` (buildSrc),
  which builds the in-app string assets from the `strings.xml` files.
- points every signing config at the generated key. If `REBRAND_KEYSTORE` names a file
  that is missing, the build stops (see "Signing and updates").
- optionally sets `versionName` / `versionCode` (the module still turns the code into
  `code * 10 + ABI digit`).
- stops the build if the account type in the three patched files does not match
  `rebrand.properties`, since a half-patched tree would break contact sync. The message
  quotes the generator command, with the recorded options, that patches them again.
- generates, per variant, a copy of `xml/auth_menu.xml` whose `android:targetPackage` is
  that variant's applicationId (task `generate<Variant>RebrandAuthMenu`).

The lines starting with `[rebrand]` in the Gradle output list what was applied.

## App name

The launcher label comes from the manifest that the build type uses:
`TMessagesProj/config/debug/AndroidManifest_SDK23.xml` (`@string/AppNameBeta`) for normal
builds, `TMessagesProj/config/release/AndroidManifest_SDK23.xml` (`@string/AppName`) for
F-Droid builds, and `TMessagesProj_App/src/main/AndroidManifest.xml` (`@string/AppName`)
underneath. The account in Settings > Accounts uses `@string/AppName` too.
`AppNameFdroid` only feeds the `appLabel` placeholder in `TMessagesProj/build.gradle`,
which no manifest uses; it is set anyway. The generator writes all three into `values/`
and into every `values-*` folder whose `strings.xml` defines them.

The title of the main chat list is not a resource: Forkgram shows the preference
`forkCustomTitle` with the literal default `"Fork Client"` (`DialogsActivity`, and the
title editor in `ForkSettingsActivity`). A one-line `MultiGram:` hook in each place takes
the default from `Rebrand.defaultTitle("Fork Client")`, which returns the app's own
`R.string.AppName` in a rebranded build and `"Fork Client"` otherwise. It reads the app's
resources, not `LocaleController`, because cloud language packs carry Telegram's name for
`AppName`; `AppName` stays in `resources.arsc` because `TelegramStringsTask` keeps it.

When a cloud language pack is loaded, its strings take precedence over the bundled ones,
and those packs use Telegram's own name. Other bundled strings that name the upstream app
(for example "Fork Client Settings") are not changed.

## Icons

The default launcher entry is the `org.telegram.messenger.DefaultIcon` activity-alias in
`TMessagesProj/src/main/AndroidManifest.xml`, which uses `@mipmap/icon_01_launcher` and
`icon_01_launcher_round`; the application icon is `@mipmap/ic_launcher` and
`ic_launcher_round`. The overlay replaces these, `icon_01_launcher_adaptive` and
`icon_01_launcher_sa`, the picker previews `icon_01_foreground_sa` and
`icon_01_background_sa`, and `ic_launcher_dr` (account, contacts and call icon). Every
qualifier folder where the tree defines one of them gets a file: an adaptive icon
(background colour, vector foreground, monochrome layer for themed icons) in
`mipmap-anydpi-v26`, and a PNG of the same pixel size in each density folder.

It also replaces:

- the Android 12+ splash-screen icon: `drawable/splash_fork_320` (set in
  `values-v31/styles.xml`, Forkgram's fork mark) and `drawable/tg_splash_320` (set in
  `values-night/styles.xml`, Telegram's animated plane, used in dark mode) both become a
  320dp vector of the generated icon (background disc, mark in the launcher's
  proportions). Nothing refers to them from code, so a plain vector can replace the
  animated one.
- `drawable/notification` (`drawable-mdpi` to `-xxhdpi`), the small icon of message,
  service and migration notifications: a white disc with the generated mark cut out, in
  the same pixel sizes.

The alternative icons of the in-app picker (Original, Vintage, Aqua, Premium, Turbo, Nox)
are Telegram's own logos (Original, Aqua and Nox are Telegram's paper plane). Their
resources and activity-aliases stay in the APK, but a one-line `MultiGram:` hook in
`AppIconsSelectorCell` asks `Rebrand.filterLauncherIcons`, which keeps only the default
(the generated) icon in a rebranded build, so they cannot be picked. A stock build lists
all of them as before. The Telegram Premium screen still shows the premium icons as a
Premium feature.

The generator warns when a manifest's label or launcher icon, or a theme's splash icon,
comes from a resource it does not cover, e.g. after Forkgram renames its icons.

## Account type (contact sync)

Android's `AccountManager` keys the contact-sync account on one string, which has to be
the same in three places under `TMessagesProj/src/main`:

- `java/org/telegram/messenger/ContactsController.java`: five `"org.telegram.messenger"`
  literals (`getAccountsByType(...)`, `new Account(...)`);
- `res/xml/auth.xml` and `res/xml/sync_contacts.xml`: `android:accountType="${applicationId}"`.

AGP expands `${applicationId}` in manifests only, not in resource files, and nothing in
this tree processes those two files, so the APK carries the literal text
`${applicationId}` as its account type while the Java code asks for
`org.telegram.messenger`. That is how Forkgram ships; the stock build is not changed.

A rebranded build sets all three to one value: by default the new base applicationId
(without the `.beta` suffix). A Java literal cannot be replaced by a resource overlay, so
the generator patches the three files in place and marks each with a
`MultiGram rebrand: patched by ...` comment. It keeps the originals under
`generated/backup/`, always patches from the original (so a new seed works), and `--clean`
puts them back byte for byte. `git status` shows the three files as modified while the
rebrand is active; do not commit them. The guards:

- If a patched file changes after it was patched, `--clean` refuses to overwrite it, and a
  new run refuses to take it as the original; both say which file.
- If the backup is gone (for example after `rm -rf generated` or `git clean -X`), neither
  a new run nor `--clean` can restore the files: both refuse and tell you to run
  `git checkout -- <files>` first. `--clean` never reports success while a marked file is
  left.
- Gradle refuses to build a tree whose three files disagree with `rebrand.properties`,
  and, without an active rebrand, a tree that still has a marked file.

The account's "Account settings" entry in the system settings (`android:accountPreferences`
in `auth.xml`, i.e. `xml/auth_menu.xml`) opens `LaunchActivity` in
`android:targetPackage="org.telegram.messenger"`, another app. Stock Forkgram never shows
it, because its account cannot be created. A rebranded build's account works, so
`rebrand.gradle` generates, per variant, an `auth_menu.xml` that names the variant's own
applicationId (`<id>.beta`, `<id>.web`, `<id>.test.beta`, ...).

Two builds of one identity with different suffixes (e.g. `.beta` and `.web`) share the
account type, so only one of them can hold the account on a device.

The contact rows the app writes use the MIME types
`vnd.android.cursor.item/vnd.org.telegram.messenger.android.profile` / `.call` /
`.call.video` (`xml/contacts.xml`, `ContactsController`, `LaunchActivity`'s intent
filters), which Telegram and every fork share. They are left as they are, so with several
Telegram-family apps installed, tapping a synced contact row may show a chooser.

## google-services.json

This tree does not use it. `TMessagesProj_App/build.gradle` does not apply the
`com.google.gms.google-services` plugin, the root `build.gradle` does not put it on the
classpath, and Firebase is commented out (push goes through UnifiedPush). The
`google-services.json` files in the tree are DrKLO's and list `org.telegram.messenger`,
`.beta` and `.web`; nothing reads them. The generator leaves them alone and warns if the
plugin comes back: then the file must list the applicationId of every built variant
(`<id>`, `<id>.beta`, `<id>.web`, ...) from your own Firebase project.

## Telegram API credentials and other keys

Each distributor needs their own `api_id` and `api_hash` from https://my.telegram.org
(API development tools). The builds you make may share yours, but never ship someone
else's: not Telegram's, Forkgram's or another fork's. That is what Telegram's API terms
require.

This tree reads them as Gradle properties `APP_ID` and `APP_HASH`: `TMessagesProj/build.gradle`
turns them into `BuildConfig.APP_ID` / `APP_HASH`, and `BuildVars` uses those. The
checked-in `gradle.properties` has `APP_ID=0` and `APP_HASH=0`, which cannot log in. Pass
yours with `-PAPP_ID=... -PAPP_HASH=...` or put them in `~/.gradle/gradle.properties`
(`local.properties` is not read for these two).

The repository's CI reads them from the repository secrets `MULTIGRAM_APP_ID` and
`MULTIGRAM_APP_HASH` and appends them to `gradle.properties` for the APK build. CI does
not run the generator, so a CI APK has the stock identity (Forkgram's name, icons and
package) unless the ref it builds contains the rebrand output, and it is signed with the
in-tree `TMessagesProj/config/release.keystore`: such APKs are for testing only. Never
commit a keystore or `rebrand.properties` with real passwords.

Other values that are not yours to reuse:

- Forkgram's updater (`org.telegram.messenger.forkgram.AppUpdater`) asks the Telegram
  channel `UPDATE_CHANNEL_USERNAME`, then the GitHub releases of `USER_REPO`, and titles
  its dialog "The latest Forkgram version". Point both at your own channel and repository,
  or leave the checked-in inert values (`a` and `0`); never Forkgram's, or the app would
  offer Forkgram's APKs.
- `BuildVars` carries Telegram's `SAFETYNET_KEY` and `GOOGLE_AUTH_CLIENT_ID` (used by the
  login screen), which belong to Telegram's own app, and `SUPPORTS_PASSKEYS`, which the
  file says only works for the official app ids.

## Signing and updates

Android only installs an update that is signed with the same key, so the key is the
app's identity on a device.

- One-off builds: the default. Each run makes a new key in `generated/rebrand.keystore`,
  and `--clean` deletes it.
- Updatable builds: create the key once with `--keystore PATH` outside the repository.
  The first run creates `PATH` and `PATH.properties` (alias and password, mode 600); every
  later run with the same `--keystore PATH` reuses them, and `--clean` leaves them alone.
  Back both files up: without them no update can ever be shipped to existing installs. An
  update also needs the same identity (the same `--seed`, or the same pinned
  `--application-id` and `--account-type`) and a higher `--version-code` than the
  installed build (or a tree with a higher version).
- Your own key: run with `--no-keystore` and give the module's usual properties:
  `RELEASE_KEYSTORE_FILE`, `RELEASE_STORE_PASSWORD`, `RELEASE_KEY_ALIAS`,
  `RELEASE_KEY_PASSWORD`, as `-P` options or in `~/.gradle/gradle.properties`
  (`gradle.properties` in the tree already sets the last three, so `local.properties`
  cannot override them). Without `RELEASE_KEYSTORE_FILE` the module signs with
  `TMessagesProj/config/test.keystore`, whose password is in `TMessagesProj_App/build.gradle`:
  anyone with the source can sign an "update" that installs over such an APK and reads its
  data. Never distribute an APK signed with an in-tree key; Gradle prints a warning then.

If `rebrand.properties` names a keystore (`REBRAND_KEYSTORE`) that is not on disk, for
example an absolute `--keystore` path on another machine, the build stops instead of
falling back to the module's key. For a compile-only check without the key (as in CI),
add `REBRAND_ALLOW_STOCK_SIGNING=true` to `rebrand.properties`, or remove the four
`REBRAND_KEY*`/`REBRAND_STORE*` lines.

## What stays recognisable

This changes the static identity only. Things that still show the app's origin, because
changing them would break it or needs code changes:

- the MTProto network traffic and Telegram's API endpoints and deep-link hosts (`t.me`,
  `telegram.me`, `telegram.dog`, `tg:`);
- class and component names kept by `TMessagesProj/proguard-rules.pro`
  (`org.telegram.messenger.*` and others), the `org.telegram.messenger.regular` namespace,
  and the activity-alias names (`org.telegram.messenger.DefaultIcon`, ...);
- the native library `libtmessages.49.so` (CMake target `tmessages.49`);
- in-app texts that mention Telegram or Fork Client, and the cloud language packs;
- Telegram's wordmark (`drawable/telegram_logo_2`), which the chat list's stories header
  shows when it is collapsed, and the welcome screens' animation and texts;
- the public media folders `Telegram`, `Telegram Images`, `Telegram Video` and so on
  (`ImageLoader`);
- the contact-row MIME types (see "Account type");
- Forkgram's updater and the keys in `BuildVars` (see "Telegram API credentials and other
  keys");
- the alternative launcher icons' resources and activity-aliases (hidden from the picker,
  see "Icons").

## Checking it

```bash
python3 multigram/rebrand/selftest.py
```

runs the generator on a throwaway copy of the tree with several seeds and checks the
output (XML parses, PNG chunks and sizes, splash and notification icons, the rebrand flag,
the keystore opens, the account type and the patch marker in all three files), that each
seed repeats (also through `REBRAND_RERUN`) and seeds differ, that git sees only the three
patched files, the name and namespace guards, `--keystore` reuse, the guards against
edited files and a lost backup, and that `--clean` leaves the tree byte-identical. Run it
after moving the stack onto a new Forkgram release, and read the generator's warnings.
Whether contact sync and the account settings entry work can only be checked on a device.
