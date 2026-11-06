import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple, Dict
import numpy as np
import jellyfish

@dataclass
class IntentResult:
    intent: str               # "direct_address", "casual_mention", "ambiguous_call"
    is_direct_address: bool   # True = Should alert; False = Should suppress
    confidence: float         # 0.0 to 1.0
    signals: List[str] = field(default_factory=list)
    score_modifier: float = 0.0


class PhoneticAmbiguityProfiler:
    """
    Evaluates whether the target name has high phonetic overlap / collision
    with common functional words (e.g. 'will', 'may', 'mark', 'ki', 'se', 'na').
    Names with high confusion risk require stronger vocative evidence.
    """
    HIGH_FREQUENCY_FUNCTION_WORDS = {
        # English
        "will", "may", "can", "mark", "art", "rob", "sue", "bill", "read",
        "rose", "pat", "chase", "grant", "well", "all", "like", "see",
        # Banglish / Bengali
        "ki", "je", "se", "na", "to", "oi", "ei", "ba", "ta", "ar", "ja",
        # Hinglish / Hindi
        "ko", "ka", "ki", "ke", "ne", "se", "bhi", "ho", "hai", "kya", "ye", "wo"
    }

    @classmethod
    def get_phonetic_risk(cls, target_name: str) -> float:
        clean = re.sub(r"[^\w]", "", target_name, flags=re.UNICODE).lower()
        if not clean:
            return 0.0

        # Exact match with common functional word
        if clean in cls.HIGH_FREQUENCY_FUNCTION_WORDS:
            return 0.75

        # Single syllable / very short names (<= 3 chars) have higher collision probability
        if len(clean) <= 3 and clean.isascii():
            target_meta = jellyfish.metaphone(clean)
            for word in cls.HIGH_FREQUENCY_FUNCTION_WORDS:
                if word.isascii() and jellyfish.metaphone(word) == target_meta:
                    return 0.60
            return 0.40

        return 0.10


class MorphologicalDecomposer:
    """
    Handles agglutinative clitic stripping and case/honorific identification
    for Bengali, Banglish, Hindi, Hinglish, and English proper names.
    """
    # Suffixes that mark genitive, accusative, or locative cases (Casual indicators)
    CASUAL_CLITICS: Dict[str, Tuple[str, float]] = {
        # English possessive
        "'s": ("genitive_possessive", -0.50),
        "’s": ("genitive_possessive", -0.50),
        "s'": ("genitive_possessive", -0.50),
        # Banglish & Bengali suffixes
        "-er": ("genitive_possessive", -0.45),
        "er": ("genitive_possessive", -0.45),
        "-ke": ("accusative_dative", -0.40),
        "ke": ("accusative_dative", -0.40),
        "-te": ("locative", -0.35),
        "te": ("locative", -0.35),
        "-ta": ("classifier_mention", -0.25),
        "ta": ("classifier_mention", -0.25),
        "ের": ("genitive_possessive", -0.45),
        "কে": ("accusative_dative", -0.40),
        "তে": ("locative", -0.35),
        "টা": ("classifier_mention", -0.25),
    }

    # Honorific / kinship clitics that act as strong vocatives (Direct indicators)
    VOCATIVE_HONORIFIC_CLITICS: Dict[str, Tuple[str, float]] = {
        "-da": ("vocative_honorific_da", +0.30),
        "da": ("vocative_honorific_da", +0.30),
        "-bhai": ("vocative_honorific_bhai", +0.30),
        "bhai": ("vocative_honorific_bhai", +0.30),
        "-didi": ("vocative_honorific_didi", +0.30),
        "didi": ("vocative_honorific_didi", +0.30),
        "-ji": ("vocative_honorific_ji", +0.30),
        "ji": ("vocative_honorific_ji", +0.30),
        "দা": ("vocative_honorific_da", +0.30),
        "ভাই": ("vocative_honorific_bhai", +0.30),
        "দিদি": ("vocative_honorific_didi", +0.30),
        "जी": ("vocative_honorific_ji", +0.30),
    }

    @classmethod
    def decompose_target(cls, token: str, clean_target: str) -> Tuple[str, List[Tuple[str, float]]]:
        """
        Decomposes a token like 'Alex-er' or 'Mayukh-da' into root + morphological signals.
        Returns: (stemmed_name, [(signal_name, score_delta), ...])
        """
        token_clean = re.sub(r"[^\w'’-]", "", token, flags=re.UNICODE).lower()
        signals = []

        if not token_clean:
            return token_clean, signals

        # 1. Check exact match
        if token_clean == clean_target:
            return clean_target, signals

        # 2. Check attached honorifics (vocative boosters)
        for clitic, (sig_name, delta) in cls.VOCATIVE_HONORIFIC_CLITICS.items():
            if token_clean.endswith(clitic) and len(token_clean) > len(clitic):
                stem = token_clean[:-len(clitic)].rstrip("-'’")
                if stem == clean_target:
                    signals.append((f"morphology:{sig_name}('{clitic}')", delta))
                    return clean_target, signals

        # 3. Check casual case clitics (genitive, accusative, locative)
        for clitic, (sig_name, delta) in cls.CASUAL_CLITICS.items():
            if token_clean.endswith(clitic) and len(token_clean) > len(clitic):
                stem = token_clean[:-len(clitic)].rstrip("-'’")
                if stem == clean_target:
                    signals.append((f"morphology:{sig_name}('{clitic}')", delta))
                    return clean_target, signals

        return token_clean, signals


