import asyncio
import logging
import threading
import time
from typing import Optional, Callable
import numpy as np

logger = logging.getLogger("beckon.audio.loopback")

class SystemAudioLoopback:
    """
    Tier 5: System-Wide Desktop Audio Loopback Capture.
    Captures system audio output (what you hear through headphones/speakers)
    directly on Windows (WASAPI Loopback), macOS (CoreAudio), or Linux (PulseAudio/PipeWire).
    Enables background monitoring of Zoom, Slack Huddles, Microsoft Teams, and Discord
    without requiring browser extensions or tab capture.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_duration_sec: float = 0.1,
        on_pcm_callback: Optional[Callable[[bytes], None]] = None
    ):
        self.sample_rate = sample_rate
        self.chunk_samples = int(sample_rate * chunk_duration_sec)
        self.on_pcm_callback = on_pcm_callback
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def _find_backend(self):
        """Attempts to discover available system audio loopback backends."""
        try:
            import soundcard as sc
            return "soundcard", sc
        except ImportError:
            pass

        try:
            import sounddevice as sd
            return "sounddevice", sd
        except ImportError:
            pass

        return "none", None

    def _loopback_worker(self):
        backend_name, backend = self._find_backend()
        logger.info("Initializing system audio loopback capture (Backend: %s)", backend_name)

        if backend_name == "soundcard":
            try:
                speaker = backend.default_speaker()
                mic = backend.get_microphone(id=str(speaker.name), include_loopback=True)
                with mic.recorder(samplerate=self.sample_rate, channels=1) as recorder:
                    while self.is_running:
                        data = recorder.record(numframes=self.chunk_samples)
                        # data is float32 [-1.0, 1.0], shape [numframes, 1]
                        float_mono = data[:, 0] if data.ndim > 1 else data
                        pcm16 = (np.clip(float_mono, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                        if self.on_pcm_callback:
                            self.on_pcm_callback(pcm16)
                return
            except Exception as e:
                logger.warning("Soundcard loopback recording failed: %s", e)

        elif backend_name == "sounddevice":
            try:
                def sd_callback(indata, frames, time_info, status):
                    if status:
                        logger.debug("Sounddevice status: %s", status)
                    float_mono = indata[:, 0] if indata.ndim > 1 else indata
                    pcm16 = (np.clip(float_mono, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    if self.on_pcm_callback:
                        self.on_pcm_callback(pcm16)

                with backend.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    callback=sd_callback,
                    blocksize=self.chunk_samples
                ):
                    while self.is_running:
                        time.sleep(0.05)
                return
            except Exception as e:
                logger.warning("Sounddevice loopback recording failed: %s", e)

        # Fallback when no third-party audio drivers are installed
        logger.info(
            "System audio loopback driver is in standby mode. "
            "(Install 'soundcard' via pip for native WASAPI desktop loopback capture)."
        )
        while self.is_running:
            time.sleep(0.5)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._thread = threading.Thread(target=self._loopback_worker, daemon=True, name="AudioLoopbackThread")
            self._thread.start()

    def stop(self):
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
