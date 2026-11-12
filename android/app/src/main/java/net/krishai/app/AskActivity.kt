package net.krishai.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * "Ask Krish" in the menu that shows when you select text in any app, and the phone's "assist" action:
 * selected text opens in a new chat; with no text, Krish opens ready to talk.
 */
class AskActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val text = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString().orEmpty().trim()
        Krish.open(this, if (text.isEmpty()) "/?voice=1" else Krish.askPath(text))
        finish()
    }
}
