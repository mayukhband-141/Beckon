let isCapturing = false;
let currentTab = null;

document.addEventListener("DOMContentLoaded", async () => {
  const nameInput = document.getElementById("name-input");
  const toggleBtn = document.getElementById("toggle-btn");
  const stopBtn = document.getElementById("stop-btn");
  const idleView = document.getElementById("idle-view");
  const activeView = document.getElementById("active-view");
  const activeNamesDisplay = document.getElementById("active-names-display");
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const offlineBanner = document.getElementById("offline-banner");
  const settingsBtn = document.getElementById("settings-btn");

  // Get active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tab;

  // Load saved target names
  chrome.storage.local.get(["canonical_name", "aliases", "isListening"], (data) => {
    let combinedNames = [];
    if (data.canonical_name) combinedNames.push(data.canonical_name);
    if (data.aliases && Array.isArray(data.aliases)) {
      combinedNames.push(...data.aliases);
    }
    
    // Deduplicate
    combinedNames = [...new Set(combinedNames)];
    if (combinedNames.length > 0) {
      nameInput.value = combinedNames.join(", ");
    } else {
      nameInput.value = "Alex";
    }

    if (data.isListening) {
      setCapturingState(true, nameInput.value);
    }
  });

  // Query engine connection & capture status
  chrome.runtime.sendMessage({ action: "CHECK_CONNECTION" }, (res) => {
    if (res && res.connected) {
      setEngineStatus(true);
      if (res.capturing) {
        setCapturingState(true, nameInput.value);
      }
    } else {
      checkEngineSocket();
    }
  });

  function checkEngineSocket() {
    const ws = new WebSocket("ws://127.0.0.1:8765");
    ws.onopen = () => {
      setEngineStatus(true);
      ws.close();
    };
    ws.onerror = () => {
      setEngineStatus(false);
    };
  }

  function setEngineStatus(online) {
    if (online) {
      statusDot.className = "status-dot online";
      statusText.textContent = "Engine Ready";
      offlineBanner.style.display = "none";
    } else {
      statusDot.className = "status-dot";
      statusText.textContent = "Offline";
      offlineBanner.style.display = "block";
    }
  }

  function setCapturingState(capturing, namesString) {
    isCapturing = capturing;
    if (capturing) {
      idleView.style.display = "none";
      activeView.className = "listening-box active";
      activeNamesDisplay.textContent = `"${namesString || nameInput.value}"`;
    } else {
      idleView.style.display = "block";
      activeView.className = "listening-box";
    }
  }

  function parseNames(raw) {
    const list = raw
      .split(/[,;\n]+/)
      .map(s => s.trim())
      .filter(s => s.length > 0);
    
    if (list.length === 0) {
      return { canonical: "Alex", aliases: [] };
    }
    return {
      canonical: list[0],
      aliases: list.slice(1)
    };
  }

  async function handleStart() {
    const rawText = nameInput.value.trim() || "Alex";
    const { canonical, aliases } = parseNames(rawText);

    // Save and sync to engine
    chrome.storage.local.set({
      canonical_name: canonical,
      aliases: aliases
    });

    chrome.runtime.sendMessage({
      action: "CONFIG_UPDATE",
      config: {
        canonical_name: canonical,
        aliases: aliases
      }
    });

    if (!currentTab || !currentTab.url || currentTab.url.startsWith("chrome://") || currentTab.url.startsWith("edge://") || currentTab.url.startsWith("chrome-extension://")) {
      alert("Please switch to an active web tab with audio (e.g. YouTube, Google Meet, podcasts), then click Start.");
      return;
    }

    toggleBtn.disabled = true;
    toggleBtn.textContent = "Connecting...";

    chrome.runtime.sendMessage({
      action: "START_LISTENING",
      tabId: currentTab.id
    }, (res) => {
      toggleBtn.disabled = false;
      toggleBtn.textContent = "Start Listening";
      if (res && res.success) {
        setCapturingState(true, rawText);
        chrome.storage.local.set({ isListening: true });
      } else {
        alert("Could not start listening: " + (res?.error || "Local engine is not responding. Please make sure python daemon/main.py is running."));
      }
    });
  }

  function handleStop() {
    chrome.runtime.sendMessage({ action: "STOP_LISTENING" }, (res) => {
      setCapturingState(false);
      chrome.storage.local.set({ isListening: false });
    });
  }

  toggleBtn.addEventListener("click", handleStart);
  stopBtn.addEventListener("click", handleStop);

  nameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      handleStart();
    }
  });

  settingsBtn.addEventListener("click", () => {
    chrome.runtime.openOptionsPage();
  });
});
