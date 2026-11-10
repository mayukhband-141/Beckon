/**
 * In-meeting Overlay Alert Banner & Chime Notification
 */

(function () {
  let alertContainer = null;

  function playAlertChime(volume = 0.4) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const now = ctx.currentTime;

      // Master gain
      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(volume, now);
      masterGain.connect(ctx.destination);

      // Note 1: D5 (587.33 Hz)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(587.33, now);
      gain1.gain.setValueAtTime(0.001, now);
      gain1.gain.exponentialRampToValueAtTime(0.3, now + 0.04);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(masterGain);
      osc1.start(now);
      osc1.stop(now + 0.4);

      // Note 2: A5 (880.00 Hz) - higher bell chime
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(880.00, now + 0.12);
      gain2.gain.setValueAtTime(0.001, now + 0.12);
      gain2.gain.exponentialRampToValueAtTime(0.35, now + 0.17);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
      osc2.connect(gain2);
      gain2.connect(masterGain);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.6);

      // Cleanup
      setTimeout(() => {
        try { ctx.close(); } catch (_) {}
      }, 700);
    } catch (err) {
      console.warn("[Beckon] Could not play alert chime:", err);
    }
  }

  function getOrCreateContainer() {
    if (!alertContainer || !document.body.contains(alertContainer)) {
      alertContainer = document.createElement("div");
      alertContainer.id = "beckon-alert-container";
      document.body.appendChild(alertContainer);
    }
    return alertContainer;
  }

  function displayAlert(alertData) {
    // Play chime if enabled in user preferences
    chrome.storage.local.get(["sound_alert_enabled", "chime_volume"], (settings) => {
      const soundEnabled = settings.sound_alert_enabled !== false; // Default true
      const volume = settings.chime_volume !== undefined ? parseFloat(settings.chime_volume) : 0.4;
      if (soundEnabled) {
        playAlertChime(volume);
      }
    });

    const container = getOrCreateContainer();
    const card = document.createElement("div");
    card.className = "beckon-card";

    const speaker = alertData.speaker || "Someone";
    const firstLetter = (speaker[0] || "S").toUpperCase();
    const scorePct = Math.round((alertData.score || 0.8) * 100);
    const sentence = alertData.sentence || "Your name was called in the meeting.";
    const rollingTranscript = alertData.rolling_transcript || "";
    const quickReplies = Array.isArray(alertData.quick_replies) ? alertData.quick_replies : [];

    card.innerHTML = `
      <div class="beckon-header">
        <div class="beckon-title">
          <span class="beckon-avatar">${escapeHtml(firstLetter)}</span>
          <span><strong>${escapeHtml(speaker)}</strong> called you</span>
          <span class="beckon-badge">${scorePct}% match</span>
        </div>
        <button class="beckon-close-btn" title="Dismiss">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div class="beckon-sentence">
        "${escapeHtml(sentence)}"
      </div>
      ${quickReplies.length > 0 ? `
        <div class="beckon-quick-replies">
          <div class="beckon-quick-reply-label">Quick Replies (Click to Copy)</div>
          ${quickReplies.map((r, idx) => `
            <button class="beckon-reply-btn" data-reply="${escapeHtml(r)}">
              <span>💬 ${escapeHtml(r)}</span>
            </button>
          `).join("")}
        </div>
      ` : ""}
      ${rollingTranscript ? `
        <button class="beckon-details-toggle">
          <svg class="beckon-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
          <span class="beckon-toggle-text">Last 45s context</span>
        </button>
        <div class="beckon-transcript-box">${escapeHtml(rollingTranscript)}</div>
      ` : ""}
    `;

    // Handle quick reply clicks (Copy & optional paste into Google Meet chat)
    card.querySelectorAll(".beckon-reply-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const replyText = btn.getAttribute("data-reply");
        if (replyText) {
          navigator.clipboard.writeText(replyText).catch(() => {});
          const originalHtml = btn.innerHTML;
          btn.classList.add("copied");
          btn.innerHTML = `<span>✓ Copied to clipboard</span>`;
          setTimeout(() => {
            btn.classList.remove("copied");
            btn.innerHTML = originalHtml;
          }, 2000);

          // If chat input exists in Google Meet, paste text into it
          const chatInput = document.querySelector('textarea[aria-label*="chat" i], textarea[placeholder*="message" i]');
          if (chatInput) {
            chatInput.value = replyText;
            chatInput.dispatchEvent(new Event("input", { bubbles: true }));
            chatInput.focus();
          }
        }
      });
    });

    // Close button
    card.querySelector(".beckon-close-btn").addEventListener("click", () => {
      card.remove();
    });

    // Transcript toggle
    const toggleBtn = card.querySelector(".beckon-details-toggle");
    if (toggleBtn) {
      const box = card.querySelector(".beckon-transcript-box");
      const toggleText = toggleBtn.querySelector(".beckon-toggle-text");
      toggleBtn.addEventListener("click", () => {
        const isOpen = box.classList.toggle("open");
        toggleBtn.classList.toggle("open", isOpen);
        toggleText.textContent = isOpen ? "Hide context" : "Last 45s context";
      });
    }

    container.appendChild(card);

    // Auto-remove after 16 seconds
    setTimeout(() => {
      if (card.parentNode) {
        card.style.opacity = "0";
        card.style.transform = "translateY(-10px)";
        card.style.transition = "all 0.3s ease";
        setTimeout(() => card.remove(), 300);
      }
    }, 16000);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "DISPLAY_ALERT") {
      displayAlert(message.alert);
      sendResponse({ status: "displayed" });
    }
  });

  console.log("[Beckon] Overlay alert and chime listener initialized.");
})();
