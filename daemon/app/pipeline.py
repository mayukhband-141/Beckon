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
from daemon.summary.replies import QuickReplyGenerator

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
        self.reply_generator = QuickReplyGenerator(groq_api_key=config.groq_api_key)

        # Tier 4: Fast-path Acoustic Keyword Spotter (KWS)
        self.kws_engine = None
        self.wake_event = asyncio.Event()
        self.kws_fast_track: Optional[dict] = None
        if config.enable_kws:
            from daemon.kws.engine import AcousticKWSEngine
            self.kws_engine = AcousticKWSEngine(
                model_path=config.kws_model_path if config.kws_model_path else None,
                sample_rate=config.sample_rate,
                threshold=config.kws_threshold,
                target_names=config.name_profile.all_names
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
        if self.kws_engine:
            self.kws_engine.update_target_names(self.config.name_profile.all_names)
        logger.info(f"Updated NameMatcher: names={self.config.name_profile.all_names}, threshold={threshold}")

    def handle_pcm_frame(self, pcm_bytes: bytes) -> Optional[dict]:
        """Fast-path acoustic processing for streaming audio chunks."""
        if self.kws_engine:
            event = self.kws_engine.process_pcm16_chunk(pcm_bytes)
            if event:
                self.kws_fast_track = event
                self.wake_event.set()
            return event
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
                is_kws_fast_track = bool(self.kws_fast_track)
                kws_hit_info = self.kws_fast_track
                min_step_samples = int(self.config.sample_rate * 0.25) if is_kws_fast_track else int(self.config.sample_rate * 0.4)

                # 1. Check if we have received enough samples and new audio has arrived
                if current_total >= int(self.config.sample_rate * 1.0) and new_samples >= min_step_samples:
                    self.kws_fast_track = None
                    # Fetch sliding window (e.g. 5.0 seconds)
                    audio_window = self.ring_buffer.get_last_n_seconds(self.config.chunk_window_sec)

                    # Dynamic speech energy gate: preserve short utterances & quiet phone mic speech
                    peak_energy = float(np.max(np.abs(audio_window))) if len(audio_window) > 0 else 0.0
                    mean_energy = float(np.mean(np.abs(audio_window))) if len(audio_window) > 0 else 0.0
                    text = ""
                    words = []

                    if peak_energy < 0.004 and mean_energy < 0.0002:
                        # True dead silence
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
                    if clean_text:
                        logger.info(f"[Heard]: \"{clean_text}\" (peak_energy={peak_energy:.3f})")
                        if clean_text not in self.processed_texts:
                            self.processed_texts.append(clean_text)

                        # Passive acoustic voiceprint recognition & enrollment
                        self.speaker_tracker.observe_audio_frame(audio_window)
                        current_speaker = self.speaker_tracker.get_current_speaker(audio_window)
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

                            # Prevent re-alerting on the identical clause across immediate sub-second cycles
                            is_duplicate_sentence = any(
                                fuzz.ratio(context_clause.lower(), prev.lower()) > 90
                                for prev in self.recent_alert_sentences
                            )

                            cooldown = 2.5  # Responsive 2.5s cooldown
                            if (now - last_name_time >= cooldown) and (now - self.last_global_alert_time >= 1.5):
                                self.last_alert_times[target_key] = now
                                self.last_global_alert_time = now
                                self.recent_alert_sentences.append(context_clause)

                                logger.info(
                                    "🚨 *** NAME MATCHED & ALERT DISPATCHED: %s (score=%.2f, phrase='%s') ***",
                                    match.target_name, match.score, match.detected_phrase
                                )

                                # Tier 3: LLM Catch-Up Summarization (Groq or Ollama, with instant fallback)
                                summary_sentence = await self.summarizer.async_summarize(
                                    target_name=match.target_name,
                                    snippet=context_clause,
                                    full_context=self.ring_buffer.get_recent_transcript_context(30.0)
                                )

                                # Tier 5: Contextual Quick-Reply Generation
                                quick_replies = self.reply_generator.generate_replies(
                                    target_name=match.target_name,
                                    sentence=context_clause,
                                    summary=summary_sentence
                                )

                                alert_event = {
                                    "type": "alert",
                                    "name": match.target_name,
                                    "detected_phrase": match.detected_phrase,
                                    "speaker": current_speaker,
                                    "score": match.score,
                                    "cue_boost": match.cue_boost,
                                    "word_confidence": match.word_confidence,
                                    "kws_fast_path": is_kws_fast_track,
                                    "kws_score": kws_hit_info.get("score") if kws_hit_info else None,
                                    "sentence": summary_sentence,
                                    "raw_sentence": context_clause,
                                    "quick_replies": quick_replies,
                                    "rolling_transcript": self.ring_buffer.get_recent_transcript_context(45.0),
                                    "timestamp": now
                                }
                                    "sentence": summary_sentence,
                                    "raw_sentence": context_clause,
                                    "quick_replies": quick_replies,
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
            try:
                await asyncio.wait_for(self.wake_event.wait(), timeout=sleep_duration)
                self.wake_event.clear()
                logger.debug("Detection pipeline awakened early by KWS fast-path trigger")
            except asyncio.TimeoutError:
                pass

    def stop(self):
        self.is_running = False

