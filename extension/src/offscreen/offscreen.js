let audioContext = null;
let mediaStream = null;
let workletNode = null;
let socket = null;
let wsUrl = "ws://127.0.0.1:8765";

let isExplicitlyClosed = false;
let reconnectTimer = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 8000;
let pingInterval = null;

let cachedConfig = null;
let cachedSpeaker = null;
let isCapturing = false;

// Preload persisted config from storage so initial WS connection immediately syncs
chrome.storage.local.get(["canonical_name", "aliases", "sensitivity", "groq_api_key", "ollama_url"], (data) => {
  if (data && data.canonical_name) {
    cachedConfig = {
      canonical_name: data.canonical_name,
      aliases: Array.isArray(data.aliases) ? data.aliases : (data.aliases ? data.aliases.split(",").map(s => s.trim()) : []),
      sensitivity: data.sensitivity || "balanced",
      groq_api_key: data.groq_api_key || "",
      ollama_url: data.ollama_url || ""
    };
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "config_update", ...cachedConfig }));
    }
  }
});

function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  isExplicitlyClosed = false;
  socket = new WebSocket(wsUrl);
  socket.binaryType = "arraybuffer";

  socket.onopen = () => {
    console.log("[Beckon Offscreen] WebSocket connected to daemon.");
    reconnectDelay = 1000;
    chrome.runtime.sendMessage({ type: "DAEMON_STATUS", connected: true }).catch(() => {});

    // Sync cached configuration if available
    if (cachedConfig) {
      socket.send(JSON.stringify({ type: "config_update", ...cachedConfig }));
    }
    if (cachedSpeaker) {
      socket.send(JSON.stringify({ type: "speaker_update", ...cachedSpeaker }));
    }

    // Start heartbeat
    clearInterval(pingInterval);
    pingInterval = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping", timestamp: Date.now() }));
      }
    }, 5000);
  };

  socket.onmessage = (event) => {
    try {
      if (typeof event.data === "string") {
        const data = JSON.parse(event.data);
        if (data.type === "alert") {
          console.log("[Beckon Offscreen] Forwarding name alert:", data);
          chrome.runtime.sendMessage({ type: "NAME_ALERT", alert: data }).catch(() => {});
        } else if (data.type === "transcript") {
          chrome.runtime.sendMessage({ type: "TRANSCRIPT_UPDATE", transcript: data }).catch(() => {});
        }
      }
    } catch (e) {
      console.error("[Beckon Offscreen] Error handling ws message:", e);
    }
  };

  socket.onclose = () => {
    clearInterval(pingInterval);
    chrome.runtime.sendMessage({ type: "DAEMON_STATUS", connected: false }).catch(() => {});
    
    if (!isExplicitlyClosed) {
      scheduleReconnect();
    }
  };

  socket.onerror = (err) => {
    console.warn("[Beckon Offscreen] WebSocket connection error (daemon might be offline).");
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  console.log(`[Beckon Offscreen] Attempting reconnect in ${reconnectDelay}ms...`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT_DELAY);
    connectWebSocket();
  }, reconnectDelay);
}

async function startAudioCapture(streamId) {
  try {
    isExplicitlyClosed = false;
    connectWebSocket();

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId
        }
      },
      video: false
    });

    audioContext = new AudioContext();

    // Route audio to local speaker destination so user still hears meeting audio
    const source = audioContext.createMediaStreamSource(mediaStream);
    source.connect(audioContext.destination);

    // Load AudioWorklet downsampler
    await audioContext.audioWorklet.addModule(chrome.runtime.getURL("src/offscreen/pcm_processor.js"));
    workletNode = new AudioWorkletNode(audioContext, "pcm-downsample-processor");

    workletNode.port.onmessage = (e) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(e.data); // Binary PCM16 ArrayBuffer
      }
    };

    source.connect(workletNode);
    isCapturing = true;
    console.log("[Beckon Offscreen] Audio capture and streaming active.");
    chrome.runtime.sendMessage({ type: "CAPTURE_STATUS", capturing: true }).catch(() => {});

  } catch (err) {
    console.error("[Beckon Offscreen] Failed to start audio capture:", err);
    chrome.runtime.sendMessage({ type: "CAPTURE_STATUS", capturing: false, error: err.message }).catch(() => {});
  }
}

function stopAudioCapture() {
  isCapturing = false;
  isExplicitlyClosed = true;

  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
  if (workletNode) {
    workletNode.disconnect();
    workletNode = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  if (socket) {
    socket.close();
    socket = null;
  }
  console.log("[Beckon Offscreen] Audio capture stopped.");
  chrome.runtime.sendMessage({ type: "CAPTURE_STATUS", capturing: false }).catch(() => {});
}

// Ensure initial connection attempt when offscreen document spawns
connectWebSocket();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "START_CAPTURE") {
    startAudioCapture(message.streamId);
    sendResponse({ status: "starting" });
  } else if (message.action === "STOP_CAPTURE") {
    stopAudioCapture();
    sendResponse({ status: "stopped" });
  } else if (message.action === "SPEAKER_UPDATE") {
    cachedSpeaker = {
      active_speaker: message.active_speaker,
      roster: message.roster
    };
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "speaker_update", ...cachedSpeaker }));
    }
  } else if (message.action === "CONFIG_UPDATE") {
    cachedConfig = message.config;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "config_update", ...cachedConfig }));
    }
  } else if (message.action === "CHECK_CONNECTION") {
    const isConnected = socket && socket.readyState === WebSocket.OPEN;
    sendResponse({ connected: isConnected, capturing: isCapturing });
  }
  return true;
});
