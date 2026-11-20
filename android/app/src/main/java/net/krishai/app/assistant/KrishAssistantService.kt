package net.krishai.app.assistant

import android.service.voice.VoiceInteractionService

/**
 * Lets people choose Krish as the phone's digital assistant (Settings > Apps > Default apps >
 * Digital assistant app). Then holding the home button, the power button or swiping up from a bottom
 * corner (depending on the phone) opens Krish ready to talk.
 */
class KrishAssistantService : VoiceInteractionService()
