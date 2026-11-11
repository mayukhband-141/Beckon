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
        model: str = "qwen/qwen3.8-27b",
        timeout_sec: float = 2.0,
    ):
        self.groq_api_key = groq_api_key.strip() if groq_api_key else ""
        self.ollama_url = ollama_url.strip() if ollama_url else ""
        # Automatically upgrade deprecated / discontinued models to ultra-fast qwen3.8-27b
        if model in ("llama-3.1-8b-instant", "llama3-8b-8192", "llama-3-8b-instruct"):
            model = "qwen/qwen3.8-27b"
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Beckon/1.0",
        }
        candidate_models = [self.model, "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
        # Deduplicate while preserving priority order
        seen_models = set()
        models_to_try = [m for m in candidate_models if not (m in seen_models or seen_models.add(m))]

        last_error = None
        for current_model in models_to_try:
            payload = {
                "model": current_model,
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

            try:
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"].strip()
                    # Strip enclosing quotes if model returned them
                    if content.startswith('"') and content.endswith('"'):
                        content = content[1:-1].strip()
                    if content:
                        return content
            except urllib.error.HTTPError as e:
                last_error = e
                # If model not found or forbidden, try next candidate model
                if e.code in (400, 404):
                    logger.warning("Groq model '%s' unavailable (HTTP %d). Trying fallback...", current_model, e.code)
                    continue
                raise
            except Exception as e:
                last_error = e
                logger.warning("Error calling Groq with model '%s': %s", current_model, e)
                break

        if last_error:
            logger.debug("Catch-up summarization fell back to snippet: %s", last_error)
        return fallback

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

