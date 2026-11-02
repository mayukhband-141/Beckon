package com.beckon.app.audio

import android.util.Log
import okhttp3.*
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class AudioStreamer(
    private val serverUrl: String,
    private val onAlertReceived: (speaker: String, sentence: String, score: Double) -> Unit,
    private val onConnectionChanged: (connected: Boolean) -> Unit
) {
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var isConnected = false

    fun connect() {
        val request = Request.Builder().url(serverUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d("AudioStreamer", "WebSocket connected to $serverUrl")
                isConnected = true
                onConnectionChanged(true)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    if (json.optString("type") == "alert") {
                        val speaker = json.optString("speaker", "Someone")
                        val sentence = json.optString("sentence", "Your name was called in the call.")
                        val score = json.optDouble("score", 0.9)
                        onAlertReceived(speaker, sentence, score)
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
            }
        })
    }

    fun sendAudioChunk(pcmBytes: ByteArray, offset: Int, length: Int) {
        if (!isConnected) return
        val byteString = pcmBytes.toByteString(offset, length)
        webSocket?.send(byteString)
    }

    fun updateTargetNames(canonicalName: String, aliases: List<String>) {
        val json = JSONObject().apply {
            put("type", "config_update")
            put("canonical_name", canonicalName)
            put("aliases", org.json.JSONArray(aliases))
        }
        webSocket?.send(json.toString())
    }

    fun disconnect() {
        webSocket?.close(1000, "Normal Closure")
        webSocket = null
        isConnected = false
    }
}
