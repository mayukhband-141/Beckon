import re
from dataclasses import dataclass, field
from typing import List, Optional, Set
import numpy as np

@dataclass
class IntentResult:
    intent: str               # "direct_address", "casual_mention", "ambiguous_call"
    is_direct_address: bool   # True = Should alert; False = Should suppress
    confidence: float         # 0.0 to 1.0
    signals: List[str] = field(default_factory=list)
    score_modifier: float = 0.0

class SemanticContextClassifier:
    """
    Tier 4 Phase 2: Directed-Address vs Casual 3rd-Person Mention Classifier.
    Evaluates whether the speaker is actively calling / addressing the user
    vs casually talking ABOUT them in third-person past tense or reference.
    Supports English, Banglish, Hinglish, Bengali, and Devanagari Hindi.
    """

    # Prepositional / indirect references ("with Alex", "about Alex", "from Alex")
    INDIRECT_PREPOSITIONS: Set[str] = {
        # English
        "with", "about", "from", "to", "by", "for", "against", "behind", "after",
        "alongside", "concerning", "regarding", "per",
        # Banglish & Bengali
        "sathe", "theke", "diye", "jonno", "kache", "proshonge",
        "সাথে", "থেকে", "দিয়ে", "জন্য", "কাছে", "বিষয়ে",
        # Hinglish & Hindi
        "se", "saath", "baare", "liye", "taraf",
        "से", "साथ", "बारे", "लिए"
    }

    # Third-person past tense / reporting verbs ("Alex told me", "Alex pushed", "Alex boleche")
    PAST_AND_REPORTING_VERBS: Set[str] = {
        # English
        "told", "said", "mentioned", "wrote", "added", "merged", "pushed", "fixed",
        "sent", "shared", "worked", "built", "created", "decided", "discussed",
        "explained", "finished", "started", "left", "submitted", "handled",
        # Banglish & Bengali
        "boleche", "koreche", "korechilo", "pathiyeche", "diyeche", "dekheche",
        "shesh", "chilo", "gelo", "bollo",
        "বলেছে", "করেছে", "করেছিল", "পাঠিয়েছে", "দিয়েছে", "দেখেছে", "বলল", "গেল",
        # Hinglish & Hindi
        "kiya", "bola", "bataya", "bheja", "diya", "dekha", "kaha", "tha", "chala",
        "किया", "बोला", "बताया", "भेजा", "दिया", "कहा"
    }

    # Direct address inquiries & imperatives ("can you", "are you able", "bolo", "ekkhuni")
    DIRECT_CALL_MARKERS: Set[str] = {
        # English
        "can", "could", "would", "will", "are", "do", "did", "have", "please",
        "unmute", "join", "share", "take", "present", "hear", "listen",
        # Banglish & Bengali
        "ekkhuni", "bolo", "koro", "dekho", "sunte", "paccho", "bolcho", "bolte",
        "parbe", "paro", "aacho", "achho", "thik", "shuno", "suno", "unmute",
        "এখুনি", "বলো", "করো", "দেখো", "শুনতে", "পাচ্ছ", "বলছ", "পারবে", "আছ", "শোনো",
        # Hinglish & Hindi
        "batao", "karo", "karoge", "sakte", "sun", "rahe", "ho", "aao", "dekho",
        "बताओ", "करो", "करोगे", "सकते", "सुन", "रहे", "हो"
    }

    # Direct vocative attention getters ("hey", "arre", "ei", "suno")
    VOCATIVE_CUES: Set[str] = {
        "hey", "hi", "hello", "so", "ok", "okay",
        "ei", "arre", "are", "shuno", "suno", "kire", "oi", "dada", "bhai", "yaar",
        "এই", "আরে", "শোনো", "কিরে", "দাদা", "ভাই", "यार", "सुनो"
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

        raw_words = raw_text.split()
        cleaned_words = [self._clean_token(w) for w in raw_words]
        clean_target = self._clean_token(target_name)

        # Locate target name index in sentence
        target_indices = [i for i, w in enumerate(cleaned_words) if w == clean_target]
        if not target_indices:
            # Check substring match for compound names
            for i, w in enumerate(cleaned_words):
                if clean_target in w:
                    target_indices.append(i)

        if not target_indices:
            return IntentResult(intent="ambiguous_call", is_direct_address=True, confidence=0.5)

        target_idx = target_indices[0]
        num_words = len(cleaned_words)

        signals = []
        direct_score = 0.5

        # 1. Isolated / Short Name Call ("Alex?", "Mayukh!")
        if num_words <= 2:
            signals.append("isolated_name_call")
            return IntentResult(
                intent="direct_address",
                is_direct_address=True,
                confidence=0.92,
                signals=signals,
                score_modifier=0.15
            )

        # 2. Possessive Reference Check ("Alex's PR", "Alex's laptop", "Alex-er")
        raw_target_word = raw_words[target_idx]
        if raw_target_word.endswith("'s") or raw_target_word.endswith("’s") or raw_target_word.lower().endswith("er"):
            signals.append("possessive_third_person")
            direct_score -= 0.50

        # 3. Prepositional Indirect Reference ("with Alex", "about Alex", "from Alex")
        if target_idx > 0:
            prev_word = cleaned_words[target_idx - 1]
            if prev_word in self.INDIRECT_PREPOSITIONS:
                signals.append(f"prepositional_indirect_reference ('{prev_word}')")
                direct_score -= 0.45

        # 4. Third-person Past Tense / Reporting Verbs immediately following name
        # e.g., "Alex merged the PR", "Alex boleche", "Alex told Sarah"
        if target_idx + 1 < num_words:
            next_word = cleaned_words[target_idx + 1]
            if next_word in self.PAST_AND_REPORTING_VERBS:
                signals.append(f"past_tense_reporting_verb ('{next_word}')")
                direct_score -= 0.45

            # Hindi/Urdu/Bengali ergative / postposition marker ("Alex ne bola", "Alex er kache")
            elif next_word in {"ne", "ने"}:
                signals.append(f"ergative_agent_marker ('{next_word}')")
                direct_score -= 0.60

        # Also check next 2 words for reporting patterns like "Alex has merged" / "Alex was talking" / "Alex ne bola"
        if target_idx + 2 < num_words:
            next_word = cleaned_words[target_idx + 1]
            next_next = cleaned_words[target_idx + 2]
            if (next_word in {"has", "was", "is", "had", "ne", "ने"}) and (next_next in self.PAST_AND_REPORTING_VERBS):
                signals.append(f"auxiliary_past_tense ('{next_word} {next_next}')")
                direct_score -= 0.50

        # 5. Direct Vocative Leading Position ("Alex, can you hear us?")
        if target_idx == 0:
            signals.append("vocative_sentence_starter")
            direct_score += 0.25

        # 6. Vocative Cues preceding name ("Hey Alex", "Ei Alex", "Suno Alex")
        if target_idx > 0:
            prev_word = cleaned_words[target_idx - 1]
            if prev_word in self.VOCATIVE_CUES:
                signals.append(f"vocative_attention_cue ('{prev_word}')")
                direct_score += 0.30

        # 7. Action / Inquiry Markers in clause ("Alex, please unmute", "Alex ekkhuni join koro")
        direct_markers_found = [w for w in cleaned_words if w in self.DIRECT_CALL_MARKERS]
        if direct_markers_found:
            signals.append(f"direct_action_markers ({', '.join(direct_markers_found[:3])})")
            direct_score += 0.25

        # 8. Question Mark Presence
        if "?" in raw_text:
            signals.append("direct_question")
            direct_score += 0.15

        # Final score bounding
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
