import numpy as np
from daemon.stt.whisper_engine import WhisperEngine

def test_whisper_loading():
    print("Initializing WhisperEngine with 'tiny' for quick validation...")
    engine = WhisperEngine(model_size="tiny", device="cpu", compute_type="int8", cpu_threads=4)
    engine.load_model()
    print("Model loaded successfully.")

    # 3 seconds of 16kHz audio (silence)
    silence = np.zeros(16000 * 3, dtype=np.float32)
    text, words = engine.transcribe_audio_window(silence, hotwords="Alex")
    print(f"Transcribed silence output: '{text}' (expected empty)")
    assert text == ""
    print("WhisperEngine integration test passed!")

if __name__ == "__main__":
    test_whisper_loading()

