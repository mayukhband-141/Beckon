import logging
from typing import List, Dict, Tuple, Optional
import numpy as np

logger = logging.getLogger("beckon.stt")

class WhisperEngine:
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.model = None

    def load_model(self):
        """Lazy load or explicit load of the faster-whisper model."""
        if self.model is None:
            logger.info(f"Loading faster-whisper model '{self.model_size}' (device={self.device}, compute_type={self.compute_type}, threads={self.cpu_threads})...")
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads
            )
            logger.info("faster-whisper model successfully loaded.")

    def transcribe_audio_window(
        self,
        audio_window: np.ndarray,
        sample_rate: int = 16000,
        hotwords: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        language: str = "en"
    ) -> Tuple[str, List[Dict]]:
        """
        Transcribe an audio buffer (float32, 16kHz).
        Returns:
            full_text: str
            words: list of dicts [{"word": str, "start": float, "end": float, "probability": float}]
        """
        if self.model is None:
            self.load_model()

        # Check for absolute silence / very low energy to skip unnecessary VAD processing
        energy = np.mean(np.abs(audio_window))
        if energy < 0.001:
            return "", []

        kwargs = {
            "language": language,
            "beam_size": 2,
            "vad_filter": True,
            "vad_parameters": dict(min_silence_duration_ms=200),
            "word_timestamps": True,
            "condition_on_previous_text": False,
        }
        if hotwords:
            kwargs["hotwords"] = hotwords
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        try:
            segments, info = self.model.transcribe(audio_window, **kwargs)
            
            full_text_parts = []
            all_words = []
            
            for segment in segments:
                full_text_parts.append(segment.text)
                if segment.words:
                    for w in segment.words:
                        all_words.append({
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "probability": getattr(w, "probability", 1.0)
                        })
            
            full_text = " ".join(full_text_parts).strip()
            return full_text, all_words
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}", exc_info=True)
            return "", []

