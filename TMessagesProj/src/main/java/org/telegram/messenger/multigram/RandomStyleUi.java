package org.telegram.messenger.multigram;

import android.os.SystemClock;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.FileLog;
import org.telegram.messenger.R;
import org.telegram.messenger.Utilities;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.EmojiThemes;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Cells.TextCell;
import org.telegram.ui.Components.BulletinFactory;
import org.telegram.ui.Components.ChatThemeBottomSheet;
import org.telegram.ui.DialogsActivity;

import java.util.List;

/**
 * UI side of {@link RandomStyle}: the "Shuffle my style" row in Chat Settings (ThemeActivity), its Undo, the custom
 * tile of the theme strip above it, and the messages shown when a share or cloud-theme action would upload the
 * generated style.
 *
 * MultiGram strings live in res/values/multigram_strings.xml, outside the strings.xml files that Telegram's
 * build turns into its localization assets, so they are read as plain Android resources, not via LocaleController.
 */
public final class RandomStyleUi {

    private static final long SHUFFLE_DEBOUNCE_MS = 1000;
    /** Emoji of the custom tile that EmojiThemes.createPreviewCustom builds for Chat Settings' theme strip. */
    private static final String CUSTOM_TILE_EMOJI = "🎨";
    private static long lastShuffleTime;

    private RandomStyleUi() {
    }

    private static String str(int res) {
        return ApplicationLoader.applicationContext.getString(res);
    }

    /** Binds the "Shuffle my style" row (a TextCell like its neighbours "Change chat background" and "Browse themes"). */
    public static void bindShuffleRow(TextCell cell) {
        cell.setSubtitle(null);
        cell.setColors(Theme.key_windowBackgroundWhiteBlueText4, Theme.key_windowBackgroundWhiteBlueText4);
        cell.setTextAndIcon(str(R.string.MultiGramShuffleStyle), R.drawable.menu_random, false);
        // Read and check the style table off the UI thread now, so a tap does not have to.
        Utilities.globalQueue.postRunnable(() -> {
            try {
                StyleTable.load(ApplicationLoader.applicationContext);
            } catch (Throwable e) {
                FileLog.e(e);
            }
        });
    }

    /**
     * "Shuffle my style" tapped: a new day and night style, applied at once. When it replaced the generated style
     * that was showing, a bulletin offers Undo for a few seconds.
     */
    public static void shuffle(BaseFragment fragment) {
        long now = SystemClock.elapsedRealtime();
        if (now - lastShuffleTime < SHUFFLE_DEBOUNCE_MS || DialogsActivity.switchingTheme) {
            return;
        }
        lastShuffleTime = now;
        if (!RandomStyle.shuffle(ApplicationLoader.applicationContext)) {
            if (fragment != null) {
                BulletinFactory.of(fragment).createErrorBulletin(str(R.string.MultiGramShuffleFailed)).show();
            }
            return;
        }
        if (fragment != null && RandomStyle.canUndoShuffle()) {
            BulletinFactory.of(fragment).createUndoBulletin(str(R.string.MultiGramStyleShuffled), () -> {
                if (!RandomStyle.undoShuffle()) {
                    BulletinFactory.of(fragment).createErrorBulletin(str(R.string.MultiGramUndoFailed)).show();
                }
            }, null).show();
        }
    }

    /**
     * DefaultThemesPreviewCell.updateDayNightMode hook. The custom tile of Chat Settings' theme strip is built once,
     * from themeconfig's lastDay/DarkCustomTheme(AccentId), but Shuffle, Undo and Reset replace the accents it points
     * to (and the colours it shows). When those keys have moved on, this rebuilds the tile in place, so it shows and
     * applies the current style. Never throws.
     */
    public static void refreshCustomTile(List<ChatThemeBottomSheet.ChatThemeItem> items, int currentAccount) {
        try {
            if (items == null) {
                return;
            }
            for (int i = 0; i < items.size(); i++) {
                ChatThemeBottomSheet.ChatThemeItem item = items.get(i);
                if (item == null || item.chatTheme == null || !CUSTOM_TILE_EMOJI.equals(item.chatTheme.getEmoticonOrSlug())) {
                    continue;
                }
                EmojiThemes current = EmojiThemes.createPreviewCustom(currentAccount);
                if (sameTile(item.chatTheme, current)) {
                    return;
                }
                current.loadPreviewColors(currentAccount);
                ChatThemeBottomSheet.ChatThemeItem fresh = new ChatThemeBottomSheet.ChatThemeItem(current);
                fresh.themeIndex = item.themeIndex;
                fresh.isSelected = item.isSelected;
                items.set(i, fresh);
                return;
            }
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /** Same day (index 0) and night (index 2) theme and accent, as createPreviewCustom lays them out. */
    private static boolean sameTile(EmojiThemes a, EmojiThemes b) {
        for (int index = 0; index <= 2; index += 2) {
            if (a.getThemeInfo(index) != b.getThemeInfo(index) || a.getAccentId(index) != b.getAccentId(index)) {
                return false;
            }
        }
        return true;
    }

    /**
     * ThemeActivity's needShareTheme handler: sharing a generated accent would upload it, which
     * {@link RandomStyle#isUploadBlocked} refuses; explain instead of waiting for an upload that never comes.
     */
    public static boolean interceptShare(BaseFragment fragment, Theme.ThemeAccent accent) {
        if (!RandomStyle.isGenerated(accent)) {
            return false;
        }
        showStaysOnDevice(fragment);
        return true;
    }

    /**
     * AlertsCreator.createThemeCreateDialog: a new theme is saved to Telegram's cloud with the colours of the accent
     * it starts from (the given one, or the current one), so it cannot start from a generated style.
     */
    public static boolean interceptThemeCreate(BaseFragment fragment, Theme.ThemeAccent switchToAccent) {
        boolean generated;
        if (switchToAccent != null) {
            generated = RandomStyle.isGenerated(switchToAccent);
        } else {
            Theme.ThemeInfo previous = Theme.getPreviousTheme();
            Theme.ThemeInfo active = Theme.getActiveTheme();
            generated = previous != null && RandomStyle.isGenerated(previous.getAccent(false))
                    || active != null && RandomStyle.isGenerated(active.getAccent(false));
        }
        if (!generated) {
            return false;
        }
        showStaysOnDevice(fragment);
        return true;
    }

    private static void showStaysOnDevice(BaseFragment fragment) {
        if (fragment != null) {
            BulletinFactory.of(fragment).createSimpleBulletin(R.raw.info, str(R.string.MultiGramStyleStaysOnDevice), 4).show(); // 4 lines: the default overload cuts at 2
        }
    }
}
