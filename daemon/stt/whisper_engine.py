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

    BANGLISH_HINGLISH_PROMPT = (
        "Meeting discussion in Indian English, Banglish, and Hinglish. "
        "Common phrases: ekkhuni, join koro, sunte paccho, bolo, slide ta dekho, "
        "unmute koro, thik ache, bolo ki bolcho, suno, haan, nah, please join."
    )

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
        language: Optional[str] = None,
        languages: Optional[List[str]] = None,
    ) -> Tuple[str, List[Dict]]:
        """
        Transcribe an audio buffer (float32, 16kHz).
        Supports multilingual auto-detection across targeted languages (e.g. en, bn, hi)
        and conditions the decoder with Banglish/Hinglish vocabulary to prevent English-only hallucinations.
        """
        if self.model is None:
            self.load_model()

        # Check for absolute silence / very low energy to skip unnecessary VAD processing
        energy = np.mean(np.abs(audio_window))
        if energy < 0.001:
            return "", []

        # Target language handling: if multiple languages are specified, allow auto-detection
        target_languages = languages or ["en", "bn", "hi"]
        selected_lang = language
        if selected_lang in ("auto", "multilingual", "") or (selected_lang is None and target_languages):
            selected_lang = None  # None tells Whisper to auto-detect the spoken language

        # Construct decoder prompt with hotwords and Banglish/Hinglish cues
        prompt_parts = []
        if hotwords:
            prompt_parts.append(hotwords)
        if initial_prompt:
            prompt_parts.append(initial_prompt)
        prompt_parts.append(self.BANGLISH_HINGLISH_PROMPT)
        effective_prompt = " ".join(prompt_parts).strip()

        kwargs = {
            "language": selected_lang,
            "beam_size": 2,
            "vad_filter": True,
            "vad_parameters": dict(min_silence_duration_ms=200),
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "hallucination_silence_threshold": 2.0,
            "initial_prompt": effective_prompt,
        }
        if hotwords:
            kwargs["hotwords"] = hotwords

        try:
            segments, info = self.model.transcribe(audio_window, **kwargs)

            # If Whisper detected a language outside our target set with low confidence, log it
            if selected_lang is None and info.language not in target_languages:
                logger.debug(
                    "Detected language '%s' (p=%.2f) outside targeted %s",
                    info.language, info.language_probability, target_languages
                )
            
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

