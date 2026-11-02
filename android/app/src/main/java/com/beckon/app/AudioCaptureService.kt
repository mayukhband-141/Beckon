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
import android.media.MediaRecorder
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.beckon.app.audio.AudioStreamer
import com.beckon.app.util.PreferencesManager
import java.util.concurrent.atomic.AtomicBoolean

class AudioCaptureService : Service() {

    private var mediaProjection: MediaProjection? = null
    private var audioRecord: AudioRecord? = null
    private var streamer: AudioStreamer? = null
    private val isRecording = AtomicBoolean(false)
    private var recordingThread: Thread? = null
    private lateinit var prefs: PreferencesManager

    companion object {
        const val ACTION_START = "ACTION_START"
        const val ACTION_STOP = "ACTION_STOP"
        const val EXTRA_SOURCE_TYPE = "EXTRA_SOURCE_TYPE" // "mic" or "internal"
        const val EXTRA_RESULT_DATA = "EXTRA_RESULT_DATA"
        const val EXTRA_SERVER_URL = "EXTRA_SERVER_URL"
        const val EXTRA_NAMES = "EXTRA_NAMES"

        const val SOURCE_MIC = "mic"
        const val SOURCE_INTERNAL = "internal"

        var instance: AudioCaptureService? = null
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = PreferencesManager(this)
        startForegroundNotification()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                val sourceType = intent.getStringExtra(EXTRA_SOURCE_TYPE) ?: SOURCE_MIC
                val resultData = intent.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
                val serverUrl = intent.getStringExtra(EXTRA_SERVER_URL) ?: ("ws://" + prefs.serverIp)
                val names = intent.getStringArrayListExtra(EXTRA_NAMES) ?: arrayListOf(prefs.targetNames)

                startAudioCapture(sourceType, resultData, serverUrl, names)
            }
            ACTION_STOP -> {
                stopAudioCapture()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun startForegroundNotification() {
        val channelId = "beckon_audio_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Beckon Listening Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }

        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Beckon is active")
            .setContentText("Listening for configured identifiers.")
            .setSmallIcon(R.drawable.ic_beckon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

        startForeground(101, notification)
    }

    @SuppressLint("MissingPermission")
    private fun startAudioCapture(
        sourceType: String,
        resultData: Intent?,
        serverUrl: String,
        names: ArrayList<String>
    ) {
        if (isRecording.get()) return

        // 1. Establish WebSocket stream to local daemon
        streamer = AudioStreamer(
            serverUrl = serverUrl,
            onAlertReceived = { speaker, sentence, score ->
                prefs.addAlert(speaker, sentence, score)
                FloatingWidgetService.instance?.showAlert(speaker, sentence, score)
                MainActivity.instance?.refreshAlerts()
            },
            onConnectionChanged = { connected ->
                MainActivity.instance?.updateConnectionStatus(connected)
            }
        )
        streamer?.connect()
        if (names.isNotEmpty()) {
            streamer?.updateTargetNames(names[0], names.drop(1))
        }

        val sampleRate = 16000
        val channelConfig = AudioFormat.CHANNEL_IN_MONO
        val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        val minBufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        val bufferSize = minBufferSize.coerceAtLeast(sampleRate * 2)

        try {
            if (sourceType == SOURCE_INTERNAL && resultData != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // Internal audio loopback via MediaProjection
                val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                mediaProjection = projectionManager.getMediaProjection(android.app.Activity.RESULT_OK, resultData)

                val config = AudioPlaybackCaptureConfiguration.Builder(mediaProjection!!)
                    .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                    .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                    .addMatchingUsage(AudioAttributes.USAGE_GAME)
                    .build()

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
            } else {
                // Default & trusted: Voice recognition mic input (NO screen capture permission needed)
                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
                )
            }

            audioRecord?.startRecording()
            isRecording.set(true)

            recordingThread = Thread {
                val buffer = ByteArray(1600 * 2) // 100ms frames
                while (isRecording.get()) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                    if (read > 0) {
                        streamer?.sendAudioChunk(buffer, 0, read)
                    }
                }
            }.apply { start() }

            Log.d("AudioCaptureService", "Audio capture successfully active using source: $sourceType")
        } catch (e: Exception) {
            Log.e("AudioCaptureService", "Failed to initialize AudioRecord", e)
            stopAudioCapture()
        }
    }

    fun updateNames(canonicalName: String, aliases: List<String>) {
        prefs.targetNames = if (aliases.isNotEmpty()) "$canonicalName, ${aliases.joinToString(", ")}" else canonicalName
        streamer?.updateTargetNames(canonicalName, aliases)
    }

    private fun stopAudioCapture() {
        isRecording.set(false)
        recordingThread?.interrupt()
        recordingThread = null

        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (_: Exception) {}
        audioRecord = null

        try {
            mediaProjection?.stop()
        } catch (_: Exception) {}
        mediaProjection = null

        streamer?.disconnect()
        streamer = null

        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    override fun onDestroy() {
        stopAudioCapture()
        instance = null
        super.onDestroy()
    }
}
