package com.beckon.app

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.beckon.app.util.PreferencesManager
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: PreferencesManager

    private lateinit var etTargetNames: EditText
    private lateinit var etServerIp: EditText
    private lateinit var btnTestPing: Button
    private lateinit var tvPingResult: TextView
    private lateinit var dotEngineStatus: View
    private lateinit var tvEngineStatus: TextView

    private lateinit var rbMic: RadioButton
    private lateinit var rbInternal: RadioButton
    private lateinit var btnToggleFloating: Button
    private lateinit var btnStartListening: Button
    private lateinit var llAlertsContainer: LinearLayout
    private lateinit var tvNoAlerts: TextView

    private var isListening = false
    private var isFloatingShown = false
    private val mainHandler = Handler(Looper.getMainLooper())

    companion object {
        var instance: MainActivity? = null
            private set
    }

    private val micPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            startAudioService(AudioCaptureService.SOURCE_MIC, null)
        } else {
            Toast.makeText(this, "Microphone permission is required to listen.", Toast.LENGTH_SHORT).show()
        }
    }

    private val overlayPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        if (checkOverlayPermission()) {
            startFloatingService()
        } else {
            Toast.makeText(this, "Display over other apps permission required for floating pill.", Toast.LENGTH_LONG).show()
        }
    }

    private val mediaProjectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            startAudioService(AudioCaptureService.SOURCE_INTERNAL, result.data)
        } else {
            Toast.makeText(this, "Internal audio permission declined.", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        instance = this
        prefs = PreferencesManager(this)
        setContentView(R.layout.activity_main)

        initViews()
        loadPreferences()
        setupListeners()
        refreshAlerts()
        testDaemonPing()
    }

    private fun initViews() {
        etTargetNames = findViewById(R.id.etTargetNamesDashboard)
        etServerIp = findViewById(R.id.etServerIp)
        btnTestPing = findViewById(R.id.btnTestPing)
        tvPingResult = findViewById(R.id.tvPingResult)
        dotEngineStatus = findViewById(R.id.dotEngineStatus)
        tvEngineStatus = findViewById(R.id.tvEngineStatus)

        rbMic = findViewById(R.id.rbMic)
        rbInternal = findViewById(R.id.rbInternal)
        btnToggleFloating = findViewById(R.id.btnToggleFloating)
        btnStartListening = findViewById(R.id.btnStartListening)
        llAlertsContainer = findViewById(R.id.llAlertsContainer)
        tvNoAlerts = findViewById(R.id.tvNoAlerts)
    }

    private fun loadPreferences() {
        etServerIp.setText(prefs.serverIp)
        etTargetNames.setText(prefs.targetNames)
        if (prefs.audioSource == "internal") {
            rbInternal.isChecked = true
        } else {
            rbMic.isChecked = true
        }
    }

    private fun setupListeners() {
        etServerIp.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                prefs.serverIp = s.toString().trim()
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        etTargetNames.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                val names = s.toString().trim()
                prefs.targetNames = names
                FloatingWidgetService.instance?.updateNamesFromDashboard(names)
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        rbMic.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) prefs.audioSource = "mic"
        }
        rbInternal.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) prefs.audioSource = "internal"
        }

        btnTestPing.setOnClickListener {
            testDaemonPing()
        }

        btnToggleFloating.setOnClickListener {
            if (!isFloatingShown) {
                if (!checkOverlayPermission()) {
                    requestOverlayPermission()
                } else {
                    startFloatingService()
                }
            } else {
                stopFloatingService()
            }
        }

        btnStartListening.setOnClickListener {
            if (!isListening) {
                initiateListening()
            } else {
                stopListening()
            }
        }
    }

    private fun testDaemonPing() {
        tvPingResult.text = "pinging..."
        val host = prefs.serverIp.ifEmpty { "192.168.29.102:8765" }
        val url = if (host.startsWith("ws://")) host else "ws://$host"

        val client = OkHttpClient.Builder().connectTimeout(2, TimeUnit.SECONDS).build()
        val request = Request.Builder().url(url).build()

        client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                mainHandler.post {
                    updateConnectionStatus(true)
                    tvPingResult.text = "connected to $host"
                }
                webSocket.close(1000, "ping")
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                mainHandler.post {
                    updateConnectionStatus(false)
                    tvPingResult.text = "offline (${t.message ?: "timeout"})"
                }
            }
        })
    }

    fun updateConnectionStatus(connected: Boolean) {
        mainHandler.post {
            if (connected) {
                dotEngineStatus.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_green)
                tvEngineStatus.text = "ready"
                tvEngineStatus.setTextColor(ContextCompat.getColor(this, R.color.accent_green))
            } else {
                dotEngineStatus.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_red)
                tvEngineStatus.text = "offline"
                tvEngineStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
            }
        }
    }

    private fun checkOverlayPermission(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(this)
        } else {
            true
        }
    }

    private fun requestOverlayPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:$packageName")
            )
            overlayPermissionLauncher.launch(intent)
        }
    }

    private fun startFloatingService() {
        val intent = Intent(this, FloatingWidgetService::class.java)
        startService(intent)
        isFloatingShown = true
        btnToggleFloating.text = "Hide Floating Pill"
        Toast.makeText(this, "Floating pill docked on right edge", Toast.LENGTH_SHORT).show()
    }

    private fun stopFloatingService() {
        val intent = Intent(this, FloatingWidgetService::class.java)
        stopService(intent)
        isFloatingShown = false
        btnToggleFloating.text = "Show Floating Pill"
    }

    private fun initiateListening() {
        if (rbInternal.isChecked) {
            // Internal audio requires MediaProjection
            val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjectionLauncher.launch(projectionManager.createScreenCaptureIntent())
        } else {
            // Standard microphone input - ONLY requests microphone permission!
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                startAudioService(AudioCaptureService.SOURCE_MIC, null)
            } else {
                micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            }
        }
    }

    private fun startAudioService(sourceType: String, mediaProjectionData: Intent?) {
        val serverUrl = "ws://" + prefs.serverIp
        val namesList = prefs.targetNames.split(",").map { it.trim() }.filter { it.isNotEmpty() }

        val captureIntent = Intent(this, AudioCaptureService::class.java).apply {
            action = AudioCaptureService.ACTION_START
            putExtra(AudioCaptureService.EXTRA_SOURCE_TYPE, sourceType)
            putExtra(AudioCaptureService.EXTRA_RESULT_DATA, mediaProjectionData)
            putExtra(AudioCaptureService.EXTRA_SERVER_URL, serverUrl)
            putStringArrayListExtra(AudioCaptureService.EXTRA_NAMES, ArrayList(namesList))
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(captureIntent)
        } else {
            startService(captureIntent)
        }

        isListening = true
        btnStartListening.text = "Stop Listening"
        btnStartListening.setBackgroundColor(ContextCompat.getColor(this, R.color.accent_red))

        // Also ensure floating pill is visible
        if (!isFloatingShown && checkOverlayPermission()) {
            startFloatingService()
        }
    }

    private fun stopListening() {
        val captureIntent = Intent(this, AudioCaptureService::class.java).apply {
            action = AudioCaptureService.ACTION_STOP
        }
        startService(captureIntent)

        isListening = false
        btnStartListening.text = "Start Listening"
        btnStartListening.setBackgroundColor(ContextCompat.getColor(this, R.color.accent_neutral))
    }

    fun refreshAlerts() {
        mainHandler.post {
            val alerts = prefs.getAlerts()
            llAlertsContainer.removeAllViews()

            if (alerts.isEmpty()) {
                llAlertsContainer.addView(tvNoAlerts)
                return@post
            }

            for (item in alerts) {
                val card = LayoutInflater.from(this).inflate(R.layout.item_alert_history, llAlertsContainer, false)
                val tvSpeaker = card.findViewById<TextView>(R.id.tvHistorySpeaker)
                val tvSentence = card.findViewById<TextView>(R.id.tvHistorySentence)

                val speaker = item.optString("speaker", "Someone")
                val sentence = item.optString("sentence", "")

                tvSpeaker.text = "$speaker called you"
                tvSentence.text = "\"$sentence\""

                llAlertsContainer.addView(card)
            }
        }
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }
}
