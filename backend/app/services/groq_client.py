"""
Groq adapter for JUSTICE. Exposes the small slice of the google-genai client API
that the app already uses (client.models.generate_content / embed_content), but
sends the request to Groq's OpenAI-compatible endpoint.
Primary model: openai/gpt-oss-120b. Spills over to openai/gpt-oss-20b on rate limits.
"""
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, List

import contextvars
import time
import httpx

logger = logging.getLogger("justice.groq")

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
SPILLOVER_MODEL = os.getenv("GROQ_SPILLOVER_MODEL", "openai/gpt-oss-20b")


# ---- Optional Gemini fallback (OFF unless explicitly configured) -------------------------------------------
# Used only when BOTH Groq models fail with a rate limit/outage, only for requests whose context allows external
# fallback (questions and statute text, never uploaded documents), and only while an in-memory counter is under GEMINI_FALLBACK_DAILY_CAP.
# That counter is a per-process guard for one UTC day: it resets on restart, redeploy or sleep, so it is NOT a durable
# daily maximum. The provider's own free-tier quota is the only hard stop.
# The key is read from the server environment; it is sent in a header, never put in a URL, and never logged.
ALLOW_EXTERNAL_FALLBACK = contextvars.ContextVar("allow_external_fallback", default=False)
_GEMINI_CALLS = {"day": None, "n": 0}


def _gemini_settings():
    enabled = os.getenv("GEMINI_FALLBACK_ENABLED", "0") == "1"
    key = os.getenv("GEMINI_FALLBACK_API_KEY", "")
    model = os.getenv("GEMINI_FALLBACK_MODEL", "")
    try:
        cap = int(os.getenv("GEMINI_FALLBACK_DAILY_CAP", "0"))
    except ValueError:
        cap = 0
    return enabled, key, model, cap


def gemini_fallback_available() -> bool:
    enabled, key, model, cap = _gemini_settings()
    return bool(enabled and key and model and cap > 0 and ALLOW_EXTERNAL_FALLBACK.get())


def _gemini_budget_ok(cap: int) -> bool:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if _GEMINI_CALLS["day"] != day:
        _GEMINI_CALLS["day"], _GEMINI_CALLS["n"] = day, 0
    if _GEMINI_CALLS["n"] >= cap:
        return False
    _GEMINI_CALLS["n"] += 1
    return True


def call_gemini_fallback(system, prompt: str, config) -> str:
    enabled, key, model, cap = _gemini_settings()
    if not gemini_fallback_available() or not _gemini_budget_ok(cap):
        raise RuntimeError("gemini fallback not available")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": getattr(config, "temperature", None) or 0.2,
                             "maxOutputTokens": max(int(getattr(config, "max_output_tokens", 0) or 0), 1024)},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": str(system)}]}
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                   headers={"x-goog-api-key": key, "content-type": "application/json"}, json=body, timeout=40.0)
    if r.status_code >= 400:
        raise RuntimeError(f"gemini {r.status_code}")  # never include the response body or URL
    data = r.json()
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    return "".join(p.get("text", "") for p in parts).strip()


class _Models:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _call(self, model: str, messages: List[dict], config: Any) -> dict:
        body = {
            "model": model,
            "messages": messages,
            "temperature": getattr(config, "temperature", None) or 0.2,
            "max_completion_tokens": max(int(getattr(config, "max_output_tokens", 0) or 0), 4096),
            "reasoning_effort": "low",
        }
        if getattr(config, "response_mime_type", None) == "application/json":
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=body,
            timeout=60.0,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code} {r.text[:300]}")
        return r.json()

    def generate_content(self, model: str = None, contents: Any = "", config: Any = None):
        system = getattr(config, "system_instruction", None)
        if isinstance(contents, list):
            contents = "\n".join(str(c) for c in contents)
        prompt = str(contents)
        schema = getattr(config, "response_schema", None)
        if schema is not None and getattr(config, "response_mime_type", None) == "application/json":
            try:
                prompt += "\n\nReturn ONLY a JSON object matching this JSON schema:\n" + json.dumps(schema.model_json_schema())
            except Exception:
                prompt += "\n\nReturn ONLY a valid JSON object."
        messages = []
        if system:
            messages.append({"role": "system", "content": str(system)})
        messages.append({"role": "user", "content": prompt})
        try:
            try:
                data = self._call(PRIMARY_MODEL, messages, config)
            except RuntimeError as e:
                if str(e).startswith("429") and SPILLOVER_MODEL:
                    logger.info("Primary Groq model rate limited, using spillover model")
                    data = self._call(SPILLOVER_MODEL, messages, config)
                else:
                    raise
        except (RuntimeError, httpx.HTTPError) as e:
            transient = isinstance(e, httpx.HTTPError) or str(e)[:3] in ("429", "500", "502", "503", "504")
            if transient and gemini_fallback_available():
                logger.info("Groq unavailable; using the configured Gemini fallback")
                try:
                    return SimpleNamespace(text=call_gemini_fallback(system, prompt, config))
                except Exception:
                    logger.warning("Gemini fallback failed")
            raise
        text = (data["choices"][0]["message"].get("content") or "").strip()
        return SimpleNamespace(text=text)

    def embed_content(self, *args, **kwargs):
        # Groq has no embeddings endpoint. Callers fall back to local embeddings.
        raise NotImplementedError("embeddings not provided by Groq; using local fallback")


class GroqClient:
    def __init__(self, api_key: str):
        self.models = _Models(api_key)
