from daemon.match.intent_classifier import (
    SemanticContextClassifier,
    PhoneticAmbiguityProfiler,
    MorphologicalDecomposer,
    AspectAgreementAnalyzer
)

def test_morphological_decomposition():
    print("--- Testing Morphological Decomposer ---")
    stem, sigs = MorphologicalDecomposer.decompose_target("Alex-er", "alex")
    assert stem == "alex"
    assert any("genitive_possessive" in s[0] for s in sigs)
    print("Alex-er ->", stem, sigs)

    stem, sigs = MorphologicalDecomposer.decompose_target("Mayukh-da", "mayukh")
    assert stem == "mayukh"
    assert any("vocative_honorific_da" in s[0] for s in sigs)
    print("Mayukh-da ->", stem, sigs)

    stem, sigs = MorphologicalDecomposer.decompose_target("Alex-ke", "alex")
    assert stem == "alex"
    assert any("accusative_dative" in s[0] for s in sigs)
    print("Alex-ke ->", stem, sigs)

    stem, sigs = MorphologicalDecomposer.decompose_target("Alex's", "alex")
    assert stem == "alex"
    assert any("genitive_possessive" in s[0] for s in sigs)
    print("Alex's ->", stem, sigs)


def test_phonetic_ambiguity_profiler():
    print("\n--- Testing Phonetic Ambiguity Profiler ---")
    risk_will = PhoneticAmbiguityProfiler.get_phonetic_risk("Will")
    risk_may = PhoneticAmbiguityProfiler.get_phonetic_risk("May")
    risk_alex = PhoneticAmbiguityProfiler.get_phonetic_risk("Alex")
    risk_mayukh = PhoneticAmbiguityProfiler.get_phonetic_risk("Mayukh")

    print(f"Risk for 'Will': {risk_will:.2f} (Expected high)")
    print(f"Risk for 'May': {risk_may:.2f} (Expected high)")
    print(f"Risk for 'Alex': {risk_alex:.2f} (Expected baseline)")
    print(f"Risk for 'Mayukh': {risk_mayukh:.2f} (Expected baseline)")

    assert risk_will >= 0.60
    assert risk_may >= 0.60
    assert risk_alex <= 0.20
    assert risk_mayukh <= 0.20


def test_intent_classifier_multilingual():
    classifier = SemanticContextClassifier()

    direct_cases = [
        # English Direct
        ("Hey Alex, can you take over the screen?", "Alex"),
        ("Alex, please unmute and share your thoughts.", "Alex"),
        ("Alex?", "Alex"),
        ("Can you hear us, Alex?", "Alex"),
        ("Alex, walk us through the deployment steps.", "Alex"),
        
        # Banglish & Bengali Direct
        ("Alex ekkhuni join koro", "Alex"),
        ("Ei Alex, sunte paccho?", "Alex"),
        ("Alex-da, eita ki bhabe korbo?", "Alex"),
        ("Mayukh, tumi eita dekho", "Mayukh"),
        ("Alex, shuno ekbar", "Alex"),
        
        # Hinglish & Hindi Direct
        ("Suno Alex, kya bol rahe ho?", "Alex"),
        ("Alex bhai, zara screen share karna", "Alex"),
        ("Alex, aap batao kya progress hai", "Alex"),
        ("Arre Alex, sun rahe ho?", "Alex"),
        
        # Ambiguous name with explicit vocative cues (Should still alert)
        ("Hey Will, can you check the server?", "Will"),
    ]

    print("\n--- Testing Direct Address Cases (Must Alert) ---")
    for sentence, target in direct_cases:
        res = classifier.classify(sentence, target)
        print(f"[DIRECT] Score: {res.confidence:.2f} | Intent: {res.intent:<14} | Target: {target:<6} | Text: \"{sentence}\"")
        assert res.is_direct_address is True, f"Failed on direct address: '{sentence}' -> {res}"
        assert res.intent in ("direct_address", "ambiguous_call")

    casual_cases = [
        # English Casual & Passive
        ("I was in a meeting with Alex yesterday.", "Alex"),
        ("Alex merged the pull request an hour ago.", "Alex"),
        ("We reviewed Alex's presentation slides earlier today.", "Alex"),
        ("I got this document from Alex.", "Alex"),
        ("This bug was actually fixed by Alex last week.", "Alex"),
        ("According to Alex, the release is scheduled for tomorrow.", "Alex"),

        # Banglish & Bengali Casual & Agglutinative Clitics
        ("Alex-er shathe amar kotha hoyeche.", "Alex"),
        ("Alex boleche project ta submit kora hoyeche.", "Alex"),
        ("Eita Alex korechilo shokal bela.", "Alex"),
        ("Alex-ke jigyasha kore janabo.", "Alex"),
        ("Alex-er laptop ta kharap hoye geche.", "Alex"),

        # Hinglish & Hindi Casual & Ergative Postpositions
        ("Alex ne bola tha ye fix ho gaya.", "Alex"),
        ("Maine Alex se baat ki thi kal.", "Alex"),
        ("Alex ko bolo ki file send kar de.", "Alex"),
        ("Alex ka code merge ho chuka hai.", "Alex"),
        ("Ye feature Alex ne banaya hai.", "Alex"),

        # Phonetically ambiguous name in casual functional context (Must suppress)
        ("Will this work for our deployment?", "Will"),
        ("May I ask what the status is?", "May"),
    ]

    print("\n--- Testing Casual Mention Cases (Must Suppress) ---")
    for sentence, target in casual_cases:
        res = classifier.classify(sentence, target)
        print(f"[CASUAL] Score: {res.confidence:.2f} | Intent: {res.intent:<14} | Target: {target:<6} | Signals: {res.signals[:2]} | Text: \"{sentence}\"")
        assert res.is_direct_address is False, f"Failed on casual mention suppression: '{sentence}' -> {res}"
        assert res.intent == "casual_mention"

    print("\nAll 30+ Morpho-Phonetic Vocative Engine tests passed successfully!")


if __name__ == "__main__":
    test_morphological_decomposition()
    test_phonetic_ambiguity_profiler()
    test_intent_classifier_multilingual()
