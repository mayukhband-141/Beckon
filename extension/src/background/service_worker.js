let capturingTabId = null;

async function ensureOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"]
  });

  if (existingContexts.length > 0) {
    return;
  }

  await chrome.offscreen.createDocument({
    url: "src/offscreen/offscreen.html",
    reasons: ["USER_MEDIA"],
    justification: "Capture meeting tab audio and downsample to 16kHz for local name detection."
  });
}

// When the extension is installed or restarted, ensure offscreen document connects
chrome.runtime.onInstalled.addListener(() => {
  ensureOffscreenDocument().catch(console.error);
});

// Click on notification focuses the Google Meet meeting tab
chrome.notifications?.onClicked.addListener((notificationId) => {
  if (capturingTabId) {
    chrome.tabs.get(capturingTabId, (tab) => {
      if (tab) {
        chrome.tabs.update(capturingTabId, { active: true });
        chrome.windows.update(tab.windowId, { focused: true });
      }
    });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.action === "START_LISTENING") {
      try {
        const tabId = message.tabId;
        capturingTabId = tabId;

        await ensureOffscreenDocument();

        // Obtain tabCapture stream ID for the target meeting tab
        chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (streamId) => {
          if (chrome.runtime.lastError || !streamId) {
            console.error("[Beckon SW] Failed to getMediaStreamId:", chrome.runtime.lastError);
            sendResponse({ success: false, error: chrome.runtime.lastError?.message });
            return;
          }

          chrome.runtime.sendMessage({
            action: "START_CAPTURE",
            streamId: streamId
          });
          sendResponse({ success: true });
        });
      } catch (err) {
        console.error("[Beckon SW] Error starting listening:", err);
        sendResponse({ success: false, error: err.message });
      }
      return true;
    }

    if (message.action === "CHECK_CONNECTION") {
      chrome.runtime.sendMessage({ action: "CHECK_CONNECTION" }, (res) => {
        sendResponse(res || { connected: false, capturing: false });
      });
      return true;
    }

    if (message.action === "STOP_LISTENING") {
      capturingTabId = null;
      chrome.runtime.sendMessage({ action: "STOP_CAPTURE" });
      sendResponse({ success: true });
      return true;
    }

    // Forward alerts to the active Meet tab content script & trigger desktop notification
    if (message.type === "NAME_ALERT") {
      console.log("[Beckon SW] Received NAME_ALERT:", message.alert);

      // Only trigger desktop alert notification if this browser is actively capturing a tab
      if (capturingTabId) {
        chrome.notifications?.create("beckon-alert-" + Date.now(), {
          type: "basic",
          iconUrl: chrome.runtime.getURL("icons/icon128.png"),
          title: `${message.alert.speaker || 'Someone'} called your name!`,
          message: message.alert.sentence || "Someone just mentioned you in the meeting.",
          priority: 2,
          requireInteraction: true
        });

        // Send to content script in the meeting tab
        chrome.tabs.sendMessage(capturingTabId, {
          type: "DISPLAY_ALERT",
          alert: message.alert
        }).catch(() => {});
      }
    }

    // Forward active speaker updates from content script to offscreen doc
    if (message.type === "SPEAKER_UPDATE") {
      chrome.runtime.sendMessage({
        action: "SPEAKER_UPDATE",
        active_speaker: message.active_speaker,
        roster: message.roster
      }).catch(() => {});
    }

    // Forward config updates to offscreen doc
    if (message.action === "CONFIG_UPDATE") {
      chrome.runtime.sendMessage({
        action: "CONFIG_UPDATE",
        config: message.config
      }).catch(() => {});
    }
  })();
  return true;
});
