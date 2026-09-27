package org.telegram.messenger.multigram;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.drawable.Drawable;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.FileLog;
import org.telegram.messenger.SharedConfig;
import org.telegram.ui.ActionBar.Theme;

/**
 * Per-install shapes and chat list layout ("style knobs"), driven by the install's style seed
 * ({@link RandomStyle#getSeed()}): bubble corner radius, two- or three-line chat list, service pill, reaction chip,
 * call-to-action button, floating action button and settings card corners, and the starting phase of the chat
 * wallpaper gradient. Avatars keep their shape (see the README). Design and limits: multigram/style-knobs/README.md.
 *
 * <ul>
 *   <li>Every knob has its own stream, {@link RandomStyle#deriveSeed}(seed, knob name), so a knob added later
 *       never changes the others. The values are stored ({@link #PREFS}) with the seed they came from, so an app
 *       update that changes a range never restyles an install; only a new seed (Shuffle, Undo) re-derives them.</li>
 *   <li>Installs without a seed (existing installs that never pressed "Shuffle my style") keep every stock value:
 *       each hook returns the stock value it is given.</li>
 *   <li>The two knobs that are stock settings (bubble radius, chat list layout) are written into mainconfig only
 *       while the setting is still at its stock default or at the value this class gave it, so a value the user
 *       picked always stays. The settings keep working as before.</li>
 *   <li>Accessibility settings (text size) are never written.</li>
 * </ul>
 *
 * Every public method never throws and is cheap enough for draw calls.
 */
public final class StyleKnobs {

    /** This feature's own preferences file: the derived values and what it last wrote into mainconfig. */
    public static final String PREFS = "rebrand_style_knobs";
    /** Version of the ranges and choices below; stored with the values it derived. */
    public static final int VERSION = 1;

    // Stream names for RandomStyle.deriveSeed. Never rename one: that would re-roll the knob for every new seed.
    // "avatar-shape" is reserved for a future avatar knob (see the README): Forkgram's Rounded mode is not used.
    static final String KNOB_BUBBLE_RADIUS = "bubble-radius";
    static final String KNOB_CHAT_LIST_DENSITY = "chat-list-density";
    static final String KNOB_REACTION_CHIP = "reaction-chip-shape";
    static final String KNOB_CTA_RADIUS = "cta-button-radius";
    static final String KNOB_FAB_SHAPE = "fab-shape";
    static final String KNOB_SETTINGS_CARDS = "settings-cards";
    static final String KNOB_WALLPAPER_PHASE = "wallpaper-phase";

    /** Message corner radius (dp): the stock slider's 0-17 range from 8 up; below 8 grouped media look broken. */
    static final int[] BUBBLE_RADII = {8, 10, 12, 14, 17};
    /** Chat list layout: three lines 2 in 5 (only on screens at least 640dp long and text below 19). */
    static final boolean[] THREE_LINES = {false, false, false, true, true};
    /** Reaction chips: a pill, or a rounded rectangle that follows the bubble radius. */
    static final boolean[] REACTION_PILL = {true, false};
    /** Call-to-action button radius = bubble radius times this percentage, clamped to 6-12dp (stock 8dp). */
    static final int[] CTA_SCALES = {50, 75, 100};
    /** Floating action button: -1 circle (stock), otherwise the corner radius (dp) of a rounded square. */
    static final int[] FAB_RADII = {-1, -1, -1, 14, 16, 18};
    /** Corner radius (dp) of settings list cards (stock 16dp, inset 12dp). */
    static final int[] SECTION_RADII = {12, 14, 16, 20};

    /** Stock values of the mainconfig settings. */
    static final int STOCK_BUBBLE_RADIUS = 17;
    static final boolean STOCK_THREE_LINES = false;

    // mainconfig keys of the stock settings (SharedConfig)
    static final String MAIN_BUBBLE_RADIUS = "bubbleRadius";
    static final String MAIN_THREE_LINES = "useThreeLinesLayout";
    static final String MAIN_FONT_SIZE = "fons_size";

