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
import java.net.InetSocketAddress
import java.net.Socket

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
        pingDaemon()
    }

    override fun onResume() {
        super.onResume()
        isListening = AudioCaptureService.instance != null
        isFloatingShown = FloatingWidgetService.instance != null
        syncButtonStates()
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

    private fun syncButtonStates() {
        if (isListening) {
            btnStartListening.text = "Stop Listening"
            btnStartListening.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_red)
        } else {
            btnStartListening.text = "Start Listening"
            btnStartListening.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_neutral)
        }
        btnToggleFloating.text = if (isFloatingShown) "Hide Floating Pill" else "Show Floating Pill"
    }

    private fun setupListeners() {
        etServerIp.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) { prefs.serverIp = s.toString().trim() }
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

        rbMic.setOnCheckedChangeListener { _, isChecked -> if (isChecked) prefs.audioSource = "mic" }
        rbInternal.setOnCheckedChangeListener { _, isChecked -> if (isChecked) prefs.audioSource = "internal" }

        btnTestPing.setOnClickListener { pingDaemon() }

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

        // Long press on floating button opens App Info (crucial for Xiaomi / HyperOS Other Permissions)
        btnToggleFloating.setOnLongClickListener {
            try {
                val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:$packageName")
                }
                startActivity(intent)
                Toast.makeText(this, "Enable 'Display pop-up windows while running in background' if on Xiaomi", Toast.LENGTH_LONG).show()
            } catch (_: Exception) {}
            true
        }

        btnStartListening.setOnClickListener {
            if (!isListening) initiateListening() else stopListening()
        }
    }

    private fun pingDaemon() {
        tvPingResult.text = "pinging..."
        updateConnectionStatus(false)

        val hostPort = prefs.serverIp.ifEmpty { "192.168.29.102:8765" }
        val parts = hostPort.split(":")
        val host = parts.getOrElse(0) { "192.168.29.102" }
        val port = parts.getOrElse(1) { "8765" }.toIntOrNull() ?: 8765

        Thread {
            val reachable = try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress(host, port), 3000)
                    true
                }
            } catch (_: Exception) {
                false
            }
            mainHandler.post {
                updateConnectionStatus(reachable)
                tvPingResult.text = if (reachable) "connected to $hostPort" else "offline — daemon not reachable"
            }
        }.start()
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
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) Settings.canDrawOverlays(this) else true
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
        try {
            val intent = Intent(this, FloatingWidgetService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ContextCompat.startForegroundService(this, intent)
            } else {
                startService(intent)
            }
            isFloatingShown = true
            btnToggleFloating.text = "Hide Floating Pill"
            Toast.makeText(this, "Floating pill docked on right edge", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Could not start floating service: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun stopFloatingService() {
        try {
            stopService(Intent(this, FloatingWidgetService::class.java))
            isFloatingShown = false
            btnToggleFloating.text = "Show Floating Pill"
        } catch (_: Exception) {}
    }

    private fun initiateListening() {
        if (rbInternal.isChecked) {
            val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjectionLauncher.launch(projectionManager.createScreenCaptureIntent())
        } else {
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

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ContextCompat.startForegroundService(this, captureIntent)
            } else {
                startService(captureIntent)
            }

            isListening = true
            btnStartListening.text = "Stop Listening"
            btnStartListening.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_red)

            // Auto-show floating pill if overlay is permitted
            if (!isFloatingShown && checkOverlayPermission()) {
                startFloatingService()
            }
        } catch (e: Exception) {
            Toast.makeText(this, "Error starting service: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun stopListening() {
        try {
            val captureIntent = Intent(this, AudioCaptureService::class.java).apply {
                action = AudioCaptureService.ACTION_STOP
            }
            startService(captureIntent)
        } catch (_: Exception) {}

        isListening = false
        btnStartListening.text = "Start Listening"
        btnStartListening.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_neutral)
    }

    fun refreshAlerts() {
        mainHandler.post {
            val alerts = prefs.getAlerts()
            llAlertsContainer.removeAllViews()

            if (alerts.isEmpty()) {
                val tv = TextView(this).apply {
                    text = "No detections yet."
                    setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_tertiary))
                    textSize = 12f
                    setPadding(16.dp, 16.dp, 16.dp, 16.dp)
                    setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.bg_card))
                }
                llAlertsContainer.addView(tv)
                return@post
            }

            for (item in alerts) {
                val card = LayoutInflater.from(this).inflate(R.layout.item_alert_history, llAlertsContainer, false)
                card.findViewById<TextView>(R.id.tvHistorySpeaker).text =
                    item.optString("speaker", "Someone") + " called you"
                card.findViewById<TextView>(R.id.tvHistorySentence).text =
                    "\"${item.optString("sentence", "")}\""
                llAlertsContainer.addView(card)
            }
        }
    }

    private val Int.dp: Int get() = (this * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }
}
