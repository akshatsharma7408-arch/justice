"""
JUSTICE Legal AI Backend - Local Semantic Embedding Service
Produces dense semantic vectors using a local sentence-transformers model (all-MiniLM-L6-v2, 384-dim).
Operates with zero paid or external API calls (never uses Gemini).
Falls back to a deterministic local hash vector only as a last resort if local model loading fails.
"""

import hashlib
import logging
import math
from typing import List, Optional

logger = logging.getLogger("justice.embeddings")

LOCAL_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def _local_hash_vector(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Deterministic hashed bag-of-words vector. Last resort fallback only."""
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
        self._model = None
        self._engine = None  # "fastembed_onnx" or "sentence_transformers_pytorch"
        self.mode = "local_hash_fallback"
        self.model_name = LOCAL_MODEL_NAME
        self._init_model()

    def _init_model(self):
        """
        Attempts to initialize a lightweight local semantic embedding model.
        Priority 1: fastembed (ONNX runtime: ~200MB RAM, fast CPU inference, ideal for Render)
        Priority 2: sentence_transformers (PyTorch CPU runtime)
        Fallback: local hash vector
        """
        # Try fastembed first (lightweight ONNX runtime)
        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
            self._engine = "fastembed_onnx"
            self.mode = "local_semantic_onnx"
            logger.info("Initialized local semantic embeddings using fastembed ONNX (all-MiniLM-L6-v2, dim=%d)", EMBEDDING_DIM)
            return
        except Exception as e:
            logger.debug("Fastembed unavailable or failed to load: %s", e)

        # Try sentence_transformers second
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._engine = "sentence_transformers_pytorch"
            self.mode = "local_semantic_pytorch"
            logger.info("Initialized local semantic embeddings using sentence-transformers PyTorch (all-MiniLM-L6-v2, dim=%d)", EMBEDDING_DIM)
            return
        except Exception as e:
            logger.warning("Local semantic model loading failed: %s. Using last resort hash fallback.", e)

        # Last resort fallback
        self._model = None
        self._engine = None
        self.mode = "local_hash_fallback"

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts using local semantic embeddings. Never raises; falls back to hash."""
        if not texts:
            return []

        if self._model:
            try:
                if self._engine == "fastembed_onnx":
                    embeddings = list(self._model.embed(texts))
                    return [list(map(float, emb)) for emb in embeddings]
                elif self._engine == "sentence_transformers_pytorch":
                    embeddings = self._model.encode(texts, convert_to_numpy=True)
                    return [list(map(float, emb)) for emb in embeddings]
            except Exception as e:
                logger.warning("Local model inference failed (%s); using last resort hash fallback: %s", self._engine, e)

        return [_local_hash_vector(t, EMBEDDING_DIM) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]

    def describe(self) -> dict:
        is_semantic = self.mode.startswith("local_semantic")
        return {
            "mode": self.mode,
            "engine": self._engine or "deterministic_hash",
            "model": self.model_name if is_semantic else "local-sha256-hashing-trick",
            "dimension": self.dimension,
            "note": (
                f"Local semantic embeddings ({self.model_name}, dim={self.dimension}) active via {self._engine}. Zero paid API dependencies."
                if is_semantic
                else "LAST RESORT FALLBACK: deterministic hash vectors, for pipeline testing only."
            ),
        }


embedding_service = EmbeddingService()
