package net.krishai.app.assistant

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognitionService
import android.speech.SpeechRecognizer

/**
 * An assistant app has to offer speech recognition, and Android may make it the phone's default when Krish
 * becomes the assistant. Krish listens inside the app itself, so this hands every request to the phone's
 * other speech service (usually Google's), which keeps voice typing in other apps working as before.
 */
class KrishRecognitionService : RecognitionService() {
    private var recognizer: SpeechRecognizer? = null

    private fun otherService(): ComponentName? {
        val services = packageManager.queryIntentServices(Intent(SERVICE_INTERFACE), PackageManager.GET_META_DATA)
        val others = services.map { it.serviceInfo }.filter { it.packageName != packageName }
        val pick = others.firstOrNull { it.packageName == "com.google.android.googlequicksearchbox" }
            ?: others.firstOrNull { it.packageName == "com.google.android.tts" }
            ?: others.firstOrNull()
        return pick?.let { ComponentName(it.packageName, it.name) }
    }

    override fun onStartListening(intent: Intent, callback: Callback) {
        recognizer?.destroy()
        val other = otherService()
        if (other == null) {
            callback.error(SpeechRecognizer.ERROR_RECOGNIZER_BUSY)
            return
        }
        recognizer = SpeechRecognizer.createSpeechRecognizer(this, other).apply {
            setRecognitionListener(Relay(callback))
            try {
                startListening(intent)
            } catch (e: RuntimeException) {
                callback.error(SpeechRecognizer.ERROR_CLIENT)
            }
        }
    }

    override fun onStopListening(callback: Callback) {
        recognizer?.stopListening()
    }

    override fun onCancel(callback: Callback) {
        recognizer?.cancel()
    }

    override fun onDestroy() {
        recognizer?.destroy()
        recognizer = null
        super.onDestroy()
    }

    private class Relay(private val cb: Callback) : RecognitionListener {
        private fun safe(block: () -> Unit) = try { block() } catch (_: Exception) { }
        override fun onReadyForSpeech(params: Bundle?) = safe { cb.readyForSpeech(params ?: Bundle()) }
        override fun onBeginningOfSpeech() = safe { cb.beginningOfSpeech() }
        override fun onRmsChanged(rmsdB: Float) = safe { cb.rmsChanged(rmsdB) }
        override fun onBufferReceived(buffer: ByteArray?) = safe { buffer?.let { cb.bufferReceived(it) } }
        override fun onEndOfSpeech() = safe { cb.endOfSpeech() }
        override fun onError(error: Int) = safe { cb.error(error) }
        override fun onResults(results: Bundle?) = safe { cb.results(results ?: Bundle()) }
        override fun onPartialResults(partialResults: Bundle?) = safe { cb.partialResults(partialResults ?: Bundle()) }
        override fun onEvent(eventType: Int, params: Bundle?) {}
    }
}
