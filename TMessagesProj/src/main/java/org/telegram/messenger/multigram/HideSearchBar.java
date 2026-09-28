package org.telegram.messenger.multigram;

import android.os.Bundle;
import android.view.View;

import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.FileLog;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.R;
import org.telegram.ui.Cells.NotificationsCheckCell;
import org.telegram.ui.Cells.TextCheckCell;
import org.telegram.ui.Components.UItem;
import org.telegram.ui.DialogsActivity;

import java.util.WeakHashMap;

/**
 * "Hide chat list search" (Fork Client Settings > Chat list view), the "no search" variant. While it is on, the main
 * chat list and the lists opened from it (archive, folders, communities) keep stock's "bar scrolled away" layout at
 * all times, minus the 48 dp the bar reserves, and the header search icon, which stock shows whenever the field is
 * invisible, stays hidden as well, so the list itself offers no way into search. Search opened another way (the
 * Downloads item, tg://search links, the topics column's search icon) still shows the field in the header, and
 * pickers and hashtag search screens keep the stock bar.
 *
 * Each chat list latches the setting at first use and changes it only in onResume (refresh), so a list never changes
 * shape while it is on screen. UI thread only. MultiGram strings are read with Context.getString.
 */
public final class HideSearchBar {

    /** mainconfig key, next to Forkgram's own Chat list rows. Default false. */
    public static final String KEY = "multigramHideSearchBar";
    /** Row id in ForkSettingsActivity: > 0 (its in-screen search skips ids <= 0), clear of Forkgram's 1-100. */
    public static final int ROW_ID = 9101;

    private static final class Latch {
        final boolean inScope; // fixed at first use: a picker may reset its delegate later
        boolean hidden;
        Latch(boolean inScope) { this.inScope = inScope; }
    }

    private static final WeakHashMap<DialogsActivity, Latch> LATCHES = new WeakHashMap<>();

    private HideSearchBar() {
    }

    /** True while this chat list lays out without the bar and without the header search icon. */
    public static boolean hides(DialogsActivity f) {
        return latch(f).hidden;
    }

    /** The bar's rest height in dp: the stock value, or 0 while hidden. Always called inside the original dp(...). */
    public static int restHeight(DialogsActivity f, int stock) {
        return hides(f) ? 0 : stock;
    }

    /** The bar's alpha from scrolling: the stock value, or 0 while hidden (the field then shows only in search mode). */
    public static float restAlpha(DialogsActivity f, float stock) {
        return hides(f) ? 0f : stock;
    }

    /**
     * Right after super.onResume(). Re-reads the setting. When this list's latched value changes, it re-anchors each
     * page's first visible chat relative to the list padding (stock's own re-anchor in DialogsRecyclerView.onMeasure
     * is skipped after onResume's notifyDataSetChanged), switches the latch, and returns true so the caller
     * re-derives its header. Returns false on the first call and whenever nothing changed.
     */
    public static boolean refresh(DialogsActivity f, DialogsActivity.ViewPage[] pages) {
        Latch l = LATCHES.get(f);
        if (l == null) {
            latch(f);
            return false;
        }
        boolean hide = l.inScope && isEnabled();
        if (hide == l.hidden) {
            return false;
        }
        if (pages != null) {
            for (DialogsActivity.ViewPage page : pages) {
                if (page != null) {
                    keepListOffset(page.listView);
                }
            }
        }
        l.hidden = hide;
        return f.getFragmentView() != null;
    }

    /** Same as stock's onMeasure re-anchor: keep the first visible chat's offset from the padding across the padding change. */
    static void keepListOffset(RecyclerView list) {
        if (list == null || !(list.getLayoutManager() instanceof LinearLayoutManager)) {
            return;
        }
        LinearLayoutManager lm = (LinearLayoutManager) list.getLayoutManager();
        if (lm.hasPendingScrollPosition()) {
            return;
        }
        int pos = lm.findFirstVisibleItemPosition();
        if (pos == RecyclerView.NO_POSITION) {
            return;
        }
        View first = lm.findViewByPosition(pos);
        if (first != null) {
            lm.scrollToPositionWithOffset(pos, first.getTop() - list.getPaddingTop());
        }
    }

    /** The row, built like Forkgram's Chat list rows. */
    public static UItem settingsRow() {
        return UItem.asButtonCheck(ROW_ID, str(R.string.MultiGramHideSearchBar), str(R.string.MultiGramHideSearchBarInfo))
            .setChecked(isEnabled()).setMultiline(true);
    }

    /** Same as Forkgram's private toggle(): flip, putBoolean + commit, check the cell. False for every other row. */
    public static boolean onSettingsClick(UItem item, View view) {
        if (item == null || item.id != ROW_ID) {
            return false;
        }
        final boolean value = !item.checked;
        item.checked = value;
        MessagesController.getGlobalMainSettings().edit().putBoolean(KEY, value).commit();
        if (view instanceof TextCheckCell) {
            ((TextCheckCell) view).setChecked(value);
        } else if (view instanceof NotificationsCheckCell) {
            ((NotificationsCheckCell) view).setChecked(value);
        }
        return true;
    }

    private static Latch latch(DialogsActivity f) {
        Latch l = LATCHES.get(f);
        if (l == null) {
            l = new Latch(inScope(f));
            l.hidden = l.inScope && isEnabled();
            LATCHES.put(f, l);
        }
        return l;
    }

    /** Main list, its folders, archive, communities, BackButtonMenu's plain list. Not pickers, not search-only screens. */
    static boolean inScope(DialogsActivity f) {
        Bundle a = f.getArguments();
        return f.getType() == DialogsActivity.DIALOGS_TYPE_DEFAULT && f.isMainDialogList()
            && (a == null || !a.getBoolean("onlySelect", false));
        // To keep community lists stock, add: && !f.isCommunity()
    }

    static boolean isEnabled() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(KEY, false);
        } catch (Throwable e) {
            FileLog.e(e);
            return false;
        }
    }

    private static String str(int res) {
        return ApplicationLoader.applicationContext.getString(res);
    }
}
