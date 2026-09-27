package org.telegram.messenger.multigram;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.text.TextUtils;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.FileLog;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.NotificationCenter;
import org.telegram.ui.ActionBar.Theme;

import java.nio.ByteBuffer;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.zip.CRC32;

/**
 * Per-install random style: every fresh install gets its own day and night style, picked by a random seed from
 * the bundled style table ({@link StyleTable}). Design and privacy notes: multigram/random-style/README.md.
 *
 * <ul>
 *   <li>Stage A, {@link #onApplicationCreate}: runs once per install, before anything touches Theme. On a fresh
 *       install it creates the seed and picks the style; installs that already have theme settings are marked
 *       {@link #STATE_EXISTING} and are never restyled automatically.</li>
 *   <li>Stage B, {@link #onThemeInit}: inside Theme's static initializer, after the saved accents are loaded. On a
 *       fresh install it turns the picked style into two runtime accents (day and night) and selects them, so the
 *       first frame already shows the style.</li>
 *   <li>{@link #shuffle}: "Shuffle my style" in Chat Settings: new seed, new style, applied at once, with
 *       {@link #undoShuffle} for a few seconds afterwards. {@link #resetToGeneratedStyle}: "Reset to defaults" also
 *       returns to the install's generated style (stock Chat Settings only resets text size and bubble radius).</li>
 *   <li>{@link StyleKnobs} (shapes and chat list layout from the same seed) is updated right before Shuffle, Undo and
 *       Reset show the style, because the theme switch reloads the wallpaper synchronously; listeners run after.</li>
 * </ul>
 *
 * The generated accents are local only: {@link #isGenerated} marks them, and the upload and share paths refuse them.
 * Nothing in the "rebrand_style" preferences file is ever sent anywhere.
 */
public final class RandomStyle {

    /** SharedPreferences file of this feature. Not in SettingsBackup's export and not in Android backup. */
    public static final String PREFS = "rebrand_style";

    /** Fresh install, style picked by Stage A, not yet turned into accents by Stage B. */
    public static final String STATE_PENDING = "pending";
    /** A generated style has been applied (automatically on a fresh install, or by Shuffle). */
    public static final String STATE_APPLIED = "applied";
    /** Fresh install whose automatic style could not be applied: it keeps the stock look until Shuffle. */
    public static final String STATE_FAILED = "failed";
    /** The install had theme settings before this feature: never restyled automatically, Shuffle still works. */
    public static final String STATE_EXISTING = "existing";

    /** {@link Listener} reasons. */
    public static final int REASON_SHUFFLE = 1;
    public static final int REASON_RESET = 2;
    /** Undo after a Shuffle: the previous seed and style are back. */
    public static final int REASON_UNDO = 3;

    /** Version of the pick algorithm below (seed -> table entries). */
    public static final int GENERATOR_VERSION = 1;

    private static final String KEY_STATE = "state";
    private static final String KEY_FRESH = "fresh";
    private static final String KEY_SEED = "seed";
    private static final String KEY_VERSION = "version";
    private static final String KEY_TABLE_CRC = "table_crc";
    private static final String KEY_GENERATED = "generated";
    /**
     * Copy of the generated-accent records in themeconfig, next to the accents they describe: Forkgram's settings
     * export (SettingsBackup) carries themeconfig but not this file, so an imported generated accent stays marked.
     */
    private static final String THEMECONFIG_GENERATED = "multigram_generated_accents";
    private static final String DAY = "day";
    private static final String NIGHT = "night";
    private static final String SUFFIX_THEME = "_theme";
    private static final String SUFFIX_STYLE = "_style";
    private static final String SUFFIX_INDEX = "_index";
    private static final String SUFFIX_ACCENT = "_accent";

    private static final long GOLDEN_GAMMA = 0x9E3779B97F4A7C15L;
    private static final long REMOVE_KEY = 0x100000000L;
    /** Record tag: the accent stays local whatever its colours (the accent editor may be changing them). */
    private static final String ANY = "*";

    /** Notified on the UI thread after Shuffle, Undo or Reset applied a style. */
    public interface Listener {
        void onStyleChanged(long seed, int reason);
    }

    private static final CopyOnWriteArrayList<Listener> listeners = new CopyOnWriteArrayList<>();

    /** What {@link #undoShuffle} returns to; memory only, because Undo is offered for a few seconds after a Shuffle. */
    private static Previous undo;

    private RandomStyle() {
    }

    // ---------------------------------------------------------------------------------------------
    // Queries (safe before Theme is initialised)
    // ---------------------------------------------------------------------------------------------

    /** True once this install has a seed: it was born with a generated style, or the user pressed Shuffle. */
    public static boolean hasSeed() {
        return prefs().contains(KEY_SEED);
    }

    /** The install's current style seed (changes on Shuffle); 0 when {@link #hasSeed()} is false. */
    public static long getSeed() {
        return prefs().getLong(KEY_SEED, 0);
    }

