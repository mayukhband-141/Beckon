package com.beckon.app

import android.annotation.SuppressLint
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
import com.beckon.app.util.ChimePlayer
import com.beckon.app.util.HapticFeedback
import com.beckon.app.util.PreferencesManager
import kotlin.math.abs

class FloatingWidgetService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var floatingView: View

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
        var instance: FloatingWidgetService? = null
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = PreferencesManager(this)
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Log.e("FloatingWidget", "Overlay permission not granted, stopping service")
            stopSelf()
            return
        }

        initFloatingView()
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

        // Preload saved target names
        etTargetNames.setText(prefs.targetNames)

        val layoutFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        // Docked on the right-hand edge by default, fully visible
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutFlag,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.CENTER_VERTICAL or Gravity.END
            x = 16
            y = 0
        }

        windowManager.addView(floatingView, params)

        setupDragBehavior(params)

        viewCollapsed.setOnClickListener {
            expandWidget(params)
        }

        btnCloseExpanded.setOnClickListener {
            collapseWidget(params)
        }

        btnDismissAlert.setOnClickListener {
            dismissAlert(params)
        }

        btnShazamListen.setOnClickListener {
            toggleListening(params)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupDragBehavior(params: WindowManager.LayoutParams) {
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
                    // For Gravity.END, moving left increases x
                    params.x = initialX - (event.rawX - initialTouchX).toInt()
                    params.y = initialY + (event.rawY - initialTouchY).toInt()
                    windowManager.updateViewLayout(floatingView, params)
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

    private fun expandWidget(params: WindowManager.LayoutParams) {
        // Enable keyboard and touch focus when expanded
        params.flags = WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
        windowManager.updateViewLayout(floatingView, params)

        etTargetNames.setText(prefs.targetNames)
        viewCollapsed.visibility = View.GONE
        viewAlert.visibility = View.GONE
        viewExpanded.visibility = View.VISIBLE
    }

    private fun collapseWidget(params: WindowManager.LayoutParams) {
        // Revert to non-focusable floating mode
        params.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        windowManager.updateViewLayout(floatingView, params)

        viewExpanded.visibility = View.GONE
        viewAlert.visibility = View.GONE
        viewCollapsed.visibility = View.VISIBLE
    }

    private fun toggleListening(params: WindowManager.LayoutParams) {
        isListening = !isListening
        val namesText = etTargetNames.text.toString().trim().ifEmpty { "Mayukh" }
        prefs.targetNames = namesText

        val namesList = namesText.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val canonical = namesList.firstOrNull() ?: "Mayukh"

        if (isListening) {
            AudioCaptureService.instance?.updateNames(canonical, namesList.drop(1))
            tvCollapsedStatus.text = "Listening · $canonical"
            dotActive.visibility = View.VISIBLE
            ivShazamIcon.setImageResource(R.drawable.ic_stop)
            tvShazamActionText.text = "Tap to Stop"

            collapseWidget(params)
        } else {
            tvCollapsedStatus.text = "Beckon"
            dotActive.visibility = View.GONE
            ivShazamIcon.setImageResource(R.drawable.ic_mic)
            tvShazamActionText.text = "Tap to Listen"

            collapseWidget(params)
        }
    }

    fun updateNamesFromDashboard(names: String) {
        prefs.targetNames = names
        if (::etTargetNames.isInitialized) {
            etTargetNames.setText(names)
        }
    }

    fun showAlert(speaker: String, sentence: String, score: Double) {
        mainHandler.post {
            ChimePlayer.playChime()
            HapticFeedback.triggerAlertVibration(this)

            val params = floatingView.layoutParams as WindowManager.LayoutParams
            params.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
            windowManager.updateViewLayout(floatingView, params)

            tvAlertSpeaker.text = "$speaker called you"
            tvAlertSentence.text = "\"$sentence\""

            viewCollapsed.visibility = View.GONE
            viewExpanded.visibility = View.GONE
            viewAlert.visibility = View.VISIBLE

            mainHandler.removeCallbacksAndMessages(null)
            mainHandler.postDelayed({
                dismissAlert(params)
            }, 10000)
        }
    }

    private fun dismissAlert(params: WindowManager.LayoutParams) {
        viewAlert.visibility = View.GONE
        viewExpanded.visibility = View.GONE
        viewCollapsed.visibility = View.VISIBLE
        windowManager.updateViewLayout(floatingView, params)
    }

    override fun onDestroy() {
        if (::floatingView.isInitialized) {
            try {
                windowManager.removeView(floatingView)
            } catch (_: Exception) {}
        }
        instance = null
        super.onDestroy()
    }
}
