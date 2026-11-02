package com.beckon.app

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.*
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.beckon.app.util.ChimePlayer
import com.beckon.app.util.HapticFeedback
import com.beckon.app.util.PreferencesManager
import kotlin.math.abs

class FloatingWidgetService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var floatingView: View
    private lateinit var params: WindowManager.LayoutParams

    private lateinit var viewCollapsed: View
    private lateinit var viewExpanded: View
    private lateinit var viewAlert: View

    private lateinit var tvCollapsedStatus: TextView
    private lateinit var dotActive: View
    private lateinit var etTargetNames: EditText
    private lateinit var btnShazamListen: FrameLayout
    private lateinit var ivShazamIcon: ImageView
    private lateinit var tvShazamActionText: TextView

    private lateinit var tvAlertSpeaker: TextView
    private lateinit var tvAlertSentence: TextView
    private lateinit var btnDismissAlert: ImageView
    private lateinit var btnCloseExpanded: ImageView

    private var isListening = false
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var prefs: PreferencesManager

    companion object {
        private const val CHANNEL_ID = "beckon_widget_channel"
        private const val NOTIF_ID = 102

        var instance: FloatingWidgetService? = null
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = PreferencesManager(this)

        startForegroundNotification()

        val canDraw = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) Settings.canDrawOverlays(this) else true
        Log.i("FloatingWidget", "canDrawOverlays: $canDraw")
        if (!canDraw) {
            Log.e("FloatingWidget", "Overlay permission not granted — stopping service")
            stopSelf()
            return
        }

        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        try {
            initFloatingView()
        } catch (e: Exception) {
            Log.e("FloatingWidget", "Failed to init floating view", e)
            stopSelf()
        }
    }

    private fun startForegroundNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Beckon Floating Widget",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps Beckon floating pill docked"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }

        val notif: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Beckon floating pill is active")
            .setContentText("Docked on your screen.")
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

        try {
            startForeground(NOTIF_ID, notif)
        } catch (e: Exception) {
            Log.w("FloatingWidget", "startForeground failed: ${e.message}")
        }
    }

    @SuppressLint("InflateParams", "ClickableViewAccessibility")
    private fun initFloatingView() {
        floatingView = LayoutInflater.from(this).inflate(R.layout.widget_floating_overlay, null)

        viewCollapsed = floatingView.findViewById(R.id.viewCollapsed)
        viewExpanded = floatingView.findViewById(R.id.viewExpanded)
        viewAlert = floatingView.findViewById(R.id.viewAlert)

        tvCollapsedStatus = floatingView.findViewById(R.id.tvCollapsedStatus)
        dotActive = floatingView.findViewById(R.id.dotActive)
        etTargetNames = floatingView.findViewById(R.id.etTargetNames)
        btnShazamListen = floatingView.findViewById(R.id.btnShazamListen)
        ivShazamIcon = floatingView.findViewById(R.id.ivShazamIcon)
        tvShazamActionText = floatingView.findViewById(R.id.tvShazamActionText)

        tvAlertSpeaker = floatingView.findViewById(R.id.tvAlertSpeaker)
        tvAlertSentence = floatingView.findViewById(R.id.tvAlertSentence)
        btnDismissAlert = floatingView.findViewById(R.id.btnDismissAlert)
        btnCloseExpanded = floatingView.findViewById(R.id.btnCloseExpanded)

        etTargetNames.setText(prefs.targetNames)

        val layoutFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val metrics = resources.displayMetrics
        val screenWidth = metrics.widthPixels
        val screenHeight = metrics.heightPixels

        // Anchor at TOP | START so coordinates are positive screen pixels
        // Place initial position visible at right side, 35% from screen top
        val initialX = (screenWidth - 130 * metrics.density).toInt().coerceAtLeast(0)
        val initialY = (screenHeight * 0.35f).toInt()

        params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutFlag,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = initialX
            y = initialY
        }

        Log.i("FloatingWidget", "Calling windowManager.addView on thread ${Thread.currentThread().name} (x=$initialX, y=$initialY)")
        try {
            windowManager.addView(floatingView, params)
            Log.i("FloatingWidget", "windowManager.addView successfully attached view")
        } catch (e: Exception) {
            Log.e("FloatingWidget", "windowManager.addView threw exception", e)
            stopSelf()
            return
        }
        setupDragBehavior(screenWidth, screenHeight)
        setupClickListeners()
    }

    private fun setupClickListeners() {
        viewCollapsed.setOnClickListener {
            expandWidget()
        }

        btnCloseExpanded.setOnClickListener {
            collapseWidget()
        }

        btnDismissAlert.setOnClickListener {
            dismissAlert()
        }

        btnShazamListen.setOnClickListener {
            toggleListening()
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupDragBehavior(screenWidth: Int, screenHeight: Int) {
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f

        viewCollapsed.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val deltaX = (event.rawX - initialTouchX).toInt()
                    val deltaY = (event.rawY - initialTouchY).toInt()

                    params.x = (initialX + deltaX).coerceIn(0, screenWidth - 60)
                    params.y = (initialY + deltaY).coerceIn(0, screenHeight - 100)

                    try {
                        windowManager.updateViewLayout(floatingView, params)
                    } catch (_: Exception) {}
                    true
                }
                MotionEvent.ACTION_UP -> {
                    val diffX = abs(event.rawX - initialTouchX)
                    val diffY = abs(event.rawY - initialTouchY)
                    if (diffX < 12 && diffY < 12) {
                        view.performClick()
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun expandWidget() {
        params.flags = WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
        try {
            windowManager.updateViewLayout(floatingView, params)
        } catch (_: Exception) {}

        etTargetNames.setText(prefs.targetNames)
        viewCollapsed.visibility = View.GONE
        viewAlert.visibility = View.GONE
        viewExpanded.visibility = View.VISIBLE
    }

    private fun collapseWidget() {
        params.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        try {
            windowManager.updateViewLayout(floatingView, params)
        } catch (_: Exception) {}

        viewExpanded.visibility = View.GONE
        viewAlert.visibility = View.GONE
        viewCollapsed.visibility = View.VISIBLE
    }

    private fun toggleListening() {
        isListening = !isListening
        val namesText = etTargetNames.text.toString().trim().ifEmpty { "Alex" }
        prefs.targetNames = namesText

        val namesList = namesText.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val canonical = namesList.firstOrNull() ?: "Alex"

        if (isListening) {
            AudioCaptureService.instance?.updateNames(canonical, namesList.drop(1))
            tvCollapsedStatus.text = "Listening · $canonical"
            dotActive.visibility = View.VISIBLE
            ivShazamIcon.setImageResource(R.drawable.ic_stop)
            tvShazamActionText.text = "Tap to Stop"
        } else {
            tvCollapsedStatus.text = "Beckon"
            dotActive.visibility = View.GONE
            ivShazamIcon.setImageResource(R.drawable.ic_mic)
            tvShazamActionText.text = "Tap to Listen"
        }

        collapseWidget()
    }

    fun updateNamesFromDashboard(names: String) {
        prefs.targetNames = names
        if (::etTargetNames.isInitialized) {
            mainHandler.post { etTargetNames.setText(names) }
        }
    }

    fun showAlert(speaker: String, sentence: String, @Suppress("UNUSED_PARAMETER") score: Double) {
        mainHandler.post {
            ChimePlayer.playChime()
            HapticFeedback.triggerAlertVibration(this)

            if (!::floatingView.isInitialized) return@post

            params.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
            try {
                windowManager.updateViewLayout(floatingView, params)
            } catch (_: Exception) {}

            tvAlertSpeaker.text = "$speaker called you"
            tvAlertSentence.text = "\"$sentence\""

            viewCollapsed.visibility = View.GONE
            viewExpanded.visibility = View.GONE
            viewAlert.visibility = View.VISIBLE

            mainHandler.removeCallbacksAndMessages(null)
            mainHandler.postDelayed({ dismissAlert() }, 10_000)
        }
    }

    private fun dismissAlert() {
        viewAlert.visibility = View.GONE
        viewExpanded.visibility = View.GONE
        viewCollapsed.visibility = View.VISIBLE
        if (::floatingView.isInitialized) {
            try { windowManager.updateViewLayout(floatingView, params) } catch (_: Exception) {}
        }
    }

    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
        if (::floatingView.isInitialized) {
            try { windowManager.removeView(floatingView) } catch (_: Exception) {}
        }
        try {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } catch (_: Exception) {}
        instance = null
        super.onDestroy()
    }
}