    // PREFS keys: the derived values ...
    static final String KEY_SEED = "seed";
    static final String KEY_VERSION = "version";
    static final String KEY_BUBBLE_RADIUS = "bubble_radius";
    static final String KEY_THREE_LINES = "three_lines";
    static final String KEY_REACTION_PILL = "reaction_pill";
    static final String KEY_CTA_SCALE = "cta_scale";
    static final String KEY_FAB_RADIUS = "fab_radius";
    static final String KEY_SECTION_RADIUS = "section_radius";
    static final String KEY_WALLPAPER_PHASE = "wallpaper_phase";
    // ... and the value last written into (or found in) mainconfig: while the setting still has it, it is ours.
    static final String SET_BUBBLE_RADIUS = "set_bubble_radius";
    static final String SET_THREE_LINES = "set_three_lines";

    /** The install's knob values. Immutable. */
    static final class Values {
        final int bubbleRadius;
        final boolean threeLines;
        final boolean reactionPill;
        final int ctaScale;
        final int fabRadius;
        final int sectionRadius;
        final int wallpaperPhase;

        Values(int bubbleRadius, boolean threeLines, boolean reactionPill, int ctaScale, int fabRadius, int sectionRadius,
               int wallpaperPhase) {
            this.bubbleRadius = bubbleRadius;
            this.threeLines = threeLines;
            this.reactionPill = reactionPill;
            this.ctaScale = ctaScale;
            this.fabRadius = fabRadius;
            this.sectionRadius = sectionRadius;
            this.wallpaperPhase = wallpaperPhase;
        }
    }

    /** Null while the install has no seed: every hook then returns its stock value. */
    private static volatile Values current;
    /** Set when a Shuffle, Undo or Reset is about to apply the style: the next wallpaper load starts at its phase. */
    private static volatile boolean restartWallpaperPhase;

    private StyleKnobs() {
    }

    // ---------------------------------------------------------------------------------------------
    // Derivation (pure)
    // ---------------------------------------------------------------------------------------------

    /** Uniform index in [0, n) from the knob's own stream. */
    static int pick(long seed, String knob, int n) {
        return (int) ((RandomStyle.deriveSeed(seed, knob) >>> 1) % n);
    }

    /**
     * The knob values of a seed. screenLongDp and fontSize (mainconfig 'fons_size') are the chat list guard: three
     * lines only on screens at least 640dp long and with message text below 19.
     */
    static Values derive(long seed, int screenLongDp, int fontSize) {
        boolean threeLines = THREE_LINES[pick(seed, KNOB_CHAT_LIST_DENSITY, THREE_LINES.length)] && screenLongDp >= 640 && fontSize < 19;
        return new Values(
                BUBBLE_RADII[pick(seed, KNOB_BUBBLE_RADIUS, BUBBLE_RADII.length)],
                threeLines,
                REACTION_PILL[pick(seed, KNOB_REACTION_CHIP, REACTION_PILL.length)],
                CTA_SCALES[pick(seed, KNOB_CTA_RADIUS, CTA_SCALES.length)],
                FAB_RADII[pick(seed, KNOB_FAB_SHAPE, FAB_RADII.length)],
                SECTION_RADII[pick(seed, KNOB_SETTINGS_CARDS, SECTION_RADII.length)],
                (int) (RandomStyle.deriveSeed(seed, KNOB_WALLPAPER_PHASE) & 7));
    }

    /**
     * The stored values when they belong to seed; a knob missing from the file (added by a later version) is
     * derived and stored. Otherwise (first start, or a new seed) all are derived and stored.
     */
    static Values load(SharedPreferences knobs, long seed, int screenLongDp, int fontSize) {
        Values d = derive(seed, screenLongDp, fontSize);
        boolean same = knobs.contains(KEY_SEED) && knobs.getLong(KEY_SEED, 0) == seed;
        if (!same) {
            store(knobs, seed, d);
            return d;
        }
        Values v = new Values(
                knobs.getInt(KEY_BUBBLE_RADIUS, d.bubbleRadius),
                knobs.getBoolean(KEY_THREE_LINES, d.threeLines),
                knobs.getBoolean(KEY_REACTION_PILL, d.reactionPill),
                knobs.getInt(KEY_CTA_SCALE, d.ctaScale),
                knobs.getInt(KEY_FAB_RADIUS, d.fabRadius),
                knobs.getInt(KEY_SECTION_RADIUS, d.sectionRadius),
                knobs.getInt(KEY_WALLPAPER_PHASE, d.wallpaperPhase));
        String[] keys = {KEY_BUBBLE_RADIUS, KEY_THREE_LINES, KEY_REACTION_PILL, KEY_CTA_SCALE, KEY_FAB_RADIUS,
                KEY_SECTION_RADIUS, KEY_WALLPAPER_PHASE};
        for (String key : keys) {
            if (!knobs.contains(key)) {
                store(knobs, seed, v);
                break;
            }
        }
        return v;
    }

