"""
Upload acknowledgement must never report false persistence.

Regression context: the upload endpoint computed its "(Qdrant reachable & mirrored)"
note from a SECOND reachability probe after the mirror attempt. If Qdrant was
reachable but the mirror write itself failed (exception caught and only logged),
the response still claimed the document was mirrored - a false persistence promise.
The note is now derived from the mirror's actual boolean result, and a failed or
unavailable mirror surfaces a visible session-only warning.

Only synthetic test documents are used. Real-Qdrant success coverage lives in
test_doc_qdrant_persistence.py; the failure paths here are monkeypatched and run
in any environment.
"""

import base64
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.routers import docchat

SYNTHETIC_TEXT = (
    "SYNTHETIC ACK TEST AGREEMENT (FICTIONAL TEST DOCUMENT - NOT A REAL CONTRACT)\n\n"
    "Clause 1. Term. This fictional agreement runs for thirty (30) fictional days.\n\n"
    "Clause 2. Confidentiality. Both fictional parties keep test information confidential "
    "for two (2) fictional years.\n"
)


def _client():
    from fastapi.testclient import TestClient
    from app.main import app

    site_pwd = os.getenv("SITE_PASSWORD", "").strip()
    headers = {}
    if site_pwd:
        headers["Authorization"] = "Basic " + base64.b64encode(f"user:{site_pwd}".encode()).decode()
    return TestClient(app, headers=headers)


def _upload(client):
    resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("ack_test.txt", SYNTHETIC_TEXT.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200, f"upload failed: {resp.text[:300]}"
    return resp.json()


def _cleanup(doc_id):
    docchat.DOC_STORE.pop(doc_id, None)
    try:
        from qdrant_client import QdrantClient
        from app.config import settings
        q = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=5.0)
        q.delete_collection(f"doc_{doc_id}")
    except Exception:
        pass


def test_session_only_when_qdrant_unreachable(monkeypatch):
    """Unreachable Qdrant: response must say session-only, never claim a mirror."""
    monkeypatch.setattr(docchat, "is_qdrant_reachable", lambda: False)
    body = _upload(_client())
    try:
        assert "Qdrant reachable & mirrored" not in body["message"]
        assert "session-only" in body["message"]
        assert any("session only" in w or "not survive a server restart" in w for w in body["warnings"]), body["warnings"]
    finally:
        _cleanup(body["doc_id"])


def test_failed_mirror_write_not_reported_as_success(monkeypatch):
    """Reachable Qdrant but the upsert throws: response must NOT claim 'mirrored'.

    This regresses the old bug where the note came from a fresh reachability
    probe rather than the mirror's actual result.
    """
    qdrant_client = pytest.importorskip("qdrant_client")

    class _ExplodingClient:
        def __init__(self, *args, **kwargs):
            pass

        def recreate_collection(self, *args, **kwargs):
            pass

        def upsert(self, *args, **kwargs):
            raise RuntimeError("simulated Qdrant write failure")

    monkeypatch.setattr(docchat, "is_qdrant_reachable", lambda: True)
    monkeypatch.setattr(qdrant_client, "QdrantClient", _ExplodingClient)
    body = _upload(_client())
    try:
        assert "Qdrant reachable & mirrored" not in body["message"], body["message"]
        assert "session-only" in body["message"], body["message"]
        assert any("not survive a server restart" in w for w in body["warnings"]), body["warnings"]
    finally:
        _cleanup(body["doc_id"])


def test_mirror_callable_result_drives_note(monkeypatch):
    """Endpoint derives the note from mirror_to_qdrant_if_available's return value."""
    monkeypatch.setattr(docchat, "is_qdrant_reachable", lambda: True)
    monkeypatch.setattr(docchat, "mirror_to_qdrant_if_available", lambda *a, **k: False)
    body = _upload(_client())
    try:
        assert "Qdrant reachable & mirrored" not in body["message"]
        assert "session-only" in body["message"]
    finally:
        _cleanup(body["doc_id"])


QDRANT_AVAILABLE = bool(os.getenv("QDRANT_URL")) and docchat.is_qdrant_reachable()


@pytest.mark.skipif(not QDRANT_AVAILABLE, reason="Qdrant cloud not reachable")
def test_successful_mirror_still_claimed(monkeypatch):
    """Real mirror success: the positive acknowledgement is preserved."""
    body = _upload(_client())
    try:
        assert "Qdrant reachable & mirrored" in body["message"], body["message"]
        assert not any("not survive a server restart" in w for w in body["warnings"])
    finally:
        _cleanup(body["doc_id"])
