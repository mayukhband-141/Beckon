# Project Plan: "Beckon" (working title)

> A background app / browser extension that listens to meeting audio, detects when **your name** is said, and tells you **who said it** and **what was just asked**.

Status: Planning · Version: 0.1 · Date: 2026-11-01

---

## 1. Vision and Problem

People zone out, multitask, or sit in long meetings (and noisy or multi-time-zone calls). When someone says their name, they get caught off guard: "Sorry, could you repeat that?"

**NameAlert** watches the meeting audio on-device, fires an instant alert when your name is called, shows who called you, and gives a short catch-up of the last 30-60 seconds so you can answer confidently.

### Goals
- Detect the user's name (and aliases) in live meeting audio with high recall and very few false alarms.
- Alert within ~1.5 s of the name being spoken.
- Identify the speaker (who called you) where possible.
- Show a rolling transcript so the user knows what was asked.
- **Process everything locally.** No audio leaves the device.

### Non-goals (for now)
- Recording or storing meetings.
- Full meeting-notes / summarization product (maybe later as an add-on).
- Native mobile meeting-audio capture (see Section 7, mobile is a companion, not a core listener).
- Speaker-identity biometrics or voice cloning.

---

## 2. Key Decisions

| # | Decision | Reason |
|---|----------|--------|
| D1 | **Do not match raw audio samples** (waveform/MFCC/DTW templates). | Breaks across voices, accents, codecs, and noise. |
| D2 | **Speech-to-text + phonetic name matching**, with the user's recordings used for *enrollment/biasing*, not as the matcher. | Far more robust to who is speaking. |
| D3 | **STT engine: faster-whisper** (CTranslate2). | 4x faster than openai-whisper at similar accuracy, int8 on CPU, built-in Silero VAD, supports `hotwords` / `initial_prompt` for name biasing, word timestamps. |
| D4 | **faster-whisper cannot run in the browser**, so the architecture is a **local companion service (daemon)**; the extension is a thin audio-capture + UI client. | faster-whisper is Python/CTranslate2 (native). No WASM build. |
| D5 | **Desktop-first.** Mobile is a companion (notifications / remote alerts), not a listener. | OS restrictions on capturing other apps' audio (Section 7). |
| D6 | Start with **Google Meet in Chrome**, then Teams/Zoom web, then desktop clients. | One platform keeps the MVP small. |
| D7 | Speaker attribution via **DOM active-speaker** first, **diarization** later. | DOM is cheap and accurate; diarization is heavy but platform-independent. |

---

## 3. Architecture

```
 ┌──────────────────────────┐        PCM16 16 kHz        ┌────────────────────────────────┐
 │ Chrome Extension (MV3)   │ ─────── WebSocket ───────► │ Local Daemon (Python)          │
 │  - tabCapture            │   ws://127.0.0.1:PORT      │  - Ring buffer (60 s)          │
 │  - Offscreen doc +       │   (token-authenticated)    │  - VAD (Silero via faster-     │
 │    AudioWorklet resample │                            │    whisper vad_filter)         │
 │  - Content script:       │ ◄──── JSON events ──────── │  - faster-whisper (int8)       │
 │    active speaker, roster│   {mention, speaker,       │  - Name matcher (phonetic +    │
 │  - Overlay UI / toast    │    transcript, score}      │    fuzzy + context cues)       │
 └──────────────────────────┘                            │  - Alert dispatcher            │
                                                         └───────────────┬────────────────┘
 ┌──────────────────────────┐                                            │
 │ Desktop shell (Phase 3)  │ ◄── same daemon, system-audio loopback ────┤
 │  Tauri tray app          │                                            │
 └──────────────────────────┘                                            │
 ┌──────────────────────────┐   optional, opt-in push (no audio,         │
 │ Mobile companion (Ph. 4) │ ◄─ only "X called you at 10:42") ──────────┘
 └──────────────────────────┘
```

### 3.1 Components

**A. Local daemon (core, Python)**
- Receives audio frames (extension or system loopback).
- Maintains a 60-second ring buffer in memory only.
- Runs faster-whisper on sliding windows, runs name matching, emits events.
- Exposes a localhost WebSocket + small HTTP API (health, config).
- Packaged as a single binary (PyInstaller / Nuitka), started by the desktop shell or by the extension through Native Messaging.

