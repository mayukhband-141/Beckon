# Beckon : laze around or work on something while we are on guard to notice the BECKONING

> On-device background meeting assistant that detects when your name is called in Google Meet, alerts you instantly, tells you who called you, and shows what was just asked.

---

## Architecture Overview

```
[ Google Meet Tab ]
        │
(chrome.tabCapture)
        ▼
[ Chrome Extension MV3 ] ── PCM16 16kHz WebSocket ──► [ Local Python Daemon ]
  - Offscreen AudioWorklet                               - 60s Ring Buffer
  - Active Speaker DOM reader                            - faster-whisper (int8 CPU)
  - Alert Overlay & Transcript                           - Phonetic + Fuzzy Matcher
                                                         - Event Dispatcher
```

---

## 1. Quickstart: Running the Local Daemon

The Python daemon runs locally and processes audio in real time on CPU.

### Activate Virtual Environment
```powershell
.\.venv\Scripts\activate
```

### Start the Daemon
```powershell
python daemon\main.py --name "Mayukh" --aliases "Mayuk" "Moyukh" "Mayukha" --model "base" --sensitivity "balanced"
```

The daemon will listen on `ws://127.0.0.1:8765`.

---

## 2. Quickstart: Loading the Chrome Extension

1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Toggle **Developer mode** ON (top right corner).
3. Click **Load unpacked** (top left corner).
4. Select the `extension/` folder inside this repository:
   ```
   C:\Users\MAYUKH\Downloads\MYDEN-proj\Beckon\extension
   ```
5. Click on the extension icon in Chrome:
   - Ensure the daemon indicator shows **Connected** (green dot).
   - Click **Settings & Enrollment** to adjust name variants or sensitivity.

---

## 3. Testing in Google Meet

1. Join any Google Meet call (`meet.google.com`).
2. Click the Beckon extension icon in your toolbar and press **"Start Listening"**.
3. When someone says: *"Hey Mayukh, what do you think?"*, Beckon will:
   - Trigger a floating in-meeting overlay banner at the top-right.
   - Display the active speaker's name.
   - Highlight the sentence just asked.
   - Provide a collapsible viewer with the rolling transcript from the last 45 seconds.

