"""
Document uploads persist across server restarts via the user's own Qdrant instance.

Regression context: DOC_STORE is in-memory, so every restart/spin-down wiped uploaded
documents and the demo required a manual re-upload. The upload path now mirrors
chunks (plus a title/raw_text meta point) into a per-document Qdrant collection,
and /api/v1/doc/chat rehydrates the DocumentRecord from that mirror on a DOC_STORE miss.

These tests run against the real Qdrant cloud when QDRANT_URL/QDRANT_API_KEY are set
(the authoritative suite environment) and skip otherwise. Test collections are deleted
afterwards; only synthetic test documents are used.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.routers import docchat
from app.routers.docchat import (
    DOC_STORE,
    ClauseChunk,
    DocumentRecord,
    mirror_to_qdrant_if_available,
    rehydrate_doc_from_qdrant,
    is_qdrant_reachable,
)

QDRANT_AVAILABLE = bool(os.getenv("QDRANT_URL")) and is_qdrant_reachable()
pytestmark = pytest.mark.skipif(
    not QDRANT_AVAILABLE,
    reason="Qdrant cloud not reachable; persistence mirror cannot be tested offline",
)

TEST_DOC_ID = "doc_testpersist01"
COLLECTION = f"doc_{TEST_DOC_ID}"

SYNTHETIC_TEXT = (
    "SYNTHETIC PERSISTENCE TEST AGREEMENT (FICTIONAL TEST DOCUMENT - NOT A REAL CONTRACT)\n\n"
    "Clause 1. Term. This fictional agreement runs for ninety (90) fictional days.\n\n"
    "Clause 2. Confidentiality. Both fictional parties keep test information confidential "
    "for eleven (11) fictional years.\n"
)


def _make_record():
    chunks = [
        ClauseChunk(
            chunk_id=i + 1,
            clause_number=f"Clause {i + 1}",
            heading=f"Test heading {i + 1}",
            text=part,
            embedding=[0.01 * (i + 1)] * 8,
        )
        for i, part in enumerate(SYNTHETIC_TEXT.split("\n\n"))
    ]
    return DocumentRecord(doc_id=TEST_DOC_ID, title="synthetic_persistence_test", raw_text=SYNTHETIC_TEXT, chunks=chunks)


@pytest.fixture(autouse=True)
def cleanup_qdrant_collection():
    yield
    try:
        from qdrant_client import QdrantClient
        from app.config import settings
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=5.0)
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    DOC_STORE.pop(TEST_DOC_ID, None)


def test_mirror_then_rehydrate_roundtrip():
    """Mirror a document, wipe DOC_STORE (simulated restart), rehydrate: chunks, text and meta survive."""
    record = _make_record()
    DOC_STORE[TEST_DOC_ID] = record
    mirror_to_qdrant_if_available(TEST_DOC_ID, record.chunks, record.title, record.raw_text)

    DOC_STORE.pop(TEST_DOC_ID, None)
    assert TEST_DOC_ID not in DOC_STORE

    restored = rehydrate_doc_from_qdrant(TEST_DOC_ID)
    assert restored is not None, "rehydration returned None; mirror or reload failed"
    assert restored.title == "synthetic_persistence_test"
    assert len(restored.chunks) == len(record.chunks)
    assert "eleven (11) fictional years" in restored.raw_text
    texts = [c.text for c in restored.chunks]
    assert any("fictional days" in t for t in texts)
    assert all(c.embedding for c in restored.chunks), "embeddings must survive for retrieval"


def test_rehydrate_unknown_doc_returns_none():
    assert rehydrate_doc_from_qdrant("doc_neveruploaded99") is None


def test_chat_survives_docstore_wipe():
    """End-to-end: upload via API, wipe DOC_STORE, chat must still answer (not 404)."""
    import base64
    from fastapi.testclient import TestClient
    from app.main import app

    site_pwd = os.getenv("SITE_PASSWORD", "").strip()
    headers = {}
    if site_pwd:
        headers["Authorization"] = "Basic " + base64.b64encode(f"user:{site_pwd}".encode()).decode()
    client = TestClient(app, headers=headers)

    up = client.post(
        "/api/v1/doc/upload",
        files={"file": ("persist_test.txt", SYNTHETIC_TEXT.encode("utf-8"), "text/plain")},
    )
    assert up.status_code == 200, f"upload failed: {up.text}"
    doc_id = up.json()["doc_id"]

    # Clean up the real mirrored collection for this upload too
    from qdrant_client import QdrantClient
    from app.config import settings
    q = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=5.0)
    try:
        DOC_STORE.pop(doc_id, None)
        resp = client.post(
            "/api/v1/doc/chat",
            json={"doc_id": doc_id, "question": "How long does confidentiality last?", "force_fallback": True},
        )
        assert resp.status_code == 200, f"chat after wipe failed: {resp.status_code} {resp.text[:200]}"
        body = resp.json()
        ans = body.get("answer", "")
        # Persistence assertion: after a DOC_STORE wipe the correct clause must still be retrieved.
        # (Sentence-level extraction quality of the deterministic fallback is a separate concern.)
        assert "Clause 2" in ans and "confidential" in ans.lower(), ans[:300]
    finally:
        DOC_STORE.pop(doc_id, None)
        try:
            q.delete_collection(f"doc_{doc_id}")
        except Exception:
            pass
