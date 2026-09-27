package org.telegram.messenger.multigram;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.FileLog;
import org.telegram.messenger.R;
import org.telegram.ui.LauncherIconController;

import java.util.List;

/**
 * What the build-time rebrand (multigram/rebrand) changes in code. The rebrand's resource
 * overlay sets R.bool.multigram_rebrand_active to true; a stock build keeps the library's
 * false, so every method here then returns Forkgram's own behaviour.
 */
public final class Rebrand {

    private static volatile Boolean active;

    private Rebrand() {
    }

    /** True in a build made with multigram/rebrand/generate_rebrand.py. */
    public static boolean isActive() {
        Boolean a = active;
        if (a == null) {
            a = false;
            try {
                if (ApplicationLoader.applicationContext != null) {
                    a = ApplicationLoader.applicationContext.getResources().getBoolean(R.bool.multigram_rebrand_active);
                    active = a;
                }
            } catch (Exception e) {
                FileLog.e(e);
            }
        }
        return a;
    }

    /**
     * The default title of the main chat list: the rebranded app name, or {@code stock}.
     * Read from the app's own resources, not LocaleController: cloud language packs carry
     * Telegram's name for AppName.
     */
    public static String defaultTitle(String stock) {
        if (!isActive()) {
            return stock;
        }
        try {
            return ApplicationLoader.applicationContext.getString(R.string.AppName);
        } catch (Exception e) {
            FileLog.e(e);
            return stock;
        }
    }

    /**
     * A rebranded build offers only its own launcher icon: the other entries are Forkgram's
     * and Telegram's logos, which do not belong to the new identity.
     */
    public static void filterLauncherIcons(List<LauncherIconController.LauncherIcon> icons) {
        if (isActive()) {
            for (int i = icons.size() - 1; i >= 0; i--) {
                if (icons.get(i) != LauncherIconController.LauncherIcon.DEFAULT) {
                    icons.remove(i);
                }
            }
        }
    }
}
