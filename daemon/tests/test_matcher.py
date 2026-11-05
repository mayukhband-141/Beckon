from daemon.match.matcher import NameMatcher

def test_exact_match():
    matcher = NameMatcher(["Alex", "Alec"], threshold=0.76)
    res = matcher.evaluate_text("Hey Alex, what do you think?")
    assert res is not None
    assert res.matched is True
    assert res.target_name == "Alex"
    assert res.score >= 0.90

def test_phonetic_variant_match():
    matcher = NameMatcher(["Alex"], threshold=0.76)
    res = matcher.evaluate_text("Can you take this one Aleks?")
    assert res is not None
    assert res.matched is True
    assert res.target_name == "Alex"
    assert res.score >= 0.76

def test_context_cues():
    matcher = NameMatcher(["Alex"], threshold=0.76)
    # Direct address with greeting and question
    res_direct = matcher.evaluate_text("Hi Alex, could you share the link?")
    # Third-person reference
    res_third = matcher.evaluate_text("We reviewed Alex's presentation yesterday.")
    
    assert res_direct is not None
    assert res_direct.matched is True
    score_direct = res_direct.score
    score_third = res_third.score if res_third else 0.0
    assert score_direct > score_third

def test_unrelated_sentence():
    matcher = NameMatcher(["Alex"], threshold=0.76)
    res = matcher.evaluate_text("Let's look at the quarterly financial results from last week.")
    assert res is None

def test_word_confidence_filtering():
    matcher = NameMatcher(["Alex"], threshold=0.76, min_word_confidence=0.40)
    # High confidence -> passes
    words_high = [
        {"word": "Hey", "probability": 0.95},
        {"word": "Alex", "probability": 0.88}
    ]
    res_high = matcher.evaluate_text("Hey Alex", word_segments=words_high)
    assert res_high is not None
    assert res_high.matched is True

    # Low confidence hallucination -> rejected
    words_low = [
        {"word": "Hey", "probability": 0.95},
        {"word": "Alex", "probability": 0.22}
    ]
    res_low = matcher.evaluate_text("Hey Alex", word_segments=words_low)
    assert res_low is None

if __name__ == "__main__":
    test_exact_match()
    test_phonetic_variant_match()
    test_context_cues()
    test_unrelated_sentence()
    test_word_confidence_filtering()
    print("All NameMatcher unit tests passed!")