class AspectAgreementAnalyzer:
    """
    Analyzes verbal person, tense, and aspect agreement across English, Banglish,
    Hinglish, Bengali, and Devanagari Hindi.
    Distinguishes 2nd-person imperative/inquiry from 3rd-person past/reporting.
    """
    # Second-person pronouns (strong indicators that the speaker is addressing someone)
    SECOND_PERSON_PRONOUNS: Set[str] = {
        "you", "your", "yours", "yourself",
        "tumi", "tomar", "tomake", "tui", "tor", "toke", "apni", "apnar", "apnake",
        "তুমি", "তোমার", "তোমাকে", "তুই", "তোর", "তোকে", "আপনি", "আপনার", "আপনাকে",
        "tum", "tumhe", "tera", "teri", "tere", "aap", "aapka", "aapko", "tu",
        "तुम", "तुम्हें", "तेरा", "तेरी", "तेरे", "आप", "आपका", "आपको", "तू"
    }

    # Second-person imperative / action request verbs
    IMPERATIVE_ACTION_VERBS: Set[str] = {
        # English
        "unmute", "mute", "share", "take", "listen", "hear", "look", "check",
        "join", "present", "lead", "show", "explain", "tell", "give", "ping",
        "confirm", "review", "start", "stop", "switch", "turn",
        # Banglish & Bengali
        "bolo", "bolun", "koro", "korun", "dekho", "dekhun", "shuno", "shunun",
        "sunte", "paccho", "bolcho", "parbe", "paro", "bolte", "ekkhuni", "aacho", "achho",
        "বলো", "বলুন", "করো", "করুন", "দেখো", "দেখুন", "শোনো", "শুনুন", "শুনতে",
        "পাচ্ছ", "বলছ", "পারবে", "আছ", "এখুনি",
        # Hinglish & Hindi
        "batao", "bataiye", "karo", "kijiye", "dekho", "dekhye", "suno", "suniye",
        "aao", "aaiye", "karoge", "sakte", "sun", "rahe", "ho", "bolo",
        "बताओ", "बताइए", "करो", "कीजिए", "देखो", "देखिए", "सुनो", "सुनिए",
        "आओ", "आइए", "करोगे", "सकते", "सुन", "रहे", "हो"
    }

    # 3rd-person past tense & reporting verbs
    PAST_REPORTING_VERBS: Set[str] = {
        # English
        "told", "said", "mentioned", "wrote", "added", "merged", "pushed", "fixed",
        "sent", "shared", "worked", "built", "created", "decided", "discussed",
        "explained", "finished", "started", "left", "submitted", "handled", "informed",
        "updated", "flagged", "confirmed", "approved", "reported", "claimed", "reviewed",
        "raised", "tested", "committed", "closed", "assigned", "refactored", "resolved",
        "commented", "noted", "suggested", "clarified", "stated",
        # Banglish & Bengali past verbs
        "boleche", "koreche", "korechilo", "pathiyeche", "diyeche", "dekheche",
        "shesh", "chilo", "gelo", "bollo", "esheche", "baniyeche", "likheche",
        "বলেছে", "করেছে", "করেছিল", "পাঠিয়েছে", "দিয়েছে", "দেখেছে", "বলল", "গেল", "এসেছে",
        # Hinglish & Hindi past verbs (Note: exclude English article 'the'; keep 'tha', 'thi', 'थे')
        "kiya", "bola", "bataya", "bheja", "diya", "dekha", "kaha", "tha", "thi",
        "chala", "gaya", "gayi", "gaye", "liya", "daala", "banaya",
        "किया", "बोला", "बताया", "भेजा", "दिया", "कहा", "था", "थी", "थे", "गया", "लिया"
    }

    # Bengali 3rd-person morphological verb suffixes (detects agglutinative past/continuous)
    BENGALI_3RD_PERSON_VERB_SUFFIXES = (
        "che", "chen", "chilo", "echilo", "chilen", "lo", "elo", "ilo", "ache", "echen"
    )

    @classmethod
    def is_3rd_person_past(cls, token: str) -> bool:
        clean = re.sub(r"[^\w]", "", token, flags=re.UNICODE).lower()
        if not clean:
            return False
        if clean in cls.PAST_REPORTING_VERBS:
            return True
        # Morphological suffix heuristic for Banglish verbs (min length 4 to avoid false stems)
        if len(clean) >= 4 and clean.endswith(cls.BENGALI_3RD_PERSON_VERB_SUFFIXES):
            return True
        return False


