package com.beckon.app.util

import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.widget.Toast

class QuickReplyReceiver : BroadcastReceiver() {
    companion object {
        const val ACTION_COPY_REPLY = "com.beckon.app.ACTION_COPY_REPLY"
        const val EXTRA_REPLY_TEXT = "extra_reply_text"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACTION_COPY_REPLY) {
            val text = intent.getStringExtra(EXTRA_REPLY_TEXT) ?: return
            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            val clip = ClipData.newPlainText("Beckon Quick Reply", text)
            clipboard?.setPrimaryClip(clip)
            Toast.makeText(context, "Copied: \"$text\"", Toast.LENGTH_SHORT).show()
        }
    }
}

