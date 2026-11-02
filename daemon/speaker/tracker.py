import time
import threading
from typing import List, Dict, Optional

class SpeakerTracker:
    """
    Tracks active speaker states reported from the browser extension's DOM observer.
    Provides attribution with fallbacks.
    """
    def __init__(self, history_retention_sec: float = 30.0):
        self.history_retention_sec = history_retention_sec
        self.current_speaker: Optional[str] = None
        self.last_speaker_update_time: float = 0.0
        self.speaker_history: List[Dict] = []
        self.roster: List[str] = []
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

    def get_current_speaker(self) -> str:
        with self.lock:
            # If current speaker was updated within the last 4 seconds, return it
            if self.current_speaker and (time.time() - self.last_speaker_update_time < 4.0):
                return self.current_speaker
            
            # If there was a speaker in the last 6 seconds, return that
            if self.speaker_history:
                recent = self.speaker_history[-1]
                if time.time() - recent["timestamp"] < 6.0:
                    return recent["speaker"]
            
            return "Someone"

    def get_roster(self) -> List[str]:
        with self.lock:
            return list(self.roster)

