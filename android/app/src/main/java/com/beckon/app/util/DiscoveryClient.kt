package com.beckon.app.util

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

object DiscoveryClient {
    private const val TAG = "BeckonDiscovery"
    private const val DISCOVERY_PORT = 8766
    private const val TIMEOUT_MS = 2500

    /**
     * Attempts to auto-discover the local Beckon Python Daemon on the Wi-Fi network.
     * Returns formatted "IP:PORT" string if found, or null if timed out.
     */
    suspend fun discoverDaemon(targetPort: Int = 8765): String? = withContext(Dispatchers.IO) {
        var socket: DatagramSocket? = null
        try {
            socket = DatagramSocket(null).apply {
                reuseAddress = true
                soTimeout = TIMEOUT_MS
                broadcast = true
                bind(java.net.InetSocketAddress(DISCOVERY_PORT))
            }

            // Send an active discovery probe to broadcast
            try {
                val probeData = "beckon_discover".toByteArray()
                val broadcastAddr = InetAddress.getByName("255.255.255.255")
                val probePacket = DatagramPacket(probeData, probeData.size, broadcastAddr, DISCOVERY_PORT)
                socket.send(probePacket)
                Log.d(TAG, "Sent active UDP discovery probe on port $DISCOVERY_PORT")
            } catch (e: Exception) {
                Log.d(TAG, "Probe send exception (passive listen will continue): ${e.message}")
            }

            val buffer = ByteArray(1024)
            val packet = DatagramPacket(buffer, buffer.size)

            val startTime = System.currentTimeMillis()
            while (System.currentTimeMillis() - startTime < TIMEOUT_MS) {
                try {
                    socket.receive(packet)
                    val jsonStr = String(packet.data, 0, packet.length, Charsets.UTF_8).trim()
                    if (jsonStr.startsWith("{") && jsonStr.contains("beckon")) {
                        val json = JSONObject(jsonStr)
                        if (json.optString("service") == "beckon") {
                            val host = json.optString("host", packet.address.hostAddress ?: "")
                            val port = json.optInt("port", targetPort)
                            val endpoint = "$host:$port"
                            Log.i(TAG, "Auto-discovered Beckon daemon at: $endpoint")
                            return@withContext endpoint
                        }
                    }
                } catch (e: java.net.SocketTimeoutException) {
                    break
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Discovery error: ${e.message}")
        } finally {
            socket?.close()
        }
        null
    }
}

