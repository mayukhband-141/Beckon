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
import androidx.lifecycle.lifecycleScope
import com.beckon.app.util.PreferencesManager
import kotlinx.coroutines.launch
import java.net.ConnectException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: PreferencesManager

    // Shazam Hero Screen Views
    private lateinit var btnShazamHero: View
    private lateinit var tvShazamTitle: TextView
    private lateinit var tvShazamSubtitle: TextView
    private lateinit var tvShazamStatusPill: TextView
    private lateinit var viewShazamPulseRing: View
    private lateinit var btnChangeTargetName: View
    private lateinit var tvShazamTargetName: TextView
    private lateinit var btnAutoScanIp: View
    private lateinit var tvCurrentIpDisplay: TextView
    private lateinit var tvScanLabel: TextView
    private var pulseAnimator: android.animation.ValueAnimator? = null

    private lateinit var etTargetNames: EditText
    private lateinit var etServerIp: EditText
    private lateinit var etGroqApiKey: EditText
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

    // Dual-page navigation views
    private lateinit var pageListener: View
    private lateinit var pageDaemon: View
    private lateinit var tabListener: View
    private lateinit var tabDaemon: View
    private lateinit var ivTabListener: ImageView
    private lateinit var tvTabListener: TextView
    private lateinit var ivTabDaemon: ImageView
    private lateinit var tvTabDaemon: TextView

    // Soundwave equalizer animation views
    private lateinit var llEqualizerBars: View
    private lateinit var eqBar1: View
    private lateinit var eqBar2: View
    private lateinit var eqBar3: View
    private lateinit var eqBar4: View
    private var equalizerAnimator: android.animation.ValueAnimator? = null

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
        if (prefs.serverIp.isBlank() || prefs.serverIp.startsWith("192.168.1.100")) {
            autoDetectDaemon()
        } else {
            pingDaemon()
        }
    }

    override fun onResume() {
        super.onResume()
        isListening = AudioCaptureService.instance != null
        isFloatingShown = FloatingWidgetService.instance != null
        syncButtonStates()
        updatePermissionsUi()
    }

    private fun initViews() {
        // Shazam Hero Screen bindings
        btnShazamHero = findViewById(R.id.btnShazamHero)
        tvShazamTitle = findViewById(R.id.tvShazamTitle)
        tvShazamSubtitle = findViewById(R.id.tvShazamSubtitle)
        tvShazamStatusPill = findViewById(R.id.tvShazamStatusPill)
        viewShazamPulseRing = findViewById(R.id.viewShazamPulseRing)
        btnChangeTargetName = findViewById(R.id.btnChangeTargetName)
        tvShazamTargetName = findViewById(R.id.tvShazamTargetName)
        btnAutoScanIp = findViewById(R.id.btnAutoScanIp)
        tvCurrentIpDisplay = findViewById(R.id.tvCurrentIpDisplay)
        tvScanLabel = findViewById(R.id.tvScanLabel)

        etTargetNames = findViewById(R.id.etTargetNamesDashboard)
        etServerIp = findViewById(R.id.etServerIp)
        etGroqApiKey = findViewById(R.id.etGroqApiKey)
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

        // Dual-page view bindings
        pageListener = findViewById(R.id.pageListener)
        pageDaemon = findViewById(R.id.pageDaemon)
        tabListener = findViewById(R.id.tabListener)
        tabDaemon = findViewById(R.id.tabDaemon)
        ivTabListener = findViewById(R.id.ivTabListener)
        tvTabListener = findViewById(R.id.tvTabListener)
        ivTabDaemon = findViewById(R.id.ivTabDaemon)
        tvTabDaemon = findViewById(R.id.tvTabDaemon)

        // Soundwave animation view bindings
        llEqualizerBars = findViewById(R.id.llEqualizerBars)
        eqBar1 = findViewById(R.id.eqBar1)
        eqBar2 = findViewById(R.id.eqBar2)
        eqBar3 = findViewById(R.id.eqBar3)
        eqBar4 = findViewById(R.id.eqBar4)
    }

    private fun switchTab(showListener: Boolean) {
        val targetPage = if (showListener) pageListener else pageDaemon
        val hidePage = if (showListener) pageDaemon else pageListener

        if (targetPage.visibility == View.VISIBLE) return

        targetPage.alpha = 0f
        targetPage.visibility = View.VISIBLE
        targetPage.animate().alpha(1f).setDuration(200).start()

        hidePage.animate().alpha(0f).setDuration(160).withEndAction {
            hidePage.visibility = View.GONE
        }.start()

        val activeColor = ContextCompat.getColor(this, R.color.accent_green)
        val inactiveColor = ContextCompat.getColor(this, R.color.text_tertiary)

        ivTabListener.setColorFilter(if (showListener) activeColor else inactiveColor)
        tvTabListener.setTextColor(if (showListener) activeColor else inactiveColor)

        ivTabDaemon.setColorFilter(if (!showListener) activeColor else inactiveColor)
        tvTabDaemon.setTextColor(if (!showListener) activeColor else inactiveColor)
    }

    private fun startEqualizerAnimation() {
        llEqualizerBars.visibility = View.VISIBLE
        equalizerAnimator?.cancel()
        equalizerAnimator = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 550
            repeatCount = android.animation.ValueAnimator.INFINITE
            repeatMode = android.animation.ValueAnimator.REVERSE
            addUpdateListener { animator ->
                val fraction = animator.animatedValue as Float
                eqBar1.scaleY = 0.35f + fraction * 0.9f
                eqBar2.scaleY = 1.0f - fraction * 0.65f
                eqBar3.scaleY = 0.45f + fraction * 0.85f
                eqBar4.scaleY = 1.1f - fraction * 0.75f
            }
            start()
        }
    }

    private fun stopEqualizerAnimation() {
        equalizerAnimator?.cancel()
        equalizerAnimator = null
        llEqualizerBars.visibility = View.GONE
    }

    private fun loadPreferences() {
        etServerIp.setText(prefs.serverIp)
        etTargetNames.setText(prefs.targetNames)
        etGroqApiKey.setText(prefs.groqApiKey)
        if (prefs.audioSource == "internal") {
            rbInternal.isChecked = true
        } else {
            rbMic.isChecked = true
        }

        val currentNames = prefs.targetNames
        val firstName = currentNames.split(",").firstOrNull()?.trim() ?: "Mayukh"
        tvShazamTargetName.text = if (firstName.isNotEmpty()) firstName else "Mayukh"
        tvCurrentIpDisplay.text = prefs.serverIp.ifEmpty { "192.168.29.102:8765" }
    }

    private fun startPulseAnimation() {
        viewShazamPulseRing.visibility = View.VISIBLE
        pulseAnimator?.cancel()
        pulseAnimator = android.animation.ValueAnimator.ofFloat(1.0f, 1.28f).apply {
            duration = 1000
            repeatCount = android.animation.ValueAnimator.INFINITE
            repeatMode = android.animation.ValueAnimator.REVERSE
            addUpdateListener { animator ->
                val scale = animator.animatedValue as Float
                viewShazamPulseRing.scaleX = scale
                viewShazamPulseRing.scaleY = scale
                viewShazamPulseRing.alpha = 1.2f - (scale - 1.0f) * 3f
            }
            start()
        }
    }

    private fun stopPulseAnimation() {
        pulseAnimator?.cancel()
        pulseAnimator = null
        viewShazamPulseRing.visibility = View.GONE
        viewShazamPulseRing.scaleX = 1f
        viewShazamPulseRing.scaleY = 1f
    }

    private fun syncButtonStates() {
        val currentNames = prefs.targetNames
        val firstName = currentNames.split(",").firstOrNull()?.trim() ?: "Mayukh"
        val displayName = if (firstName.isNotEmpty()) firstName else "Mayukh"
        tvShazamTargetName.text = displayName

        if (isListening) {
            tvShazamTitle.text = "Listening for $displayName"
            tvShazamSubtitle.text = "Audio is streaming live to Beckon PC"
            tvShazamStatusPill.text = "ACTIVE • LISTENING LIVE"
            tvShazamStatusPill.setTextColor(ContextCompat.getColor(this, R.color.accent_green))
            startPulseAnimation()
        } else {
            tvShazamTitle.text = "Tap to Beckon"
            tvShazamSubtitle.text = "Hears your name and alerts you instantly"
            tvShazamStatusPill.text = "IDLE • TAP CIRCLE TO START"
            tvShazamStatusPill.setTextColor(ContextCompat.getColor(this, R.color.text_tertiary))
            stopPulseAnimation()
        }

        if (btnStartListening is com.google.android.material.button.MaterialButton) {
            val mb = btnStartListening as com.google.android.material.button.MaterialButton
            if (isListening) {
                mb.text = "Stop Monitoring"
                mb.setIconResource(R.drawable.ic_stop)
                mb.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_red)
                mb.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
                mb.iconTint = ContextCompat.getColorStateList(this, R.color.text_primary)
                startEqualizerAnimation()
            } else {
                mb.text = "Start Monitoring"
                mb.setIconResource(R.drawable.ic_nav_listener)
                mb.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_neutral)
                mb.setTextColor(android.graphics.Color.parseColor("#09090B"))
                mb.iconTint = android.content.res.ColorStateList.valueOf(android.graphics.Color.parseColor("#09090B"))
                stopEqualizerAnimation()
            }
        } else {
            btnStartListening.text = if (isListening) "Stop Monitoring" else "Start Monitoring"
            btnStartListening.backgroundTintList = ContextCompat.getColorStateList(
                this,
                if (isListening) R.color.accent_red else R.color.accent_neutral
            )
            if (isListening) startEqualizerAnimation() else stopEqualizerAnimation()
        }
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

        etGroqApiKey.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                val key = s.toString().trim()
                prefs.groqApiKey = key
                AudioCaptureService.instance?.updateGroqApiKey(key)
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

        rbMic.setOnCheckedChangeListener { _, isChecked -> if (isChecked) prefs.audioSource = "mic" }
        rbInternal.setOnCheckedChangeListener { _, isChecked -> if (isChecked) prefs.audioSource = "internal" }

        tabListener.setOnClickListener { switchTab(showListener = true) }
        tabDaemon.setOnClickListener { switchTab(showListener = false) }

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

        // Shazam Hero Screen Click Listeners
        btnShazamHero.setOnClickListener {
            if (!isListening) {
                initiateListening()
            } else {
                stopListening()
            }
        }

        btnChangeTargetName.setOnClickListener {
            showChangeTargetNameDialog()
        }

        btnAutoScanIp.setOnClickListener {
            autoDetectDaemon()
        }
    }

    private fun showChangeTargetNameDialog() {
        val input = EditText(this).apply {
            setText(prefs.targetNames)
            hint = "Mayukh, Alex"
            setPadding(48, 36, 48, 36)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
        }
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Set Target Name")
            .setMessage("Enter your name so Beckon alerts you when it is called:")
            .setView(input)
            .setPositiveButton("Save") { _, _ ->
                val newName = input.text.toString().trim()
                if (newName.isNotEmpty()) {
                    prefs.targetNames = newName
                    val first = newName.split(",").first().trim()
                    tvShazamTargetName.text = first
                    etTargetNames.setText(newName)
                    val allList = newName.split(",").map { it.trim() }.filter { it.isNotEmpty() }
                    AudioCaptureService.instance?.updateNames(allList[0], allList.drop(1))
                    syncButtonStates()
                    Toast.makeText(this, "Listening for: $first", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun autoDetectDaemon() {
        tvScanLabel.text = "Scanning network..."
        lifecycleScope.launch {
            val endpoint = com.beckon.app.util.DiscoveryClient.discoverDaemon()
            if (endpoint != null) {
                prefs.serverIp = endpoint
                etServerIp.setText(endpoint)
                tvCurrentIpDisplay.text = endpoint
                tvScanLabel.text = "✓ Discovered"
                Toast.makeText(this@MainActivity, "Found Beckon at: $endpoint", Toast.LENGTH_SHORT).show()
                pingDaemon()
            } else {
                tvScanLabel.text = "(Tap to Retry)"
                Toast.makeText(this@MainActivity, "Scan timed out. Make sure PC daemon is running.", Toast.LENGTH_SHORT).show()
            }
        }
    }

    // --- Ping via raw TCP socket with detailed diagnostics ---
    private fun pingDaemon() {
        tvPingResult.text = "pinging..."
        updateConnectionStatus(false)

        val hostPort = prefs.serverIp.ifEmpty { "192.168.1.100:8765" }
        val parts = hostPort.split(":")
        val host = parts.getOrElse(0) { "192.168.1.100" }
        val port = parts.getOrElse(1) { "8765" }.toIntOrNull() ?: 8765

        Thread {
            try {
                Socket().use { socket ->
                    socket.soTimeout = 4000
                    socket.connect(InetSocketAddress(host, port), 4000)
                    val writer = socket.getOutputStream().bufferedWriter()
                    writer.write("GET / HTTP/1.1\r\nHost: $host\r\nConnection: close\r\n\r\n")
                    writer.flush()
                    val reader = socket.getInputStream().bufferedReader()
                    reader.readLine() // Cleanly consumes HTTP status response line
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
                tvEngineStatus.text = "ONLINE"
                tvEngineStatus.setTextColor(ContextCompat.getColor(this, R.color.accent_green))
            } else {
                dotEngineStatus.backgroundTintList = ContextCompat.getColorStateList(this, R.color.accent_red)
                tvEngineStatus.text = "OFFLINE"
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
            syncButtonStates()

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
        syncButtonStates()
    }

    fun refreshAlerts() {
        mainHandler.post {
            val alerts = prefs.getAlerts()
            llAlertsContainer.removeAllViews()

            if (alerts.isEmpty()) {
                val tv = TextView(this).apply {
                    text = "No detections yet. Beckon is listening for your name."
                    setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_tertiary))
                    textSize = 12f
                    setPadding(16.dp, 16.dp, 16.dp, 16.dp)
                    setBackgroundResource(R.drawable.bg_input_field)
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
        stopEqualizerAnimation()
        instance = null
        super.onDestroy()
    }
}