    /**
     * True when Stage A found no theme settings, i.e. this install gets the generated style automatically.
     * False for installs that existed before this feature (they are never restyled without Shuffle).
     */
    public static boolean isFreshInstall() {
        return prefs().getBoolean(KEY_FRESH, false);
    }

    /** One of the STATE_* values, or null before Stage A ran. */
    public static String getState() {
        return prefs().getString(KEY_STATE, null);
    }

    /** True when this install has a generated style that Reset returns to. */
    public static boolean hasGeneratedStyle() {
        SharedPreferences p = prefs();
        return STATE_APPLIED.equals(p.getString(KEY_STATE, null)) && loadStyle(p, false) != null && loadStyle(p, true) != null;
    }

    /** The install's current day (night = false) or night style, or null. */
    public static StyleTable.Entry getStyle(boolean night) {
        return loadStyle(prefs(), night);
    }

    /**
     * An independent 64-bit value for one knob, derived from the seed and the knob's name (FNV-1a 64 of the name's
     * UTF-16 units, XOR the seed, then the SplitMix64 finaliser). Deterministic, so the same seed always gives the
     * same knob value.
     */
    public static long deriveSeed(long seed, String knob) {
        long h = 0xcbf29ce484222325L;
        for (int i = 0; i < knob.length(); i++) {
            h ^= knob.charAt(i);
            h *= 0x100000001b3L;
        }
        return mix64(seed ^ h);
    }

    public static void addListener(Listener listener) {
        listeners.addIfAbsent(listener);
    }

    public static void removeListener(Listener listener) {
        listeners.remove(listener);
    }

    // ---------------------------------------------------------------------------------------------
    // Privacy
    // ---------------------------------------------------------------------------------------------

    /**
     * True for an accent this install generated, every later edit of it and every copy made from it in the accent
     * editor: such accents never leave the device. Recognised by a record of its theme key and id that also holds
     * its colours' fingerprint (or {@link #ANY} while the editor may change them), so a different accent that got
     * the same id, for example from a settings import, is not mistaken for it.
     */
    public static boolean isGenerated(Theme.ThemeAccent accent) {
        if (accent == null || accent.info != null || accent.id <= PaletteFix.LAST_STOCK_ACCENT_ID || accent.parentTheme == null) {
            return false;
        }
        try {
            Record r = readRecords(prefs()).get(recordKey(accent.parentTheme.getKey(), accent.id));
            return r != null && (r.tags.contains(ANY) || r.tags.contains(fingerprint(accent)));
        } catch (Throwable e) {
            FileLog.e(e);
            return true; // unsure: keep it on the device
        }
    }

