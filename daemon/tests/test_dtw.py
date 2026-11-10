import numpy as np
from daemon.kws.phonemes import PhoneticAcousticMapper
from daemon.kws.dtw import AcousticDTWScorer
from daemon.kws.engine import AcousticKWSEngine

def test_phonetic_mapper():
    print("--- Testing PhoneticAcousticMapper ---")
    alex_phonemes = PhoneticAcousticMapper.text_to_phonemes("Alex")
    mayukh_phonemes = PhoneticAcousticMapper.text_to_phonemes("Mayukh")
    sarah_phonemes = PhoneticAcousticMapper.text_to_phonemes("Sarah")

    print(f"'Alex' phonemes:   {alex_phonemes}")
    print(f"'Mayukh' phonemes: {mayukh_phonemes}")
    print(f"'Sarah' phonemes:  {sarah_phonemes}")

    assert len(alex_phonemes) >= 4
    assert len(mayukh_phonemes) >= 4
    assert len(sarah_phonemes) >= 3

    alex_mat = PhoneticAcousticMapper.get_template_matrix("Alex")
    assert alex_mat.shape == (len(alex_phonemes), 80)
    print(f"Alex prototype matrix shape: {alex_mat.shape}")


def test_dtw_scorer_exact_match():
    print("\n--- Testing Subsequence DTW Matching ---")
    scorer = AcousticDTWScorer(target_names=["Alex", "Mayukh"])

    # Synthesize an audio spectrogram where Alex's phonemes appear between frames 20..60
    alex_template = PhoneticAcousticMapper.get_template_matrix("Alex")
    T = 98
    mel = np.random.uniform(0.01, 0.05, size=(80, T)).astype(np.float32)

    # Inject repeated phoneme frames corresponding to Alex
    M = alex_template.shape[0]
    frames_per_phoneme = 6
    start_frame = 25
    for p_idx in range(M):
        p_frame = alex_template[p_idx]
        for f in range(frames_per_phoneme):
            idx = start_frame + p_idx * frames_per_phoneme + f
            if idx < T:
                mel[:, idx] = p_frame

    score, matched = scorer.score_mel(mel)
    print(f"Synthesized 'Alex' audio window DTW score: {score:.3f} | Matched: {matched}")
    assert matched == "Alex"
    assert score >= 0.70, f"Expected DTW score >= 0.70 on injected template, got {score}"

    # Pure noise window should have low score
    noise_mel = np.random.uniform(0.01, 0.05, size=(80, T)).astype(np.float32)
    noise_score, noise_matched = scorer.score_mel(noise_mel)
    print(f"Random noise window DTW score: {noise_score:.3f} | Matched: {noise_matched}")
    assert noise_score < 0.40, f"Expected low score on noise, got {noise_score}"


def test_engine_dynamic_update():
    print("\n--- Testing Engine Dynamic Target Name Update ---")
    engine = AcousticKWSEngine(
        sample_rate=16000,
        threshold=0.60,
        target_names=["Alex"]
    )
    assert "Alex" in engine.dtw_scorer.templates

    # Dynamically update to new names without restart
    engine.update_target_names(["Mayukh", "Sarah"])
    assert "Mayukh" in engine.dtw_scorer.templates
    assert "Sarah" in engine.dtw_scorer.templates
    assert "Alex" not in engine.dtw_scorer.templates
    print("Engine dynamically updated target templates in memory successfully!")


if __name__ == "__main__":
    test_phonetic_mapper()
    test_dtw_scorer_exact_match()
    test_engine_dynamic_update()
    print("\nAll Dynamic Phoneme DTW tests passed successfully!")
