/**
 * AudioWorkletProcessor to downsample tab audio to 16kHz mono signed 16-bit PCM.
 */
class PCMDownsampleProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.buffer = [];
    // We emit chunks approximately every ~100ms (1600 samples at 16kHz)
    this.chunkSize = 1600;
    this.sampleRatio = sampleRate / this.targetSampleRate;
    this.resampleIndex = 0.0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }

    const channelData = input[0]; // Take mono or left channel
    if (!channelData || channelData.length === 0) {
      return true;
    }

    // Linear interpolation / downsampling
    const inputLen = channelData.length;
    while (this.resampleIndex < inputLen) {
      const idx = Math.floor(this.resampleIndex);
      const frac = this.resampleIndex - idx;
      const s0 = channelData[idx];
      const s1 = idx + 1 < inputLen ? channelData[idx + 1] : s0;
      const sample = s0 + frac * (s1 - s0);

      // Clamp and convert to 16-bit PCM integer (-32768 to 32767)
      const clamped = Math.max(-1.0, Math.min(1.0, sample));
      const pcm16 = clamped < 0 ? clamped * 32768 : clamped * 32767;
      this.buffer.push(Math.round(pcm16));

      this.resampleIndex += this.sampleRatio;

      if (this.buffer.length >= this.chunkSize) {
        const int16Buffer = new Int16Array(this.buffer);
        this.port.postMessage(int16Buffer.buffer, [int16Buffer.buffer]);
        this.buffer = [];
      }
    }

    this.resampleIndex -= inputLen;
    return true;
  }
}

registerProcessor("pcm-downsample-processor", PCMDownsampleProcessor);

