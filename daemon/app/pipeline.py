import time
import asyncio
import logging
from collections import deque
from typing import Callable, Optional, Dict
import numpy as np
from rapidfuzz import fuzz
from daemon.app.config import DaemonConfig
from daemon.app.ring_buffer import AudioRingBuffer
from daemon.match.matcher import NameMatcher
from daemon.stt.whisper_engine import WhisperEngine
from daemon.speaker.tracker import SpeakerTracker
from daemon.summary.catchup import CatchUpSummarizer

logger = logging.getLogger("beckon.pipeline")

class DetectionPipeline:
    def __init__(
        self,
        config: DaemonConfig,
        ring_buffer: AudioRingBuffer,
        speaker_tracker: SpeakerTracker,
        on_alert_callback: Optional[Callable[[dict], None]] = None,
        on_transcript_callback: Optional[Callable[[dict], None]] = None
    ):
        self.config = config
        self.ring_buffer = ring_buffer
        self.speaker_tracker = speaker_tracker
        self.on_alert_callback = on_alert_callback
        self.on_transcript_callback = on_transcript_callback
        
        self.whisper_engine = WhisperEngine(
            model_size=config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
            cpu_threads=config.whisper_threads
        )
        
        threshold = config.thresholds.get(config.name_profile.sensitivity, 0.76)
        self.name_matcher = NameMatcher(
            names=config.name_profile.all_names,
            threshold=threshold,
            min_word_confidence=config.min_word_confidence
        )

        self.summarizer = CatchUpSummarizer(
            groq_api_key=config.groq_api_key,
            ollama_url=config.ollama_url,
            model=config.summary_model,
            timeout_sec=2.0
        )

        # Tier 4: Fast-path Acoustic Keyword Spotter (KWS)
        self.kws_engine = None
        if config.enable_kws:
            from daemon.kws.engine import AcousticKWSEngine
            self.kws_engine = AcousticKWSEngine(
                model_path=config.kws_model_path if config.kws_model_path else None,
                sample_rate=config.sample_rate,
                threshold=config.kws_threshold
            )
        
        self.is_running = False
        self.last_alert_times: Dict[str, float] = {}
        self.last_global_alert_time: float = 0.0
        self.last_processed_sample = 0
        self.recent_alert_sentences = deque(maxlen=20)
        self.processed_texts = deque(maxlen=50)

    def update_name_profile(self, canonical_name: str, aliases: list, sensitivity: str):
        self.config.name_profile.canonical_name = canonical_name
        self.config.name_profile.aliases = aliases
        self.config.name_profile.sensitivity = sensitivity
        
        threshold = self.config.thresholds.get(sensitivity, 0.76)
        self.name_matcher = NameMatcher(
            names=self.config.name_profile.all_names,
            threshold=threshold,
            min_word_confidence=self.config.min_word_confidence
        )
        logger.info(f"Updated NameMatcher: names={self.config.name_profile.all_names}, threshold={threshold}")

    def handle_pcm_frame(self, pcm_bytes: bytes) -> Optional[dict]:
        """Fast-path acoustic processing for streaming audio chunks."""
        if self.kws_engine:
            return self.kws_engine.process_pcm16_chunk(pcm_bytes)
        return None

    async def run_loop(self):
        """Asynchronous processing loop for streaming sliding-window audio."""
        self.is_running = True
        logger.info("Detection pipeline loop started.")

        # Preload the Whisper model
        await asyncio.to_thread(self.whisper_engine.load_model)

        while self.is_running:
            start_tick = time.time()
            try:
                current_total = self.ring_buffer.total_samples_written
                new_samples = current_total - self.last_processed_sample
                min_step_samples = int(self.config.sample_rate * 0.8)  # Require at least 800ms of new audio

                # 1. Check if we have received enough samples and new audio has arrived
                if current_total >= int(self.config.sample_rate * 1.5) and new_samples >= min_step_samples:
                    # Fetch sliding window (e.g. 5.0 seconds)
                    audio_window = self.ring_buffer.get_last_n_seconds(self.config.chunk_window_sec)

                    # Quick energy gate: skip heavy STT when room is quiet / silence
                    energy = float(np.mean(np.abs(audio_window))) if len(audio_window) > 0 else 0.0
                    text = ""
                    words = []

                    if energy < 0.003:
                        # Advance sample counter so silence doesn't accumulate
                        self.last_processed_sample = current_total
                    else:
                        self.last_processed_sample = current_total

                        # Build hotwords from enrolled names (if dynamically registered by client)
                        names_str = ", ".join(self.config.name_profile.all_names) if self.config.name_profile.all_names else None

                        # 2. Transcribe in threadpool with Banglish & multilingual support
                        text, words = await asyncio.to_thread(
                            self.whisper_engine.transcribe_audio_window,
                            audio_window=audio_window,
                            sample_rate=self.config.sample_rate,
                            hotwords=names_str,
                            languages=self.config.languages
                        )

                    clean_text = text.strip()
                    if clean_text and clean_text not in self.processed_texts:
                        logger.info(f"[Heard]: \"{clean_text}\"")
                        self.processed_texts.append(clean_text)

                        current_speaker = self.speaker_tracker.get_current_speaker()
                        self.ring_buffer.add_transcript(clean_text, current_speaker)

                        if self.on_transcript_callback:
                            await self.on_transcript_callback({
                                "type": "transcript",
                                "speaker": current_speaker,
                                "text": clean_text,
                                "timestamp": time.time()
                            })

                        # 3. Name matching
                        match = self.name_matcher.evaluate_text(clean_text, words)
                        now = time.time()
                        if match:
                            target_key = match.target_name.lower().strip()
                            last_name_time = self.last_alert_times.get(target_key, 0.0)
                            context_clause = match.context_sentence.strip()

                            # Prevent re-alerting on the identical clause across overlapping sliding windows
                            is_duplicate_sentence = any(
                                fuzz.ratio(context_clause.lower(), prev.lower()) > 85
                                for prev in self.recent_alert_sentences
                            )

                            if (
                                (now - last_name_time >= self.config.cooldown_sec)
                                and (now - self.last_global_alert_time >= 2.0)
                                and not is_duplicate_sentence
                            ):
                                self.last_alert_times[target_key] = now
                                self.last_global_alert_time = now
                                self.recent_alert_sentences.append(context_clause)

                                # Tier 3: LLM Catch-Up Summarization (Groq or Ollama, with instant fallback)
                                summary_sentence = await self.summarizer.async_summarize(
                                    target_name=match.target_name,
                                    snippet=context_clause,
                                    full_context=self.ring_buffer.get_recent_transcript_context(30.0)
                                )

                                alert_event = {
                                    "type": "alert",
                                    "name": match.target_name,
                                    "detected_phrase": match.detected_phrase,
                                    "speaker": current_speaker,
                                    "score": match.score,
                                    "cue_boost": match.cue_boost,
                                    "word_confidence": match.word_confidence,
                                    "sentence": summary_sentence,
                                    "raw_sentence": context_clause,
                                    "rolling_transcript": self.ring_buffer.get_recent_transcript_context(45.0),
                                    "timestamp": now
                                }
                                logger.info(f"*** NAME DETECTED ***: {alert_event}")
                                if self.on_alert_callback:
                                    await self.on_alert_callback(alert_event)

            except Exception as e:
                logger.error(f"Error in pipeline cycle: {e}", exc_info=True)

            elapsed = time.time() - start_tick
            sleep_duration = max(0.05, self.config.chunk_hop_sec - elapsed)
            await asyncio.sleep(sleep_duration)

    def stop(self):
        self.is_running = False