    private static void store(SharedPreferences knobs, long seed, Values v) {
        knobs.edit()
                .putLong(KEY_SEED, seed)
                .putInt(KEY_VERSION, VERSION)
                .putInt(KEY_BUBBLE_RADIUS, v.bubbleRadius)
                .putBoolean(KEY_THREE_LINES, v.threeLines)
                .putBoolean(KEY_REACTION_PILL, v.reactionPill)
                .putInt(KEY_CTA_SCALE, v.ctaScale)
                .putInt(KEY_FAB_RADIUS, v.fabRadius)
                .putInt(KEY_SECTION_RADIUS, v.sectionRadius)
                .putInt(KEY_WALLPAPER_PHASE, v.wallpaperPhase)
                .commit();
    }

    // ---------------------------------------------------------------------------------------------
    // Stock settings: written only while they are ours
    // ---------------------------------------------------------------------------------------------

    /** The setting still has the value this class last gave it or, before that, its stock default. */
    static boolean owned(SharedPreferences knobs, String record, int value, int stock) {
        return knobs.contains(record) ? knobs.getInt(record, stock) == value : value == stock;
    }

    static boolean owned(SharedPreferences knobs, String record, boolean value, boolean stock) {
        return knobs.contains(record) ? knobs.getBoolean(record, stock) == value : value == stock;
    }

