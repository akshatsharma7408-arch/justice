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

import httpx

logger = logging.getLogger("justice.groq")

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
SPILLOVER_MODEL = os.getenv("GROQ_SPILLOVER_MODEL", "openai/gpt-oss-20b")


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
            data = self._call(PRIMARY_MODEL, messages, config)
        except RuntimeError as e:
            if str(e).startswith("429") and SPILLOVER_MODEL:
                logger.info("Primary Groq model rate limited, using spillover model")
                data = self._call(SPILLOVER_MODEL, messages, config)
            else:
                raise
        text = (data["choices"][0]["message"].get("content") or "").strip()
        return SimpleNamespace(text=text)

    def embed_content(self, *args, **kwargs):
        # Groq has no embeddings endpoint. Callers fall back to local embeddings.
        raise NotImplementedError("embeddings not provided by Groq; using local fallback")


class GroqClient:
    def __init__(self, api_key: str):
        self.models = _Models(api_key)
