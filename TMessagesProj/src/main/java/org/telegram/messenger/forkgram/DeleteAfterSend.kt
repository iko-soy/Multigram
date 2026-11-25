package org.telegram.messenger.forkgram

import android.content.ContentUris
import android.provider.MediaStore
import android.system.Os
import android.system.OsConstants
import org.telegram.messenger.AndroidUtilities
import org.telegram.messenger.ApplicationLoader
import org.telegram.messenger.FileLog
import org.telegram.messenger.LocaleController
import org.telegram.messenger.NotificationCenter
import org.telegram.messenger.R
import org.telegram.messenger.Utilities
import org.telegram.ui.Components.Bulletin
import java.io.File
import java.util.UUID

object DeleteAfterSend {
    private const val PARAM = "forkDeleteAfterSend"
    private const val EXPIRE_MS = 24L * 60 * 60 * 1000

    private data class Source(
        val path: String,
        val device: Long,
        val inode: Long,
        val length: Long,
        val modified: Long
    )
    private data class Pending(val source: Source?, val imageId: Int, val expires: Long)

    private val pending = HashMap<String, Pending>()

    @JvmStatic
    fun arm(params: HashMap<String, String>, deletePath: String?, imageId: Int) {
        if (deletePath.isNullOrEmpty()) return
        val source = snapshot(deletePath)
        val now = System.currentTimeMillis()
        val token = UUID.randomUUID().toString()
        synchronized(pending) {
            pending.values.removeAll { it.expires < now }
            pending[token] = Pending(source, imageId, now + EXPIRE_MS)
        }
        params[PARAM] = token
    }

    @JvmStatic
    fun onMessageSent(params: HashMap<String, String>?, scheduled: Boolean) {
        val entry = take(params) ?: return
        if (scheduled || entry.expires < System.currentTimeMillis()) return
        Utilities.globalQueue.postRunnable {
            val source = entry.source
            val deleted = when {
                source == null || snapshot(source.path) != source -> false
                entry.imageId > 0 -> deleteMedia(source, entry.imageId)
                else -> deleteFile(source)
            }
            AndroidUtilities.runOnUIThread { showResult(deleted) }
        }
    }

    @JvmStatic
    fun disarm(params: HashMap<String, String>?) {
        take(params)
    }

    private fun take(params: HashMap<String, String>?): Pending? {
        val token = params?.get(PARAM) ?: return null
        return synchronized(pending) { pending.remove(token) }
    }

    private fun snapshot(path: String): Source? = try {
        val file = File(path)
        val state = Os.lstat(file.absolutePath)
        if (!OsConstants.S_ISREG(state.st_mode)) null
        else Source(file.canonicalPath, state.st_dev, state.st_ino, state.st_size, file.lastModified())
    } catch (error: Exception) {
        FileLog.e(error)
        null
    }

    private fun deleteMedia(source: Source, imageId: Int): Boolean {
        val resolver = ApplicationLoader.applicationContext.contentResolver
        val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, imageId.toLong())
        return try {
            val path = resolver.query(uri, arrayOf(MediaStore.MediaColumns.DATA), null, null, null)?.use {
                if (it.moveToFirst()) it.getString(0) else null
            }
            path != null && snapshot(path) == source && resolver.delete(uri, null, null) > 0
        } catch (error: Exception) {
            FileLog.e(error)
            false
        }
    }

    private fun deleteFile(source: Source): Boolean = try {
        File(source.path).delete()
    } catch (error: Exception) {
        FileLog.e(error)
        false
    }

    private fun showResult(deleted: Boolean) {
        NotificationCenter.getGlobalInstance().postNotificationName(
            NotificationCenter.showBulletin,
            if (deleted) Bulletin.TYPE_SUCCESS else Bulletin.TYPE_ERROR,
            LocaleController.getString(if (deleted) R.string.DeleteFromDeviceDone else R.string.DeleteFromDeviceFailed)
        )
    }
}