    /** Writes the stored values into mainconfig where the setting is still ours (start of the app). */
    static void applyAtStart(SharedPreferences knobs, SharedPreferences main, Values v) {
        SharedPreferences.Editor m = main.edit();
        SharedPreferences.Editor k = knobs.edit();
        boolean mainChanged = false;
        boolean knobsChanged = false;
        int radius = main.getInt(MAIN_BUBBLE_RADIUS, STOCK_BUBBLE_RADIUS);
        if (owned(knobs, SET_BUBBLE_RADIUS, radius, STOCK_BUBBLE_RADIUS)) {
            if (radius != v.bubbleRadius) {
                m.putInt(MAIN_BUBBLE_RADIUS, v.bubbleRadius);
                mainChanged = true;
            }
            if (!knobs.contains(SET_BUBBLE_RADIUS) || knobs.getInt(SET_BUBBLE_RADIUS, 0) != v.bubbleRadius) {
                k.putInt(SET_BUBBLE_RADIUS, v.bubbleRadius);
                knobsChanged = true;
            }
        }
        boolean threeLines = main.getBoolean(MAIN_THREE_LINES, STOCK_THREE_LINES);
        if (owned(knobs, SET_THREE_LINES, threeLines, STOCK_THREE_LINES)) {
            if (threeLines != v.threeLines) {
                m.putBoolean(MAIN_THREE_LINES, v.threeLines);
                mainChanged = true;
            }
            if (!knobs.contains(SET_THREE_LINES) || knobs.getBoolean(SET_THREE_LINES, false) != v.threeLines) {
                k.putBoolean(SET_THREE_LINES, v.threeLines);
                knobsChanged = true;
            }
        }
        // Main thread, before the first frame; only when something changed (the first start).
        if (mainChanged) {
            m.commit();
        }
        if (knobsChanged) {
            k.commit();
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Lifecycle
    // ---------------------------------------------------------------------------------------------

    /**
     * ApplicationLoader.onCreate, right after {@link RandomStyle#onApplicationCreate}: loads (or, on a fresh install,
     * derives) the values and writes the stock settings that are still ours into mainconfig, then into SharedConfig's
     * in-memory copies. That second step matters on large screens (sw600dp: tablets, unfolded foldables): there
     * AndroidUtilities' static initialiser, which runs earlier in onCreate, calls isTablet(), which reads
     * SharedConfig.forceDisableTabletMode, so SharedConfig has already loaded mainconfig and its later loadConfig()
     * does nothing. On phones touching SharedConfig loads it here, from the values just committed; tablets load it
     * even earlier, so nothing in it depends on loading later. Before the first frame on both. Writes through
     * Context.getSharedPreferences, so no account singleton is created.
     */
    public static void onApplicationCreate(Context context) {
        try {
            if (!RandomStyle.hasSeed()) {
                return; // existing install that never shuffled: everything stays stock
            }
            SharedPreferences knobs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            SharedPreferences main = context.getSharedPreferences("mainconfig", Context.MODE_PRIVATE);
            Values v = load(knobs, RandomStyle.getSeed(), screenLongSideDp(context), main.getInt(MAIN_FONT_SIZE, 16));
            applyAtStart(knobs, main, v);
            current = v;
            SharedConfig.bubbleRadius = main.getInt(MAIN_BUBBLE_RADIUS, STOCK_BUBBLE_RADIUS);
            SharedConfig.useThreeLinesLayout = main.getBoolean(MAIN_THREE_LINES, STOCK_THREE_LINES);
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /**
     * RandomStyle, right before Shuffle, Undo or Reset shows the style (so the theme switch that follows already
     * sees the new values): a new seed re-derives every knob. The bubble radius and chat list layout change at once
     * where they are still ours, and so do the shapes read at draw or layout time (service pills when laid out again,
     * reaction chips, the floating button on its theme update); button and settings card corners are read when a
     * screen builds them, so they follow when each screen is next opened. The next wallpaper load starts at the
     * style's phase. UI thread.
     */
    static void onStyleApplying(long seed) {
        try {
            Context context = ApplicationLoader.applicationContext;
            SharedPreferences knobs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            SharedPreferences main = context.getSharedPreferences("mainconfig", Context.MODE_PRIVATE);
            Values v = load(knobs, seed, screenLongSideDp(context), SharedConfig.fontSize);
            current = v;
            restartWallpaperPhase = true;

            SharedPreferences.Editor k = knobs.edit();
            int radius = main.getInt(MAIN_BUBBLE_RADIUS, STOCK_BUBBLE_RADIUS);
            if (owned(knobs, SET_BUBBLE_RADIUS, radius, STOCK_BUBBLE_RADIUS)) {
                if (radius != v.bubbleRadius || SharedConfig.bubbleRadius != v.bubbleRadius) {
                    SharedConfig.bubbleRadius = v.bubbleRadius;
                    main.edit().putInt(MAIN_BUBBLE_RADIUS, v.bubbleRadius).apply();
                }
                k.putInt(SET_BUBBLE_RADIUS, v.bubbleRadius);
            }
            boolean threeLines = main.getBoolean(MAIN_THREE_LINES, STOCK_THREE_LINES);
            if (owned(knobs, SET_THREE_LINES, threeLines, STOCK_THREE_LINES)) {
                if (threeLines != v.threeLines || SharedConfig.useThreeLinesLayout != v.threeLines) {
                    SharedConfig.setUseThreeLinesLayout(v.threeLines); // writes mainconfig and reloads the chat list
                }
                k.putBoolean(SET_THREE_LINES, v.threeLines);
            }
            k.apply();
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /** The install has style knobs (a seed): false for installs that never shuffled, whose hooks all return stock. */
    static boolean isActive() {
        return current != null;
    }

    /** The long side of the screen in dp, or 0 when unknown (then the chat list stays two-line). */
    private static int screenLongSideDp(Context context) {
        try {
            Configuration c = context.getResources().getConfiguration();
            return Math.max(c.screenWidthDp, c.screenHeightDp);
        } catch (Throwable e) {
            return 0;
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Hooks (each returns the stock value it is given while the install has no seed)
    // ---------------------------------------------------------------------------------------------

    /**
     * ThemeActivity "Reset to defaults": the bubble radius goes back to this install's radius instead of stock 17,
     * and follows the style again from then on.
     */
    public static int resetBubbleRadius(int stock) {
        Values v = current;
        if (v == null) {
            return stock;
        }
        try {
            ApplicationLoader.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putInt(SET_BUBBLE_RADIUS, v.bubbleRadius).apply();
        } catch (Throwable e) {
            FileLog.e(e);
        }
        return v.bubbleRadius;
    }

    /**
     * ChatActionCell: the service and date pill's outer corner (stock 11dp) and its inner corners (8dp, 6dp). The
     * outer corner is clamp(round(bubble radius * 0.65), 4, 11) dp of the current bubble radius, so the user's
     * slider drives it too; the inner ones scale with it, at least 3dp. Never above stock, so a pill never
     * self-intersects. The pill's size and side padding stay stock ({@link #servicePillCornerOffset}).
     */
    public static int servicePillRadius(int stockPx) {
        if (current == null) {
            return stockPx;
        }
        int cornerDp = Math.max(4, Math.min(11, Math.round(SharedConfig.bubbleRadius * 0.65f)));
        if (cornerDp >= 11) {
            return stockPx;
        }
        return Math.max(AndroidUtilities.dp(3), Math.round(stockPx * cornerDp / 11f));
    }

    /**
     * ChatActionCell: the pill's cornerOffset (stock 3dp), the part of each corner arc on the text's side. The pill's
     * side padding is corner - cornerOffset (stock 11dp - 3dp = 8dp), so with a smaller corner the offset shrinks
     * with it (below 0 when the corner is under 8dp) and the text keeps the stock padding; the arcs keep their 2 x
     * corner width. Stock when the corner is stock.
     */
    public static int servicePillCornerOffset(int stockOffsetPx, int cornerPx, int stockCornerPx) {
        if (cornerPx == stockCornerPx) {
            return stockOffsetPx;
        }
        return cornerPx - (stockCornerPx - stockOffsetPx);
    }

    /**
     * ReactionsLayoutInBubble: the reaction chip's corner radius (stock height / 2, a pill). The rounded style uses
     * clamp(round(bubble radius * 0.6), 6, 10) dp, never more than the pill. Saved-message tags keep their shape.
     */
    public static float reactionChipRadius(float stockPx) {
        Values v = current;
        if (v == null || v.reactionPill) {
            return stockPx;
        }
        int dp = Math.max(6, Math.min(10, Math.round(SharedConfig.bubbleRadius * 0.6f)));
        return Math.min(stockPx, AndroidUtilities.dp(dp));
    }

    /**
     * ButtonWithCounterView: the default corner radius of call-to-action buttons (stock 8dp); explicit
     * setRoundRadius and setRound calls keep their values. clamp(round(bubble radius * scale), 6, 12) dp: at most
     * half of the usual 24dp+ button height and below the 24dp sheet corners.
     */
    public static int ctaRadiusDp(int stockDp) {
        Values v = current;
        if (v == null) {
            return stockDp;
        }
        return Math.max(6, Math.min(12, Math.round(SharedConfig.bubbleRadius * v.ctaScale / 100f)));
    }

    /** FragmentFloatingButton: the main button's background, a circle (stock) or this install's rounded square. */
    public static Drawable floatingButtonBackground(int size, int defaultColor, int pressedColor) {
        Values v = current;
        if (v == null || v.fabRadius < 0) {
            return Theme.createSimpleSelectorCircleDrawable(size, defaultColor, pressedColor);
        }
        return Theme.createSimpleSelectorRoundRectDrawable(AndroidUtilities.dp(v.fabRadius), defaultColor, pressedColor);
    }

    /**
     * FragmentFloatingButton: the small button above it (36dp inside a 48dp view, stock radius 18dp, a circle)
     * gets the same shape as the main button: its radius scaled by 36/48.
     */
    public static int floatingSubButtonRadius(int stockPx) {
        Values v = current;
        if (v == null || v.fabRadius < 0) {
            return stockPx;
        }
        return Math.round(AndroidUtilities.dp(v.fabRadius) * 0.75f);
    }

    /** RecyclerListView.setSections(): the default corner radius of settings list cards (stock 16dp). */
    public static int sectionRadius(int stockPx) {
        Values v = current;
        if (v == null) {
            return stockPx;
        }
        return AndroidUtilities.dp(v.sectionRadius);
    }

    /**
     * Theme.reloadWallpaper, after the phase to continue from is taken from the old wallpaper: the gradient starts
     * at this install's phase (stock: 0) when there is no gradient to continue (the first load after start), and
     * once after Shuffle, Undo or Reset. Otherwise it keeps the phase, as stock does.
     */
    public static int wallpaperPhase(int phase, boolean continuing) {
        Values v = current;
        if (v == null) {
            return phase;
        }
        if (restartWallpaperPhase || !continuing) {
            restartWallpaperPhase = false;
            return v.wallpaperPhase;
        }
        return phase;
    }
}
