package net.krishai.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/** Share > Krish AI from any app: the text or link opens in a new Krish chat, ready to send. */
class ShareActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val subject = intent.getStringExtra(Intent.EXTRA_SUBJECT).orEmpty().trim()
        val text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString().orEmpty().trim()
        val shared = when {
            subject.isNotEmpty() && text.isNotEmpty() && !text.contains(subject) -> "$subject\n$text"
            text.isNotEmpty() -> text
            else -> subject
        }
        Krish.open(this, if (shared.isEmpty()) "/?new=1" else Krish.askPath(shared))
        finish()
    }
}
