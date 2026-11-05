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

    def __init__(self, names: List[str], threshold: float = 0.76, min_word_confidence: float = 0.40):
        self.names = [n.strip() for n in names if n.strip()]
        self.threshold = threshold
        self.min_word_confidence = min_word_confidence
        self.clean_names = [self._clean(n) for n in self.names]
        # Only compute ASCII metaphone if text is latin; otherwise store empty string
        self.phonetic_keys = [
            jellyfish.metaphone(n) if n.isascii() else ""
            for n in self.clean_names
        ]

    @staticmethod
    def _clean(text: str) -> str:
        # Preserve Unicode alphanumeric characters (Bengali, Devanagari, Latin) while stripping punctuation
        return re.sub(r"[^\w\s]", "", text, flags=re.UNICODE).lower().strip()

    @staticmethod
    def _extract_context_clause(text: str, detected_word: str) -> str:
        """Extract only the specific sentence/clause containing the detected name."""
        sentences = re.split(r'(?<=[.!?।\n])\s+', text.strip())
        clean_target = re.sub(r'[^\w\s]', '', detected_word, flags=re.UNICODE).lower()

        for s in sentences:
            clean_s = re.sub(r'[^\w\s]', '', s, flags=re.UNICODE).lower()
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

                for target, target_phonetic in zip(self.names, self.phonetic_keys):
                    target_clean = self._clean(target)

                    # 1. Exact string match
                    if candidate_str == target_clean:
                        base_score = 1.0
                    else:
                        # 2. Phonetic match (ASCII only)
                        cand_phonetic = jellyfish.metaphone(candidate_str) if candidate_str.isascii() else ""
                        phonetic_hit = bool(cand_phonetic and target_phonetic and cand_phonetic == target_phonetic)
                        
                        # 3. Fuzzy string similarity
                        fuzzy_ratio = fuzz.ratio(candidate_str, target_clean) / 100.0

                        if phonetic_hit:
                            # Strong bonus if phonetics match and fuzzy ratio is decent
                            base_score = max(0.85, (fuzzy_ratio * 0.5) + 0.45)
                        else:
                            base_score = fuzzy_ratio * 0.90

                    # Soft scale base score if confidence is mediocre
                    if cand_confidence < 0.65:
                        base_score *= max(0.75, cand_confidence)

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

                    # Third-person penalty ("Alex's slide", "about Alex")
                    if raw_words[word_indices[-1]].endswith("'s") or raw_words[word_indices[-1]].endswith("’s"):
                        cue_boost -= 0.12

                    final_score = min(1.0, max(0.0, base_score + cue_boost))

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
                            context_sentence=self._extract_context_clause(text, candidate_str),
                            cue_boost=round(cue_boost, 3),
                            start_time=start_t,
                            end_time=end_t,
                            word_confidence=round(cand_confidence, 3)
                        )

        return best_match

