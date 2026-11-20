package net.krishai.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Settings

/** Brings the floating Krish button back after the phone restarts, if it was on. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        if (BubbleService.isEnabled(context) && Settings.canDrawOverlays(context)) {
            runCatching { BubbleService.start(context) }
        }
    }
}
