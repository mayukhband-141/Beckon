let testSocket = null;
let micStream = null;
let micAudioCtx = null;
let micWorklet = null;
let micAnalyser = null;
let meterAnimFrame = null;
let isMicTesting = false;

document.addEventListener("DOMContentLoaded", () => {
  const nameInput = document.getElementById("canonical-name");
  const aliasesInput = document.getElementById("aliases");
  const sensitivitySelect = document.getElementById("sensitivity");
  const soundAlertCheckbox = document.getElementById("sound-alert");
  const chimeVolumeSlider = document.getElementById("chime-volume");
  const volLabel = document.getElementById("vol-label");
  const saveBtn = document.getElementById("save-btn");
  const statusMsg = document.getElementById("status-msg");

  const micToggleBtn = document.getElementById("mic-toggle-btn");
  const liveTranscriptEl = document.getElementById("live-transcript");
  const matchStatusArea = document.getElementById("match-status-area");
  const matchBadge = document.getElementById("match-badge");
  const aliasSuggestion = document.getElementById("alias-suggestion");
  const micStatusText = document.getElementById("mic-status-text");
  const meterBar = document.getElementById("meter-bar");

  const simInput = document.getElementById("sim-input");
  const simBtn = document.getElementById("sim-btn");
  const simResult = document.getElementById("sim-result");

  // Load saved settings
  chrome.storage.local.get([
    "canonical_name",
    "aliases",
    "sensitivity",
    "sound_alert_enabled",
    "chime_volume"
  ], (data) => {
    if (data.canonical_name) nameInput.value = data.canonical_name;
    if (data.aliases) {
      aliasesInput.value = Array.isArray(data.aliases) ? data.aliases.join(", ") : data.aliases;
    }
    if (data.sensitivity) sensitivitySelect.value = data.sensitivity;
    if (data.sound_alert_enabled !== undefined) soundAlertCheckbox.checked = data.sound_alert_enabled;
    if (data.chime_volume !== undefined) {
      chimeVolumeSlider.value = data.chime_volume;
      volLabel.textContent = Math.round(data.chime_volume * 100) + "%";
    }
  });

  chimeVolumeSlider.addEventListener("input", () => {
    volLabel.textContent = Math.round(chimeVolumeSlider.value * 100) + "%";
  });

  // Save Settings
  saveBtn.addEventListener("click", () => {
    const canonical_name = nameInput.value.trim() || "Alex";
    const aliases = aliasesInput.value
      .split(",")
      .map(s => s.trim())
      .filter(s => s.length > 0);
    const sensitivity = sensitivitySelect.value;
    const sound_alert_enabled = soundAlertCheckbox.checked;
    const chime_volume = parseFloat(chimeVolumeSlider.value);

    chrome.storage.local.set({
      canonical_name,
      aliases,
      sensitivity,
      sound_alert_enabled,
      chime_volume
    }, () => {
      // Broadcast config to daemon & background
      chrome.runtime.sendMessage({
        action: "CONFIG_UPDATE",
        config: {
          canonical_name,
          aliases,
          sensitivity
        }
      });

      statusMsg.style.display = "inline";
      setTimeout(() => {
        statusMsg.style.display = "none";
      }, 3000);
    });
  });

  // Init options test WebSocket connection to daemon
  function initTestSocket() {
    if (testSocket && (testSocket.readyState === WebSocket.OPEN || testSocket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    testSocket = new WebSocket("ws://127.0.0.1:8765");
    testSocket.binaryType = "arraybuffer";

    testSocket.onmessage = (e) => {
      try {
        if (typeof e.data === "string") {
          const msg = JSON.parse(e.data);

          if (msg.type === "transcript") {
            liveTranscriptEl.textContent = `"${msg.text}"`;
            checkAliasHarvest(msg.text, nameInput.value.trim());
          }

          if (msg.type === "alert") {
            matchStatusArea.style.display = "block";
            const scorePct = Math.round(msg.score * 100);
            matchBadge.className = "match-result-badge match-success";
            matchBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Detected '${msg.name}' (${scorePct}% match)`;

            // Test chime if audio is enabled
            if (soundAlertCheckbox.checked) {
              playTestChime(parseFloat(chimeVolumeSlider.value));
            }
          }

          if (msg.type === "test_evaluate_result") {
            simResult.style.display = "block";
            if (msg.matched) {
              const pct = Math.round(msg.score * 100);
              simResult.innerHTML = `<span style="color:#4ade80;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Match Detected!</span> Target: <strong>${msg.target_name}</strong> (Score: <strong>${pct}%</strong>, Cue Boost: +${msg.cue_boost})`;
            } else {
              simResult.innerHTML = `<span style="color:#94a3b8;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>No Match</span> (Score below threshold for this sensitivity level).`;
            }
          }
        }
      } catch (err) {
        console.error("Error processing daemon response:", err);
      }
    };
  }

  initTestSocket();

  // Test Chime Synthesizer
  function playTestChime(vol = 0.4) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      const now = ctx.currentTime;
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(vol, now);
      gain.connect(ctx.destination);

      const o1 = ctx.createOscillator();
      o1.frequency.setValueAtTime(587.33, now);
      o1.connect(gain);
      o1.start(now);
      o1.stop(now + 0.3);

      const o2 = ctx.createOscillator();
      o2.frequency.setValueAtTime(880.00, now + 0.1);
      o2.connect(gain);
      o2.start(now + 0.1);
      o2.stop(now + 0.45);

      setTimeout(() => ctx.close(), 600);
    } catch (_) {}
  }

  // Suggest adding spoken variations to aliases
  function checkAliasHarvest(transcript, primaryName) {
    const words = transcript.replace(/[^a-zA-Z0-9\s]/g, "").split(/\s+/);
    const existing = aliasesInput.value.toLowerCase().split(",").map(s => s.trim());
    existing.push(primaryName.toLowerCase());

    for (const w of words) {
      if (w.length > 2 && !existing.includes(w.toLowerCase())) {
        // If word is reasonably close to primary name
        if (w.toLowerCase().startsWith(primaryName.slice(0, 2).toLowerCase())) {
          aliasSuggestion.style.display = "block";
          aliasSuggestion.innerHTML = `
            <div style="font-size:12px; color:#cbd5e1; margin-bottom:4px;">Whisper heard: <strong>"${w}"</strong></div>
            <button id="add-alias-btn" class="btn btn-success">+ Add "${w}" to Aliases</button>
          `;
          document.getElementById("add-alias-btn").onclick = () => {
            const current = aliasesInput.value.trim();
            aliasesInput.value = current ? `${current}, ${w}` : w;
            aliasSuggestion.style.display = "none";
          };
          break;
        }
      }
    }
  }

  // Live Mic Toggle
  micToggleBtn.addEventListener("click", async () => {
    if (!isMicTesting) {
      await startMicTesting();
    } else {
      stopMicTesting();
    }
  });

  async function startMicTesting() {
    try {
      initTestSocket();
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      micAudioCtx = new AudioContext();

      // Analyser for VU Meter
      micAnalyser = micAudioCtx.createAnalyser();
      micAnalyser.fftSize = 256;
      const source = micAudioCtx.createMediaStreamSource(micStream);
      source.connect(micAnalyser);

      // Load Worklet to stream 16kHz PCM16 to daemon
      await micAudioCtx.audioWorklet.addModule(chrome.runtime.getURL("src/offscreen/pcm_processor.js"));
      micWorklet = new AudioWorkletNode(micAudioCtx, "pcm-downsample-processor");

      micWorklet.port.onmessage = (e) => {
        if (testSocket && testSocket.readyState === WebSocket.OPEN) {
          testSocket.send(e.data); // Binary PCM16 ArrayBuffer
        }
      };

      source.connect(micWorklet);

      isMicTesting = true;
      micToggleBtn.textContent = "Stop Mic Test";
      micToggleBtn.className = "btn btn-danger";
      micStatusText.textContent = "● Mic Active (Listening...)";
      micStatusText.style.color = "#22c55e";
      liveTranscriptEl.textContent = "Listening... say your name (e.g. 'Hey Alex, what do you think?')";

      updateVUMeter();

    } catch (err) {
      console.error("Mic access error:", err);
      alert("Could not access microphone: " + err.message);
    }
  }

  function updateVUMeter() {
    if (!isMicTesting || !micAnalyser) return;
    const dataArray = new Uint8Array(micAnalyser.frequencyBinCount);
    micAnalyser.getByteFrequencyData(dataArray);

    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const avg = sum / dataArray.length;
    const pct = Math.min(100, Math.round((avg / 128) * 100));
    meterBar.style.width = pct + "%";

    meterAnimFrame = requestAnimationFrame(updateVUMeter);
  }

  function stopMicTesting() {
    isMicTesting = false;
    cancelAnimationFrame(meterAnimFrame);
    meterBar.style.width = "0%";

    if (micWorklet) {
      micWorklet.disconnect();
      micWorklet = null;
    }
    if (micStream) {
      micStream.getTracks().forEach(t => t.stop());
      micStream = null;
    }
    if (micAudioCtx) {
      micAudioCtx.close();
      micAudioCtx = null;
    }

    micToggleBtn.textContent = "Start Mic Test";
    micToggleBtn.className = "btn btn-secondary";
    micStatusText.textContent = "Mic Idle";
    micStatusText.style.color = "#94a3b8";
  }

  // Simulation Sandbox
  simBtn.addEventListener("click", () => {
    const text = simInput.value.trim();
    if (!text) return;
    initTestSocket();

    if (testSocket && testSocket.readyState === WebSocket.OPEN) {
      testSocket.send(JSON.stringify({
        type: "test_evaluate",
        text: text
      }));
    } else {
      simResult.style.display = "block";
      simResult.innerHTML = `<span style="color:#ef4444;">Daemon is not currently connected. Please start daemon/main.py.</span>`;
    }
  });

  simInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      simBtn.click();
    }
  });
});
