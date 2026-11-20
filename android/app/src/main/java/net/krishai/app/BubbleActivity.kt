package net.krishai.app

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast

/**
 * Turns the floating Krish button on or off (long-press the Krish icon > "Floating button", or the button
 * in Krish's menu inside the app). The first time, Android asks to let Krish "display over other apps".
 */
class BubbleActivity : Activity() {
    private var askedForPermission = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val wanted = when (intent?.data?.getQueryParameter("on")) {
            "1" -> true
            "0" -> false
            else -> !BubbleService.isEnabled(this)
        }
        if (!wanted) {
            BubbleService.stop(this)
            Toast.makeText(this, R.string.bubbleOff, Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        if (Settings.canDrawOverlays(this)) turnOn() else askForPermission()
    }

    private fun askForPermission() {
        askedForPermission = true
        Toast.makeText(this, R.string.bubblePermission, Toast.LENGTH_LONG).show()
        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
    }

    // Back from Android's "display over other apps" screen.
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus || !askedForPermission) return
        if (Settings.canDrawOverlays(this)) turnOn() else finish()
    }

    private fun turnOn() {
        BubbleService.start(this)
        Toast.makeText(this, R.string.bubbleOn, Toast.LENGTH_LONG).show()
        finish()
    }
}
