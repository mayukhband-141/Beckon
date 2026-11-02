package com.beckon.app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var etServerIp: EditText
    private lateinit var btnLaunchFloating: Button

    private val overlayPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        if (checkOverlayPermission()) {
            requestMediaProjection()
        } else {
            Toast.makeText(this, R.string.overlay_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    private val mediaProjectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            launchServices(result.data!!)
        } else {
            Toast.makeText(this, "Screen / Audio capture permission denied", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        etServerIp = findViewById(R.id.etServerIp)
        btnLaunchFloating = findViewById(R.id.btnLaunchFloating)

        btnLaunchFloating.setOnClickListener {
            if (!checkOverlayPermission()) {
                requestOverlayPermission()
            } else {
                requestMediaProjection()
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

    private fun requestMediaProjection() {
        val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjectionLauncher.launch(projectionManager.createScreenCaptureIntent())
    }

    private fun launchServices(mediaProjectionData: Intent) {
        val serverIp = etServerIp.text.toString().trim().ifEmpty { "10.0.2.2:8765" }
        val serverUrl = if (serverIp.startsWith("ws://")) serverIp else "ws://$serverIp"

        // 1. Start Floating Overlay Service
        val floatIntent = Intent(this, FloatingWidgetService::class.java)
        startService(floatIntent)

        // 2. Start Internal Audio Capture Service
        val captureIntent = Intent(this, AudioCaptureService::class.java).apply {
            action = AudioCaptureService.ACTION_START
            putExtra(AudioCaptureService.EXTRA_RESULT_DATA, mediaProjectionData)
            putExtra(AudioCaptureService.EXTRA_SERVER_URL, serverUrl)
            putStringArrayListExtra(AudioCaptureService.EXTRA_NAMES, arrayListOf("Mayukh"))
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(captureIntent)
        } else {
            startService(captureIntent)
        }

        Toast.makeText(this, "Beckon Floating Pill Active!", Toast.LENGTH_SHORT).show()

        // Move to background so floating bubble hovers over whatever the user opens
        moveTaskToBack(true)
    }
}
