package org.telegram.ui;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Environment;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.LocaleController;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.R;
import org.telegram.messenger.forkgram.VoiceTimecodesConfig;
import org.telegram.ui.ActionBar.ActionBar;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Cells.TextCheckCell;
import org.telegram.ui.Components.EditTextBoldCursor;
import org.telegram.ui.Components.LayoutHelper;
import org.telegram.ui.Components.OutlineEditText;

import java.io.File;

public class VoiceTimecodesSettingsActivity extends BaseFragment {

    private static final int DONE_BUTTON = 1;

    private TextCheckCell enabledCell;
    private EditTextBoldCursor sttUrlField;
    private EditTextBoldCursor sttTokenField;
    private EditTextBoldCursor llmUrlField;
    private EditTextBoldCursor llmTokenField;
    private EditTextBoldCursor llmModelField;
    private EditTextBoldCursor minDurationField;
    private EditTextBoldCursor promptField;

    private EditTextBoldCursor lastField;

    @Override
    public View createView(Context context) {
        actionBar.setBackButtonImage(R.drawable.ic_ab_back);
        actionBar.setTitle(LocaleController.getString(R.string.VoiceTimecodes));
        actionBar.setAllowOverlayTitle(true);
        actionBar.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
        actionBar.setTitleColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
        actionBar.setItemsColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText), false);
        if (AndroidUtilities.isTablet()) {
            actionBar.setOccupyStatusBar(false);
        }
        actionBar.setActionBarMenuOnItemClick(new ActionBar.ActionBarMenuOnItemClick() {
            @Override
            public void onItemClick(int id) {
                if (id == -1) {
                    finishFragment();
                } else if (id == DONE_BUTTON) {
                    save();
                }
            }
        });
        actionBar.createMenu().addItemWithWidth(DONE_BUTTON, R.drawable.ic_ab_done, AndroidUtilities.dp(56), LocaleController.getString(R.string.Done));

        fragmentView = new FrameLayout(context);
        fragmentView.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
        FrameLayout frameLayout = (FrameLayout) fragmentView;

        ScrollView scrollView = new ScrollView(context);
        scrollView.setFillViewport(true);
        frameLayout.addView(scrollView, LayoutHelper.createFrame(LayoutHelper.MATCH_PARENT, LayoutHelper.MATCH_PARENT));

        LinearLayout content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = AndroidUtilities.dp(16);
        content.setPadding(pad, pad, pad, pad);
        scrollView.addView(content, new ScrollView.LayoutParams(ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));

        TextView info = new TextView(context);
        info.setText(LocaleController.getString(R.string.VoiceTimecodesInfo));
        info.setTextSize(14);
        info.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        content.addView(info, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT, 0, 0, 0, 16));

        enabledCell = new TextCheckCell(context);
        enabledCell.setTextAndCheck(LocaleController.getString(R.string.VoiceTimecodesEnabled), VoiceTimecodesConfig.isEnabled(), false);
        enabledCell.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
        enabledCell.setOnClickListener(v -> enabledCell.setChecked(!enabledCell.isChecked()));
        content.addView(enabledCell, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT, 0, 0, 0, 12));

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesSttUrl),
                VoiceTimecodesConfig.sttUrl(), LocaleController.getString(R.string.VoiceTimecodesSttUrlHint),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI, EditorInfo.IME_ACTION_NEXT, false);
        sttUrlField = lastField;

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesSttToken),
                VoiceTimecodesConfig.sttToken(), null,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD, EditorInfo.IME_ACTION_NEXT, false);
        sttTokenField = lastField;
        sttTokenField.setTransformationMethod(PasswordTransformationMethod.getInstance());

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesLlmUrl),
                VoiceTimecodesConfig.llmUrl(), LocaleController.getString(R.string.VoiceTimecodesLlmUrlHint),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI, EditorInfo.IME_ACTION_NEXT, false);
        llmUrlField = lastField;

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesLlmToken),
                VoiceTimecodesConfig.llmToken(), null,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD, EditorInfo.IME_ACTION_NEXT, false);
        llmTokenField = lastField;
        llmTokenField.setTransformationMethod(PasswordTransformationMethod.getInstance());

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesLlmModel),
                VoiceTimecodesConfig.llmModel(), LocaleController.getString(R.string.VoiceTimecodesLlmModelHint),
                InputType.TYPE_CLASS_TEXT, EditorInfo.IME_ACTION_NEXT, false);
        llmModelField = lastField;

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesMinDuration),
                String.valueOf(VoiceTimecodesConfig.minDuration()), "10",
                InputType.TYPE_CLASS_NUMBER, EditorInfo.IME_ACTION_NEXT, false);
        minDurationField = lastField;

        addField(content, context, LocaleController.getString(R.string.VoiceTimecodesPrompt),
                VoiceTimecodesConfig.promptTemplate(), null,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE, EditorInfo.IME_ACTION_NONE, true);
        promptField = lastField;

        TextView resetPrompt = new TextView(context);
        resetPrompt.setText(LocaleController.getString(R.string.VoiceTimecodesResetPrompt));
        resetPrompt.setTextSize(14);
        resetPrompt.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlueText4));
        resetPrompt.setPadding(0, AndroidUtilities.dp(6), 0, AndroidUtilities.dp(16));
        resetPrompt.setOnClickListener(v -> promptField.setText(VoiceTimecodesConfig.DEFAULT_PROMPT));
        content.addView(resetPrompt, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT));

        TextView importButton = new TextView(context);
        importButton.setText(LocaleController.getString(R.string.VoiceTimecodesImportFile));
        importButton.setTextSize(14);
        importButton.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlueText4));
        importButton.setPadding(0, AndroidUtilities.dp(6), 0, AndroidUtilities.dp(24));
        importButton.setOnClickListener(v -> tryImportFromFile());
        content.addView(importButton, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT));

        return fragmentView;
    }

    private void addField(LinearLayout content, Context context, String label, String value, String hint, int inputType, int imeOptions, boolean multiline) {
        OutlineEditText outline = new OutlineEditText(context);
        outline.setHint(label);
        EditTextBoldCursor field = outline.getEditText();
        field.setText(value != null ? value : "");
        if (hint != null) {
            field.setHint(hint);
        }
        field.setInputType(inputType);
        field.setImeOptions(imeOptions);
        if (multiline) {
            field.setSingleLine(false);
            field.setMaxLines(Integer.MAX_VALUE);
            field.setMinLines(3);
            field.setGravity(LocaleController.isRTL ? Gravity.RIGHT : Gravity.LEFT);
            field.setHorizontallyScrolling(false);
        }
        int pad = AndroidUtilities.dp(16);
        field.setPadding(AndroidUtilities.dp(15), pad, AndroidUtilities.dp(15), pad);
        content.addView(outline, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT, 0, 0, 0, AndroidUtilities.dp(10)));
        lastField = field;
    }

    private void tryImportFromFile() {
        java.util.List<File> candidates = new java.util.ArrayList<>();
        try {
            File downloadDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
            if (downloadDir != null) {
                candidates.add(new File(downloadDir, "voice_timecodes.json"));
                candidates.add(new File(downloadDir, "voice_timecodes_backup.json"));
            }
        } catch (Exception ignore) {
        }
        if (getContext() != null) {
            try {
                File ext = getContext().getExternalFilesDir(null);
                if (ext != null) {
                    candidates.add(new File(ext, "voice_timecodes.json"));
                    candidates.add(new File(ext, "voice_timecodes_backup.json"));
                }
            } catch (Exception ignore) {
            }
        }
        boolean success = false;
        for (File target : candidates) {
            if (target.exists() && target.canRead() && VoiceTimecodesConfig.importFromFile(target)) {
                success = true;
                break;
            }
        }
        if (success) {
            enabledCell.setChecked(VoiceTimecodesConfig.isEnabled());
            sttUrlField.setText(VoiceTimecodesConfig.sttUrl());
            sttTokenField.setText(VoiceTimecodesConfig.sttToken());
            llmUrlField.setText(VoiceTimecodesConfig.llmUrl());
            llmTokenField.setText(VoiceTimecodesConfig.llmToken());
            llmModelField.setText(VoiceTimecodesConfig.llmModel());
            minDurationField.setText(String.valueOf(VoiceTimecodesConfig.minDuration()));
            promptField.setText(VoiceTimecodesConfig.promptTemplate());
            if (getParentActivity() != null) {
                Toast.makeText(getParentActivity(), LocaleController.getString(R.string.VoiceTimecodesImportSuccess), Toast.LENGTH_SHORT).show();
            }
        } else {
            if (getParentActivity() != null) {
                Toast.makeText(getParentActivity(), LocaleController.getString(R.string.VoiceTimecodesImportFailed), Toast.LENGTH_SHORT).show();
            }
        }
    }

    private void save() {
        boolean enabled = enabledCell.isChecked();
        String sttUrl = sttUrlField.getText().toString().trim();
        String sttToken = sttTokenField.getText().toString().trim();
        String llmUrl = llmUrlField.getText().toString().trim();
        String llmToken = llmTokenField.getText().toString().trim();
        String llmModel = llmModelField.getText().toString().trim();
        int minDuration = 10;
        try {
            minDuration = Integer.parseInt(minDurationField.getText().toString().trim());
        } catch (Exception ignore) {
        }
        String prompt = promptField.getText().toString();

        VoiceTimecodesConfig.saveValues(enabled, sttUrl, sttToken, llmUrl, llmToken, llmModel, minDuration, prompt);

        if (getParentActivity() != null) {
            Toast.makeText(getParentActivity(), LocaleController.getString(R.string.VoiceTimecodesSaved), Toast.LENGTH_SHORT).show();
        }
        finishFragment();
    }
}
