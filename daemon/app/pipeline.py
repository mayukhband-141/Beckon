import time
import asyncio
import logging
from typing import Callable, Optional
from daemon.app.config import DaemonConfig
from daemon.app.ring_buffer import AudioRingBuffer
from daemon.match.matcher import NameMatcher
from daemon.stt.whisper_engine import WhisperEngine
from daemon.speaker.tracker import SpeakerTracker

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
            threshold=threshold
        )
        
        self.is_running = False
        self.last_alert_time = 0.0
        self.processed_texts = set()

    def update_name_profile(self, canonical_name: str, aliases: list, sensitivity: str):
        self.config.name_profile.canonical_name = canonical_name
        self.config.name_profile.aliases = aliases
        self.config.name_profile.sensitivity = sensitivity
        
        threshold = self.config.thresholds.get(sensitivity, 0.76)
        self.name_matcher = NameMatcher(
            names=self.config.name_profile.all_names,
            threshold=threshold
        )
        logger.info(f"Updated NameMatcher: names={self.config.name_profile.all_names}, threshold={threshold}")

    async def run_loop(self):
        """Asynchronous processing loop for streaming sliding-window audio."""
        self.is_running = True
        logger.info("Detection pipeline loop started.")

        # Preload the Whisper model
        await asyncio.to_thread(self.whisper_engine.load_model)

        while self.is_running:
            start_tick = time.time()
            try:
                # 1. Check if we have received enough samples
                if self.ring_buffer.total_samples_written >= int(self.config.sample_rate * 1.5):
                    # Fetch sliding window (e.g. 5.0 seconds)
                    audio_window = self.ring_buffer.get_last_n_seconds(self.config.chunk_window_sec)

                    # Build hotwords and initial prompt from enrolled names + roster
                    names_str = " ".join(self.config.name_profile.all_names)
                    roster = self.speaker_tracker.get_roster()
                    initial_prompt = f"Meeting participants: {names_str}. " + (", ".join(roster) if roster else "")

                    # 2. Transcribe in threadpool so event loop is not blocked
                    text, words = await asyncio.to_thread(
                        self.whisper_engine.transcribe_audio_window,
                        audio_window=audio_window,
                        sample_rate=self.config.sample_rate,
                        hotwords=names_str,
                        initial_prompt=initial_prompt
                    )

                    clean_text = text.strip()
                    if clean_text and clean_text not in self.processed_texts:
                        logger.info(f"[Heard]: \"{clean_text}\"")
                        # Keep a small set to prevent identical consecutive duplicate checks
                        self.processed_texts.add(clean_text)
                        if len(self.processed_texts) > 50:
                            self.processed_texts.pop()

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
                        if match and (now - self.last_alert_time >= self.config.cooldown_sec):
                            self.last_alert_time = now
                            alert_event = {
                                "type": "alert",
                                "name": match.target_name,
                                "detected_phrase": match.detected_phrase,
                                "speaker": current_speaker,
                                "score": match.score,
                                "cue_boost": match.cue_boost,
                                "sentence": match.context_sentence,
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

