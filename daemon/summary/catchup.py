import json
import logging
import urllib.request
import urllib.error
import asyncio
from typing import Optional

logger = logging.getLogger("beckon.summary")

class CatchUpSummarizer:
    """
    Tier 3 LLM post-processor.
    Condenses raw meeting audio transcripts into an actionable 1-sentence alert notification.
    Uses Groq API (default llama-3.1-8b-instant, free tier, ~300ms) or local Ollama.
    Strict 2.0s timeout with instantaneous pass-through fallback.
    Audio never leaves the device — only the matching short text snippet is sent.
    """

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        ollama_url: Optional[str] = None,
        model: str = "llama-3.1-8b-instant",
        timeout_sec: float = 2.0,
    ):
        self.groq_api_key = groq_api_key.strip() if groq_api_key else ""
        self.ollama_url = ollama_url.strip() if ollama_url else ""
        self.model = model
        self.timeout_sec = timeout_sec

    @property
    def is_enabled(self) -> bool:
        return bool(self.groq_api_key or self.ollama_url)

    def summarize(self, target_name: str, snippet: str, full_context: Optional[str] = None) -> str:
        """
        Synchronous call to Groq or Ollama.
        Returns a concise 1-sentence explanation of what was asked.
        Falls back to snippet on any error or timeout.
        """
        if not self.is_enabled or not snippet:
            return snippet

        context_text = full_context.strip() if full_context else snippet.strip()
        system_instruction = (
            f"You are an on-device meeting listener assistant. The user '{target_name}' was just addressed in a call. "
            "Given the spoken audio context, summarize in ONE concise, actionable sentence (max 15 words) "
            "why they were addressed or what was asked of them. "
            "If in Bengali, Hindi, or Banglish, translate into natural English. "
            "Output ONLY the summary sentence. No quotes, no preamble, no markdown."
        )

        try:
            if self.groq_api_key:
                return self._call_groq(system_instruction, context_text, snippet)
            elif self.ollama_url:
                return self._call_ollama(system_instruction, context_text, snippet)
        except Exception as e:
            logger.debug("Catch-up summarization fell back to raw snippet: %s", e)

        return snippet

    def _call_groq(self, system_prompt: str, user_prompt: str, fallback: str) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Beckon-Meeting-Assistant/1.0",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Spoken context: {user_prompt}"},
            ],
            "max_tokens": 40,
            "temperature": 0.2,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            # Strip enclosing quotes if model returned them
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1].strip()
            return content if content else fallback

    def _call_ollama(self, system_prompt: str, user_prompt: str, fallback: str) -> str:
        base_url = self.ollama_url.rstrip("/")
        url = f"{base_url}/api/generate"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model if "llama" in self.model else "llama3.2:1b",
            "system": system_prompt,
            "prompt": f"Spoken context: {user_prompt}",
            "stream": False,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("response", "").strip()
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1].strip()
            return content if content else fallback

    async def async_summarize(self, target_name: str, snippet: str, full_context: Optional[str] = None) -> str:
        """Non-blocking async wrapper around summarize."""
        if not self.is_enabled:
            return snippet
        return await asyncio.to_thread(self.summarize, target_name, snippet, full_context)