**B. Chrome extension (Manifest V3)**
- `chrome.tabCapture` (via offscreen document) captures the meeting tab's audio.
- AudioWorklet downsamples to 16 kHz mono PCM16 and streams to the daemon.
- Content script reads the **active speaker tile** and **participant list** from the Meet DOM.
- Overlay shows: "**Priya** said your name · [last 45 s transcript]".
- Options page: enrollment, aliases, sensitivity, snooze/focus mode.

**C. Desktop shell (Phase 3)**
- Tauri (Rust + web UI) tray app: start/stop, status, settings, notifications.
- System-audio capture for non-browser clients (Zoom/Teams desktop).

**D. Mobile companion (Phase 4)**, see Section 7.

---

## 4. Detection Pipeline (faster-whisper)

### 4.1 Flow
1. **Capture** audio -> 16 kHz mono float32.
2. **Chunking:** sliding window of ~4-6 s, hop ~1 s (overlap avoids cutting names in half).
3. **VAD gate:** skip windows with no speech (`vad_filter=True`, tuned `min_silence_duration_ms`).
4. **Transcribe** with faster-whisper, biasing toward the user's names.
5. **Match** words/n-grams against the name profile (Section 4.3).
6. **De-duplicate:** merge overlapping windows using word timestamps; cooldown (e.g., 10 s) after an alert.
7. **Alert** + attach speaker + last 30-60 s of transcript.

### 4.2 faster-whisper configuration (starting point)
```python
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
# GPU: WhisperModel("small", device="cuda", compute_type="float16")

segments, info = model.transcribe(
    audio_window,                 # numpy float32, 16 kHz
    language="en",                # or None for auto; fix it for speed/accuracy
    beam_size=1,                  # greedy for latency; try 3-5 for accuracy tests
    vad_filter=True,
    vad_parameters={"min_silence_duration_ms": 300},
    word_timestamps=True,
    condition_on_previous_text=False,   # avoids hallucination loops in streaming
    initial_prompt="Meeting participants: Saurav, Priya, Anirban.",
    hotwords="Saurav Sourav",           # bias toward user's name + variants
)
```

