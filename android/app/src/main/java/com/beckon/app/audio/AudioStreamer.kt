package com.beckon.app.audio

import android.os.Handler
import android.os.Looper
import android.util.Log
import okhttp3.*
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class AudioStreamer(
    private val serverUrl: String,
    private val onAlertReceived: (speaker: String, sentence: String, score: Double, quickReplies: List<String>) -> Unit,
    private val onConnectionChanged: (connected: Boolean) -> Unit
) {
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var isConnected = false
    private var pendingConfigJson: String? = null

    // Exponential backoff reconnect state
    private val reconnectHandler = Handler(Looper.getMainLooper())
    private var reconnectAttempts = 0
    private val maxReconnectAttempts = 5
    private val baseReconnectDelayMs = 2000L
    private var reconnectPending = false

    fun connect() {
        reconnectAttempts = 0
        reconnectPending = false
        reconnectHandler.removeCallbacksAndMessages(null)
        doConnect()
    }

    private fun doConnect() {
        val request = Request.Builder().url(serverUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d("AudioStreamer", "WebSocket connected to $serverUrl")
                isConnected = true
                reconnectAttempts = 0
                reconnectPending = false
                reconnectHandler.removeCallbacksAndMessages(null)
                pendingConfigJson?.let {
                    webSocket.send(it)
                    pendingConfigJson = null
                }
                onConnectionChanged(true)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    val msgType = json.optString("type")
                    if (msgType == "alert" || msgType == "alert_update") {
                        val speaker = json.optString("speaker", "Someone")
                        val sentence = json.optString("sentence", json.optString("summary", "Your name was called in the call."))
                        val score = json.optDouble("score", 0.9)
                        val quickRepliesList = mutableListOf<String>()
                        val repliesArr = json.optJSONArray("quick_replies")
                        if (repliesArr != null) {
                            for (i in 0 until repliesArr.length()) {
                                val reply = repliesArr.optString(i)
                                if (reply.isNotBlank()) {
                                    quickRepliesList.add(reply)
                                }
                            }
                        }
                        onAlertReceived(speaker, sentence, score, quickRepliesList)
                    }
                } catch (e: Exception) {
                    Log.e("AudioStreamer", "Error parsing message: $text", e)
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                onConnectionChanged(false)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e("AudioStreamer", "WebSocket failure: ${t.message}")
                isConnected = false
                onConnectionChanged(false)
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (reconnectPending) return
        reconnectAttempts++
        val delayMs = minOf(15000L, baseReconnectDelayMs * (1L shl minOf(reconnectAttempts - 1, 4)))
        Log.d("AudioStreamer", "Reconnecting to $serverUrl in ${delayMs}ms (attempt $reconnectAttempts)")
        reconnectPending = true
        reconnectHandler.postDelayed({
            reconnectPending = false
            if (!isConnected) doConnect()
        }, delayMs)
    }

    fun sendAudioChunk(pcmBytes: ByteArray, offset: Int, length: Int) {
        if (!isConnected) return
        val byteString = pcmBytes.toByteString(offset, length)
        webSocket?.send(byteString)
    }

    fun updateTargetNames(canonicalName: String, aliases: List<String>, groqApiKey: String = "") {
        val json = JSONObject().apply {
            put("type", "config_update")
            put("canonical_name", canonicalName)
            put("aliases", org.json.JSONArray(aliases))
            if (groqApiKey.isNotBlank()) {
                put("groq_api_key", groqApiKey)
            }
        }
        val jsonStr = json.toString()
        if (isConnected && webSocket != null) {
            webSocket?.send(jsonStr)
        } else {
            pendingConfigJson = jsonStr
        }
    }

    fun disconnect() {
        reconnectHandler.removeCallbacksAndMessages(null)
        reconnectAttempts = maxReconnectAttempts // prevent any pending reconnects from firing
        reconnectPending = false
        webSocket?.close(1000, "Normal Closure")
        webSocket = null
        isConnected = false
    }
}

