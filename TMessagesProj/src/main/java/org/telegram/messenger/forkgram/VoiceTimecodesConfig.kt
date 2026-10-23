package org.telegram.messenger.forkgram

import android.content.SharedPreferences
import android.os.Environment
import org.json.JSONObject
import org.telegram.messenger.ApplicationLoader
import org.telegram.messenger.FileLog
import org.telegram.messenger.MessagesController
import org.telegram.messenger.UserConfig
import java.io.File
import java.net.URL

object VoiceTimecodesConfig {

    const val PREF_ENABLED = "voice_timecodes_enabled"
    const val PREF_STT_URL = "voice_timecodes_stt_url"
    const val PREF_STT_TOKEN = "voice_timecodes_stt_token"
    const val PREF_LLM_URL = "voice_timecodes_llm_url"
    const val PREF_LLM_TOKEN = "voice_timecodes_llm_token"
    const val PREF_LLM_MODEL = "voice_timecodes_llm_model"
    const val PREF_MIN_DURATION = "voice_timecodes_min_duration"
    const val PREF_PROMPT = "voice_timecodes_prompt"

    const val DEFAULT_LLM_MODEL = "gpt-4o-mini"
    const val DEFAULT_MIN_DURATION = 10

    const val DEFAULT_PROMPT =
        "Below is a transcript of a voice message with timestamps.\n" +
        "Divide it into meaningful topics. For each topic, provide the start timestamp and a concise title.\n" +
        "Response format — only the list of timecodes, no extra text:\n" +
        "00:00 — Topic name\n" +
        "05:30 — Another topic\n" +
        "...\n\n" +
        "Transcript:\n{transcript}"

    @JvmStatic
    fun prefs(): SharedPreferences {
        return MessagesController.getGlobalMainSettings()
    }

    @JvmStatic
    fun isEnabled(): Boolean {
        ensureAutoImport()
        return prefs().getBoolean(PREF_ENABLED, false)
    }

    @JvmStatic
    fun setEnabled(value: Boolean) {
        prefs().edit().putBoolean(PREF_ENABLED, value).apply()
    }

    @JvmStatic
    fun sttUrl(): String {
        ensureAutoImport()
        return prefs().getString(PREF_STT_URL, "")?.trim() ?: ""
    }

    @JvmStatic
    fun sttToken(): String {
        ensureAutoImport()
        return prefs().getString(PREF_STT_TOKEN, "")?.trim() ?: ""
    }

    @JvmStatic
    fun llmUrl(): String {
        ensureAutoImport()
        return prefs().getString(PREF_LLM_URL, "")?.trim() ?: ""
    }

    @JvmStatic
    fun llmToken(): String {
        ensureAutoImport()
        return prefs().getString(PREF_LLM_TOKEN, "")?.trim() ?: ""
    }

    @JvmStatic
    fun llmModel(): String {
        ensureAutoImport()
        val m = prefs().getString(PREF_LLM_MODEL, DEFAULT_LLM_MODEL)?.trim() ?: ""
        return if (m.isEmpty()) DEFAULT_LLM_MODEL else m
    }

    @JvmStatic
    fun minDuration(): Int {
        val d = prefs().getInt(PREF_MIN_DURATION, DEFAULT_MIN_DURATION)
        return if (d <= 0) DEFAULT_MIN_DURATION else d
    }

    @JvmStatic
    fun promptTemplate(): String {
        val p = prefs().getString(PREF_PROMPT, DEFAULT_PROMPT)
        return if (p.isNullOrBlank()) DEFAULT_PROMPT else p
    }

    @JvmStatic
    fun maxCaptionLimit(account: Int): Int {
        return if (UserConfig.getInstance(account).isPremium) 4096 else 1024
    }

    @JvmStatic
    fun isConfigured(): Boolean {
        return isEnabled() && sttUrl().isNotEmpty() && llmUrl().isNotEmpty()
    }

