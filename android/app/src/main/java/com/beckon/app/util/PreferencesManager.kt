package com.beckon.app.util

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

class PreferencesManager(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("beckon_settings", Context.MODE_PRIVATE)

    companion object {
        private const val KEY_SERVER_IP = "server_ip"
        private const val KEY_TARGET_NAMES = "target_names"
        private const val KEY_AUDIO_SOURCE = "audio_source"
        private const val KEY_ALERTS_LOG = "alerts_log"
        private const val DEFAULT_SERVER_IP = "192.168.29.102:8765"
        private const val DEFAULT_NAMES = "Mayukh"
    }

    var serverIp: String
        get() = prefs.getString(KEY_SERVER_IP, DEFAULT_SERVER_IP) ?: DEFAULT_SERVER_IP
        set(value) = prefs.edit().putString(KEY_SERVER_IP, value).apply()

    var targetNames: String
        get() = prefs.getString(KEY_TARGET_NAMES, DEFAULT_NAMES) ?: DEFAULT_NAMES
        set(value) = prefs.edit().putString(KEY_TARGET_NAMES, value).apply()

    var audioSource: String
        get() = prefs.getString(KEY_AUDIO_SOURCE, "mic") ?: "mic"
        set(value) = prefs.edit().putString(KEY_AUDIO_SOURCE, value).apply()

    fun addAlert(speaker: String, sentence: String, score: Double) {
        val list = getAlerts().toMutableList()
        val item = JSONObject().apply {
            put("speaker", speaker)
            put("sentence", sentence)
            put("score", score)
            put("timestamp", System.currentTimeMillis())
        }
        list.add(0, item)
        // Keep last 15 alerts
        val trimmed = if (list.size > 15) list.subList(0, 15) else list
        val array = JSONArray()
        trimmed.forEach { array.put(it) }
        prefs.edit().putString(KEY_ALERTS_LOG, array.toString()).apply()
    }

    fun getAlerts(): List<JSONObject> {
        val raw = prefs.getString(KEY_ALERTS_LOG, null) ?: return emptyList()
        val results = mutableListOf<JSONObject>()
        try {
            val array = JSONArray(raw)
            for (i in 0 until array.length()) {
                results.add(array.getJSONObject(i))
            }
        } catch (_: Exception) {}
        return results
    }
}

