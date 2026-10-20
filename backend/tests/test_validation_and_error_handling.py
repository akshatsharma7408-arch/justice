"""
JUSTICE Legal AI Backend — Search Validation & Error Handling Tests (Item 12)
Verifies:
1. HTTP 400 on blank/whitespace search with friendly message.
2. HTTP 400 on queries exceeding 300 characters ('Please shorten your question').
"""

import sys
import os
import base64
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)


def test_search_post_blank_query_returns_400():
    """POST /api/v1/search with blank query must return HTTP 400 with friendly message."""
    resp = client.post("/api/v1/search", json={"query": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "cannot be empty" in detail.lower() or "empty" in detail.lower()


def test_search_post_whitespace_query_returns_400():
    """POST /api/v1/search with whitespace-only query must return HTTP 400."""
    resp = client.post("/api/v1/search", json={"query": "   \n\t  "})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "cannot be empty" in detail.lower() or "empty" in detail.lower()


def test_search_post_too_long_query_returns_400():
    """POST /api/v1/search with >300 chars must return HTTP 400 asking to shorten question."""
    long_query = "What is the constitutional validity of " + ("article " * 45)
    assert len(long_query) > 300
    resp = client.post("/api/v1/search", json={"query": long_query})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "shorten your question" in detail.lower()


def test_search_get_blank_query_returns_400():
    """GET /api/v1/search with blank query must return HTTP 400."""
    resp = client.get("/api/v1/search?q=")
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "cannot be empty" in detail.lower() or "empty" in detail.lower()


def test_search_get_too_long_query_returns_400():
    """GET /api/v1/search with >300 chars must return HTTP 400 asking to shorten question."""
    long_query = "a" * 305
    resp = client.get(f"/api/v1/search?q={long_query}")
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "shorten your question" in detail.lower()


def test_search_answer_post_too_long_returns_400():
    """POST /api/v1/search/answer with >300 chars must return HTTP 400."""
    long_query = "section " * 50
    assert len(long_query) > 300
    resp = client.post("/api/v1/search/answer", json={"query": long_query})
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "shorten your question" in detail.lower()