    /**
     * ThemePreviewActivity hook, right after the accent editor got its accent (copied = a new accent, otherwise the
     * current accent is edited in place). A new accent ("+" in the accent list) starts as a copy of the theme's
     * current accent (Theme.ThemeInfo.getAccent(true) sets prevAccentId to it), and saving uploads it. A copy of a
     * generated accent, and a generated accent opened for editing, are therefore marked {@link #ANY}: they stay on
     * the device whatever colours the editor gives them. The save adds the new fingerprint ({@link #isUploadBlocked})
     * and the next start narrows the record to the colours on disk. Never throws.
     */
    public static void onAccentCopied(Theme.ThemeInfo theme, Theme.ThemeAccent accent, boolean copied) {
        try {
            if (theme == null || accent == null) {
                return;
            }
            if (copied) {
                if (theme.themeAccentsMap == null || theme.prevAccentId == -1) {
                    return;
                }
                Theme.ThemeAccent source = theme.themeAccentsMap.get(theme.prevAccentId);
                if (source == null || source == accent || !isGenerated(source)) {
                    return;
                }
            } else if (!isGenerated(accent)) {
                return;
            }
            SharedPreferences p = prefs();
            LinkedHashMap<String, Record> records = readRecords(p);
            if (addTag(records, theme, accent, ANY)) {
                writeRecords(p, records, true);
            }
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /**
     * MessagesController.saveThemeToServer hook: true when the upload must not happen. Saving an edited accent
     * reaches it too, so it also records the accent's colours as they are now.
     */
    public static boolean isUploadBlocked(Theme.ThemeInfo themeInfo, Theme.ThemeAccent accent) {
        if (!isGenerated(accent)) {
            return false;
        }
        try {
            SharedPreferences p = prefs();
            LinkedHashMap<String, Record> records = readRecords(p);
            if (addTag(records, accent.parentTheme, accent, fingerprint(accent))) {
                writeRecords(p, records, true);
            }
        } catch (Throwable e) {
            FileLog.e(e);
        }
        FileLog.d("MultiGram: a generated style stays on this device; theme upload skipped");
        return true;
    }

    // ---------------------------------------------------------------------------------------------
    // Stage A: ApplicationLoader.onCreate
    // ---------------------------------------------------------------------------------------------

    /**
     * Classifies the install once (fresh or existing) and, on a fresh install, creates the seed and picks the style.
     * Must run before anything touches Theme. Never throws.
     */
    public static void onApplicationCreate(Context context) {
        try {
            SharedPreferences p = context.getSharedPreferences(PREFS, Activity.MODE_PRIVATE);
            if (p.contains(KEY_STATE)) {
                return;
            }
            SharedPreferences.Editor editor = p.edit();
            if (hasThemeSettings(context)) {
                editor.putBoolean(KEY_FRESH, false).putString(KEY_STATE, STATE_EXISTING);
            } else {
                long seed = new SecureRandom().nextLong();
                editor.putBoolean(KEY_FRESH, true).putLong(KEY_SEED, seed).putInt(KEY_VERSION, GENERATOR_VERSION);
                boolean picked = false;
                try {
                    picked = pick(StyleTable.load(context), seed, editor);
                } catch (Throwable e) {
                    FileLog.e(e);
                }
                editor.putString(KEY_STATE, picked ? STATE_PENDING : STATE_FAILED);
            }
            editor.commit();
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /**
     * Whether the install already has theme settings. Theme writes themeconfig 'remote_version' on every start, so
     * any themeconfig key means Theme has run before; mainconfig 'theme' / 'nighttheme' are the saved theme choices.
     */
    private static boolean hasThemeSettings(Context context) {
        SharedPreferences themeConfig = context.getSharedPreferences("themeconfig", Activity.MODE_PRIVATE);
        if (!themeConfig.getAll().isEmpty()) {
            return true;
        }
        SharedPreferences mainConfig = context.getSharedPreferences("mainconfig", Activity.MODE_PRIVATE);
        return mainConfig.contains("theme") || mainConfig.contains("nighttheme") || mainConfig.contains("selectedAutoNightType");
    }

    // ---------------------------------------------------------------------------------------------
    // Stage B: Theme's static initializer
    // ---------------------------------------------------------------------------------------------

    /**
     * Called by Theme's static initializer after the saved accents are loaded and before the auto-night settings
     * are read. On a fresh install it creates and selects the generated day and night accents and returns the day
     * theme to apply; otherwise it returns applyingTheme unchanged. Never throws: on any error the install keeps
     * the stock style.
     */
    public static Theme.ThemeInfo onThemeInit(Theme.ThemeInfo applyingTheme) {
        try {
            SharedPreferences p = prefs();
            pruneRecords(p, true);
            if (!STATE_PENDING.equals(p.getString(KEY_STATE, null))) {
                return applyingTheme;
            }
            if (Theme.getActiveTheme() != null || Theme.getCurrentNightTheme() == null) {
                return applyingTheme; // not inside Theme's initializer as expected (nothing may be applied yet)
            }
            // Decided once: if anything below fails (even fatally) the next start keeps the stock style.
            p.edit().putString(KEY_STATE, STATE_FAILED).commit();

            Pair pair = createPair(p, loadStyle(p, false), loadStyle(p, true), true);
            if (pair == null) {
                return applyingTheme;
            }
            Theme.setCurrentNightTheme(pair.nightTheme); // no visible effect: nothing is applied yet
            ApplicationLoader.applicationContext.getSharedPreferences("mainconfig", Activity.MODE_PRIVATE).edit()
                    .putString("theme", pair.dayTheme.getKey())
                    .putString("nighttheme", pair.nightTheme.getKey())
                    .apply();
            saveSelection(pair);
            putPair(p.edit(), pair).putString(KEY_STATE, STATE_APPLIED).commit();
            return pair.dayTheme;
        } catch (Throwable e) {
            FileLog.e(e);
            return applyingTheme;
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Shuffle and Reset (UI thread)
    // ---------------------------------------------------------------------------------------------

    /**
     * "Shuffle my style": a new seed, a new day and night style, applied at once (the variant that is showing is
     * animated in, the other one is switched silently). The previous generated accents are removed unless the user
     * edited them. Custom themes and the user's own accents are never touched. When the generated style was showing,
     * {@link #undoShuffle} can bring it back afterwards ({@link #canUndoShuffle}). Returns false on failure, in which
     * case nothing changed.
     */
    public static boolean shuffle(Context context) {
        try {
            StyleTable table = StyleTable.load(context);
            long seed = new SecureRandom().nextLong();
            int dayIndex = pickIndex(seed, false, table.getCount(false));
            int nightIndex = pickIndex(seed, true, table.getCount(true));
            StyleTable.Entry day = table.get(false, dayIndex);
            StyleTable.Entry night = table.get(true, nightIndex);
            SharedPreferences p = prefs();
            Previous previous = generatedStyleShowing(p) ? capture(p) : null;
            Pair pair = replacePair(p, day, night);
            if (pair == null) {
                return false;
            }
            SharedPreferences.Editor editor = p.edit()
                    .putLong(KEY_SEED, seed)
                    .putInt(KEY_VERSION, GENERATOR_VERSION)
                    .putInt(KEY_TABLE_CRC, table.getCrc());
            putStyle(editor, DAY, day, dayIndex);
            putStyle(editor, NIGHT, night, nightIndex);
            putPair(editor, pair).putString(KEY_STATE, STATE_APPLIED).commit();
            if (previous != null) {
                previous.shuffledSeed = seed;
            }
            undo = previous;
            StyleKnobs.onStyleApplying(seed); // before the theme switch, which reloads the wallpaper at once
            show(pair);
            notifyListeners(seed, REASON_SHUFFLE);
            return true;
        } catch (Throwable e) {
            FileLog.e(e);
            return false;
        }
    }

    /** True right after a Shuffle that replaced the generated style that was showing: {@link #undoShuffle} brings it back. */
    public static boolean canUndoShuffle() {
        Previous u = undo;
        return u != null && prefs().getLong(KEY_SEED, 0) == u.shuffledSeed;
    }

    /**
     * Undo for the last Shuffle: the previous seed and generated style come back (as new accents; the shuffled ones
     * are removed unless edited). Returns false, with nothing changed, when there is nothing to undo or it failed.
     */
    public static boolean undoShuffle() {
        Previous u = undo;
        undo = null;
        if (u == null) {
            return false;
        }
        try {
            SharedPreferences p = prefs();
            if (p.getLong(KEY_SEED, 0) != u.shuffledSeed || !STATE_APPLIED.equals(p.getString(KEY_STATE, null))) {
                return false;
            }
            Pair pair = replacePair(p, u.day, u.night);
            if (pair == null) {
                return false;
            }
            SharedPreferences.Editor editor = p.edit()
                    .putLong(KEY_SEED, u.seed)
                    .putInt(KEY_VERSION, u.version)
                    .putInt(KEY_TABLE_CRC, u.tableCrc);
            putStyle(editor, DAY, u.day, u.dayIndex);
            putStyle(editor, NIGHT, u.night, u.nightIndex);
            putPair(editor, pair).commit();
            StyleKnobs.onStyleApplying(u.seed);
            show(pair);
            notifyListeners(u.seed, REASON_UNDO);
            return true;
        } catch (Throwable e) {
            FileLog.e(e);
            return false;
        }
    }

    /**
     * "Reset to defaults" in Chat Settings. Stock Chat Settings only resets text size and bubble radius there (its
     * colour branch needs the theme list, which that screen no longer has), so this adds the colours: back to this
     * install's generated style (the one the seed picked), recreating its accents so that edits made to them are
     * left alone. It leaves a custom, cloud or Monet theme the user chose alone. Returns false, with nothing changed,
     * when the install has no generated style or such a theme is selected.
     */
    public static boolean resetToGeneratedStyle() {
        try {
            undo = null;
            if (!hasGeneratedStyle() || !isColorTheme(Theme.getCurrentTheme()) || !isColorTheme(Theme.getCurrentNightTheme())
                    || !isColorTheme(Theme.getActiveTheme())) {
                return false;
            }
            SharedPreferences p = prefs();
            Pair pair = replacePair(p, loadStyle(p, false), loadStyle(p, true));
            if (pair == null) {
                return false;
            }
            putPair(p.edit(), pair).commit();
            StyleKnobs.onStyleApplying(p.getLong(KEY_SEED, 0));
            show(pair);
            notifyListeners(p.getLong(KEY_SEED, 0), REASON_RESET);
            return true;
        } catch (Throwable e) {
            FileLog.e(e);
            return false;
        }
    }

    /** A bundled colour theme (Blue, Day, Dark Blue, ...), not a custom or cloud theme file and not Monet. */
    private static boolean isColorTheme(Theme.ThemeInfo theme) {
        return theme != null && theme.assetName != null && !theme.isMonet();
    }

    /** Whether the theme showing now uses the generated day or night accent. */
    private static boolean generatedStyleShowing(SharedPreferences p) {
        Theme.ThemeInfo active = Theme.getActiveTheme();
        if (active == null || !hasGeneratedStyle()) {
            return false;
        }
        String key = active.getKey();
        return key.equals(p.getString(DAY + SUFFIX_THEME, null)) && active.currentAccentId == p.getInt(DAY + SUFFIX_ACCENT, -1)
                || key.equals(p.getString(NIGHT + SUFFIX_THEME, null)) && active.currentAccentId == p.getInt(NIGHT + SUFFIX_ACCENT, -1);
    }

    private static Previous capture(SharedPreferences p) {
        Previous u = new Previous();
        u.seed = p.getLong(KEY_SEED, 0);
        u.version = p.getInt(KEY_VERSION, GENERATOR_VERSION);
        u.tableCrc = p.getInt(KEY_TABLE_CRC, 0);
        u.day = loadStyle(p, false);
        u.night = loadStyle(p, true);
        u.dayIndex = p.getInt(DAY + SUFFIX_INDEX, -1);
        u.nightIndex = p.getInt(NIGHT + SUFFIX_INDEX, -1);
        return u.day != null && u.night != null ? u : null;
    }

    /**
     * Creates the new pair, then deletes the previous generated pair unless the user edited it (it is theirs now;
     * it stays marked as generated, so it still never leaves the device). Returns null, with nothing changed, on
     * failure.
     */
    private static Pair replacePair(SharedPreferences p, StyleTable.Entry day, StyleTable.Entry night) {
        ArrayList<Old> old = new ArrayList<>(2);
        addOld(old, p, false);
        addOld(old, p, true);
        Pair pair = createPair(p, day, night, false);
        if (pair == null) {
            return null;
        }
        ArrayList<Theme.ThemeInfo> changed = new ArrayList<>(4);
        changed.add(pair.dayTheme);
        changed.add(pair.nightTheme);
        for (Old o : old) {
            Theme.ThemeInfo theme = Theme.getTheme(o.themeKey);
            if (theme == null || theme.themeAccentsMap == null) {
                continue;
            }
            Theme.ThemeAccent accent = theme.themeAccentsMap.get(o.id);
            if (accent != null && accent != pair.dayAccent && accent != pair.nightAccent && isUnedited(accent, o.style)) {
                Theme.deleteThemeAccent(theme, accent, false); // local accent: no server call; saved below
                if (!changed.contains(theme)) {
                    changed.add(theme);
                }
            }
        }
        for (Theme.ThemeInfo theme : changed) {
            Theme.saveThemeAccents(theme, true, false, false, false);
        }
        pruneRecords(p, false);
        saveSelection(pair);
        return pair;
    }

    /** Applies the variant that is showing (animated, stock path) and switches the other one silently. */
    private static void show(Pair pair) {
        Theme.ThemeInfo active = Theme.getActiveTheme();
        boolean darkShowing = active != null && active.isDark();
        boolean autoNightShowing = darkShowing && Theme.selectedAutoNightType != Theme.AUTO_NIGHT_TYPE_NONE && Theme.isCurrentThemeNight();
        SharedPreferences.Editor main = MessagesController.getGlobalMainSettings().edit();
        main.putString("nighttheme", pair.nightTheme.getKey());
        // Only records the night theme: the variants are both dark or both light here, so nothing switches.
        Theme.setCurrentNightTheme(pair.nightTheme);
        if (!darkShowing) {
            // Day showing: the day style becomes the day theme (the apply writes mainconfig 'theme').
            post(pair.dayTheme, false, pair.dayAccent.id);
        } else if (autoNightShowing) {
            // Night showing through auto-night: the night style is shown, the day style waits for the next switch.
            Theme.setCurrentDayTheme(pair.dayTheme);
            main.putString("theme", pair.dayTheme.getKey());
            post(pair.nightTheme, true, pair.nightAccent.id);
        } else {
            // A dark theme is the day theme (manual night mode): stay dark with the new night style; the day/night
            // toggle switches to the new day style (themeconfig 'lastDayTheme').
            post(pair.nightTheme, false, pair.nightAccent.id);
        }
        main.apply();
    }

    private static void post(Theme.ThemeInfo theme, boolean night, int accentId) {
        NotificationCenter.getGlobalInstance().postNotificationName(NotificationCenter.needSetDayNightTheme, theme, night, null, accentId);
    }

    private static void notifyListeners(long seed, int reason) {
        for (Listener l : listeners) {
            try {
                l.onStyleChanged(seed, reason);
            } catch (Throwable e) {
                FileLog.e(e);
            }
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Accents
    // ---------------------------------------------------------------------------------------------

    private static final class Pair {
        Theme.ThemeInfo dayTheme;
        Theme.ThemeInfo nightTheme;
        Theme.ThemeAccent dayAccent;
        Theme.ThemeAccent nightAccent;
    }

    private static final class Old {
        String themeKey;
        int id;
        StyleTable.Entry style;
    }

    private static final class Previous {
        long shuffledSeed; // the seed that Shuffle created; Undo applies only while it is current
        long seed;
        int version;
        int tableCrc;
        StyleTable.Entry day;
        StyleTable.Entry night;
        int dayIndex;
        int nightIndex;
    }

    /**
     * Creates the day and night accents from two table entries, makes each its theme's current accent, records
     * them as generated and saves them (never uploaded). Returns null, with nothing changed, when either cannot be
     * created.
     */
    private static Pair createPair(SharedPreferences p, StyleTable.Entry day, StyleTable.Entry night, boolean themeInit) {
        Theme.ThemeInfo dayTheme = baseTheme(day, false);
        Theme.ThemeInfo nightTheme = baseTheme(night, true);
        if (dayTheme == null || nightTheme == null) {
            return null;
        }
        int dayCurrent = dayTheme.currentAccentId;
        int nightCurrent = nightTheme.currentAccentId;
        Pair pair = new Pair();
        pair.dayTheme = dayTheme;
        pair.nightTheme = nightTheme;
        try {
            pair.dayAccent = addAccent(dayTheme, day);
            pair.nightAccent = pair.dayAccent != null ? addAccent(nightTheme, night) : null;
        } catch (Throwable e) {
            FileLog.e(e);
        }
        if (pair.dayAccent == null || pair.nightAccent == null) {
            removeAccent(dayTheme, pair.dayAccent, dayCurrent);
            removeAccent(nightTheme, pair.nightAccent, nightCurrent);
            return null;
        }
        // Recorded before saving, so a generated accent is never on disk without its local-only mark.
        LinkedHashMap<String, Record> records = readRecords(p);
        addTag(records, dayTheme, pair.dayAccent, fingerprint(pair.dayAccent));
        addTag(records, nightTheme, pair.nightAccent, fingerprint(pair.nightAccent));
        writeRecords(p, records, true);
        if (themeInit) {
            // Inside Theme's static initializer: no notifications (migration = true), no upload.
            Theme.saveThemeAccents(dayTheme, true, false, false, false, true);
            Theme.saveThemeAccents(nightTheme, true, false, false, false, true);
        }
        return pair;
    }

    private static Theme.ThemeInfo baseTheme(StyleTable.Entry entry, boolean night) {
        if (entry == null || entry.night != night) {
            return null;
        }
        Theme.ThemeInfo theme = Theme.getTheme(entry.themeKey);
        if (theme == null || theme.assetName == null || theme.isMonet() || theme.isDark() != night
                || theme.themeAccents == null || theme.themeAccentsMap == null) {
            return null;
        }
        return theme;
    }

    /**
     * A new runtime accent (next free id above 100, info == null, no pattern) on theme, set up exactly as the table
     * was validated (multigram/tools/README.md, "Applying an entry") and made the theme's current accent.
     */
    private static Theme.ThemeAccent addAccent(Theme.ThemeInfo theme, StyleTable.Entry e) {
        // getAccent(true) copies the current accent's own wallpaper files into the new accent; it gets none.
        Theme.OverrideWallpaperInfo wallpaper = theme.overrideWallpaper;
        theme.overrideWallpaper = null;
        Theme.ThemeAccent a = theme.getAccent(true);
        if (a == null) {
            theme.overrideWallpaper = wallpaper;
            return null;
        }
        a.accentColor = e.accent;
        a.accentColor2 = 0;
        a.myMessagesAccentColor = e.bubble;
        a.myMessagesGradientAccentColor1 = e.bubbleGradient1;
        a.myMessagesGradientAccentColor2 = e.bubbleGradient2;
        a.myMessagesGradientAccentColor3 = e.bubbleGradient3;
        a.myMessagesAnimated = e.isAnimated();
        a.backgroundOverrideColor = e.wallpaper1;
        a.backgroundGradientOverrideColor1 = e.wallpaper2;
        a.backgroundGradientOverrideColor2 = e.wallpaper3 != 0 ? e.wallpaper3 : REMOVE_KEY;
        a.backgroundGradientOverrideColor3 = e.wallpaper4 != 0 ? e.wallpaper4 : REMOVE_KEY;
        a.backgroundRotation = e.rotation;
        a.patternSlug = ""; // no pattern: nothing to download, nothing to install on the server
        a.patternIntensity = 0f;
        a.patternMotion = e.isMotion();
        a.pattern = null;
        a.overrideWallpaper = null;
        a.info = null;
        a.isDefault = false;
        theme.overrideWallpaper = null;
        return a;
    }

    private static void removeAccent(Theme.ThemeInfo theme, Theme.ThemeAccent accent, int previousCurrentId) {
        if (accent == null) {
            return;
        }
        theme.themeAccentsMap.remove(accent.id);
        theme.themeAccents.remove(accent);
        theme.prevAccentId = -1;
        theme.setCurrentAccentId(previousCurrentId);
    }

    /**
     * True when the accent is still exactly as the style made it: the same colours, no pattern and no chat background
     * of its own ("Change chat background" attaches one to the current accent; deleting the accent deletes it too).
     */
    private static boolean isUnedited(Theme.ThemeAccent a, StyleTable.Entry e) {
        return e != null && a.info == null && a.overrideWallpaper == null
                && a.accentColor == e.accent
                && a.accentColor2 == 0
                && a.myMessagesAccentColor == e.bubble
                && a.myMessagesGradientAccentColor1 == e.bubbleGradient1
                && a.myMessagesGradientAccentColor2 == e.bubbleGradient2
                && a.myMessagesGradientAccentColor3 == e.bubbleGradient3
                && a.myMessagesAnimated == e.isAnimated()
                && (int) a.backgroundOverrideColor == e.wallpaper1
                && (int) a.backgroundGradientOverrideColor1 == e.wallpaper2
                && (int) a.backgroundGradientOverrideColor2 == e.wallpaper3
                && (int) a.backgroundGradientOverrideColor3 == e.wallpaper4
                && a.backgroundRotation == e.rotation
                && a.patternMotion == e.isMotion()
                && Math.abs(a.patternIntensity) < 0.001f
                && TextUtils.isEmpty(a.patternSlug);
    }

    /** Remembers the chosen pair where the stock day/night toggle and the chat-theme strip look for it. */
    private static void saveSelection(Pair pair) {
        themeConfig().edit()
                .putString("lastDayTheme", pair.dayTheme.getKey())
                .putString("lastDarkTheme", pair.nightTheme.getKey())
                .putString("lastDayCustomTheme", pair.dayTheme.getKey())
                .putInt("lastDayCustomThemeAccentId", pair.dayAccent.id)
                .putString("lastDarkCustomTheme", pair.nightTheme.getKey())
                .putInt("lastDarkCustomThemeAccentId", pair.nightAccent.id)
                .apply();
    }

    // ---------------------------------------------------------------------------------------------
    // Seed -> table entries, stored style
    // ---------------------------------------------------------------------------------------------

    /** SplitMix64 finaliser. */
    private static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }

    /** Index among the day (or night) entries: SplitMix64 outputs 1 (day) and 2 (night) of the seed, uniform. */
    private static int pickIndex(long seed, boolean night, int count) {
        long r = mix64(seed + (night ? 2 : 1) * GOLDEN_GAMMA);
        return (int) ((r >>> 1) % count);
    }

    /** Picks the day and night entries for seed and stores them (not committed) in editor. */
    private static boolean pick(StyleTable table, long seed, SharedPreferences.Editor editor) {
        int dayIndex = pickIndex(seed, false, table.getCount(false));
        int nightIndex = pickIndex(seed, true, table.getCount(true));
        StyleTable.Entry day = table.get(false, dayIndex);
        StyleTable.Entry night = table.get(true, nightIndex);
        if (day == null || night == null) {
            return false;
        }
        editor.putInt(KEY_TABLE_CRC, table.getCrc());
        putStyle(editor, DAY, day, dayIndex);
        putStyle(editor, NIGHT, night, nightIndex);
        return true;
    }

    private static void putStyle(SharedPreferences.Editor editor, String variant, StyleTable.Entry e, int index) {
        editor.putString(variant + SUFFIX_THEME, e.themeKey)
                .putString(variant + SUFFIX_STYLE, e.toHex())
                .putInt(variant + SUFFIX_INDEX, index)
                .remove(variant + SUFFIX_ACCENT);
    }

    private static SharedPreferences.Editor putPair(SharedPreferences.Editor editor, Pair pair) {
        return editor.putString(DAY + SUFFIX_THEME, pair.dayTheme.getKey())
                .putInt(DAY + SUFFIX_ACCENT, pair.dayAccent.id)
                .putString(NIGHT + SUFFIX_THEME, pair.nightTheme.getKey())
                .putInt(NIGHT + SUFFIX_ACCENT, pair.nightAccent.id);
    }

    private static StyleTable.Entry loadStyle(SharedPreferences p, boolean night) {
        String variant = night ? NIGHT : DAY;
        return StyleTable.Entry.fromHex(p.getString(variant + SUFFIX_THEME, null), night, p.getString(variant + SUFFIX_STYLE, null));
    }

    private static void addOld(ArrayList<Old> out, SharedPreferences p, boolean night) {
        String variant = night ? NIGHT : DAY;
        Old o = new Old();
        o.themeKey = p.getString(variant + SUFFIX_THEME, null);
        o.id = p.getInt(variant + SUFFIX_ACCENT, -1);
        o.style = loadStyle(p, night);
        if (o.themeKey != null && o.id > PaletteFix.LAST_STOCK_ACCENT_ID && o.style != null) {
            out.add(o);
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Generated-accent records: "<theme key>|<accent id>|<tags>" separated by ';'. Tags, separated by ',', are
    // fingerprints of the accent's colours (8 hex digits) or ANY.
    // ---------------------------------------------------------------------------------------------

    private static final class Record {
        final String themeKey;
        final int id;
        final LinkedHashSet<String> tags = new LinkedHashSet<>();

        Record(String themeKey, int id) {
            this.themeKey = themeKey;
            this.id = id;
        }

        @Override
        public String toString() {
            return recordKey(themeKey, id) + "|" + TextUtils.join(",", tags);
        }
    }

    private static String recordKey(String themeKey, int id) {
        return themeKey + "|" + id;
    }

    /** CRC-32 of the values that make up an accent's style, as 8 hex digits. */
    static String fingerprint(Theme.ThemeAccent a) {
        ByteBuffer b = ByteBuffer.allocate(64);
        b.putInt(a.accentColor).putInt(a.accentColor2).putInt(a.myMessagesAccentColor)
                .putInt(a.myMessagesGradientAccentColor1).putInt(a.myMessagesGradientAccentColor2).putInt(a.myMessagesGradientAccentColor3)
                .put((byte) (a.myMessagesAnimated ? 1 : 0))
                .putLong(a.backgroundOverrideColor).putLong(a.backgroundGradientOverrideColor1)
                .putLong(a.backgroundGradientOverrideColor2).putLong(a.backgroundGradientOverrideColor3)
                .putInt(a.backgroundRotation);
        CRC32 crc = new CRC32();
        crc.update(b.array(), 0, b.position());
        return String.format(Locale.US, "%08x", crc.getValue());
    }

    private static void parseRecords(String s, LinkedHashMap<String, Record> out) {
        if (TextUtils.isEmpty(s)) {
            return;
        }
        for (String entry : s.split(";")) {
            String[] parts = entry.split("\\|", -1);
            if (parts.length < 2 || parts.length > 3 || parts[0].isEmpty()) {
                continue;
            }
            int id;
            try {
                id = Integer.parseInt(parts[1]);
            } catch (NumberFormatException e) {
                continue;
            }
            String key = recordKey(parts[0], id);
            Record r = out.get(key);
            if (r == null) {
                r = new Record(parts[0], id);
                out.put(key, r);
            }
            boolean tagged = false;
            if (parts.length == 3) {
                for (String tag : parts[2].split(",")) {
                    if (!tag.isEmpty()) {
                        r.tags.add(tag);
                        tagged = true;
                    }
                }
            }
            if (!tagged) {
                r.tags.add(ANY); // no fingerprint recorded: keep it on the device
            }
        }
    }

    /** The records of this file and of themeconfig's copy together (after a settings import they can differ). */
    private static LinkedHashMap<String, Record> readRecords(SharedPreferences p) {
        LinkedHashMap<String, Record> out = new LinkedHashMap<>();
        parseRecords(p.getString(KEY_GENERATED, null), out);
        parseRecords(themeConfig().getString(THEMECONFIG_GENERATED, null), out);
        return out;
    }

    /** Adds tag to the accent's record, creating it; returns whether anything changed. */
    private static boolean addTag(LinkedHashMap<String, Record> records, Theme.ThemeInfo theme, Theme.ThemeAccent accent, String tag) {
        String key = recordKey(theme.getKey(), accent.id);
        Record r = records.get(key);
        if (r == null) {
            r = new Record(theme.getKey(), accent.id);
            records.put(key, r);
        }
        return r.tags.add(tag);
    }

    /**
     * Writes the records to this file and to themeconfig's copy (only that key: other themeconfig keys are kept).
     * Adding a record is committed (sync), so a generated accent is never on disk without its mark; dropping one
     * can be applied lazily.
     */
    private static void writeRecords(SharedPreferences p, LinkedHashMap<String, Record> records, boolean sync) {
        String joined = TextUtils.join(";", records.values());
        SharedPreferences.Editor own = p.edit().putString(KEY_GENERATED, joined);
        SharedPreferences.Editor copy = themeConfig().edit().putString(THEMECONFIG_GENERATED, joined);
        if (sync) {
            own.commit();
            copy.commit();
        } else {
            own.apply();
            copy.apply();
        }
    }

    /**
     * Drops records of accents that no longer exist (deleted by the user or by Shuffle). At start (Theme's
     * initializer, before anything can upload) it also checks each record against the accent as saved: ANY and
     * matching records are narrowed to the saved colours' fingerprint, and a record whose accent has other colours
     * is dropped, because that accent is not the one that was generated (a settings import replaced it).
     */
    private static void pruneRecords(SharedPreferences p, boolean atStart) {
        try {
            LinkedHashMap<String, Record> records = readRecords(p);
            LinkedHashMap<String, Record> kept = new LinkedHashMap<>();
            for (Record r : records.values()) {
                Theme.ThemeInfo theme = Theme.getTheme(r.themeKey);
                Theme.ThemeAccent accent = theme != null && theme.themeAccentsMap != null ? theme.themeAccentsMap.get(r.id) : null;
                if (accent == null || accent.info != null) {
                    continue;
                }
                if (atStart) {
                    String fingerprint = fingerprint(accent);
                    if (!r.tags.contains(ANY) && !r.tags.contains(fingerprint)) {
                        continue;
                    }
                    r.tags.clear();
                    r.tags.add(fingerprint);
                }
                kept.put(recordKey(r.themeKey, r.id), r);
            }
            String joined = TextUtils.join(";", kept.values());
            if (!joined.equals(p.getString(KEY_GENERATED, "")) || !joined.equals(themeConfig().getString(THEMECONFIG_GENERATED, ""))) {
                writeRecords(p, kept, false);
            }
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    private static SharedPreferences prefs() {
        return ApplicationLoader.applicationContext.getSharedPreferences(PREFS, Activity.MODE_PRIVATE);
    }

    private static SharedPreferences themeConfig() {
        return ApplicationLoader.applicationContext.getSharedPreferences("themeconfig", Activity.MODE_PRIVATE);
    }
}
