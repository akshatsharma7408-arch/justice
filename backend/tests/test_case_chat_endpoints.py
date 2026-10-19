"""
Unit and API integration tests for Case Chat and Explain Selection endpoints:
- POST /api/case-chat (valid, empty, too long, question not covered by the case, cache)
- POST /api/explain-selection (valid, empty, too short, too long)
- GET  /api/case-text/{case_id}
"""

import sys
import os
import base64
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app, SITE_PASSWORD

headers = {}
if SITE_PASSWORD:
    b64 = base64.b64encode(f"admin:{SITE_PASSWORD}".encode()).decode()
    headers["Authorization"] = f"Basic {b64}"
client = TestClient(app, headers=headers)

# ---------------------------------------------------------------------------
# Tests for /api/case-chat
# ---------------------------------------------------------------------------

def test_case_chat_valid_summary(client=client):
    """Summarise this case returns 200, fixed structure, and is cached."""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "Summarise this case"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "sc-2006-percept"
    assert "What it was about:" in data["answer"]
    assert "What the court decided:" in data["answer"]
    assert "Why it matters:" in data["answer"]
    assert "Key points:" in data["answer"]
    assert data["disclaimer"] == "AI answer, not legal advice"

    # Second call should be a cache hit
    res_cached = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "Summarise this case"
    })
    assert res_cached.status_code == 200
    assert res_cached.json()["cached"] is True

def test_case_chat_valid_factual_question(client=client):
    """Valid question about parties returns grounded answer and Based on line."""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "Who were the parties?"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Percept" in data["answer"] or "Zaheer" in data["answer"]
    assert data["based_on"] is not None
    assert data["disclaimer"] == "AI answer, not legal advice"

def test_case_chat_question_not_covered_by_case(client=client):
    """Question asking about an entity not in the case returns 'This case does not say that.'"""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "What did the court say about bitcoin mining?"
    })
    assert res.status_code == 200
    data = res.json()
    assert "This case does not say that." in data["answer"]

def test_case_chat_empty_question(client=client):
    """Empty question returns 400 Bad Request."""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "   "
    })
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()

def test_case_chat_too_long_question(client=client):
    """Question > 2000 characters returns 400 Bad Request."""
    too_long = "What is this case about? " * 100  # 2500 chars
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": too_long
    })
    assert res.status_code == 400
    assert "exceeds maximum allowed length" in res.json()["detail"].lower()

def test_case_chat_empty_case_id(client=client):
    """Empty case_id returns 400 Bad Request."""
    res = client.post("/api/case-chat", json={
        "case_id": "",
        "question": "Who were the parties?"
    })
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()

def test_case_chat_nonexistent_case(client=client):
    """Non-existent case returns 404 Not Found."""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-9999-totally-fake-case",
        "question": "What was the holding?"
    })
    assert res.status_code == 404

# ---------------------------------------------------------------------------
# Tests for /api/explain-selection
# ---------------------------------------------------------------------------

def test_explain_selection_valid(client=client):
    """Valid text selection returns 200 and formatted explanation."""
    res = client.post("/api/explain-selection", json={
        "selected_text": "A covenant in restraint of trade is void ab initio under Section 27"
    })
    assert res.status_code == 200
    data = res.json()
    assert "In simple words:" in data["explanation"]
    assert "Why it matters:" in data["explanation"]
    assert data["disclaimer"] == "AI explanation, not verified, not legal advice"

def test_explain_selection_empty(client=client):
    """Empty selection returns 400 Bad Request."""
    res = client.post("/api/explain-selection", json={
        "selected_text": "   "
    })
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()

def test_explain_selection_too_short(client=client):
    """Selection under 3 words returns 400 Bad Request."""
    res = client.post("/api/explain-selection", json={
        "selected_text": "Two words"
    })
    assert res.status_code == 400
    assert "at least 3 words" in res.json()["detail"].lower()

def test_explain_selection_too_long(client=client):
    """Selection over 1500 chars returns 400 Bad Request."""
    too_long = "This is a very long text passage being selected by the user. " * 30  # >1800 chars
    res = client.post("/api/explain-selection", json={
        "selected_text": too_long
    })
    assert res.status_code == 400
    assert "exceeds maximum length" in res.json()["detail"].lower()

# ---------------------------------------------------------------------------
# Tests for /api/case-text
# ---------------------------------------------------------------------------

def test_get_case_text_valid(client=client):
    """Retrieves case paragraphs with anchors and paragraph numbers."""
    res = client.get("/api/case-text/sc-2006-percept")
    assert res.status_code == 200
    data = res.json()
    assert data["total_paragraphs"] > 0
    assert len(data["paragraphs"]) > 0
    first_para = data["paragraphs"][0]
    assert first_para["id"] == "chunk-0"
    assert first_para["paragraph_number"] == 1
    assert len(first_para["text"]) > 0

if __name__ == "__main__":
    headers = {}
    if SITE_PASSWORD:
        b64 = base64.b64encode(f"admin:{SITE_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {b64}"
    c = TestClient(app, headers=headers)

    tests = [
        ("test_case_chat_valid_summary", test_case_chat_valid_summary),
        ("test_case_chat_valid_factual_question", test_case_chat_valid_factual_question),
        ("test_case_chat_question_not_covered_by_case", test_case_chat_question_not_covered_by_case),
        ("test_case_chat_empty_question", test_case_chat_empty_question),
        ("test_case_chat_too_long_question", test_case_chat_too_long_question),
        ("test_case_chat_empty_case_id", test_case_chat_empty_case_id),
        ("test_case_chat_nonexistent_case", test_case_chat_nonexistent_case),
        ("test_explain_selection_valid", test_explain_selection_valid),
        ("test_explain_selection_empty", test_explain_selection_empty),
        ("test_explain_selection_too_short", test_explain_selection_too_short),
        ("test_explain_selection_too_long", test_explain_selection_too_long),
        ("test_get_case_text_valid", test_get_case_text_valid),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn(c)
            print(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")

    print(f"\nAll tests completed: {passed}/{len(tests)} passed.")
    if passed < len(tests):
        sys.exit(1)