    @JvmStatic
    fun saveValues(
        enabled: Boolean,
        sttUrl: String,
        sttToken: String,
        llmUrl: String,
        llmToken: String,
        llmModel: String,
        minDuration: Int,
        prompt: String
    ) {
        prefs().edit()
            .putBoolean(PREF_ENABLED, enabled)
            .putString(PREF_STT_URL, sttUrl.trim())
            .putString(PREF_STT_TOKEN, sttToken.trim())
            .putString(PREF_LLM_URL, llmUrl.trim())
            .putString(PREF_LLM_TOKEN, llmToken.trim())
            .putString(PREF_LLM_MODEL, llmModel.trim())
            .putInt(PREF_MIN_DURATION, if (minDuration <= 0) DEFAULT_MIN_DURATION else minDuration)
            .putString(PREF_PROMPT, if (prompt.isBlank()) DEFAULT_PROMPT else prompt)
            .apply()
    }

    @Volatile
    private var autoImportChecked = false

    @JvmStatic
    fun ensureAutoImport() {
        if (autoImportChecked) return
        autoImportChecked = true

        val currentStt = prefs().getString(PREF_STT_URL, null)
        val currentLlm = prefs().getString(PREF_LLM_URL, null)
        if (!currentStt.isNullOrEmpty() && !currentLlm.isNullOrEmpty()) {
            return
        }

        val candidateDirs = mutableListOf<File>()
        try {
            val downloadDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (downloadDir != null) {
                candidateDirs.add(downloadDir)
            }
        } catch (e: Exception) {
            FileLog.e(e)
        }
        val context = ApplicationLoader.applicationContext
        if (context != null) {
            try {
                val extFiles = context.getExternalFilesDir(null)
                if (extFiles != null) {
                    candidateDirs.add(extFiles)
                }
            } catch (e: Exception) {
                FileLog.e(e)
            }
        }

        for (dir in candidateDirs) {
            val f1 = File(dir, "voice_timecodes.json")
            if (f1.exists() && f1.canRead() && importFromFile(f1)) {
                return
            }
            val f2 = File(dir, "voice_timecodes_backup.json")
            if (f2.exists() && f2.canRead() && importFromFile(f2)) {
                return
            }
        }
    }

    @JvmStatic
    fun importFromFile(file: File): Boolean {
        return try {
            val text = file.readText(Charsets.UTF_8)
            importFromJson(text)
        } catch (e: Exception) {
            FileLog.e("VoiceTimecodesConfig import error from ${file.absolutePath}: $e")
            false
        }
    }

    @JvmStatic
    fun importFromJson(jsonString: String): Boolean {
        return try {
            val root = JSONObject(jsonString)
            val editor = prefs().edit()

            if (root.has("prefs")) {
                val prefsObj = root.optJSONObject("prefs")
                val mainConfig = prefsObj?.optJSONObject("mainconfig")
                if (mainConfig != null) {
                    val it = mainConfig.keys()
                    while (it.hasNext()) {
                        val key = it.next()
                        val item = mainConfig.optJSONObject(key) ?: continue
                        val t = item.optString("t")
                        when (t) {
                            "b" -> editor.putBoolean(key, item.optBoolean("v"))
                            "s" -> editor.putString(key, item.optString("v"))
                            "i" -> editor.putInt(key, item.optInt("v"))
                        }
                    }
                    editor.apply()
                    return true
                }
            }

            var updated = false
            if (root.has("enabled")) {
                editor.putBoolean(PREF_ENABLED, root.getBoolean("enabled"))
                updated = true
            }
            if (root.has("stt_url")) {
                editor.putString(PREF_STT_URL, root.getString("stt_url"))
                updated = true
            }
            if (root.has("stt_token")) {
                editor.putString(PREF_STT_TOKEN, root.getString("stt_token"))
                updated = true
            }
            if (root.has("llm_url")) {
                editor.putString(PREF_LLM_URL, root.getString("llm_url"))
                updated = true
            }
            if (root.has("llm_token")) {
                editor.putString(PREF_LLM_TOKEN, root.getString("llm_token"))
                updated = true
            }
            if (root.has("llm_model")) {
                editor.putString(PREF_LLM_MODEL, root.getString("llm_model"))
                updated = true
            }
            if (root.has("min_duration")) {
                editor.putInt(PREF_MIN_DURATION, root.getInt("min_duration"))
                updated = true
            }
            if (root.has("prompt")) {
                editor.putString(PREF_PROMPT, root.getString("prompt"))
                updated = true
            }
            if (updated) {
                editor.apply()
                return true
            }
            false
        } catch (e: Exception) {
            FileLog.e(e)
            false
        }
    }
}
