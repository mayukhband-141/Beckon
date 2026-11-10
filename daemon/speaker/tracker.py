import time
import threading
from typing import List, Dict, Optional
import numpy as np
from daemon.speaker.diarization import AcousticSpeakerIdentifier

class SpeakerTracker:
    """
    Tier 5: Hybrid Speaker Tracker with Passive Acoustic Voiceprinting.
    Combines:
      1. Acoustic Voiceprint Identification (ECAPA/FFT Voiceprint Cosine Matcher)
      2. Browser DOM active speaker detection (Google Meet / Zoom tile readers)
      3. Automatic background voice enrollment when speaker name is known from DOM
    """
    def __init__(self, history_retention_sec: float = 30.0, auto_enroll: bool = True):
        self.history_retention_sec = history_retention_sec
        self.auto_enroll = auto_enroll
        self.current_speaker: Optional[str] = None
        self.last_speaker_update_time: float = 0.0
        self.speaker_history: List[Dict] = []
        self.roster: List[str] = []
        self.acoustic_identifier = AcousticSpeakerIdentifier(min_similarity_threshold=0.72)
        self.lock = threading.Lock()

    def update_active_speaker(self, speaker_name: Optional[str], roster: Optional[List[str]] = None):
        now = time.time()
        with self.lock:
            if roster is not None:
                self.roster = roster
            
            clean_name = speaker_name.strip() if speaker_name else None
            self.current_speaker = clean_name
            self.last_speaker_update_time = now
            
            if clean_name:
                self.speaker_history.append({
                    "speaker": clean_name,
                    "timestamp": now
                })
                # Clean old entries
                cutoff = now - self.history_retention_sec
                self.speaker_history = [s for s in self.speaker_history if s["timestamp"] >= cutoff]

    def observe_audio_frame(self, audio: np.ndarray):
        """Passively refines the voiceprint of the currently active DOM speaker."""
        if not self.auto_enroll:
            return
        with self.lock:
            active = self.current_speaker
        if active and active not in ("Someone", "Unknown") and len(audio) >= 4800:
            self.acoustic_identifier.enroll_speaker(active, audio)

    def get_current_speaker(self, audio_slice: Optional[np.ndarray] = None) -> str:
        """
        Determines the most accurate speaker attribution.
        Prioritizes:
          1. Acoustic Voiceprint recognition (if audio slice matches an enrolled profile)
          2. Live DOM speaker tile from browser
          3. Recent speaker turn history
          4. Fallback 'Someone'
        """
        with self.lock:
            # 1. Acoustic voiceprint match
            if audio_slice is not None and len(audio_slice) >= 4800:
                matched_name, conf = self.acoustic_identifier.identify_speaker(audio_slice)
                if matched_name:
                    return f"{matched_name} (Voiceprint)"

            # 2. Browser DOM active speaker
            if self.current_speaker and (time.time() - self.last_speaker_update_time < 4.0):
                return self.current_speaker

            # 3. Recent speaker history
            if self.speaker_history:
                recent = self.speaker_history[-1]
                if time.time() - recent["timestamp"] < 6.0:
                    return recent["speaker"]

            return "Someone"

    def get_roster(self) -> List[str]:
        with self.lock:
            return list(self.roster)
