# Tier 4 Machine Learning Architecture & Roadmap

This document outlines the advanced machine learning roadmap for **Beckon**, detailing the transition from heuristic string/phonetic matching to a hybrid **Acoustic Keyword Spotting (KWS)** and neural NLP architecture.

---

## Roadmap Overview

| Phase | Component | Technology | Primary Benefit | Status |
|---|---|---|---|---|
| **Phase 1** | **Acoustic Keyword Spotting (Option 1)** | ONNX Runtime + Log-Mel DSP (`scipy`/`numpy`) | Sub-200ms detection latency, <1% CPU, resilience to fast/muffled speech | **In Development** |
| **Phase 2** | **Directed-Address Context Classifier (Option 2)** | Quantized Multilingual MiniLM / DistilBERT | Replaces regex rules with semantic classification; zero false alarms on 3rd-person mentions | *Planned* |
| **Phase 3** | **Regional Accent & Fine-Tuning Harness (Option 3)** | PyTorch + HuggingFace Seq2Seq + CTranslate2 | Custom acoustic weights fine-tuned on South Asian & Banglish meeting datasets | *Planned* |

---

## Phase 1: Acoustic Keyword Spotting (KWS) Subsystem

### 1. Motivation
The default Beckon pipeline relies entirely on Whisper automatic speech recognition (ASR):
$$\text{Audio} \xrightarrow{\text{5s window}} \text{Whisper ASR} \xrightarrow{\text{1.5s latency}} \text{Transcript} \xrightarrow{\text{Rapidfuzz + Metaphone}} \text{Alert}$$

While accurate for structured speech, ASR-only triggering has three inherent limitations:
1. **Latency**: Whisper operates on chunks (typically 2 to 5 seconds). An alert cannot fire until the full chunk is transcribed.
2. **Phonetic Dropouts**: When names are spoken rapidly, whispered, or slurred during casual speech, Whisper's decoder may omit the name or substitute an ordinary dictionary word.
3. **CPU Load**: Running Whisper continuously every 500ms consumes noticeable CPU cycles on lower-tier machines.

### 2. Two-Stage Hybrid Architecture
Phase 1 introduces a **Dual-Engine Hybrid Pipeline**:

```
                       [Incoming 16kHz PCM Audio Stream]
                                       │
                     ┌─────────────────┴─────────────────┐
                     ▼                                   ▼
          ┌───────────────────────┐           ┌───────────────────────┐
          │   Audio Ring Buffer   │           │    Acoustic KWS       │
          │  (5.0s Rolling RAM)   │           │ (Log-Mel + ONNX Net)  │
          └──────────┬────────────┘           └──────────┬────────────┘
                     │                                   │ Real-time frame scoring
                     │                                   │ (<10ms per 80ms hop)
                     │                                   ▼
                     │                        [ Acoustic Hit Confirmed? ]
                     │                             /             \
                     │                           YES              NO
                     │                            │                │
                     │                            ▼                ▼
                     │                 ┌──────────────────┐   Continue streaming
                     │                 │ Low-Latency Flag │   idle state
                     │                 └─────────┬────────┘
                     │                           │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │   Whisper ASR Context     │
                     │  (Verification & Clauses) │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │    Catch-Up Summarizer    │
                     │    (Groq / Ollama / Raw)  │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                       [Alert Notification Sent]
```

### 3. DSP & Audio Feature Extraction
The incoming 16kHz mono audio is converted to **Log-Mel Filterbank Energies**:
- **Sample Rate**: 16,000 Hz
- **Window Size**: 25ms (`win_length = 400` samples) with Hann window
- **Hop Size**: 10ms (`hop_length = 160` samples)
- **Mel Filterbanks**: 80 triangular filters spanning 80 Hz to 7,600 Hz
- **Compression**: Natural log with stabilizer $\ln(\text{mel\_energy} + 10^{-6})$

This extraction is implemented in pure vectorized `numpy` + `scipy.signal` with zero heavy dependencies (no PyTorch, librosa, or torchaudio required).

### 4. Neural Network Architecture
The KWS model is an efficient **1D Temporal Convolutional + Pooling Network (TCN/CNN)** deployed via **ONNX Runtime**:
- **Input Shape**: `[batch_size, 80, time_steps]` (e.g. `1 x 80 x 98` for ~1.0 second of audio)
- **Layer 1**: Conv1D (kernel=3, filters=64, ReLU) + BatchNorm + MaxPool1D(2)
- **Layer 2**: Conv1D (kernel=3, filters=96, ReLU) + BatchNorm + MaxPool1D(2)
- **Layer 3**: Global Average Pooling
- **Output**: Sigmoid probability $[0.0, 1.0]$ representing wake-word acoustic presence.
- **Inference Time**: **< 5ms** on a single CPU core.

### 5. Fallback & Co-existence Strategy
- If `enable_kws = True` and a model is loaded, the fast-path triggers immediate low-latency notification and priorities transcription.
- If no custom acoustic weights exist or KWS is disabled in configuration, the system gracefully operates on the standard Whisper phonetic pipeline without interruption.
