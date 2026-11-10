import numpy as np
from daemon.discovery.beacon import UDPDiscoveryBeacon, get_local_ip
from daemon.speaker.diarization import SpeakerVoiceprintExtractor, AcousticSpeakerIdentifier
from daemon.speaker.tracker import SpeakerTracker
from daemon.summary.replies import QuickReplyGenerator
from daemon.audio.loopback import SystemAudioLoopback

def test_udp_discovery_beacon():
    print("--- Testing UDPDiscoveryBeacon ---")
    ip = get_local_ip()
    assert isinstance(ip, str) and len(ip.split(".")) == 4
    print(f"Detected local IP: {ip}")

    beacon = UDPDiscoveryBeacon(ws_port=8765, auth_token="test_tok")
    payload = beacon.get_pairing_payload()
    assert payload["service"] == "beckon"
    assert payload["port"] == 8765
    assert payload["token"] == "test_tok"
    print(f"Pairing payload verified: {payload}")


def test_acoustic_speaker_diarization():
    print("\n--- Testing Acoustic Speaker Diarization ---")
    extractor = SpeakerVoiceprintExtractor()
    identifier = AcousticSpeakerIdentifier(min_similarity_threshold=0.70)

    # Synthesize two distinct speaker audio signals with different pitch & formants
    sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False).astype(np.float32)

    # Speaker 1: Low-pitch male voice (~120Hz fundamental + harmonics)
    spk1_audio = (
        0.5 * np.sin(2 * np.pi * 120 * t) +
        0.3 * np.sin(2 * np.pi * 240 * t) +
        0.2 * np.sin(2 * np.pi * 360 * t)
    )

    # Speaker 2: High-pitch female voice (~220Hz fundamental + harmonics)
    spk2_audio = (
        0.5 * np.sin(2 * np.pi * 220 * t) +
        0.3 * np.sin(2 * np.pi * 440 * t) +
        0.2 * np.sin(2 * np.pi * 660 * t)
    )

    # Enroll Speaker 1 as "John"
    identifier.enroll_speaker("John", spk1_audio)
    # Enroll Speaker 2 as "Sarah"
    identifier.enroll_speaker("Sarah", spk2_audio)

    assert "John" in identifier.profiles
    assert "Sarah" in identifier.profiles

    # Test identification with fresh noisy samples
    noisy_spk1 = spk1_audio + np.random.normal(0, 0.02, size=len(spk1_audio)).astype(np.float32)
    matched, conf = identifier.identify_speaker(noisy_spk1)
    print(f"Probe Speaker 1 -> Matched: {matched} (Confidence: {conf:.3f})")
    assert matched == "John"
    assert conf >= 0.70

    noisy_spk2 = spk2_audio + np.random.normal(0, 0.02, size=len(spk2_audio)).astype(np.float32)
    matched, conf = identifier.identify_speaker(noisy_spk2)
    print(f"Probe Speaker 2 -> Matched: {matched} (Confidence: {conf:.3f})")
    assert matched == "Sarah"
    assert conf >= 0.70


def test_speaker_tracker_voiceprint_fallback():
    print("\n--- Testing SpeakerTracker Hybrid Fallback ---")
    tracker = SpeakerTracker()
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False).astype(np.float32)
    voice_audio = 0.5 * np.sin(2 * np.pi * 150 * t)

    # Initially unknown
    assert tracker.get_current_speaker() == "Someone"

    # Passive auto-enrollment when DOM speaker is active
    tracker.update_active_speaker("Alex Manager")
    tracker.observe_audio_frame(voice_audio)

    # Fast forward: DOM tile is gone, but voice audio matches!
    tracker.current_speaker = None
    tracker.last_speaker_update_time = 0.0

    detected = tracker.get_current_speaker(voice_audio)
    print(f"Acoustic fallback speaker attribution: {detected}")
    assert "Voiceprint" in detected
    assert "Alex Manager" in detected


def test_quick_replies_generator():
    print("\n--- Testing QuickReplyGenerator ---")
    gen = QuickReplyGenerator()

    # Screen share request
    r_screen = gen.generate_replies("Alex", "Alex, can you take over screen sharing for a moment?")
    print("Screen share replies:", r_screen)
    assert len(r_screen) == 3
    assert any("screen" in r.lower() for r in r_screen)

    # Mic check request
    r_mic = gen.generate_replies("Alex", "Alex, please unmute, we can't hear you.")
    print("Mic replies:", r_mic)
    assert len(r_mic) == 3
    assert any("unmut" in r.lower() or "mic" in r.lower() for r in r_mic)

    # Code PR request
    r_pr = gen.generate_replies("Alex", "Did you push the PR branch to main?")
    print("PR replies:", r_pr)
    assert len(r_pr) == 3
    assert any("push" in r.lower() or "review" in r.lower() for r in r_pr)


def test_system_audio_loopback_lifecycle():
    print("\n--- Testing SystemAudioLoopback Lifecycle ---")
    received_chunks = []
    loopback = SystemAudioLoopback(
        sample_rate=16000,
        chunk_duration_sec=0.05,
        on_pcm_callback=lambda pcm: received_chunks.append(len(pcm))
    )
    backend_name, _ = loopback._find_backend()
    print(f"Discovered loopback backend: {backend_name}")

    loopback.start()
    assert loopback.is_running is True
    loopback.stop()
    assert loopback.is_running is False
    print("SystemAudioLoopback initialized and terminated cleanly.")


if __name__ == "__main__":
    test_udp_discovery_beacon()
    test_acoustic_speaker_diarization()
    test_speaker_tracker_voiceprint_fallback()
    test_quick_replies_generator()
    test_system_audio_loopback_lifecycle()
    print("\nAll Tier 5 Advanced Feature tests passed successfully!")
