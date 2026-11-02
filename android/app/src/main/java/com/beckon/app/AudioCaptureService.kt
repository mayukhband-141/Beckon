package com.beckon.app

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
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
import androidx.core.content.ContextCompat
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
        const val EXTRA_SOURCE_TYPE = "EXTRA_SOURCE_TYPE"
        const val EXTRA_RESULT_DATA = "EXTRA_RESULT_DATA"
        const val EXTRA_SERVER_URL = "EXTRA_SERVER_URL"
        const val EXTRA_NAMES = "EXTRA_NAMES"

        const val SOURCE_MIC = "mic"
        const val SOURCE_INTERNAL = "internal"

        private const val CHANNEL_ID = "beckon_audio_channel"
        private const val NOTIF_ID = 101

        var instance: AudioCaptureService? = null
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = PreferencesManager(this)
        ensureNotificationChannel()
        safeStartForeground(null)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                val sourceType = intent.getStringExtra(EXTRA_SOURCE_TYPE) ?: SOURCE_MIC
                val resultData = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(EXTRA_RESULT_DATA)
                }
                val serverUrl = intent.getStringExtra(EXTRA_SERVER_URL) ?: ("ws://" + prefs.serverIp)
                val names = intent.getStringArrayListExtra(EXTRA_NAMES) ?: arrayListOf(prefs.targetNames)

                safeStartForeground(sourceType)
                startAudioCapture(sourceType, resultData, serverUrl, names)
            }
            ACTION_STOP -> {
                stopAudioCapture()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Beckon Listening Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Runs while Beckon is listening for your name"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Beckon is active")
            .setContentText("Listening for configured identifiers.")
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    private fun safeStartForeground(sourceType: String?) {
        val notif = buildNotification()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && sourceType != null) {
                val type = if (sourceType == SOURCE_INTERNAL) {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
                } else {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
                }
                try {
                    startForeground(NOTIF_ID, notif, type)
                    return
                } catch (se: SecurityException) {
                    Log.w("AudioCaptureService", "Could not start FGS with type $type, falling back to basic: ${se.message}")
                }
            }
            startForeground(NOTIF_ID, notif)
        } catch (e: Exception) {
            Log.e("AudioCaptureService", "safeStartForeground failed", e)
        }
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
        if (minBufferSize == AudioRecord.ERROR_BAD_VALUE || minBufferSize == AudioRecord.ERROR) {
            Log.e("AudioCaptureService", "Invalid buffer size, aborting AudioRecord init")
            return
        }
        val bufferSize = minBufferSize.coerceAtLeast(sampleRate * 2)

        try {
            if (sourceType == SOURCE_INTERNAL && resultData != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
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
                // Check runtime permission before starting record
                if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    Log.e("AudioCaptureService", "RECORD_AUDIO permission missing at startAudioCapture")
                    return
                }

                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
                )
            }

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e("AudioCaptureService", "AudioRecord failed to initialize (state=${audioRecord?.state})")
                audioRecord?.release()
                audioRecord = null
                return
            }

            audioRecord?.startRecording()
            isRecording.set(true)

            recordingThread = Thread {
                val buffer = ByteArray(1600 * 2) // 100 ms frames at 16kHz
                while (isRecording.get()) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                    if (read > 0) {
                        streamer?.sendAudioChunk(buffer, 0, read)
                    }
                }
            }.also { it.start() }

            Log.d("AudioCaptureService", "Audio capture successfully active: source=$sourceType")
        } catch (e: Exception) {
            Log.e("AudioCaptureService", "AudioRecord init exception", e)
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

        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null

        try { mediaProjection?.stop() } catch (_: Exception) {}
        mediaProjection = null

        streamer?.disconnect()
        streamer = null

        try {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        stopAudioCapture()
        instance = null
        super.onDestroy()
    }
}
