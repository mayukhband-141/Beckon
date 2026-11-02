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
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.beckon.app.util.PreferencesManager
import java.net.ConnectException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: PreferencesManager

    private lateinit var etTargetNames: EditText
    private lateinit var etServerIp: EditText
    private lateinit var btnTestPing: Button
    private lateinit var tvPingResult: TextView
    private lateinit var dotEngineStatus: View
    private lateinit var tvEngineStatus: TextView

    private lateinit var tvPermNotifications: TextView
    private lateinit var tvPermMic: TextView
    private lateinit var tvPermOverlay: TextView
    private lateinit var tvGrantAllPermissions: TextView
    private lateinit var btnMiuiPopups: TextView

    private lateinit var rbMic: RadioButton
    private lateinit var rbInternal: RadioButton
    private lateinit var btnToggleFloating: Button
    private lateinit var btnStartListening: Button
    private lateinit var llAlertsContainer: LinearLayout

    private var isListening = false
    private var isFloatingShown = false
    private val mainHandler = Handler(Looper.getMainLooper())
    private var pendingActionAfterPermissions: (() -> Unit)? = null

    companion object {
        var instance: MainActivity? = null
            private set
    }

    // --- Sequential Permission Launchers ---

    private val notifPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        updatePermissionsUi()
        if (granted) {
            // Step to next: Microphone
            gateMicPermission()
        } else {
            Toast.makeText(this, "Notification permission is recommended for status display.", Toast.LENGTH_SHORT).show()
            gateMicPermission()
        }
    }

    private val micPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        updatePermissionsUi()
        if (granted) {
            // Step to next: Overlay
            gateOverlayPermission()
        } else {
            Toast.makeText(this, "Microphone permission is required to listen.", Toast.LENGTH_SHORT).show()
            pendingActionAfterPermissions = null
        }
    }

    private val overlayPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        updatePermissionsUi()
        if (checkOverlayPermission()) {
            pendingActionAfterPermissions?.invoke()
            pendingActionAfterPermissions = null
        } else {
            Toast.makeText(this, "Display over other apps permission required for floating pill.", Toast.LENGTH_LONG).show()
            pendingActionAfterPermissions = null
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
        updatePermissionsUi()
    }

    private fun initViews() {
        etTargetNames = findViewById(R.id.etTargetNamesDashboard)
        etServerIp = findViewById(R.id.etServerIp)
        btnTestPing = findViewById(R.id.btnTestPing)
        tvPingResult = findViewById(R.id.tvPingResult)
        dotEngineStatus = findViewById(R.id.dotEngineStatus)
        tvEngineStatus = findViewById(R.id.tvEngineStatus)

        tvPermNotifications = findViewById(R.id.tvPermNotifications)
        tvPermMic = findViewById(R.id.tvPermMic)
        tvPermOverlay = findViewById(R.id.tvPermOverlay)
        tvGrantAllPermissions = findViewById(R.id.tvGrantAllPermissions)
        btnMiuiPopups = findViewById(R.id.btnMiuiPopups)

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

    private fun updatePermissionsUi() {
        val hasNotif = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        } else {
            true
        }
        val hasMic = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        val hasOverlay = checkOverlayPermission()

        tvPermNotifications.text = if (hasNotif) "Notif: Granted" else "Notif: Needed"
        tvPermNotifications.setTextColor(ContextCompat.getColor(this, if (hasNotif) R.color.accent_green else R.color.accent_red))

        tvPermMic.text = if (hasMic) "Mic: Granted" else "Mic: Needed"
        tvPermMic.setTextColor(ContextCompat.getColor(this, if (hasMic) R.color.accent_green else R.color.accent_red))

        tvPermOverlay.text = if (hasOverlay) "Overlay: Granted" else "Overlay: Needed"
        tvPermOverlay.setTextColor(ContextCompat.getColor(this, if (hasOverlay) R.color.accent_green else R.color.accent_red))

        tvGrantAllPermissions.visibility = if (hasNotif && hasMic && hasOverlay) View.GONE else View.VISIBLE
    }

    // --- Sequential Permission Gate: Notif -> Mic -> Overlay ---

    fun startSequentialPermissionsGate(onCompleted: (() -> Unit)? = null) {
        pendingActionAfterPermissions = onCompleted
        gateNotificationPermission()
    }

    private fun gateNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                notifPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                return
            }
        }
        gateMicPermission()
    }

    private fun gateMicPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        gateOverlayPermission()
    }

    private fun gateOverlayPermission() {
        if (!checkOverlayPermission()) {
            requestOverlayPermission()
            return
        }
        // All permissions satisfied!
        updatePermissionsUi()
        pendingActionAfterPermissions?.invoke()
        pendingActionAfterPermissions = null
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

        tvGrantAllPermissions.setOnClickListener {
            startSequentialPermissionsGate()
        }

        btnMiuiPopups.setOnClickListener {
            openMiuiPermissions(this)
        }

        btnToggleFloating.setOnClickListener {
            if (!isFloatingShown) {
                if (!checkOverlayPermission()) {
                    pendingActionAfterPermissions = { startFloatingService() }
                    requestOverlayPermission()
                } else {
                    startFloatingService()
                }
            } else {
                stopFloatingService()
            }
        }

        btnToggleFloating.setOnLongClickListener {
            openMiuiPermissions(this)
            true
        }

        btnStartListening.setOnClickListener {
            if (!isListening) {
                initiateListening()
            } else {
                stopListening()
            }
        }
    }

    // --- Ping via raw TCP socket with detailed diagnostics ---
    private fun pingDaemon() {
        tvPingResult.text = "pinging..."
        updateConnectionStatus(false)

        val hostPort = prefs.serverIp.ifEmpty { "192.168.29.102:8765" }
        val parts = hostPort.split(":")
        val host = parts.getOrElse(0) { "192.168.29.102" }
        val port = parts.getOrElse(1) { "8765" }.toIntOrNull() ?: 8765

        Thread {
            try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress(host, port), 4000)
                }
                mainHandler.post {
                    updateConnectionStatus(true)
                    tvPingResult.text = "connected to $hostPort"
                }
            } catch (e: SocketTimeoutException) {
                mainHandler.post {
                    updateConnectionStatus(false)
                    tvPingResult.text = "offline (timeout: check PC firewall/Wi-Fi)"
                }
            } catch (e: ConnectException) {
                mainHandler.post {
                    updateConnectionStatus(false)
                    tvPingResult.text = "offline (connection refused: is daemon running?)"
                }
            } catch (e: Exception) {
                mainHandler.post {
                    updateConnectionStatus(false)
                    tvPingResult.text = "offline (${e.javaClass.simpleName}: ${e.message})"
                }
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

    private fun openMiuiPermissions(context: Context) {
        try {
            val intent = Intent("miui.intent.action.APP_PERM_EDITOR").apply {
                setClassName("com.miui.securitycenter", "com.miui.permcenter.permissions.PermissionsEditorActivity")
                putExtra("extra_pkgname", context.packageName)
            }
            context.startActivity(intent)
            Toast.makeText(context, "Allow 'Display pop-up windows while running in background'", Toast.LENGTH_LONG).show()
        } catch (_: Exception) {
            try {
                val intent = Intent("miui.intent.action.APP_PERM_EDITOR").apply {
                    putExtra("extra_pkgname", context.packageName)
                }
                context.startActivity(intent)
                Toast.makeText(context, "Allow 'Display pop-up windows while running in background'", Toast.LENGTH_LONG).show()
            } catch (_: Exception) {
                val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:${context.packageName}")
                }
                context.startActivity(intent)
                Toast.makeText(context, "Tap Other Permissions -> Display pop-up windows", Toast.LENGTH_LONG).show()
            }
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
            onServiceError("Could not start floating service: ${e.message}")
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
            // Sequential check: if mic or notif missing, start sequence, then launch audio service
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                startAudioService(AudioCaptureService.SOURCE_MIC, null)
            } else {
                startSequentialPermissionsGate {
                    startAudioService(AudioCaptureService.SOURCE_MIC, null)
                }
            }
        }
    }

    fun onServiceError(message: String) {
        isListening = false
        syncButtonStates()
        tvPingResult.text = "Error: $message"
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun startAudioService(sourceType: String, mediaProjectionData: Intent?) {
        if (sourceType == AudioCaptureService.SOURCE_MIC) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                onServiceError("Microphone permission required")
                micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                return
            }
        }

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
            onServiceError(e.message ?: "Failed to start listening service")
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
