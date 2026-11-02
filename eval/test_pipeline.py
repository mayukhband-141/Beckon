import time
import numpy as np
from daemon.app.config import DaemonConfig
from daemon.app.ring_buffer import AudioRingBuffer
from daemon.match.matcher import NameMatcher

def simulate_pipeline_matching():
    config = DaemonConfig()
    config.name_profile.canonical_name = "Mayukh"
    config.name_profile.aliases = ["Mayuk", "Moyukh", "Mayukha"]
    
    threshold = config.thresholds["balanced"]
    matcher = NameMatcher(config.name_profile.all_names, threshold=threshold)

    test_cases = [
        ("Hey Mayukh, what are your thoughts on this design?", True, "Mayukh"),
        ("I think Mayuk can take over the next slide.", True, "Mayuk"),
        ("Moyukh, are you able to hear us clearly?", True, "Moyukh"),
        ("Let's proceed with the deployment schedule.", False, None),
        ("We reviewed Mayukh's notes earlier today.", False, None), # Third-person below direct threshold or lower score
    ]

    print(f"--- Running NameMatcher Test Suite for '{config.name_profile.canonical_name}' ---")
    passed = 0
    for text, should_match, expected_name in test_cases:
        res = matcher.evaluate_text(text)
        is_match = res is not None and res.matched
        score = res.score if res else 0.0
        
        status = "PASS" if is_match == should_match else "FAIL"
        if status == "PASS":
            passed += 1
            
        print(f"[{status}] Score: {score:.2f} | Text: \"{text}\"")
        if res:
            print(f"       -> Detected: '{res.detected_phrase}', Target: '{res.target_name}', Boost: {res.cue_boost}")

    print(f"\nResult: {passed}/{len(test_cases)} tests passed.")
    assert passed >= 4, "Matcher accuracy check failed"

if __name__ == "__main__":
    simulate_pipeline_matching()

