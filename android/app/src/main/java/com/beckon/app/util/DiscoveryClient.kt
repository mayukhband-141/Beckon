package com.beckon.app.util

import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONObject
import java.net.*

object DiscoveryClient {
    private const val TAG = "BeckonDiscovery"
    private const val DISCOVERY_PORT = 8766
    private const val TIMEOUT_MS = 2500

    /**
     * Attempts to auto-discover the local Beckon Python Daemon on the Wi-Fi network.
     * Uses hybrid strategy: UDP Beacon discovery + ultra-fast parallel TCP subnet sweep.
     * Returns formatted "IP:PORT" string if found, or null if timed out.
     */
    suspend fun discoverDaemon(targetPort: Int = 8765): String? = withContext(Dispatchers.IO) {
        val udpDeferred = async { listenUdpBeacon(targetPort) }
        val tcpDeferred = async { scanLocalSubnet(targetPort) }

        // Whichever completes first with a non-null result wins
        val results = listOf(udpDeferred, tcpDeferred)
        while (results.any { it.isActive }) {
            for (def in results) {
                if (def.isCompleted) {
                    val res = def.getCompleted()
                    if (res != null) {
                        udpDeferred.cancel()
                        tcpDeferred.cancel()
                        return@withContext res
                    }
                }
            }
            delay(50)
        }

        udpDeferred.await() ?: tcpDeferred.await()
    }

    private fun listenUdpBeacon(targetPort: Int): String? {
        var socket: DatagramSocket? = null
        try {
            socket = DatagramSocket(null).apply {
                reuseAddress = true
                soTimeout = 1800
                broadcast = true
                try {
                    bind(InetSocketAddress(DISCOVERY_PORT))
                } catch (_: Exception) {
                    // Fall back to ephemeral port if 8766 is busy
                    bind(InetSocketAddress(0))
                }
            }

            try {
                val probeData = "beckon_discover".toByteArray()
                val broadcastAddr = InetAddress.getByName("255.255.255.255")
                val probePacket = DatagramPacket(probeData, probeData.size, broadcastAddr, DISCOVERY_PORT)
                socket.send(probePacket)
            } catch (_: Exception) {}

            val buffer = ByteArray(1024)
            val packet = DatagramPacket(buffer, buffer.size)

            val startTime = System.currentTimeMillis()
            while (System.currentTimeMillis() - startTime < 1800) {
                try {
                    socket.receive(packet)
                    val jsonStr = String(packet.data, 0, packet.length, Charsets.UTF_8).trim()
                    if (jsonStr.startsWith("{") && jsonStr.contains("beckon")) {
                        val json = JSONObject(jsonStr)
                        if (json.optString("service") == "beckon") {
                            val host = json.optString("host", packet.address.hostAddress ?: "")
                            val port = json.optInt("port", targetPort)
                            val endpoint = "$host:$port"
                            Log.i(TAG, "UDP Beacon auto-discovered Beckon at: $endpoint")
                            return endpoint
                        }
                    }
                } catch (_: SocketTimeoutException) {
                    break
                }
            }
        } catch (e: Exception) {
            Log.d(TAG, "UDP listen exception: ${e.message}")
        } finally {
            socket?.close()
        }
        return null
    }

    private suspend fun scanLocalSubnet(targetPort: Int): String? = coroutineScope {
        val localIp = getLocalWifiIp() ?: return@coroutineScope null
        val parts = localIp.split(".")
        if (parts.size != 4) return@coroutineScope null
        val prefix = "${parts[0]}.${parts[1]}.${parts[2]}."

        // Fast parallel probe across all 254 addresses in subnet
        val probeJobs = (1..254).map { i ->
            async(Dispatchers.IO) {
                val candidateIp = "$prefix$i"
                try {
                    val s = Socket()
                    s.connect(InetSocketAddress(candidateIp, targetPort), 220)
                    s.close()
                    // Port is open! Verify it's Beckon by probing /pair or /ping
                    val verifyUrl = URL("http://$candidateIp:$targetPort/pair")
                    val conn = verifyUrl.openConnection() as HttpURLConnection
                    conn.connectTimeout = 400
                    conn.readTimeout = 400
                    conn.requestMethod = "GET"
                    val code = conn.responseCode
                    conn.disconnect()
                    if (code == 200) {
                        Log.i(TAG, "Subnet scan verified Beckon at: $candidateIp:$targetPort")
                        return@async "$candidateIp:$targetPort"
                    }
                } catch (_: Exception) {}
                null
            }
        }

        for (job in probeJobs) {
            val endpoint = job.await()
            if (endpoint != null) {
                probeJobs.forEach { it.cancel() }
                return@coroutineScope endpoint
            }
        }
        null
    }

    private fun getLocalWifiIp(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val addresses = iface.inetAddresses
                while (addresses.hasMoreElements()) {
                    val addr = addresses.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val host = addr.hostAddress ?: ""
                        if (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.")) {
                            return host
                        }
                    }
                }
            }
        } catch (_: Exception) {}
        return null
    }
}
