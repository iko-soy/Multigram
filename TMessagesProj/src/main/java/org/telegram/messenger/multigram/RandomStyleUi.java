package org.telegram.messenger.multigram;

import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.FileLog;
import org.telegram.messenger.MessageObject;
import org.telegram.messenger.R;
import org.telegram.messenger.SharedConfig;
import org.telegram.messenger.Utilities;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.EmojiThemes;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Cells.ChatListCell;
import org.telegram.ui.Cells.ChatMessageCell;
import org.telegram.ui.Cells.TextCell;
import org.telegram.ui.Cells.ThemePreviewMessagesCell;
import org.telegram.ui.Components.BulletinFactory;
import org.telegram.ui.Components.ChatThemeBottomSheet;
import org.telegram.ui.Components.RadioButton;
import org.telegram.ui.DialogsActivity;
import org.telegram.ui.ThemeActivity;

import java.util.ArrayList;
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
        refreshStyleKnobRows(fragment);
        if (fragment != null && RandomStyle.canUndoShuffle()) {
            BulletinFactory.of(fragment).createUndoBulletin(str(R.string.MultiGramStyleShuffled), () -> {
                if (!RandomStyle.undoShuffle()) {
                    BulletinFactory.of(fragment).createErrorBulletin(str(R.string.MultiGramUndoFailed)).show();
                } else {
                    refreshStyleKnobRows(fragment);
                }
            }, null).show();
        }
    }

    /**
     * Shuffle and Undo may change the bubble radius and the chat list layout ({@link StyleKnobs}); Chat Settings
     * rebinds the rows that show them ({@link #bindStyleKnobRow}).
     */
    private static void refreshStyleKnobRows(BaseFragment fragment) {
        try {
            if (fragment instanceof ThemeActivity) {
                ((ThemeActivity) fragment).refreshStyleKnobRows();
            }
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /**
     * ThemeActivity.ListAdapter.onBindViewHolder hook for the text size preview, the message corners slider and the
     * chat list picker. Their cells read the bubble radius and chat list layout only when created (the picker's
     * radio buttons) or measured (the slider's position, the preview's bubbles), and binding them does nothing in
     * stock, so after Shuffle or Undo ({@link ThemeActivity#refreshStyleKnobRows}) a visible row, or one kept
     * off screen, would still show the old values. This brings the cell in line with SharedConfig the way the
     * stock slider does: the preview messages are laid out again, the cell is measured again, and the picker's
     * radio buttons are re-checked. A cell never laid out was just created from the current values and is left
     * alone, and so is every cell while the install has no style knobs. Never throws.
     */
    public static void bindStyleKnobRow(View itemView) {
        try {
            if (itemView == null || !StyleKnobs.isActive() || itemView.getWidth() == 0) {
                return;
            }
            if (itemView instanceof ChatListCell) {
                // Its two options in order (two lines, three lines), each with one radio button; a button animates
                // only while attached, and does nothing when it already shows the value.
                List<RadioButton> buttons = new ArrayList<>();
                collect(itemView, RadioButton.class, buttons);
                if (buttons.size() == 2) {
                    buttons.get(0).setChecked(!SharedConfig.useThreeLinesLayout, true);
                    buttons.get(1).setChecked(SharedConfig.useThreeLinesLayout, true);
                }
            } else {
                List<ThemePreviewMessagesCell> previews = new ArrayList<>();
                collect(itemView, ThemePreviewMessagesCell.class, previews);
                for (ThemePreviewMessagesCell preview : previews) {
                    ChatMessageCell[] cells = preview.getCells();
                    for (int i = 0; cells != null && i < cells.length; i++) {
                        MessageObject message = cells[i] == null ? null : cells[i].getMessageObject();
                        if (message != null) {
                            message.resetLayout();
                            cells[i].requestLayout();
                        }
                    }
                }
                itemView.requestLayout(); // the corners slider takes its position from SharedConfig in onMeasure
            }
            itemView.invalidate();
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

    /** Adds view and its descendants that are instances of type to out, depth first. */
    private static <T> void collect(View view, Class<T> type, List<T> out) {
        if (type.isInstance(view)) {
            out.add(type.cast(view));
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                collect(group.getChildAt(i), type, out);
            }
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
