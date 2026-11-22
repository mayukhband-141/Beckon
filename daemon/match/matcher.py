import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
import jellyfish
from rapidfuzz import fuzz

@dataclass
class MatchResult:
    matched: bool
    detected_phrase: str
    target_name: str
    score: float
    context_sentence: str
    cue_boost: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    word_confidence: float = 1.0
    intent: str = "direct_address"
    intent_confidence: float = 1.0

class NameMatcher:
    GREETINGS_AND_CALLS = {
        # English
        "hey", "hi", "hello", "so", "okay", "ok", "thanks", "thank",
        "asking", "ask", "tell", "to", "with", "for", "yo",
        # Banglish & Bengali
        "ei", "arre", "are", "shuno", "suno", "bolchi", "kire", "oi", "dada",
        "এই", "আরে", "শোনো", "বলছি", "কিরে", "ওই", "দাদা",
        # Hinglish & Hindi
        "bhai", "yaar", "arey", "भाई", "यार", "अरे", "सुनो"
    }
    
    ACTION_WORDS = {
        # English
        "can", "could", "would", "will", "what", "how", "do", "did",
        "are", "have", "think", "mind", "share", "take", "unmute", "join",
        # Banglish & Bengali
        "koro", "bolo", "dekho", "paro", "parbe", "sunte", "paccho", "bolcho",
        "bolte", "korbe", "ekkhuni", "aacho", "achho",
        "করো", "বলো", "দেখো", "পারবে", "শুনতে", "পাচ্ছ", "বলছ", "করবে", "এখুনি", "আছ",
        # Hinglish & Hindi
        "karo", "batao", "karoge", "kar", "sakte", "kya", "sun", "rahe", "ho", "aao",
        "करो", "बताओ", "करोगे", "सकते", "क्या", "सुन", "रहे", "हो"
    }

    KNOWN_NAME_VARIANTS = {
        "mayukh": [
            "mayukh", "mayuk", "moyukh", "mayookh", "mayook", "myukh", "mayuq", "mayooq",
            "mayukha", "moyuk", "mayukh's", "mayuk's", "mayank", "mayur", "mio", "mayo",
            "ময়ূখ", "ময়ুখ", "মৈয়ুখ", "ময়ূখের", "ময়ুখের",
            "मयूख", "मयुक", "मयुख"
        ],
        "alex": [
            "alex", "alec", "aleks", "alexander", "alexa", "alex's",
            "অ্যালেক্স", "এলেক্স", "एलेक्स"
        ]
    }

    def __init__(self, names: List[str], threshold: float = 0.65, min_word_confidence: float = 0.15):
        self.names = [n.strip() for n in names if n.strip()]
        self.threshold = threshold
        self.min_word_confidence = min_word_confidence
        self.clean_names = [self._clean(n) for n in self.names]
        from daemon.match.intent_classifier import SemanticContextClassifier
        self.intent_classifier = SemanticContextClassifier()

        # Build expanded multi-script & pronunciation map
        self.expanded_map = {}
        self.phonetic_map = {}
        self.soundex_map = {}
        self.phonetic_keys = []
        for n in self.names:
            clean = self._clean(n)
            variants = {clean, n.lower()}
            if clean in self.KNOWN_NAME_VARIANTS:
                variants.update(self.KNOWN_NAME_VARIANTS[clean])
            # Auto-generate common phonetic variations
            if clean.endswith("h"):
                variants.add(clean[:-1])
            else:
                variants.add(clean + "h")
            if "oo" in clean:
                variants.add(clean.replace("oo", "u"))
            elif "u" in clean:
                variants.add(clean.replace("u", "oo"))
            if clean.startswith("ma"):
                variants.add("mo" + clean[2:])
            elif clean.startswith("mo"):
                variants.add("ma" + clean[2:])
            self.expanded_map[n] = list(variants)
            
            p_set = set()
            s_set = set()
            for v in variants:
                if v.isascii():
                    m = jellyfish.metaphone(v)
                    if m:
                        p_set.add(m)
                    sx = jellyfish.soundex(v)
                    if sx:
                        s_set.add(sx)
            self.phonetic_map[n] = p_set
            self.soundex_map[n] = s_set
            self.phonetic_keys.append(jellyfish.metaphone(clean) if clean.isascii() else "")

    @staticmethod
    def _clean(text: str) -> str:
        # Preserve Unicode alphanumeric characters and combining marks (Bengali vowel signs, viramas)
        import unicodedata
        chars = []
        for c in text:
            cat = unicodedata.category(c)
            if cat.startswith("L") or cat.startswith("N") or cat.startswith("M") or c.isspace():
                chars.append(c)
        return "".join(chars).lower().strip()

    @staticmethod
    def _extract_context_clause(text: str, detected_word: str) -> str:
        """Extract only the specific sentence/clause containing the detected name."""
        sentences = re.split(r'(?<=[.!?।\n])\s+', text.strip())
        clean_target = re.sub(r'[^\w\s]', '', detected_word, flags=re.UNICODE).lower().strip()

        for s in sentences:
            clean_s = re.sub(r'[^\w\s]', '', s, flags=re.UNICODE).lower()
            if " " in clean_target:
                if clean_target in clean_s:
                    return s.strip()
            else:
                if clean_target in clean_s.split():
                    return s.strip()

        return sentences[-1].strip() if sentences else text.strip()

    def evaluate_text(self, text: str, word_segments: Optional[List[dict]] = None) -> Optional[MatchResult]:
        """
        Evaluates a segment of transcribed text (and optional word-level timestamps)
        to detect if any enrolled name or variant is addressed.
        """
        if not text:
            return None

        # Clean words while keeping punctuation for question mark check
        raw_words = text.strip().split()
        if not raw_words:
            return None

        words_cleaned = [self._clean(w) for w in raw_words]
        best_match: Optional[MatchResult] = None
        highest_score = 0.0

        has_question = "?" in text

        # Test single words and 2-grams (for compound names or nicknames like "Alex B")
        for i, word in enumerate(words_cleaned):
            if not word:
                continue

            candidates = [
                (word, [i]),
            ]
            if i + 1 < len(words_cleaned):
                candidates.append((f"{word} {words_cleaned[i+1]}", [i, i+1]))

            for candidate_str, word_indices in candidates:
                # Word-level confidence filtering (Tier 1)
                cand_confidence = 1.0
                if word_segments:
                    cand_probs = [
                        word_segments[idx].get("probability", 1.0)
                        for idx in word_indices
                        if idx < len(word_segments)
                    ]
                    if cand_probs:
                        min_prob = min(cand_probs)
                        cand_confidence = sum(cand_probs) / len(cand_probs)
                        # Reject candidates where Whisper's confidence is too low (noise/hallucination)
                        if min_prob < self.min_word_confidence:
                            continue

                for target in self.names:
                    target_clean = self._clean(target)
                    variants = self.expanded_map.get(target, [target_clean])

                    # 1. Exact string or script variant match
                    if candidate_str == target_clean or candidate_str in variants:
                        base_score = 1.0
                    else:
                        # 2. Phonetic match (ASCII) - requiring matching initial character sound
                        cand_phonetic = jellyfish.metaphone(candidate_str) if candidate_str.isascii() else ""
                        target_phonetics = self.phonetic_map.get(target, set())

                        same_initial = bool(
                            candidate_str and target_clean and
                            candidate_str[0].lower() == target_clean[0].lower()
                        )

                        phonetic_hit = False
                        if same_initial and cand_phonetic:
                            if cand_phonetic in target_phonetics:
                                phonetic_hit = True
                            elif any(cand_phonetic.rstrip("H") == tp.rstrip("H") for tp in target_phonetics):
                                phonetic_hit = True
                            elif len(candidate_str) >= 4 and any(
                                abs(len(cand_phonetic) - len(tp)) <= 1 and
                                jellyfish.levenshtein_distance(cand_phonetic, tp) <= 1
                                for tp in target_phonetics
                            ):
                                phonetic_hit = True

                        # 3. Fuzzy string similarity against target and variants
                        best_fuzzy = max([fuzz.ratio(candidate_str, v) for v in variants] + [fuzz.ratio(candidate_str, target_clean)]) / 100.0

                        if phonetic_hit or best_fuzzy >= 0.82:
                            base_score = max(0.88, (best_fuzzy * 0.5) + 0.45)
                        else:
                            base_score = best_fuzzy * 0.90

                    # Soft scale base score if confidence is low
                    if cand_confidence < 0.40:
                        base_score *= max(0.85, cand_confidence)

                    # 4. Context cues
                    cue_boost = 0.0

                    # Prior word greeting/attention cue
                    prior_index = word_indices[0] - 1
                    if prior_index >= 0:
                        prior_word = words_cleaned[prior_index]
                        if prior_word in self.GREETINGS_AND_CALLS:
                            cue_boost += 0.08

                    # Subsequent word action/question cue
                    next_index = word_indices[-1] + 1
                    if next_index < len(words_cleaned):
                        next_word = words_cleaned[next_index]
                        if next_word in self.ACTION_WORDS:
                            cue_boost += 0.07

                    if has_question:
                        cue_boost += 0.05

                    # Third-person possessive penalty ("Alex's slide", "Mayukh's PR")
                    is_possessive = raw_words[word_indices[-1]].endswith(("'s", "’s"))
                    if is_possessive:
                        cue_boost -= 0.35

                    context_clause = self._extract_context_clause(text, candidate_str)
                    cand_base = candidate_str[:-2] if candidate_str.endswith(("'s", "’s")) else (
                        candidate_str[:-1] if candidate_str.endswith("s") and len(candidate_str) > 3 and not target_clean.endswith("s")
                        else candidate_str
                    )
                    intent_res = self.intent_classifier.classify(context_clause, cand_base)
                    if not intent_res.signals:
                        intent_res = self.intent_classifier.classify(context_clause, target_clean)

                    if is_possessive and intent_res.is_direct_address:
                        intent_res.is_direct_address = False

                    # Tier 4 Phase 2: Semantic Intent Modifier
                    final_score = min(1.0, max(0.0, base_score + cue_boost + intent_res.score_modifier))

                    # Suppress confirmed casual third-person references
                    if not intent_res.is_direct_address and final_score < 0.90:
                        continue

                    if final_score >= self.threshold and final_score > highest_score:
                        highest_score = final_score
                        
                        # Time range from word_segments if available
                        start_t, end_t = 0.0, 0.0
                        if word_segments and word_indices[0] < len(word_segments):
                            start_t = word_segments[word_indices[0]].get("start", 0.0)
                            end_idx = min(word_indices[-1], len(word_segments) - 1)
                            end_t = word_segments[end_idx].get("end", 0.0)

                        best_match = MatchResult(
                            matched=True,
                            detected_phrase=candidate_str,
                            target_name=target,
                            score=round(final_score, 3),
                            context_sentence=context_clause,
                            cue_boost=round(cue_boost + intent_res.score_modifier, 3),
                            start_time=start_t,
                            end_time=end_t,
                            word_confidence=round(cand_confidence, 3),
                            intent=intent_res.intent,
                            intent_confidence=intent_res.confidence
                        )

        return best_match

