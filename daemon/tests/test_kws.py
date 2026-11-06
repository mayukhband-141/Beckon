import numpy as np
from daemon.kws.features import LogMelFeatureExtractor
from daemon.kws.engine import AcousticKWSEngine, NumpyAcousticScorer

def test_feature_extractor():
    extractor = LogMelFeatureExtractor(sample_rate=16000, n_mels=80)
    audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000)).astype(np.float32)

    mel = extractor.extract(audio)
    assert mel.shape[0] == 80, f"Expected 80 mel bins, got {mel.shape[0]}"
    assert mel.shape[1] > 0, "Expected positive number of time steps"
    assert not np.isnan(mel).any(), "Mel spectrogram contains NaNs"
    assert not np.isinf(mel).any(), "Mel spectrogram contains Infs"

def test_numpy_scorer():
    scorer = NumpyAcousticScorer(in_channels=80, hidden_dim=32)
    fake_mel = np.random.randn(80, 98).astype(np.float32)
    score = scorer.forward(fake_mel)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0, f"Score {score} outside [0.0, 1.0]"

def test_kws_engine_silence():
    engine = AcousticKWSEngine(threshold=0.60)
    silence = np.zeros(16000, dtype=np.float32)
    score = engine.score_audio_window(silence)
    assert score == 0.0, f"Silence score should be 0.0, got {score}"

def test_kws_streaming_chunks():
    engine = AcousticKWSEngine(threshold=0.01) # Lower threshold for test trigger
    sine_audio = (np.sin(2 * np.pi * 300 * np.linspace(0, 1.0, 16000)) * 10000).astype(np.int16)
    pcm_bytes = sine_audio.tobytes()

    # Stream in 1600 sample (100ms) chunks
    chunk_size = 3200 # 1600 samples * 2 bytes
    hit_detected = False

    for offset in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[offset : offset + chunk_size]
        res = engine.process_pcm16_chunk(chunk)
        if res and res.get("type") == "kws_hit":
            hit_detected = True
            break

    assert hit_detected is True, "Streaming audio chunk should trigger KWS evaluation"

if __name__ == "__main__":
    test_feature_extractor()
    test_numpy_scorer()
    test_kws_engine_silence()
    test_kws_streaming_chunks()
    print("All Acoustic KWS (Tier 4 Phase 1) tests passed!")

