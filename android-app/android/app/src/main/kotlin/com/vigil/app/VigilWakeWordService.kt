package com.vigil.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import androidx.core.app.NotificationCompat
import java.util.Locale

class VigilWakeWordService : Service() {

    companion object {
        const val TAG = "VigilWakeWord"
        const val CHANNEL_ID = "vigil_wake_word"
        const val NOTIFICATION_ID = 2
        const val WAKE_WORD = "vigil"
        var isListening = false
        var isSpeakingWake = false
    }

    private var speechRecognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var isDestroyed = false

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        initTts()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        startForeground(NOTIFICATION_ID, notification)
        startWakeWordDetection()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Vigil Wake Word",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Listening for 'Vigil' wake word"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            else
                PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Vigil — listening for 'Vigil'")
            .setContentText("Say \"Vigil\" to activate")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(openPendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun initTts() {
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.US
            }
        }
        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onDone(utteranceId: String?) {
                isSpeakingWake = false
                if (!isDestroyed) startWakeWordDetection()
            }

            override fun onError(utteranceId: String?) {
                isSpeakingWake = false
                if (!isDestroyed) startWakeWordDetection()
            }

            override fun onStart(utteranceId: String?) {}
        })
    }

    private fun startWakeWordDetection() {
        if (isDestroyed || isSpeakingWake) return
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {}

        isListening = true
        try {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)
            speechRecognizer?.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {
                    restartListening()
                }

                override fun onError(error: Int) {
                    Log.e(TAG, "SpeechRecognizer error: $error")
                    if (!isDestroyed) {
                        Thread.sleep(500)
                        startWakeWordDetection()
                    }
                }

                override fun onResults(results: Bundle?) {
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if (matches != null) {
                        for (match in matches) {
                            val text = match.lowercase(Locale.ROOT).trim()
                            if (text.contains(WAKE_WORD)) {
                                onWakeWordDetected()
                                return
                            }
                        }
                    }
                    if (!isDestroyed) startWakeWordDetection()
                }

                override fun onPartialResults(partialResults: Bundle?) {
                    val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if (matches != null) {
                        for (match in matches) {
                            val text = match.lowercase(Locale.ROOT).trim()
                            if (text.contains(WAKE_WORD)) {
                                onWakeWordDetected()
                                return
                            }
                        }
                    }
                }

                override fun onEvent(eventType: Int, params: Bundle?) {}
            })

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
                putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            }
            speechRecognizer?.startListening(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start wake word: ${e.message}")
        }
    }

    private fun restartListening() {
        if (!isDestroyed) startWakeWordDetection()
    }

    private fun onWakeWordDetected() {
        isListening = false
        isSpeakingWake = true
        try { speechRecognizer?.stopListening() } catch (_: Exception) {}
        try { speechRecognizer?.destroy() } catch (_: Exception) {}

        val response = "I'm here. Alert count: ${getAlertCount()}. Say a command."
        tts?.speak(response, TextToSpeech.QUEUE_FLUSH, null, "wake_response")
    }

    private fun getAlertCount(): Int {
        return VigilForegroundService.alertCount
    }

    override fun onDestroy() {
        isDestroyed = true
        isListening = false
        isSpeakingWake = false
        try { speechRecognizer?.destroy() } catch (_: Exception) {}
        try { tts?.stop() } catch (_: Exception) {}
        try { tts?.shutdown() } catch (_: Exception) {}
        super.onDestroy()
    }
}
