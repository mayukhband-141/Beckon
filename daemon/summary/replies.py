import re
import logging
from typing import List, Optional

logger = logging.getLogger("beckon.replies")

class QuickReplyGenerator:
    """
    Tier 5: Contextual Quick-Reply Assistant.
    Generates 3 ultra-concise, professional one-tap action responses when the user's name is called.
    Displayed on the Chrome in-meeting HUD and Android floating pill/notifications.
    """

    def __init__(self, groq_api_key: str = ""):
        self.groq_api_key = groq_api_key

    def generate_replies(self, target_name: str, sentence: str, summary: Optional[str] = None) -> List[str]:
        """
        Generates 3 tailored, 1-click response options based on the detected speech act.
        """
        text = (sentence or "").lower()
        clean_name = target_name.strip()

        # 1. Screen sharing / Presentation request
        if any(w in text for w in ("screen", "share", "present", "take over", "slides", "slide")):
            return [
                "Yes, sharing my screen now.",
                "One second, pulling up the window.",
                "Can you grant me screen sharing permission?"
            ]

        # 2. Mic / Mute / Audio verification check
        if any(w in text for w in ("unmute", "mute", "mic", "hear us", "hear me", "audio", "sound")):
            return [
                "Unmuting now, can you hear me clearly?",
                "My mic was muted — give me 10 seconds.",
                "Yes, loud and clear!"
            ]

        # 3. Code review / PR / Commit / Deployment request
        if any(w in text for w in ("pr", "pull request", "merge", "branch", "commit", "push", "deploy", "release")):
            return [
                "Yes, pushed and ready for review.",
                "Will push the changes in 5 minutes.",
                "Checking the CI build status right now."
            ]

        # 4. Review / Checking / Logs investigation request
        if any(w in text for w in ("check", "look", "review", "logs", "bug", "issue", "error", "investigate")):
            return [
                "Looking into it right now.",
                "Checking the logs, will update you shortly.",
                "I reviewed it earlier — looks good to go."
            ]

        # 5. Question / Opinion / Turn-taking request ("what do you think", "your thoughts")
        if any(w in text for w in ("think", "thoughts", "opinion", "agree", "take")):
            return [
                "I agree with this direction.",
                "Checking the details, will update in chat shortly.",
                "Give me a minute to review, then I'll chime in."
            ]

        # 6. Banglish & Bengali direct requests
        if any(w in text for w in ("bolo", "koro", "dekho", "shuno", "sunte", "join")):
            return [
                "Hyan, ami dekhchi ekhuni.",
                "Ek minute, ami unmute korchi.",
                "Thik ache, ami complete kore janaccho."
            ]

        # 7. Hinglish & Hindi direct requests
        if any(w in text for w in ("batao", "bataiye", "karo", "kijiye", "suno", "sun rahe")):
            return [
                "Haan, main abhi check kar raha hoon.",
                "Ek minute, mic unmute kar raha hoon.",
                "Thik hai, main dekh kar update karta hoon."
            ]

        # Default professional situational responses
        return [
            "Yes, on it right now.",
            "My mic was muted — give me 10 seconds.",
            "Checking the details, will update you shortly."
        ]
