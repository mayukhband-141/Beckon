from daemon.match.matcher import NameMatcher

def test_exact_match():
    matcher = NameMatcher(["Mayukh", "Mayuk"], threshold=0.76)
    res = matcher.evaluate_text("Hey Mayukh, what do you think?")
    assert res is not None
    assert res.matched is True
    assert res.target_name == "Mayukh"
    assert res.score >= 0.90

def test_phonetic_variant_match():
    # If Whisper transcribes "Mayuk" or "Moyukh"
    matcher = NameMatcher(["Mayukh"], threshold=0.76)
    res = matcher.evaluate_text("Can you take this one Moyukh?")
    assert res is not None
    assert res.matched is True
    assert res.target_name == "Mayukh"
    assert res.score >= 0.76

def test_context_cues():
    matcher = NameMatcher(["Mayukh"], threshold=0.76)
    # Direct address with greeting and question
    res_direct = matcher.evaluate_text("Hi Mayukh, could you share the link?")
    # Third-person reference
    res_third = matcher.evaluate_text("We reviewed Mayukh's presentation yesterday.")
    
    assert res_direct is not None
    assert res_direct.matched is True
    # The direct address with cues should have a higher score than third person
    score_direct = res_direct.score
    score_third = res_third.score if res_third else 0.0
    assert score_direct > score_third

def test_unrelated_sentence():
    matcher = NameMatcher(["Mayukh"], threshold=0.76)
    res = matcher.evaluate_text("Let's look at the quarterly financial results from last week.")
    assert res is None

if __name__ == "__main__":
    test_exact_match()
    test_phonetic_variant_match()
    test_context_cues()
    test_unrelated_sentence()
    print("All NameMatcher unit tests passed!")

