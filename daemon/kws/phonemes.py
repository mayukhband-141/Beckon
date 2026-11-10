import re
from typing import List, Tuple, Dict
import numpy as np
import jellyfish

class PhoneticAcousticMapper:
    """
    Tier 4 Phase 4: Dynamic Phonetic-to-Acoustic Prototype Mapper.
    Translates arbitrary user names (English, Banglish, Hinglish, Bengali, Hindi)
    into sequences of acoustic spectral prototypes across 80 Mel frequency bands (16kHz).
    Enables zero-training, dynamic wake-word alignment via Dynamic Time Warping (DTW).
    """

    # 80-channel Mel filter frequency characteristics (approximate center indices):
    # Mel 0-15:   100Hz - 600Hz  (F0, Nasal murmur, Vowel F1 fundamental)
    # Mel 16-35:  600Hz - 1800Hz (Vowel F1/F2 region, sonorant transitions)
    # Mel 36-55: 1800Hz - 3800Hz (Vowel F2/F3 region, plosive bursts)
    # Mel 56-79: 3800Hz - 8000Hz (Sibilant frication /s/, /z/, /sh/, /ch/)

    PHONEME_PROTOTYPES: Dict[str, np.ndarray] = {}

    @classmethod
    def _init_prototypes(cls):
        if cls.PHONEME_PROTOTYPES:
            return

        def make_profile(low: float, mid_low: float, mid_high: float, high: float) -> np.ndarray:
            profile = np.zeros(80, dtype=np.float32)
            profile[0:16] = low
            profile[16:36] = mid_low
            profile[36:56] = mid_high
            profile[56:80] = high
            norm = np.linalg.norm(profile)
            return profile / norm if norm > 0 else profile

        # Vowels (high low/mid-low energy, distinct formants)
        cls.PHONEME_PROTOTYPES["AA"] = make_profile(0.8, 0.9, 0.4, 0.1)  # "ah" (father, Mayukh)
        cls.PHONEME_PROTOTYPES["AE"] = make_profile(0.7, 0.9, 0.7, 0.2)  # "ae" (cat, Alex)
        cls.PHONEME_PROTOTYPES["AH"] = make_profile(0.8, 0.7, 0.4, 0.1)  # "uh" (but, Sarah)
        cls.PHONEME_PROTOTYPES["EH"] = make_profile(0.6, 0.9, 0.6, 0.2)  # "eh" (bed, Alec)
        cls.PHONEME_PROTOTYPES["IY"] = make_profile(0.9, 0.4, 0.9, 0.3)  # "ee" (see, Ali)
        cls.PHONEME_PROTOTYPES["UW"] = make_profile(0.9, 0.5, 0.3, 0.1)  # "oo" (too, Mayukh)
        cls.PHONEME_PROTOTYPES["OW"] = make_profile(0.8, 0.7, 0.3, 0.1)  # "oh" (go)

        # Consonants - Sibilants & Fricatives (high frequency energy)
        cls.PHONEME_PROTOTYPES["S"]  = make_profile(0.1, 0.2, 0.6, 1.0)  # /s/ (Alex)
        cls.PHONEME_PROTOTYPES["Z"]  = make_profile(0.3, 0.3, 0.6, 0.9)  # /z/
        cls.PHONEME_PROTOTYPES["SH"] = make_profile(0.1, 0.3, 0.9, 0.8)  # /sh/ (Mayukh, Bengali)
        cls.PHONEME_PROTOTYPES["F"]  = make_profile(0.2, 0.4, 0.5, 0.7)  # /f/
        cls.PHONEME_PROTOTYPES["HH"] = make_profile(0.2, 0.5, 0.6, 0.5)  # /h/ (Mayukh)

        # Consonants - Nasals (concentrated low murmur)
        cls.PHONEME_PROTOTYPES["M"]  = make_profile(1.0, 0.4, 0.2, 0.05) # /m/ (Mayukh, Mark)
        cls.PHONEME_PROTOTYPES["N"]  = make_profile(0.9, 0.6, 0.3, 0.1)  # /n/
        cls.PHONEME_PROTOTYPES["NG"] = make_profile(0.9, 0.4, 0.2, 0.05) # /ng/

        # Consonants - Plosives / Stops (mid-high burst)
        cls.PHONEME_PROTOTYPES["K"]  = make_profile(0.2, 0.4, 0.9, 0.6)  # /k/ (Alex, Mayukh)
        cls.PHONEME_PROTOTYPES["G"]  = make_profile(0.4, 0.5, 0.8, 0.4)  # /g/
        cls.PHONEME_PROTOTYPES["T"]  = make_profile(0.2, 0.3, 0.8, 0.8)  # /t/
        cls.PHONEME_PROTOTYPES["D"]  = make_profile(0.4, 0.4, 0.7, 0.6)  # /d/
        cls.PHONEME_PROTOTYPES["P"]  = make_profile(0.3, 0.4, 0.6, 0.4)  # /p/
        cls.PHONEME_PROTOTYPES["B"]  = make_profile(0.5, 0.4, 0.5, 0.3)  # /b/

        # Liquids & Glides
        cls.PHONEME_PROTOTYPES["L"]  = make_profile(0.8, 0.8, 0.5, 0.2)  # /l/ (Alex)
        cls.PHONEME_PROTOTYPES["R"]  = make_profile(0.7, 0.7, 0.6, 0.3)  # /r/
        cls.PHONEME_PROTOTYPES["Y"]  = make_profile(0.8, 0.6, 0.8, 0.3)  # /y/ (Mayukh)
        cls.PHONEME_PROTOTYPES["W"]  = make_profile(0.9, 0.6, 0.3, 0.1)  # /w/ (Will)

    @classmethod
    def text_to_phonemes(cls, text: str) -> List[str]:
        """
        Converts a canonical name or alias string into a list of phoneme codes.
        Handles English, Banglish, and Hinglish transliterations.
        """
        clean = re.sub(r"[^\w]", "", text.strip()).upper()
        if not clean:
            return []

        # Common known names table for direct canonical decomposition
        KNOWN_NAMES = {
            "ALEX": ["AE", "L", "EH", "K", "S"],
            "ALEC": ["AE", "L", "EH", "K"],
            "ALEKS": ["AE", "L", "EH", "K", "S"],
            "ALEXANDER": ["AE", "L", "EH", "K", "S", "AE", "N", "D", "ER"],
            "MAYUKH": ["M", "AA", "Y", "UW", "K", "HH"],
            "MOYUKH": ["M", "OW", "Y", "UW", "K", "HH"],
            "SARAH": ["S", "EH", "R", "AH"],
            "SARA": ["S", "EH", "R", "AH"],
            "WILL": ["W", "IH", "L"],
            "MARK": ["M", "AA", "R", "K"],
            "ROB": ["R", "AA", "B"],
            "JOHN": ["JH", "AA", "N"],
            "RAHUL": ["R", "AA", "HH", "UW", "L"],
            "PRIYA": ["P", "R", "IY", "Y", "AA"],
            "ANANYA": ["AA", "N", "AA", "N", "Y", "AA"],
        }

        if clean in KNOWN_NAMES:
            return KNOWN_NAMES[clean]

        # Rule-based phonetic grapheme-to-phoneme synthesizer for arbitrary custom names
        cls._init_prototypes()
        phonemes = []
        i = 0
        n = len(clean)

        while i < n:
            sub2 = clean[i:i+2]
            if sub2 == "CH":
                phonemes.append("SH")
                i += 2
            elif sub2 == "SH":
                phonemes.append("SH")
                i += 2
            elif sub2 == "TH":
                phonemes.append("T")
                i += 2
            elif sub2 == "KH":
                phonemes.append("K")
                phonemes.append("HH")
                i += 2
            elif sub2 == "PH":
                phonemes.append("F")
                i += 2
            elif sub2 == "EE" or sub2 == "EA":
                phonemes.append("IY")
                i += 2
            elif sub2 == "OO":
                phonemes.append("UW")
                i += 2
            elif sub2 == "OU" or sub2 == "OW":
                phonemes.append("OW")
                i += 2
            else:
                char = clean[i]
                if char in "A":
                    phonemes.append("AE" if i == 0 else "AA")
                elif char in "E":
                    phonemes.append("EH")
                elif char in "I":
                    phonemes.append("IY")
                elif char in "O":
                    phonemes.append("OW")
                elif char in "U":
                    phonemes.append("UW")
                elif char in "Y":
                    phonemes.append("Y")
                elif char in "S":
                    phonemes.append("S")
                elif char in "Z":
                    phonemes.append("Z")
                elif char in "M":
                    phonemes.append("M")
                elif char in "N":
                    phonemes.append("N")
                elif char in "K" or char in "C" or char in "Q":
                    phonemes.append("K")
                elif char in "X":
                    phonemes.append("K")
                    phonemes.append("S")
                elif char in "T":
                    phonemes.append("T")
                elif char in "D":
                    phonemes.append("D")
                elif char in "P":
                    phonemes.append("P")
                elif char in "B":
                    phonemes.append("B")
                elif char in "L":
                    phonemes.append("L")
                elif char in "R":
                    phonemes.append("R")
                elif char in "H":
                    phonemes.append("HH")
                elif char in "W" or char in "V":
                    phonemes.append("W")
                i += 1

        return phonemes if phonemes else ["AA"]

    @classmethod
    def get_template_matrix(cls, name: str) -> np.ndarray:
        """
        Builds a [n_phonemes, 80] prototype trajectory matrix for a target name.
        """
        cls._init_prototypes()
        phonemes = cls.text_to_phonemes(name)
        matrices = []

        for p in phonemes:
            proto = cls.PHONEME_PROTOTYPES.get(p, cls.PHONEME_PROTOTYPES["AA"])
            matrices.append(proto)

        if not matrices:
            return np.ones((1, 80), dtype=np.float32) / np.sqrt(80)

        return np.vstack(matrices)
