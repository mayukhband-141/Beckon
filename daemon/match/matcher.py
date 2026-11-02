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

class NameMatcher:
    GREETINGS_AND_CALLS = {
        "hey", "hi", "hello", "so", "okay", "ok", "thanks", "thank",
        "asking", "ask", "tell", "to", "with", "for", "yo"
    }
    
    ACTION_WORDS = {
        "can", "could", "would", "will", "what", "how", "do", "did",
        "are", "have", "think", "mind", "share", "take", "unmute"
    }

    def __init__(self, names: List[str], threshold: float = 0.76):
        self.names = [n.strip() for n in names if n.strip()]
        self.threshold = threshold
        self.clean_names = [self._clean(n) for n in self.names]
        self.phonetic_keys = [jellyfish.metaphone(n) for n in self.clean_names]

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9\s]", "", text).lower().strip()

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

        # Test single words and 2-grams (for compound names or nicknames like "Mayukh da")
        for i, word in enumerate(words_cleaned):
            if not word:
                continue

            candidates = [
                (word, [i]),
            ]
            if i + 1 < len(words_cleaned):
                candidates.append((f"{word} {words_cleaned[i+1]}", [i, i+1]))

            for candidate_str, word_indices in candidates:
                for target, target_phonetic in zip(self.names, self.phonetic_keys):
                    target_clean = self._clean(target)

                    # 1. Exact string match
                    if candidate_str == target_clean:
                        base_score = 1.0
                    else:
                        # 2. Phonetic match
                        cand_phonetic = jellyfish.metaphone(candidate_str)
                        phonetic_hit = bool(cand_phonetic and cand_phonetic == target_phonetic)
                        
                        # 3. Fuzzy string similarity
                        fuzzy_ratio = fuzz.ratio(candidate_str, target_clean) / 100.0

                        if phonetic_hit:
                            # Strong bonus if phonetics match and fuzzy ratio is decent
                            base_score = max(0.85, (fuzzy_ratio * 0.5) + 0.45)
                        else:
                            base_score = fuzzy_ratio * 0.90

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

                    # Third-person penalty ("Mayukh's slide", "about Mayukh")
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
                            context_sentence=text,
                            cue_boost=round(cue_boost, 3),
                            start_time=start_t,
                            end_time=end_t
                        )

        return best_match

