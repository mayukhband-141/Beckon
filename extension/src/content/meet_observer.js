/**
 * Tab & Meeting DOM Observer
 * Detects who is speaking (Google Meet, YouTube channel/video, or generic audio tab).
 */

(function () {
  let lastReportedSpeaker = null;
  let lastReportedTime = 0;

  function findActiveSpeaker() {
    const host = window.location.hostname;

    // 1. Google Meet DOM
    if (host.includes("meet.google.com")) {
      const speakingElements = document.querySelectorAll(
        '[aria-label*="speaking"], [aria-label*="Speaking"], [data-is-muted="false"]'
      );
      for (const el of speakingElements) {
        const label = el.getAttribute("aria-label") || "";
        const match = label.match(/^(.*?)(?: is speaking| speaking)/i);
        if (match && match[1]) {
          return match[1].trim();
        }
      }

      const activeTiles = document.querySelectorAll(
        'div[data-participant-id], div[data-requested-participant-id]'
      );
      for (const tile of activeTiles) {
        const activeBar = tile.querySelector('div[style*="opacity: 1"], div[class*="active"], div[class*="speaking"]');
        if (activeBar) {
          const nameEl = tile.querySelector(".notranslate, [data-self-name]");
          if (nameEl && nameEl.textContent) {
            return nameEl.textContent.trim();
          }
        }
      }

      const subtitleSpeaker = document.querySelector(".bh44bd, .TBMuR");
      if (subtitleSpeaker && subtitleSpeaker.textContent) {
        return subtitleSpeaker.textContent.trim();
      }

      return null;
    }

    // 2. YouTube DOM
    if (host.includes("youtube.com")) {
      const channelEl = document.querySelector(
        "ytd-channel-name a, #owner #channel-name a, .ytd-video-owner-renderer a, #upload-info #channel-name"
      );
      if (channelEl && channelEl.textContent.trim()) {
        return channelEl.textContent.trim();
      }
      // Fallback: video title or "YouTube Video"
      const titleEl = document.querySelector("h1.ytd-watch-metadata, #title h1");
      if (titleEl && titleEl.textContent.trim()) {
        const title = titleEl.textContent.trim();
        return title.length > 30 ? title.substring(0, 30) + "..." : title;
      }
      return "YouTube";
    }

    // 3. Generic site fallback
    const title = document.title ? document.title.split(/[-|–]/)[0].trim() : "";
    return title ? (title.length > 25 ? title.substring(0, 25) + "..." : title) : "Video";
  }

  function getRoster() {
    const host = window.location.hostname;
    const roster = new Set();

    if (host.includes("meet.google.com")) {
      const nameElements = document.querySelectorAll(".notranslate, [data-self-name]");
      nameElements.forEach((el) => {
        const name = el.textContent ? el.textContent.trim() : "";
        if (name && name.length > 1 && !name.includes(":") && name.length < 50) {
          roster.add(name);
        }
      });
    } else if (host.includes("youtube.com")) {
      const channel = findActiveSpeaker();
      if (channel) roster.add(channel);
    }
    return Array.from(roster);
  }

  function checkSpeaker() {
    const speaker = findActiveSpeaker();
    const now = Date.now();

    if (speaker && (speaker !== lastReportedSpeaker || now - lastReportedTime > 3000)) {
      lastReportedSpeaker = speaker;
      lastReportedTime = now;
      const roster = getRoster();

      chrome.runtime.sendMessage({
        type: "SPEAKER_UPDATE",
        active_speaker: speaker,
        roster: roster
      }).catch(() => {});
    }
  }

  // Poll every 500ms
  setInterval(checkSpeaker, 500);

  console.log("[Beckon] DOM Observer initialized on:", window.location.hostname);
})();