class SemanticContextClassifier:
    """
    Tier 4 Phase 2: Morpho-Phonetic Vocative Context Engine.
    Distinguishes direct addressee vocatives from casual 3rd-person mentions.
    Integrates:
      1. Phonetic ambiguity risk profiling (jellyfish metaphone)
      2. Agglutinative clitic decomposition (Bengali/Hindi case & honorifics)
      3. Verbal aspect & person agreement analyzer (2nd person imperative vs 3rd person past)
      4. Universal Dependencies vocative tree heuristics
    """

    # Prepositional / indirect oblique markers ("with Alex", "about Alex", "from Alex", "Alex se")
    INDIRECT_PREPOSITIONS: Set[str] = {
        # English
        "with", "about", "from", "to", "by", "for", "against", "behind", "after",
        "alongside", "concerning", "regarding", "per", "via",
        # Banglish & Bengali
        "sathe", "theke", "diye", "jonno", "kache", "proshonge", "moto",
        "সাথে", "থেকে", "দিয়ে", "জন্য", "কাছে", "বিষয়ে", "দ্বারা",
        # Hinglish & Hindi
        "se", "saath", "baare", "liye", "taraf", "dwara",
        "से", "साथ", "बारे", "लिए", "द्वारा"
    }

    # Vocative cues & attention getters
    VOCATIVE_CUES: Set[str] = {
        "hey", "hi", "hello", "so", "ok", "okay",
        "ei", "arre", "are", "shuno", "suno", "kire", "oi", "dada", "bhai", "yaar",
        "please", "excuse",
        "এই", "আরে", "শোনো", "কিরে", "দাদা", "ভাই", "यार", "सुनो", "अरे"
    }

    def __init__(self, model_path: Optional[str] = None):
        self.onnx_session = None
        if model_path:
            try:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                self.onnx_session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
            except Exception:
                pass

    @staticmethod
    def _clean_token(token: str) -> str:
        return re.sub(r"[^\w]", "", token, flags=re.UNICODE).lower()

    def classify(self, sentence: str, target_name: str) -> IntentResult:
        """
        Classifies whether a sentence containing target_name is a direct address or casual mention.
        """
        raw_text = sentence.strip()
        if not raw_text or not target_name:
            return IntentResult(intent="ambiguous_call", is_direct_address=True, confidence=0.5)

        clean_target = self._clean_token(target_name)
        phonetic_risk = PhoneticAmbiguityProfiler.get_phonetic_risk(target_name)

        raw_tokens = raw_text.split()
        num_tokens = len(raw_tokens)

        # Locate target name while applying morphological clitic decomposition
        target_indices: List[int] = []
        morph_signals: List[Tuple[str, float]] = []

        for i, token in enumerate(raw_tokens):
            stem, sigs = MorphologicalDecomposer.decompose_target(token, clean_target)
            if stem == clean_target:
                target_indices.append(i)
                morph_signals.extend(sigs)

        # Substring search fallback for hyphenated/compound tokens
        if not target_indices:
            for i, token in enumerate(raw_tokens):
                clean_tok = self._clean_token(token)
                if clean_target in clean_tok:
                    target_indices.append(i)

        if not target_indices:
            return IntentResult(intent="ambiguous_call", is_direct_address=True, confidence=0.5)

        target_idx = target_indices[0]
        cleaned_words = [self._clean_token(w) for w in raw_tokens]

        signals: List[str] = []
        direct_score = 0.50

        # Apply morphological clitic signals from decomposition
        for sig_name, delta in morph_signals:
            signals.append(sig_name)
            direct_score += delta

        # 1. Isolated / Short Name Call ("Alex?", "Mayukh!")
        if num_tokens <= 2:
            # If name has high phonetic risk (e.g. 'Will', 'May'), require punctuation or mark as ambiguous
            if phonetic_risk >= 0.50 and "?" not in raw_text and "!" not in raw_text:
                signals.append(f"phonetic_risk_dampened (risk={phonetic_risk:.2f})")
                return IntentResult(
                    intent="ambiguous_call",
                    is_direct_address=True,
                    confidence=0.50,
                    signals=signals,
                    score_modifier=0.0
                )
            signals.append("isolated_name_call")
            return IntentResult(
                intent="direct_address",
                is_direct_address=True,
                confidence=0.92,
                signals=signals,
                score_modifier=0.15
            )

        # 2. Ergative & Oblique Postposition Markers (Hindi/Bengali: "Alex ne bola", "Alex se", "Alex ko", "Alex theke")
        has_postposition = False
        if target_idx + 1 < num_tokens:
            next_word = cleaned_words[target_idx + 1]
            if next_word in {"ne", "ने"}:
                signals.append(f"ergative_agent_marker ('{next_word}')")
                direct_score -= 0.60
                has_postposition = True
            elif next_word in {"se", "से", "dwara", "দ্বারা"}:
                signals.append(f"postposition_ablative_instrumental ('{next_word}')")
                direct_score -= 0.50
                has_postposition = True
            elif next_word in {"ko", "को"}:
                signals.append(f"dative_recipient_marker ('{next_word}')")
                direct_score -= 0.55
                has_postposition = True
            elif next_word in {"ka", "ki", "ke", "का", "की", "के"}:
                signals.append(f"genitive_marker ('{next_word}')")
                direct_score -= 0.45
                has_postposition = True
            elif next_word in {"theke", "sathe", "kache", "moto", "দ্বারা", "থেকে", "সাথে", "কাছে"}:
                signals.append(f"postposition_oblique ('{next_word}')")
                direct_score -= 0.45
                has_postposition = True

        # 3. Prepositional & Indirect Directive Reference ("with Alex", "about Alex", "ask Alex", "tell Alex")
        if target_idx > 0:
            prev_word = cleaned_words[target_idx - 1]
            if prev_word in self.INDIRECT_PREPOSITIONS:
                signals.append(f"prepositional_indirect_reference ('{prev_word}')")
                direct_score -= 0.45
            elif prev_word in {"ask", "tell", "told", "asking", "remind", "inform", "ping", "call"}:
                signals.append(f"indirect_directive_recipient ('{prev_word}')")
                direct_score -= 0.50

        # 4. Third-person Past Tense / Reporting Verbs immediately following or nearby
        if target_idx + 1 < num_tokens:
            next_word = cleaned_words[target_idx + 1]
            if AspectAgreementAnalyzer.is_3rd_person_past(next_word):
                signals.append(f"past_reporting_verb ('{next_word}')")
                direct_score -= 0.45

        # Check auxiliary past constructions: "Alex has merged", "Alex was saying", "Alex ne kaha"
        if target_idx + 2 < num_tokens:
            w1 = cleaned_words[target_idx + 1]
            w2 = cleaned_words[target_idx + 2]
            if (w1 in {"has", "was", "is", "had", "ne", "ने"}) and AspectAgreementAnalyzer.is_3rd_person_past(w2):
                signals.append(f"auxiliary_past_tense ('{w1} {w2}')")
                direct_score -= 0.50

        # Inverted passive voice check ("done by Alex", "fixed by Alex")
        if target_idx >= 2:
            p2 = cleaned_words[target_idx - 2]
            p1 = cleaned_words[target_idx - 1]
            if p1 in {"by", "দ্বারা", "se"} and AspectAgreementAnalyzer.is_3rd_person_past(p2):
                signals.append(f"passive_agent_construction ('{p2} {p1}')")
                direct_score -= 0.55

        # 4b. Modal Auxiliary Inversion check for phonetically ambiguous names ("Will this work?", "May I ask?")
        if target_idx == 0 and phonetic_risk >= 0.50 and target_idx + 1 < num_tokens:
            next_tok = cleaned_words[target_idx + 1]
            if next_tok in {"this", "that", "it", "i", "we", "they", "there", "the", "a", "an", "our", "my", "your", "any", "someone", "anyone"}:
                signals.append(f"modal_auxiliary_inversion ('{clean_target} {next_tok}')")
                direct_score -= 0.65

        # 5. Direct Vocative Punctuation & Position Heuristics
        # Leading vocative ("Alex, can you hear us?") - only if NOT marked by postpositions or casual clitics
        has_casual_clitic = any("morphology:genitive" in s or "morphology:accusative" in s for s in signals)
        has_comma = raw_tokens[target_idx].endswith(",") or raw_tokens[target_idx].endswith(":")
        
        # High phonetic risk names (Will, May) require a comma or non-modal grammar to claim leading vocative
        if target_idx == 0 and not has_postposition and not has_casual_clitic:
            if phonetic_risk < 0.50 or has_comma:
                signals.append("vocative_sentence_starter")
                direct_score += 0.25

        # Trailing comma after name token ("Alex, ...")
        raw_target = raw_tokens[target_idx]
        if raw_target.endswith(",") or raw_target.endswith(":") or raw_target.endswith("—"):
            signals.append("vocative_comma_separation")
            direct_score += 0.20

        # Trailing vocative at sentence end ("Can you hear us, Alex?")
        if target_idx == num_tokens - 1:
            signals.append("vocative_sentence_ender")
            direct_score += 0.20

        # 6. Vocative Cues preceding name ("Hey Alex", "Ei Alex", "Suno Alex")
        if target_idx > 0:
            prev_word = cleaned_words[target_idx - 1]
            if prev_word in self.VOCATIVE_CUES:
                signals.append(f"vocative_attention_cue ('{prev_word}')")
                direct_score += 0.30

        # 7. Second-Person Pronouns & Imperatives in clause
        # Look for second-person pronouns ("you", "tumi", "aap")
        has_2nd_person = any(w in AspectAgreementAnalyzer.SECOND_PERSON_PRONOUNS for w in cleaned_words)
        if has_2nd_person:
            signals.append("second_person_agreement")
            direct_score += 0.20

        # Look for direct imperative / action markers ("unmute", "bolo", "batao", "share")
        imperatives_found = [w for w in cleaned_words if w in AspectAgreementAnalyzer.IMPERATIVE_ACTION_VERBS]
        if imperatives_found:
            signals.append(f"imperative_action_verbs ({', '.join(imperatives_found[:3])})")
            direct_score += 0.25

        # 8. Question Mark Presence
        if "?" in raw_text:
            signals.append("direct_question")
            direct_score += 0.15

        # Final phonetic risk adjustment: if target name is highly ambiguous, apply conservative penalty
        if phonetic_risk >= 0.50 and "vocative_attention_cue" not in "".join(signals) and not has_2nd_person:
            signals.append(f"phonetic_ambiguity_penalty (-{phonetic_risk * 0.2:.2f})")
            direct_score -= (phonetic_risk * 0.20)

        confidence = float(np.clip(direct_score, 0.0, 1.0))

        if confidence >= 0.55:
            intent = "direct_address"
            is_direct = True
            modifier = 0.12
        elif confidence <= 0.40:
            intent = "casual_mention"
            is_direct = False
            modifier = -0.35
        else:
            intent = "ambiguous_call"
            is_direct = True
            modifier = 0.0

        return IntentResult(
            intent=intent,
            is_direct_address=is_direct,
            confidence=round(confidence, 3),
            signals=signals,
            score_modifier=round(modifier, 3)
        )