**Model selection (benchmark in Phase 0, don't guess):**
| Model | Use | Notes |
|---|---|---|
| `tiny` / `base` (int8) | Low-end laptops | Fast, but weak on names/accents. |
| `small` (int8) | **Default candidate** | Best accuracy/latency balance on CPU. |
| `distil-small.en` / `distil-large-v3` | English-only, faster | Check accent performance. |
| `medium` / `large-v3` | Users with NVIDIA GPU | Optional "high accuracy" mode. |

Latency budget (target): capture 0.25 s + window wait ~1 s + inference <0.7 s + UI <0.1 s ≈ **<1.5-2 s**. If inference can't keep up, reduce window size, use a smaller model, or use `beam_size=1`.

### 4.3 Name matching
Build a **name profile** at enrollment:
- Canonical name + aliases/nicknames (e.g., "Saurav", "Sourav", "Saurabh", "Sau").
- Phonetic keys: Double Metaphone, plus G2P phoneme sequence (`g2p_en` / `phonemizer`).
- Common mis-transcriptions harvested from the user's own recordings run through faster-whisper (what does Whisper *actually* output for this name?). This step matters a lot.

Match score = weighted mix of:
- Exact / alias hit (highest weight)
- Phonetic key equality
- Phoneme edit distance (`rapidfuzz`)
- Fuzzy string ratio

**Context cues** (reduce false positives for common-word names like "Will", "Mark", "Hope"):
- Preceded by greeting/address: "hey", "hi", "so", "okay", "thanks".
- Followed by a question/request: "can you", "could you", "what do you think", question prosody (`?` in text).
- At sentence start/end, or after a pause (word-timestamp gap > 300 ms).
- Name in third person ("Sourav's report") should score lower than direct address, where possible.

User-tunable **sensitivity** slider maps to the score threshold. Provide "strict / balanced / sensitive".

### 4.4 Optional fast gate (later)
A tiny wake-word model (openWakeWord) trained on the user's name could run continuously at near-zero CPU and wake faster-whisper only when likely. Evaluate in Phase 2 if CPU usage is a problem.

---

## 5. Enrollment Flow (where the "audio sample" idea lives)

1. User types name, spelling variants, and nicknames.
2. User records the name 3-5 times (normal voice, quick, with a different intonation).
3. App runs faster-whisper on the recordings -> collects the *transcribed variants* -> adds to alias list (user can review and remove).
4. App generates TTS pronunciations (several accents) -> run through faster-whisper -> more variants.
5. App builds phonetic keys and the `hotwords` / `initial_prompt` string.
6. **Test screen:** user says the name and sees detection live; adjust sensitivity.

Recordings stay on the device, encrypted at rest (OS keychain-protected key), deletable at any time.

---

## 6. Speaker Attribution ("who is calling me")

| Method | Phase | Pros | Cons |
|---|---|---|---|
| DOM active-speaker tile (Meet/Teams/Zoom web) | 1 | Accurate, near-zero compute | Breaks when platforms change UI; web only |
| Timing correlation (who unmuted/started speaking just before the name) | 1-2 | Good fallback | Heuristic |
| Diarization (pyannote / ECAPA embeddings) + map clusters to names | 3 | Platform-independent, works for desktop apps | Heavy; mapping cluster -> name needs roster hints |

Policy: if confidence is low, show "Someone" rather than a wrong name. A wrong attribution is worse than none.

---

## 7. Mobile: The Real Constraints

**Short answer:** there is no clean module/API that lets a normal mobile app listen to a meeting running in another app. Mobile will be a *companion*, not the listener.

### Android
- `AudioPlaybackCapture` (Android 10+, via `MediaProjection`) can capture other apps' audio, **but** it only captures certain usages (media/game/unknown) and apps can opt out. **Voice-call / VoIP audio (what Zoom, Meet, Teams use) is generally not capturable.**
- Mic capture works but only hears the room (and only your side unless on speaker); needs a **foreground service** with a microphone type and a persistent notification (Android 11+ restrictions on background mic).
- Running faster-whisper on-device: not available (it's CTranslate2/Python). You'd use whisper.cpp / Sherpa-ONNX instead, a separate engine and a separate accuracy-tuning effort.

### iOS
- No system-audio capture of other apps. `ReplayKit` broadcast extensions can receive app audio during a screen broadcast, but with a **~50 MB memory limit**, user-initiated start, and VoIP audio caveats, so it's unreliable for running STT.
- Background mic use is heavily restricted and visible to the user.
- App Store review is strict about continuous listening.

### Viable mobile strategies (pick in order)
1. **Companion app (recommended first):** the desktop daemon sends an opt-in push ("Priya called you - 10:42") to your phone/watch. No audio is sent, only an event. Great when you step away from the desk but keep the meeting running.
2. **Meeting-bot / platform-integration route (later, cloud):** a bot or SDK joins the meeting (Zoom Meeting SDK, Teams bot, Meet add-on) and processes audio server-side. Works for mobile attendees, but **breaks the "100% local" promise**, needs consent UX, hosting cost, and per-platform approval. Treat as a separate product tier.
3. **Phone-as-listener (experimental):** phone mic on speaker next to the laptop/phone playing the call. Low quality; ship only as "beta".

**Decision:** no native mobile listening in v1. Revisit after desktop traction.

---

## 8. Tech Stack

| Layer | Choice |
|---|---|
| STT | faster-whisper (CTranslate2), int8 CPU / float16 CUDA |
| VAD | Silero VAD (bundled in faster-whisper) |
| Name matching | `rapidfuzz`, `jellyfish`/`metaphone`, `g2p_en` or `phonemizer` |
| Daemon | Python 3.11+, `asyncio`, `websockets`, `numpy`, packaged with PyInstaller/Nuitka |
| Extension | Manifest V3, TypeScript, offscreen document, AudioWorklet |
| Desktop shell | Tauri (Rust) + web UI; daemon as a sidecar |
| System audio capture | Windows: WASAPI loopback (`pyaudiowpatch`); macOS: ScreenCaptureKit (13+) or BlackHole fallback; Linux: PipeWire/PulseAudio monitor |
| Diarization (Phase 3) | pyannote.audio or SpeechBrain ECAPA |
| Storage | Local encrypted JSON/SQLite; OS keychain for key |
| Backend (minimal) | Auth, license, update feed. **No audio.** |
| CI | GitHub Actions (build, sign, notarize, release) |

### Suggested repo layout
```
nameAlert/
├─ daemon/            # Python core
│  ├─ app/            # ws server, ring buffer, pipeline
│  ├─ stt/            # faster-whisper wrapper, windowing
│  ├─ match/          # phonetic, fuzzy, context cues
│  ├─ speaker/        # DOM events, diarization (later)
│  └─ tests/
├─ extension/         # MV3 (TS)
│  ├─ background/  offscreen/  content/  options/  overlay/
├─ desktop/           # Tauri shell (Phase 3)
├─ mobile/            # Companion (Phase 4)
├─ eval/              # datasets, labeling tool, benchmark scripts
├─ docs/
└─ plan.md
```

---

## 9. Phased Roadmap

### Phase 0: Validation and Prototype (Weeks 1-2)
**Goal:** prove detection works on real audio before building any UI.
- [ ] Interview 15-20 target users (remote workers, ADHD/inattentive meeting-goers, non-native speakers, people in noisy or multi-time-zone calls). Validate pain and willingness to pay.
- [ ] Collect 8-10 hours of consented meeting audio (varied accents, mic quality). Hand-label every name mention with timestamps (labeling script in `eval/`).
- [ ] Python prototype: audio file -> faster-whisper -> fuzzy/phonetic matcher -> detections.
- [ ] Benchmark model sizes (tiny/base/small/distil) x CPU/GPU: **recall, false alarms/hour, latency, CPU%, RAM**.
- [ ] Test `hotwords` / `initial_prompt` impact on recall.
- [ ] Confirm `tabCapture` on Meet works in an MV3 offscreen document and a WebSocket to localhost is allowed.

**Exit criteria:** recall >= 85% and < 3 false alarms/hour on the offline set with `small` int8 on a mid-range laptop; interviews show clear demand. If not, adjust approach before Phase 1.

### Phase 1: MVP, Meet + Daemon (Weeks 3-8)
- [ ] Daemon: live streaming pipeline (windowing, dedupe, cooldown), WebSocket API, config.
- [ ] Extension: tab capture, resampling, WebSocket client, overlay alert, rolling transcript.
- [ ] Enrollment flow + test screen (Section 5).
- [ ] DOM active-speaker detection for Google Meet.
- [ ] Installer for the daemon (Win + macOS first) with first-run model download and checksum verification.
- [ ] Private beta with 10-20 users; in-app feedback button ("false alarm" / "missed me") that stores only a **local** note plus an optional user-submitted 10 s clip.

**Exit criteria:** recall >= 90%, < 1 false alarm/hour in beta, median latency < 2 s, CPU < 15% on target hardware.

### Phase 2: Hardening (Weeks 9-12)
- [ ] Teams web + Zoom web DOM adapters.
- [ ] Alias manager, per-meeting sensitivity, snooze / focus mode, sound options.
- [ ] Noise/accent tuning; evaluate optional wake-word gate to cut CPU.
- [ ] Crash handling, auto-restart, daemon health UI, self-update.
- [ ] Latency-only telemetry (opt-in, no audio, no transcripts).

### Phase 3: Desktop App (Weeks 13-20)
- [ ] Tauri tray app wrapping the daemon.
- [ ] System-audio capture (WASAPI / ScreenCaptureKit / PipeWire) for Zoom/Teams desktop and others.
- [ ] Diarization-based speaker attribution + roster mapping.
- [ ] Auto-start, meeting detection, notification center integration.
- [ ] Code signing, macOS notarization, Windows SmartScreen reputation.

### Phase 4: Mobile Companion + Launch (Weeks 21-28)
- [ ] Companion app (iOS/Android): opt-in push events from desktop daemon via end-to-end encrypted relay (events only).
- [ ] Pricing, landing page, Chrome Web Store listing, privacy policy, docs, support flow.
- [ ] Public launch.

### Later / Option Tier
- Server-side meeting-bot tier for mobile attendees (explicit consent, separate privacy terms).
- LLM catch-up summary of the last 60 s (local small model or opt-in cloud).
- Multi-language support (Hindi/Hinglish tests, multilingual Whisper models).
- Team/admin plan.

---

## 10. Evaluation Plan

**Dataset:** consented real meetings plus synthetic mixes (clean speech + noise + codec simulation: Opus at low bitrates, packet loss).

**Metrics**
| Metric | Target (MVP) |
|---|---|
| Recall (name mentions caught) | >= 90% |
| False alarms | < 1 per meeting-hour |
| Alert latency (p50 / p95) | < 1.5 s / < 3 s |
| CPU (typical laptop, in meeting) | < 15% |
| RAM (daemon) | < 1 GB (small int8) |
| Speaker attribution accuracy (when shown) | >= 90%; otherwise show "Someone" |
| Activation | >= 60% of installs get a correct alert in first meeting |

**Slices to report separately:** accent (Indian English, US, UK, other), noise level, name type (common word vs distinctive), 1-on-1 vs large meeting, mic vs system audio.

**Regression gate:** every pipeline change reruns the benchmark in CI; block merges that drop recall or raise false alarms past thresholds.

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Name mis-transcription (esp. Indian names, accents) | Missed alerts | Alias harvesting from enrollment, `hotwords`, phonetic matching, user-reviewed alias list |
| Common-word names | False alarms | Context cues, sensitivity levels, cooldown |
| Whisper hallucination on silence/noise | False alarms | VAD gate, `condition_on_previous_text=False`, ignore low-confidence/no-speech segments |
| CPU/battery drain | Users disable app | int8, smallest adequate model, VAD gating, optional wake-word gate, "battery saver" mode |
| Model download size (~100-500 MB) | Install friction | Lazy download with progress, choose model by hardware detection |
| Platform DOM changes | Speaker attribution breaks | Adapter pattern per platform, remote-updatable selectors, diarization fallback, monitoring |
| Chrome Web Store review (audio capture) | Delay | Clear justification, privacy policy, minimal permissions, demo video |
| Localhost daemon security | Other sites/processes could connect | Bind 127.0.0.1 only, random per-install auth token, origin checks, native messaging for pairing |
| Mobile limitations | Feature gap | Companion strategy (Section 7); don't promise mobile listening |
| Competitors adding "mention alerts" (Zoom/Teams/Otter) | Differentiation | Cross-platform, local/private, catch-up context, speed |

---

## 12. Privacy, Security, and Legal

- **No audio or transcripts leave the device** (core product). Ring buffer in RAM only; nothing written to disk by default.
- Voice enrollment samples stored locally, encrypted; one-click delete.
- Any telemetry is opt-in and contains no audio/text (latency, crash counts).
- Recording/consent laws vary by jurisdiction. Even though you don't record, you *process* others' speech, so get legal review on product wording and consent/notice recommendations (e.g., a suggestion to disclose use in meetings where required).
- Review meeting-platform ToS for audio capture and DOM reading.
- Compliance: India DPDP Act, GDPR (data minimisation, transparency, deletion), Chrome Web Store User Data Policy.
- Security: signed binaries and updates, checksum-verified model downloads, dependency scanning, no remote code execution paths.

---

## 13. Team, Cost, Timeline

**Team (lean):** 1 audio/ML engineer (daemon, models, eval), 1 full-stack/extension + desktop engineer, part-time designer, part-time legal/privacy advisor.

**Costs:** mostly developer time. Inference is on the user's device, so there is no per-minute cloud bill. Other costs: code-signing certificates (Win + Apple Developer account), Chrome Web Store fee, small backend for auth/updates, legal review.

**Timeline summary:** validation (2 wk) -> extension+daemon MVP (6 wk) -> hardening (4 wk) -> desktop app (8 wk) -> mobile companion + launch (8 wk) ≈ **28 weeks**.

---

## 14. Monetization

- **Free:** 1 platform, 1 name, basic alert.
- **Pro ($4-8/mo):** all platforms, multiple aliases, catch-up transcript, desktop app, mobile push.
- **Team (later):** admin controls, shared deployment, SSO.
- Optional add-ons: LLM catch-up summaries, server-side bot tier.

---

## 15. Open Questions

1. Primary audience: general remote workers, or accessibility-first (ADHD, hearing, non-native speakers)?
2. Languages at launch: English only, or Hindi/Hinglish too?
3. Is requiring a local daemon install acceptable for the target users, or must v1 be browser-only? (If browser-only is mandatory, we'd need whisper.cpp WASM / Transformers.js instead of faster-whisper, with lower accuracy.)
4. Minimum supported hardware (CPU-only laptops with 8 GB RAM?).
5. Do we want a server-side bot tier at all, given it conflicts with the privacy promise?

---

## 16. Next Actions (this week)

1. Set up repo and `eval/` folder; write the labeling script.
2. Record or collect 5-10 consented meetings and label name mentions.
3. Install `faster-whisper`; run `small` int8 on the samples; log recall / false alarms / latency.
4. Build a 100-line prototype: file -> faster-whisper (with `hotwords`) -> phonetic matcher -> printed detections.
5. Verify MV3 `tabCapture` + offscreen AudioWorklet + `ws://127.0.0.1` on Google Meet.
6. Schedule the first 5 user interviews.