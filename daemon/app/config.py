import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

def load_dotenv(path: Optional[Path] = None) -> Optional[Path]:
    """
    Lightweight zero-dependency .env parser.
    Searches current working directory and project root.
    Populates os.environ without overwriting pre-existing variables.
    """
    if path is None:
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
            Path(__file__).resolve().parents[1] / ".env",
        ]
        for c in candidates:
            if c.is_file():
                path = c
                break

    if path and path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        if k and k not in os.environ:
                            os.environ[k] = v
            return path
        except Exception:
            pass
    return None

# Automatically load environment variables on import
LOADED_ENV_PATH = load_dotenv()

@dataclass
class NameProfile:
    canonical_name: str = os.getenv("BECKON_TARGET_NAME", "")
    aliases: List[str] = field(
        default_factory=lambda: [
            a.strip()
            for a in os.getenv("BECKON_ALIASES", "").split(",")
            if a.strip()
        ]
    )
    sensitivity: str = os.getenv("BECKON_SENSITIVITY", "balanced")  # "strict", "balanced", "sensitive"

    @property
    def all_names(self) -> List[str]:
        names = ([self.canonical_name] if self.canonical_name else []) + [a for a in self.aliases if a]
        return list(dict.fromkeys(names))  # Deduplicate preserving order

@dataclass
class DaemonConfig:
    host: str = os.getenv("BECKON_HOST", "127.0.0.1")
    port: int = int(os.getenv("BECKON_PORT", "8765"))
    auth_token: str = os.getenv("BECKON_AUTH_TOKEN", "beckon_dev_token_2026")
    
    # Audio parameters
    sample_rate: int = 16000
    channels: int = 1
    chunk_hop_sec: float = 0.5       # evaluate every 1/2 s
    chunk_window_sec: float = 5.0    # 2-second sliding window
    ring_buffer_sec: float = 60.0    # keep last 60s in RAM
    
    # Cooldown after firing an alert to prevent repetitive spamming
    cooldown_sec: float = 8.0
    
    # Whisper settings
    whisper_model: str = os.getenv("BECKON_WHISPER_MODEL") or os.getenv("BECKON_MODEL", "small")  # Default upgraded to "small" for better multilingual/accent accuracy
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_threads: int = 4
    min_word_confidence: float = float(os.getenv("BECKON_MIN_WORD_CONFIDENCE", "0.40"))
    
    # Tier 4: Acoustic Keyword Spotting (KWS) Fast-Path
    enable_kws: bool = os.getenv("BECKON_ENABLE_KWS", "true").lower() in ("true", "1", "yes")
    kws_model_path: str = os.getenv("BECKON_KWS_MODEL_PATH", "")
    kws_threshold: float = float(os.getenv("BECKON_KWS_THRESHOLD", "0.65"))
    
    # Catch-up LLM Summary (Tier 3)
    groq_api_key: str = os.getenv("BECKON_GROQ_API_KEY", "")
    ollama_url: str = os.getenv("BECKON_OLLAMA_URL", "")
    summary_model: str = os.getenv("BECKON_SUMMARY_MODEL", "llama-3.1-8b-instant")
    
    # Sensitivity score thresholds
    thresholds = {
        "strict": 0.88,
        "balanced": 0.76,
        "sensitive": 0.65,
    }

    # Multilingual & code-switching support (English, Bengali, Hindi)
    languages: List[str] = field(
        default_factory=lambda: [
            l.strip()
            for l in os.getenv("BECKON_LANGUAGES", "en, bn, hi").split(",")
            if l.strip()
        ]
    )

    name_profile: NameProfile = field(default_factory=NameProfile)

