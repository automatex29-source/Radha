package net.krishai.app

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import kotlin.math.abs

/**
 * The floating Krish button: a small round Krish chakra at the edge of the screen, on top of every app.
 * Tap it to ask Krish; drag it anywhere (it settles at the nearest side); drag it to the bottom of the
 * screen, or tap "Hide" in its notification, to put it away.
 */
class BubbleService : Service() {
    private var windowManager: WindowManager? = null
    private var bubble: View? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_HIDE || !Settings.canDrawOverlays(this)) {
            setEnabled(this, false)
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        if (bubble == null) showBubble()
        return START_STICKY
    }

    private fun startInForeground() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, getString(R.string.bubbleChannel), NotificationManager.IMPORTANCE_MIN)
                    .apply { setShowBadge(false) })
        }
        val hide = PendingIntent.getService(
            this, 10, Intent(this, BubbleService::class.java).setAction(ACTION_HIDE),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL)
        else @Suppress("DEPRECATION") Notification.Builder(this)
        val notification = builder
            .setSmallIcon(R.drawable.ic_krish_mono)
            .setContentTitle(getString(R.string.bubbleNotificationTitle))
            .setContentText(getString(R.string.bubbleNotificationText))
            .setContentIntent(Krish.pendingIntent(this, "/?new=1", 11))
            .addAction(Notification.Action.Builder(null, getString(R.string.bubbleHide), hide).build())
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun showBubble() {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        windowManager = wm
        val density = resources.displayMetrics.density
        val size = (52 * density).toInt()
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)

        val view = ImageView(this).apply {
            setImageResource(R.drawable.widget_logo)
            val pad = (9 * density).toInt()
            setPadding(pad, pad, pad, pad)
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(getColor(R.color.widgetSurface))
                setStroke((1 * density).toInt(), 0x33FF8A1E)
            }
            elevation = 6 * density
            contentDescription = getString(R.string.bubbleNotificationTitle)
            alpha = 0.92f
        }

        @Suppress("DEPRECATION")
        val type = if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else WindowManager.LayoutParams.TYPE_PHONE
        val params = WindowManager.LayoutParams(
            size, size, type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            val screen = resources.displayMetrics
            x = if (prefs.getBoolean("left", false)) 0 else screen.widthPixels - size
            y = prefs.getInt("y", (screen.heightPixels * 0.45f).toInt())
        }

        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var moved = false
        view.setOnTouchListener { v, e ->
            val screen = resources.displayMetrics
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = e.rawX; downY = e.rawY; startX = params.x; startY = params.y; moved = false
                    v.alpha = 1f
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = e.rawX - downX
                    val dy = e.rawY - downY
                    if (abs(dx) > 10 * density || abs(dy) > 10 * density) moved = true
                    if (moved) {
                        params.x = (startX + dx).toInt()
                        params.y = (startY + dy).toInt().coerceIn(0, screen.heightPixels - size)
                        wm.updateViewLayout(v, params)
                    }
                }
                MotionEvent.ACTION_UP -> {
                    v.alpha = 0.92f
                    if (!moved) {
                        Krish.open(this, "/?new=1")
                    } else if (e.rawY > screen.heightPixels - 90 * density) {
                        // Dropped at the very bottom: put the button away.
                        setEnabled(this, false)
                        stopSelf()
                    } else {
                        val left = params.x + size / 2 < screen.widthPixels / 2
                        prefs.edit().putBoolean("left", left).putInt("y", params.y).apply()
                        ValueAnimator.ofInt(params.x, if (left) 0 else screen.widthPixels - size).apply {
                            duration = 180
                            addUpdateListener {
                                params.x = it.animatedValue as Int
                                if (bubble != null) wm.updateViewLayout(v, params)
                            }
                            start()
                        }
                    }
                }
            }
            true
        }
        wm.addView(view, params)
        bubble = view
    }

    override fun onDestroy() {
        bubble?.let { runCatching { windowManager?.removeView(it) } }
        bubble = null
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL = "krish_bubble"
        private const val NOTIFICATION_ID = 7
        private const val PREFS = "krish_bubble"
        const val ACTION_HIDE = "net.krishai.app.HIDE_BUBBLE"

        fun isEnabled(context: Context) =
            context.getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("on", false)

        fun setEnabled(context: Context, on: Boolean) =
            context.getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("on", on).apply()

        fun start(context: Context) {
            setEnabled(context, true)
            val intent = Intent(context, BubbleService::class.java)
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent) else context.startService(intent)
        }

        fun stop(context: Context) {
            setEnabled(context, false)
            context.stopService(Intent(context, BubbleService::class.java))
        }
    }
}
