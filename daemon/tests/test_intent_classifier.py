from daemon.match.intent_classifier import SemanticContextClassifier

def test_intent_classifier():
    classifier = SemanticContextClassifier()

    direct_cases = [
        ("Hey Alex, can you take over the screen?", "Alex"),
        ("Alex ekkhuni join koro", "Alex"),
        ("Ei Alex, sunte paccho?", "Alex"),
        ("Suno Alex, kya bol rahe ho?", "Alex"),
        ("Alex, please unmute and share your thoughts.", "Alex"),
        ("Alex?", "Alex"),
        ("Can you hear us, Alex?", "Alex"),
    ]

    print("--- Testing Direct Address Cases (Must Alert) ---")
    for sentence, target in direct_cases:
        res = classifier.classify(sentence, target)
        print(f"[DIRECT] Score: {res.confidence:.2f} | Intent: {res.intent} | Text: \"{sentence}\"")
        assert res.is_direct_address is True, f"Failed on direct address: '{sentence}' -> {res}"
        assert res.intent in ("direct_address", "ambiguous_call")

    casual_cases = [
        ("I was in a meeting with Alex yesterday.", "Alex"),
        ("Alex merged the pull request an hour ago.", "Alex"),
        ("We reviewed Alex's presentation slides earlier today.", "Alex"),
        ("Alex boleche project ta submit kora hoyeche.", "Alex"),
        ("Alex ne bola tha ye fix ho gaya.", "Alex"),
        ("I got this document from Alex.", "Alex"),
    ]

    print("\n--- Testing Casual Mention Cases (Must Suppress) ---")
    for sentence, target in casual_cases:
        res = classifier.classify(sentence, target)
        print(f"[CASUAL] Score: {res.confidence:.2f} | Intent: {res.intent} | Signals: {res.signals} | Text: \"{sentence}\"")
        assert res.is_direct_address is False, f"Failed on casual mention suppression: '{sentence}' -> {res}"
        assert res.intent == "casual_mention"

    print("\nAll Semantic Intent Classifier (Tier 4 Phase 2) tests passed successfully!")

if __name__ == "__main__":
    test_intent_classifier()
