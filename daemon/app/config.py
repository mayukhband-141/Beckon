from dataclasses import dataclass, field
from typing import List

@dataclass
class NameProfile:
    canonical_name: str = "Mayukh"
    aliases: List[str] = field(default_factory=lambda: ["Mayuk", "Moyukh", "Mayukhda", "Mayukha"])
    sensitivity: str = "balanced"  # "strict", "balanced", "sensitive"

    @property
    def all_names(self) -> List[str]:
        names = [self.canonical_name] + [a for a in self.aliases if a]
        return list(dict.fromkeys(names))  # Deduplicate preserving order

@dataclass
class DaemonConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    auth_token: str = "beckon_dev_token_2026"
    
    # Audio parameters
    sample_rate: int = 16000
    channels: int = 1
    chunk_hop_sec: float = 1.0       # evaluate every 1s
    chunk_window_sec: float = 5.0    # 5-second sliding window
    ring_buffer_sec: float = 60.0    # keep last 60s in RAM
    
    # Cooldown after firing an alert to prevent repetitive spamming
    cooldown_sec: float = 8.0
    
    # Whisper settings
    whisper_model: str = "base"      # starting with "base" for faster CPU iteration, can switch to "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_threads: int = 4
    
    # Sensitivity score thresholds
    thresholds = {
        "strict": 0.88,
        "balanced": 0.76,
        "sensitive": 0.65,
    }

    name_profile: NameProfile = field(default_factory=NameProfile)

