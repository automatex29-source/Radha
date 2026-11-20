package net.krishai.app

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import com.google.androidbrowserhelper.trusted.LauncherActivity

/** Opens a page of krishai.net inside the Krish app (full screen, signed in). */
object Krish {
    const val SITE = "https://krishai.net"

    /** Longest text passed in from Share or "Ask Krish"; the chat box takes the rest from there. */
    private const val MAX_TEXT = 4000

    /** "/?new=1" a new chat, "/?voice=1" talk to Krish, "/?q=..." a new chat with that text ready to send. */
    fun intent(context: Context, path: String): Intent {
        val sep = if (path.contains('?')) '&' else '?'
        return Intent(Intent.ACTION_VIEW, Uri.parse("$SITE$path${sep}source=android"))
            .setClass(context, LauncherActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }

    fun open(context: Context, path: String) = context.startActivity(intent(context, path))

    fun askPath(text: String): String = "/?q=" + Uri.encode(text.trim().take(MAX_TEXT))

    fun pendingIntent(context: Context, path: String, requestCode: Int): PendingIntent =
        PendingIntent.getActivity(
            context, requestCode, intent(context, path),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
}
