package com.vigil.app

import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log

class VigilNotificationListener : NotificationListenerService() {

    companion object {
        private const val TAG = "VigilNotifListener"

        /* Package names we care about */
        private val MONITORED_PACKAGES = setOf(
            "com.whatsapp",
            "com.whatsapp.w4b",
            "org.telegram.messenger",
            "com.twitter.android",
            "com.google.android.gm",
            "com.google.android.apps.messaging"
        )
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName
        if (pkg !in MONITORED_PACKAGES) return

        /* Skip non-user notifications (groups, summaries) */
        if (sbn.isGroupSummary) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && sbn.notification.isMediaNotification) return

        val extras = sbn.notification.extras
        val title = extras.getString(android.app.Notification.EXTRA_TITLE) ?: "Unknown"
        val text = extras.getString(android.app.Notification.EXTRA_TEXT)
            ?: extras.getCharSequence(android.app.Notification.EXTRA_BIG_TEXT)?.toString()
            ?: ""

        if (text.isBlank()) return

        Log.d(TAG, "Notification from $pkg: $title - $text")

        /* Send to Flutter via MethodChannel */
        VigilForegroundService.methodChannel?.invokeMethod("onNotification", mapOf(
            "app" to pkg,
            "title" to title,
            "text" to text
        ))
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        /* No-op: we don't need to react to removal */
    }
}
