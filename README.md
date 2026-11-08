<div align="center">

# Beckon

**On-device meeting intelligence that alerts you the instant you're called — while silently suppressing casual mentions.**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](daemon/)
[![Android](https://img.shields.io/badge/Android-API%2026%2B%20(Target%2034)-green?logo=android)](android/)
[![Chrome Extension](https://img.shields.io/badge/Chrome-MV3-yellow?logo=googlechrome)](extension/)
[![Tests](https://img.shields.io/badge/Tests-100%25%20Passing-brightgreen)](eval/)

*Zero audio leaves your machine. Real-time sub-second acoustic alerts with contextual sentence verification and AI catch-up summaries.*

---

</div>

## Architecture Overview

Beckon runs as a **dual-stream hybrid pipeline**. Audio streamed from Google Meet (via Chrome Tab Capture) or the Android microphone is processed concurrently across an ultra-low latency acoustic path and a deep contextual STT verification path:

```
[ Google Meet Tab (Chrome) ]      [ Android Mic Capture ]
         │ (16kHz PCM16)                   │ (16kHz PCM16)
         └───────────────┬─────────────────┘
                         ▼
             [ Local Python Daemon ]
             │  • Zero-alloc Ring Buffer (60s)
             │  • Dynamic Client Identity Enrollment
             │
      ┌──────┴──────────────────────────────────────┐
      │                                             │
      ▼ (Fast-Path: < 250ms)                        ▼ (Context-Path: ~1.0s)
[ Tier 4: Acoustic KWS Engine ]             [ faster-whisper (int8 CPU) ]
  • 80-channel Log-Mel DSP (1.47ms)           • Silero VAD segmentation
  • Streaming acoustic scorer                 • Word-level confidence filter
  • Early-wake pipeline interrupt             • Context clause extraction
      │                                             │
      │                                             ▼
      │                             [ Morpho-Phonetic Vocative Engine ]
      │                               • Agglutinative clitic stripper (-er, -ke, -da)
      │                               • Modal homophone inversion guard ("Will this...")
      │                               • Ergative / Dative markers (ne, se, ko, dwara)
      │                               • Indic Unicode diacritic preservation
      │                                             │
      └──────────────────────┬──────────────────────┘
                             ▼
                [ Intent-Verified Alert Event ]
                │  • Direct address: Alert user!
                │  • Casual mention: Suppress false ding
                │
                ├──► [ Chrome HUD & In-Meeting Overlay ]
                ├──► [ Android Floating Pill & Haptic Alert ]
                └──► [ Optional: Tier 3 AI Catch-Up Summary (Groq / Ollama) ]
```

---

## Key Capabilities (Tiers 1–4)

### 1. Dual-Path Acoustic & Contextual Fusion (Tier 4)
* **$< 250\text{ms}$ Early Alert**: Zero-dependency 80-channel Log-Mel spectrogram filterbank computes acoustic similarity on CPU in **$1.47\text{ms}$**, triggering early pipeline wake before full transcription finishes.
* **Morpho-Phonetic Vocative Engine**: Replicates formal Universal Dependencies (`vocative` vs `nsubj` / `obl`) in **$0.065\text{ms}$** without neural transformer bloat.
  * **Agglutinative Clitics**: Decomposes attached case suffixes in South Asian languages (*Alex-er*, *Alex-ke*, *Mayukh-da*).
  * **Modal Homophone Inversion**: Distinguishes names from common verbs (*"Will this work?"* $\rightarrow$ suppressed; *"Hey Will, can you review?"* $\rightarrow$ alert).
  * **Ergative & Dative Oblique Filtering**: Suppresses 3rd-person reports (*"Alex ne bola tha"*, *"Alex ko bolo"*, *"fixed by Alex"*).

### 2. Zero-Cloud Privacy & Dynamic Client Identity (Tiers 1–2)
* **Local Processing**: Audio is processed entirely in RAM on your machine via `faster-whisper` (int8 quantized CPU). No audio streams ever leave your hardware.
* **Dynamic Client Enrollment**: Target names, phonetic aliases, and sensitivity levels are configured dynamically from the Chrome extension or Android companion app over authenticated WebSockets. No restarting or editing `.env` files required.
* **Word Confidence Gating**: Filters out low-probability hallucinations during background babble or noisy environments.

### 3. AI Catch-Up Summaries (Tier 3)
* When your name is called while you were context-switching, Beckon extracts the preceding 30–60 seconds of conversational context and condenses it into a single clean summary line (e.g. *"Sarah is asking for your sign-off on the staging database migration"*).
* Powered by Groq's free cloud API (`Llama 3.1 8B`) or local on-device `Ollama`. Only short transcript snippets are sent — never audio.

---

## Performance & Benchmark Metrics

Evaluated on the 78-sample multi-party meeting corpus ([`eval/data/vocative_corpus.jsonl`](eval/data/vocative_corpus.jsonl)) across English, Banglish, Hinglish, Bengali script, and Devanagari Hindi:

| Metric | Target Budget | Measured Performance | Verification Suite |
| :--- | :---: | :---: | :--- |
| **Acoustic KWS Evaluation** | $\le 15.0\text{ ms}$ | **$1.47\text{ ms}$** | [`eval/benchmark_kws.py`](eval/benchmark_kws.py) |
| **Vocative Engine Latency** | $\le 2.0\text{ ms}$ | **$0.065\text{ ms}$** ($65.5\mu\text{s}$) | [`eval/benchmark_intent_corpus.py`](eval/benchmark_intent_corpus.py) |
| **Direct Address Recall** | $\ge 95.0\%$ | **$100.0\%$** ($39/39$) | Multilingual meeting corpus |
| **Casual Mention Suppression** | $\ge 95.0\%$ | **$100.0\%$** ($39/39$ suppressed) | 3rd-person & homophone suite |
| **RAM Overhead for NLP** | $< 100\text{ MB}$ | **$0\text{ MB}$** (Stdlib + NumPy + Jellyfish) | In-process execution |

---

## Getting Started

### Prerequisites
* Python 3.10+
* Google Chrome (for Chrome Tab Capture) or Android 8.0+ (for Android Mic Capture)

### 1. Set Up the Local Python Daemon

```powershell
# Clone the repository
git clone https://github.com/mayukhband-141/Beckon.git
cd Beckon

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS / Linux

# Install dependencies
pip install -r daemon/requirements.txt
```

Create your local `.env` configuration (or copy from [`.env.example`](.env.example)):
```bash
cp .env.example .env
```

Start the daemon:
```powershell
python -m daemon.main
```
The daemon will launch on `ws://127.0.0.1:8765`.

---

### 2. Set Up the Chrome Extension

1. Open Google Chrome and go to `chrome://extensions/`.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the [`extension/`](extension/) directory.
4. Click the Beckon toolbar icon:
   * Verify the daemon status indicates **Connected** (green dot).
   * Enter your name and phonetic variants (e.g. `Alex`, `Alec`, `Alexander`).
   * (Optional) Enter your free Groq API key for AI Catch-Up Summaries.
5. In any Google Meet call (`meet.google.com`), click **Start Listening**.

---

### 3. Set Up the Android Companion App

1. Download the pre-built `beckon.apk` from the latest **GitHub Actions Artifacts** build, or build it locally via Android Studio:
   ```bash
   cd android
   ./gradlew assembleDebug
   ```
2. Install the APK on your phone and grant **Microphone** and **Display over other apps** permissions.
3. In the Beckon app settings:
   * Enter your PC's local IP address (e.g., `192.168.1.100:8765`).
   * Set your target name and aliases.
4. Tap **Start Listening**. A compact floating status widget will appear, and your phone will buzz with haptic alerts whenever your name is addressed in the room or on speakerphone.

---

## Configuration Reference

All settings can be configured via environment variables in `.env` or passed as CLI arguments to `daemon/main.py`:

| Environment Variable | CLI Flag | Default | Description |
| :--- | :--- | :---: | :--- |
| `BECKON_HOST` | `--host` | `0.0.0.0` | Daemon WebSocket host address |
| `BECKON_PORT` | `--port` | `8765` | Daemon WebSocket listening port |
| `BECKON_AUTH_TOKEN` | `--token` | `""` | Optional shared secret for client authentication |
| `BECKON_MODEL` | `--model` | `small` | Faster-Whisper model size (`tiny`, `base`, `small`, `medium`) |
| `BECKON_LANGUAGES` | `--languages` | `en,bn,hi` | Active speech transcription languages |
| `BECKON_MIN_WORD_CONFIDENCE`| `--confidence`| `0.40` | Minimum word probability threshold to prevent hallucinations |
| `BECKON_ENABLE_KWS` | `--enable-kws` | `true` | Enables Tier 4 Acoustic Keyword Spotting fast path |
| `BECKON_KWS_THRESHOLD` | `--kws-thresh` | `0.65` | Sensitivity threshold for acoustic trigger |
| `BECKON_GROQ_API_KEY` | `--groq-key` | `""` | Optional Groq key for Tier 3 summaries (or passed dynamically from client) |

---

## Running Test Suites

Verify all acoustic, linguistic, and pipeline components locally:

```powershell
# Run NameMatcher & confidence filter tests
python -m daemon.tests.test_matcher

# Run Acoustic KWS feature extraction & engine tests
python -m daemon.tests.test_kws

# Run Morpho-Phonetic Vocative Context tests
python -m daemon.tests.test_intent_classifier

# Run 78-sample multilingual benchmark corpus
python -m eval.benchmark_intent_corpus

# Run sub-15ms DSP profiler
python -m eval.benchmark_kws
```

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
