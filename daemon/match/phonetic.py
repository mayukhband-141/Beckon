"""
daemon/match/phonetic.py  --  zero-shot phonetic name matcher for Beckon.

Pipeline
  enroll(name)  : G2P (multi-accent) -> IPA segments -> lexicon collision calibration
  match(words)  : cached token -> articulatory-weighted edit distance -> context fusion

Deps: panphon (required). phonemizer + espeak-ng (recommended G2P), wordfreq (recommended lexicon).
Without espeak a crude rule G2P is used (Latin script only) -- fine for tests, not for prod.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol, Sequence

import panphon

# ───────────────────────── G2P ─────────────────────────

class G2P(Protocol):
    def variants(self, name: str) -> list[str]: ...   # enrollment: several accents
    def phonemize(self, token: str) -> str: ...       # runtime: one cheap pronunciation


def _script(s: str) -> str:
    for ch in s:
        if ch.isalpha():
            return unicodedata.name(ch, "LATIN").split()[0]
    return "LATIN"


class EspeakG2P:
    """espeak-ng via phonemizer. Reads Latin romanizations with different language
    rule-sets => naturally different accent hypotheses for the same spelling."""
    ENROLL_VOICES = ("en-us", "en-gb", "hi", "bn", "es", "de")
    SCRIPT_VOICE = {"BENGALI": "bn", "DEVANAGARI": "hi", "CYRILLIC": "ru", "ARABIC": "ar",
                    "CJK": "cmn", "HIRAGANA": "ja", "KATAKANA": "ja", "HANGUL": "ko",
                    "TAMIL": "ta", "GREEK": "el"}

    def __init__(self, voices: Sequence[str] = ENROLL_VOICES):
        from phonemizer.backend import EspeakBackend  # noqa
        self._cls, self._voices, self._be = EspeakBackend, tuple(voices), {}

    def _run(self, lang: str, words: list[str]) -> list[str]:
        be = self._be.get(lang)
        if be is None:
            be = self._be[lang] = self._cls(lang, with_stress=False, language_switch="remove-flags")
        return be.phonemize(words, strip=True, njobs=1)

    def variants(self, name: str) -> list[str]:
        sc = _script(name)
        voices = [self.SCRIPT_VOICE[sc]] if sc in self.SCRIPT_VOICE else list(self._voices)
        out = {self._run(v, [name])[0] for v in voices}
        return [p for p in out if p]

    def phonemize(self, token: str) -> str:
        return self._run(self.SCRIPT_VOICE.get(_script(token), "en-us"), [token])[0]


class RuleG2P:
    """Zero-dependency fallback. Crude, Latin only."""
    _DI = [("kh", "kʰ"), ("gh", "gʰ"), ("sh", "ʃ"), ("ch", "tʃ"), ("th", "θ"), ("ph", "f"),
           ("ng", "ŋ"), ("oo", "u"), ("ee", "i"), ("ou", "aʊ"), ("ai", "aɪ"), ("ay", "eɪ"),
           ("ck", "k"), ("ll", "l"), ("ss", "s")]
    _SI = {"c": "k", "q": "k", "x": "ks", "j": "dʒ", "y": "j", "a": "a", "e": "e", "i": "i",
           "o": "o", "u": "u"}

    def variants(self, name: str) -> list[str]:
        return [self.phonemize(name)]

    def phonemize(self, token: str) -> str:
        if _script(token) != "LATIN":
            return ""
        w = unicodedata.normalize("NFKD", token.casefold())
        w = "".join(c for c in w if c.isalpha() and ord(c) < 128)
        if len(w) > 2 and w.endswith("e") and w[-2] not in "aeiouy":
            w = w[:-1]
        out, i = [], 0
        while i < len(w):
            for g, p in self._DI:
                if w.startswith(g, i):
                    out.append(p); i += len(g); break
            else:
                out.append(self._SI.get(w[i], w[i])); i += 1
        return "".join(out)


def default_g2p() -> G2P:
    try:
        return EspeakG2P()
    except Exception:
        return RuleG2P()


# ───────────────── articulatory distance ─────────────────

# Accent-driven confusions that are near-free (compared on base symbols).
_DISCOUNT = {frozenset(p) for p in [
    ("ʊ", "u"), ("ɪ", "i"), ("ə", "a"), ("ɐ", "a"), ("ʌ", "a"), ("ɑ", "a"), ("ɛ", "e"), ("ɔ", "o"),
    ("æ", "a"), ("v", "w"), ("ʈ", "t"), ("ɖ", "d"), ("θ", "t"), ("ð", "d"), ("x", "k"),
    ("ɾ", "r"), ("ɹ", "r"), ("ɽ", "r"), ("ʃ", "s"), ("tʃ", "ts"), ("ɡ", "g"), ("z", "s"),
]}
_WEAK = {"h", "ɦ", "ə", "ɐ", "ʔ"}


def _base(seg: str) -> str:
    return "".join(c for c in seg if unicodedata.category(c) not in ("Mn", "Lm", "Sk")) or seg


class PhonDist:
    ONSET = 1.5          # word-initial errors are rare in ASR -> weigh them up
    FEAT_SCALE = 8.0     # sum|Δfeature| / FEAT_SCALE, capped at 1

    def __init__(self):
        self.ft = panphon.FeatureTable()
        self._vec: dict[str, Optional[tuple]] = {}
        self._sub: dict[tuple[str, str], float] = {}

    def segs(self, ipa: str) -> tuple[str, ...]:
        return tuple(self.ft.ipa_segs(re.sub(r"[ˈˌ.\s‿_]", "", ipa)))

    def _v(self, s: str):
        if s not in self._vec:
            f = self.ft.fts(s)
            self._vec[s] = tuple(f.numeric()) if f else None
        return self._vec[s]

    def sub(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        k = (a, b) if a < b else (b, a)
        c = self._sub.get(k)
        if c is None:
            ba, bb = _base(a), _base(b)
            if ba == bb:
                c = 0.1
            elif frozenset((ba, bb)) in _DISCOUNT:
                c = 0.15
            else:
                va, vb = self._v(a), self._v(b)
                c = 1.0 if va is None or vb is None else min(
                    1.0, sum(abs(x - y) for x, y in zip(va, vb)) / self.FEAT_SCALE)
            self._sub[k] = c
        return c

    @staticmethod
    def indel(s: str, onset: bool) -> float:
        c = 0.3 if _base(s) in _WEAK else 0.7
        return c * (PhonDist.ONSET if onset else 1.0)

    def wed(self, a: tuple[str, ...], b: tuple[str, ...]) -> float:
        """Weighted edit distance normalised by the longer sequence, in [0, ~1]."""
        la, lb = len(a), len(b)
        if not la or not lb:
            return 1.0
        prev = [0.0] * (lb + 1)
        for j in range(1, lb + 1):
            prev[j] = prev[j - 1] + self.indel(b[j - 1], j == 1)
        for i in range(1, la + 1):
            cur = [prev[0] + self.indel(a[i - 1], i == 1)]
            for j in range(1, lb + 1):
                s = self.sub(a[i - 1], b[j - 1]) * (self.ONSET if i == j == 1 else 1.0)
                cur.append(min(prev[j] + self.indel(a[i - 1], i == 1),
                               cur[j - 1] + self.indel(b[j - 1], j == 1),
                               prev[j - 1] + s))
            prev = cur
        return min(1.0, prev[lb] / max(la, lb))


# ───────────────────────── matcher ─────────────────────────

_VOC_PRE = {"hey", "hi", "hello", "ok", "okay", "thanks", "thank", "yo", "so", "and", "right",
            "over", "to", "ask", "about", "है", "হ্যালো", "arre", "are", "shuno", "suno", "bolchi", "kire", "oi", "dada", "bhai", "yaar"}
_VOC_NEXT = {"can", "could", "would", "will", "do", "are", "what", "how", "any", "thoughts",
             "you", "did", "have", "should", "want", "koro", "bolo", "dekho", "paro", "parbe", "karo", "batao"}


@dataclass
class Tok:
    text: str
    norm: str
    prob: Optional[float] = None
    trail: str = ""
    lead: str = ""


@dataclass
class Hit:
    start: int
    end: int
    text: str
    score: float
    dist: float
    reasons: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def tokenize(text: str) -> list[Tok]:
    """Whitespace split + punctuation strip by Unicode category (keeps Indic matras intact)."""
    out = []
    for raw in text.split():
        a, b = 0, len(raw)
        while a < b and unicodedata.category(raw[a]).startswith("P"):
            a += 1
        while b > a and unicodedata.category(raw[b - 1]).startswith("P"):
            b -= 1
        core = raw[a:b]
        if core:
            out.append(Tok(core, _norm(core), None, raw[b:], raw[:a]))
    return out


def from_whisper(words: Iterable) -> list[Tok]:
    """faster-whisper Word objects (.word/.probability) or (text, prob) tuples."""
    toks = []
    for w in words:
        text, prob = (w.word, w.probability) if hasattr(w, "word") else w
        t = tokenize(text)
        if t:
            t[0].prob = prob
            toks.append(t[0])
    return toks


class PhoneticNameMatcher:
    def __init__(self, g2p: Optional[G2P] = None, *, soft: float = 0.30,
                 accept: float = 0.60, common_zipf: float = 3.5, len_slack: int = 2):
        self.g2p = g2p or default_g2p()
        self.pd = PhonDist()
        self.soft, self.accept, self.common_zipf, self.len_slack = soft, accept, common_zipf, len_slack
        self.forms: set[str] = set()
        self.prons: list[tuple[str, ...]] = []
        self.lex: dict[str, float] = {}
        self.collisions: list[tuple[str, float, float]] = []   # (word, zipf, dist) – diagnostics
        self._cache: dict[str, float] = {}

    # ---- enrollment ----
    def enroll(self, name: str, *, also_spelled: Iterable[str] = (),
               lexicon: Optional[Iterable[tuple[str, float]]] = None) -> None:
        """name: as the user types it. also_spelled: e.g. native-script spelling.
        lexicon: iterable of (word, zipf); defaults to wordfreq top-30k English if installed."""
        for n in (name, *also_spelled):
            self.forms.add(_norm(n))
            for ipa in self.g2p.variants(n):
                self._add_pron(ipa)
        if lexicon is None:
            lexicon = self._default_lexicon()
        self.lex = {w: z for w, z in lexicon}
        self._calibrate()

    def add_observed(self, asr_text: str) -> None:
        """Feed back what Whisper actually wrote for the user's name (voice enrollment / confirmed alerts)."""
        for t in tokenize(asr_text):
            self.forms.add(t.norm)
            self._add_pron(self.g2p.phonemize(t.norm))
        self._cache.clear()
        self._calibrate()

    def _add_pron(self, ipa: str) -> None:
        s = self.pd.segs(ipa) if ipa else ()
        if s and s not in self.prons:
            self.prons.append(s)

    @staticmethod
    def _default_lexicon():
        try:
            from wordfreq import top_n_list, zipf_frequency
            return [(w, zipf_frequency(w, "en")) for w in top_n_list("en", 30000)]
        except Exception:
            return []

    def _calibrate(self) -> None:
        """Find real words that sit inside the acceptance radius. Done once; also warms the cache."""
        self.collisions = []
        for w, z in self.lex.items():
            d = self.dist(w)
            if d <= self.soft and w not in self.forms:
                self.collisions.append((w, z, d))
        self.collisions.sort(key=lambda x: -x[1])

    # ---- distance (cached) ----
    def dist(self, token_norm: str) -> float:
        d = self._cache.get(token_norm)
        if d is None:
            ipa = self.g2p.phonemize(token_norm)
            segs = self.pd.segs(ipa) if ipa else ()
            d = 1.0
            for p in self.prons:
                if segs and abs(len(p) - len(segs)) <= self.len_slack:
                    d = min(d, self.pd.wed(p, segs))
            if len(self._cache) > 100_000:
                self._cache.clear()
            self._cache[token_norm] = d
        return d

    # ---- runtime ----
    def match(self, toks: Sequence[Tok] | str) -> list[Hit]:
        if isinstance(toks, str):
            toks = tokenize(toks)
        hits: list[Hit] = []
        n = len(toks)
        for i, t in enumerate(toks):
            cands = [(i, i, t.norm, t.prob)]
            if i + 1 < n and not t.trail and 2 <= len(t.norm) <= 6 and len(toks[i + 1].norm) <= 6:
                probs = [p for p in (t.prob, toks[i + 1].prob) if p is not None]
                cands.append((i, i + 1, t.norm + toks[i + 1].norm, min(probs) if probs else None))
            best = None
            for s, e, norm, prob in cands:
                h = self._score(toks, s, e, norm, prob)
                if h and (best is None or h.score > best.score):
                    best = h
            if best:
                hits.append(best)
        return hits

    def _score(self, toks, s, e, norm, prob) -> Optional[Hit]:
        text = " ".join(x.text for x in toks[s:e + 1])
        if norm in self.forms:
            return Hit(s, e, text, 1.0, 0.0, ["exact"])
        d = self.dist(norm)
        if d > self.soft:
            return None
        why = []
        phon = 1.0 - d / self.soft
        ev = 0.0
        prev = toks[s - 1].norm if s > 0 else ""
        nxt = toks[e + 1].norm if e + 1 < len(toks) else ""
        trail = toks[e].trail
        if prev in _VOC_PRE or any(c in trail for c in ",?!") or (s == 0 and nxt in _VOC_NEXT):
            ev += 0.30; why.append("vocative")
        if prob is not None and prob < 0.55:
            ev += 0.20; why.append(f"low_conf={prob:.2f}")
        if toks[s].text[:1].isupper() and s > 0:
            ev += 0.10; why.append("cap")
        common = self.lex.get(norm, 0.0) >= self.common_zipf
        w = 0.35 if common else 0.70
        if common:
            why.append("common_word")
        score = w * phon + ev
        if score < self.accept:
            return None
        return Hit(s, e, text, score, d, why)


# ───────────── Whisper conditioning (Q2) ─────────────

def whisper_kwargs(name: str, *, extra_names: Sequence[str] = ()) -> dict:
    """Pass as model.transcribe(audio, **whisper_kwargs(...)).
    - initial_prompt biases the decoder LM prior toward the spelling (canonical spelling only).
    - hotwords (faster-whisper >= 1.0.1) is prepended to the prompt; ignored if `prefix` is set.
    - word_timestamps gives per-word probability, which the matcher uses as evidence."""
    names = ", ".join((name, *extra_names))
    return dict(initial_prompt=f"Meeting participants: {names}.", hotwords=names,
                word_timestamps=True, beam_size=5, condition_on_previous_text=True)
