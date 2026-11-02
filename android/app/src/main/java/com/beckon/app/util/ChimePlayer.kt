package com.beckon.app.util

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.sin

/**
 * Synthesizes a crisp two-tone alert chime (D5 -> A5) directly in memory
 * using AudioTrack without requiring any bundled audio asset files.
 */
object ChimePlayer {
    fun playChime() {
        Thread {
            try {
                val sampleRate = 44100
                val durationSec = 0.5
                val numSamples = (sampleRate * durationSec).toInt()
                val buffer = ShortArray(numSamples)

                val freq1 = 587.33 // D5
                val freq2 = 880.00 // A5

                for (i in 0 until numSamples) {
                    val t = i.toDouble() / sampleRate
                    val freq = if (t < 0.15) freq1 else freq2
                    
                    // Simple exponential decay envelope
                    val envelope = if (t < 0.15) {
                        1.0 - (t / 0.15) * 0.5
                    } else {
                        1.0 - ((t - 0.15) / 0.35)
                    }
                    
                    val sample = sin(2.0 * Math.PI * freq * t) * envelope
                    buffer[i] = (sample * 16384).toInt().coerceIn(-32768, 32767).toShort()
                }

                val audioTrack = AudioTrack.Builder()
                    .setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                            .build()
                    )
                    .setAudioFormat(
                        AudioFormat.Builder()
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .setSampleRate(sampleRate)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                            .build()
                    )
                    .setBufferSizeInBytes(buffer.size * 2)
                    .setTransferMode(AudioTrack.MODE_STATIC)
                    .build()

                audioTrack.write(buffer, 0, buffer.size)
                audioTrack.play()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }.start()
    }
}
