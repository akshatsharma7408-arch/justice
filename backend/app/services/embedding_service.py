"""
JUSTICE Legal AI Backend - Embedding Service
Produces dense vectors for legal text. Uses the Gemini embedding API when a
valid GEMINI_API_KEY is configured; otherwise falls back to a deterministic
local hashed bag-of-words vector so the Qdrant pipeline is fully testable
offline. The active mode is reported in every response and in /health, so
fallback output is never mistaken for neural embeddings.
"""

import hashlib
import logging
import math
from typing import List, Optional

from app.config import settings

logger = logging.getLogger("justice.embeddings")

GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
GEMINI_EMBEDDING_DIM = 768
LOCAL_EMBEDDING_DIM = 384


def _local_hash_vector(text: str, dim: int = LOCAL_EMBEDDING_DIM) -> List[float]:
    """Deterministic hashed bag-of-words vector. Offline fallback only."""
    vec = [0.0] * dim
    tokens = [t.strip(".,;:()[]{}\"'").lower() for t in text.split() if len(t) > 1]
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class EmbeddingService:
    def __init__(self):
        self._client = None
        self.mode = "local_hash_fallback"
        if settings.is_gemini_active:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
                self.mode = "gemini"
                logger.info("Embedding service: Gemini '%s' (dim=%d)", GEMINI_EMBEDDING_MODEL, GEMINI_EMBEDDING_DIM)
            except Exception as e:
                logger.warning("Gemini embedding client init failed, using local hash fallback: %s", e)
                self._client = None

    @property
    def dimension(self) -> int:
        return GEMINI_EMBEDDING_DIM if self.mode == "gemini" else LOCAL_EMBEDDING_DIM

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Never raises; falls back per-call."""
        if self._client:
            try:
                result = self._client.models.embed_content(
                    model=GEMINI_EMBEDDING_MODEL,
                    contents=texts,
                )
                return [list(e.values) for e in result.embeddings]
            except Exception as e:
                logger.warning("Gemini embed_content failed, using local hash fallback for this batch: %s", e)
        return [_local_hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "model": GEMINI_EMBEDDING_MODEL if self.mode == "gemini" else "local-sha256-hashing-trick",
            "dimension": self.dimension,
            "note": (
                "Neural embeddings active."
                if self.mode == "gemini"
                else "OFFLINE FALLBACK: deterministic hash vectors, for pipeline testing only - not semantic search quality."
            ),
        }


embedding_service = EmbeddingService()
