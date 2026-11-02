import time
import threading
from typing import List, Dict, Optional
import numpy as np

class AudioRingBuffer:
    """
    In-memory circular audio buffer holding the last `capacity_sec` of 16kHz mono float32 audio.
    Also retains a rolling history of recent transcripts and active speakers.
    """
    def __init__(self, sample_rate: int = 16000, capacity_sec: float = 60.0):
        self.sample_rate = sample_rate
        self.capacity_samples = int(sample_rate * capacity_sec)
        self.buffer = np.zeros(self.capacity_samples, dtype=np.float32)
        self.write_index = 0
        self.total_samples_written = 0
        self.lock = threading.Lock()
        
        # Rolling transcript history: [{"timestamp": float, "speaker": str, "text": str}]
        self.transcript_history: List[Dict] = []
        self.max_transcript_history_sec = 120.0

    def append_pcm16_bytes(self, pcm_bytes: bytes):
        """Convert little-endian signed 16-bit PCM bytes to float32 (-1.0 to 1.0) and append."""
        if not pcm_bytes:
            return
        
        # Convert bytes to int16 array
        int16_arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        float32_arr = int16_arr.astype(np.float32) / 32768.0
        self.append_samples(float32_arr)

    def append_samples(self, samples: np.ndarray):
        """Append float32 16kHz mono samples into circular buffer."""
        if len(samples) == 0:
            return
            
        with self.lock:
            n = len(samples)
            if n >= self.capacity_samples:
                # Samples exceed capacity, take only the tail
                self.buffer[:] = samples[-self.capacity_samples:]
                self.write_index = 0
                self.total_samples_written += n
                return

            end_index = self.write_index + n
            if end_index <= self.capacity_samples:
                self.buffer[self.write_index:end_index] = samples
            else:
                first_part = self.capacity_samples - self.write_index
                second_part = n - first_part
                self.buffer[self.write_index:] = samples[:first_part]
                self.buffer[:second_part] = samples[first_part:]
                
            self.write_index = end_index % self.capacity_samples
            self.total_samples_written += n

    def get_last_n_seconds(self, seconds: float) -> np.ndarray:
        """Extract the last `seconds` of audio in chronological order."""
        num_samples = int(self.sample_rate * seconds)
        with self.lock:
            available = min(self.total_samples_written, self.capacity_samples)
            if available < num_samples:
                # Pad with silence at the beginning if not enough audio has been captured yet
                out = np.zeros(num_samples, dtype=np.float32)
                if available > 0:
                    start_read = (self.write_index - available) % self.capacity_samples
                    if start_read < self.write_index:
                        samples = self.buffer[start_read:self.write_index]
                    else:
                        samples = np.concatenate((self.buffer[start_read:], self.buffer[:self.write_index]))
                    out[-available:] = samples
                return out

            start_read = (self.write_index - num_samples) % self.capacity_samples
            if start_read < self.write_index:
                return self.buffer[start_read:self.write_index].copy()
            else:
                return np.concatenate((self.buffer[start_read:], self.buffer[:self.write_index]))

    def add_transcript(self, text: str, speaker: str = "Unknown"):
        """Record a recognized transcript segment."""
        now = time.time()
        with self.lock:
            self.transcript_history.append({
                "timestamp": now,
                "speaker": speaker,
                "text": text.strip()
            })
            # Prune transcripts older than max_transcript_history_sec
            cutoff = now - self.max_transcript_history_sec
            self.transcript_history = [t for t in self.transcript_history if t["timestamp"] >= cutoff]

    def get_recent_transcript_context(self, lookback_sec: float = 45.0) -> str:
        """Returns the combined text of the last `lookback_sec` of transcripts formatted with speaker."""
        now = time.time()
        cutoff = now - lookback_sec
        with self.lock:
            recent = [t for t in self.transcript_history if t["timestamp"] >= cutoff]
            if not recent:
                return ""
            
            # Format nicely: "[Speaker]: Hello everyone..."
            formatted_chunks = []
            for item in recent:
                spk = item.get("speaker") or "Unknown"
                txt = item.get("text", "")
                formatted_chunks.append(f"{spk}: {txt}")
            return " | ".join(formatted_chunks)

