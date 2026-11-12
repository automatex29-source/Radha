package net.krishai.app.assistant

import android.content.Context
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService
import net.krishai.app.Krish

class KrishSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession = KrishSession(this)
}

/** The assistant gesture opens Krish full screen, ready to talk. */
class KrishSession(context: Context) : VoiceInteractionSession(context) {
    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        val intent = Krish.intent(context, "/?voice=1")
        try {
            startAssistantActivity(intent)
        } catch (e: RuntimeException) {
            try { context.startActivity(intent) } catch (_: RuntimeException) { }
        }
        hide()
    }
}
