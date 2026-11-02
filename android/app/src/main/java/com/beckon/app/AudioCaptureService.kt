package com.beckon.app

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.beckon.app.audio.AudioStreamer
import java.util.concurrent.atomic.AtomicBoolean

class AudioCaptureService : Service() {

    private var mediaProjection: MediaProjection? = null
    private var audioRecord: AudioRecord? = null
    private var streamer: AudioStreamer? = null
    private val isRecording = AtomicBoolean(false)
    private var recordingThread: Thread? = null

    companion object {
        const val ACTION_START = "ACTION_START"
        const val ACTION_STOP = "ACTION_STOP"
        const val EXTRA_RESULT_DATA = "EXTRA_RESULT_DATA"
        const val EXTRA_SERVER_URL = "EXTRA_SERVER_URL"
        const val EXTRA_NAMES = "EXTRA_NAMES"

        var instance: AudioCaptureService? = null
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        startForegroundServiceNotification()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                val resultData = intent.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
                val serverUrl = intent.getStringExtra(EXTRA_SERVER_URL) ?: "ws://10.0.2.2:8765"
                val names = intent.getStringArrayListExtra(EXTRA_NAMES) ?: arrayListOf("Mayukh")

                if (resultData != null) {
                    startAudioCapture(resultData, serverUrl, names)
                }
            }
            ACTION_STOP -> {
                stopAudioCapture()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun startForegroundServiceNotification() {
        val channelId = "beckon_audio_capture"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Beckon Audio Listener",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }

        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Beckon is listening")
            .setContentText("Monitoring meeting audio on-device.")
            .setSmallIcon(R.drawable.ic_beckon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        startForeground(101, notification)
    }

    @SuppressLint("MissingPermission")
    private fun startAudioCapture(resultData: Intent, serverUrl: String, names: ArrayList<String>) {
        if (isRecording.get()) return

        val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjection = projectionManager.getMediaProjection(android.app.Activity.RESULT_OK, resultData)

        if (mediaProjection == null) {
            Log.e("AudioCaptureService", "MediaProjection was null")
            return
        }

        // Initialize WebSocket streamer to Whisper daemon
        streamer = AudioStreamer(
            serverUrl = serverUrl,
            onAlertReceived = { speaker, sentence, score ->
                FloatingWidgetService.instance?.showAlert(speaker, sentence, score)
            },
            onConnectionChanged = { connected ->
                Log.d("AudioCaptureService", "Streamer connection status: $connected")
            }
        )
        streamer?.connect()
        if (names.isNotEmpty()) {
            streamer?.updateTargetNames(names[0], names.drop(1))
        }

        val sampleRate = 16000
        val channelConfig = AudioFormat.CHANNEL_IN_MONO
        val audioFormat = AudioFormat.ENCODING_PCM_16BIT

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val config = AudioPlaybackCaptureConfiguration.Builder(mediaProjection!!)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                .addMatchingUsage(AudioAttributes.USAGE_GAME)
                .build()

            val minBufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
            val bufferSize = minBufferSize.coerceAtLeast(sampleRate * 2) // 1 second buffer

            audioRecord = AudioRecord.Builder()
                .setAudioPlaybackCaptureConfig(config)
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(audioFormat)
                        .setSampleRate(sampleRate)
                        .setChannelMask(channelConfig)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .build()
        }

        audioRecord?.startRecording()
        isRecording.set(true)

        recordingThread = Thread {
            val buffer = ByteArray(1600 * 2) // 100ms chunks at 16kHz 16-bit
            while (isRecording.get()) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                if (read > 0) {
                    streamer?.sendAudioChunk(buffer, 0, read)
                }
            }
        }.apply { start() }

        Log.d("AudioCaptureService", "Internal AudioPlaybackCapture running.")
    }

    private fun stopAudioCapture() {
        isRecording.set(false)
        recordingThread?.interrupt()
        recordingThread = null

        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        mediaProjection?.stop()
        mediaProjection = null

        streamer?.disconnect()
        streamer = null

        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    fun updateNames(canonicalName: String, aliases: List<String>) {
        streamer?.updateTargetNames(canonicalName, aliases)
    }

    override fun onDestroy() {
        stopAudioCapture()
        instance = null
        super.onDestroy()
    }
}
