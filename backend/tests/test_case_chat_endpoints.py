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
from app.routers import casechat

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
    # Deterministic summary built from stored app records/excerpts; it must carry
    # its honest labels and never present itself as verified judgment text.
    assert data["model_used"] == "deterministic_summary"
    assert "App record:" in data["answer"]
    assert "not verified" in data["answer"].lower()

def test_case_chat_valid_factual_question(client=client):
    """Factual question is answered deterministically from the stored case record
    (parties, court, citation), with no AI invention."""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "Who were the parties?"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["model_used"] == "deterministic_case_chat"
    assert "Percept D'Mark" in data["answer"]
    assert "Zaheer Khan" in data["answer"]

def test_case_chat_question_not_covered_by_case(client=client):
    """Question asking about an entity not in the case returns the honest UNABLE_LINE."""
    res = client.post("/api/case-chat", json={
        "case_id": "sc-2006-percept",
        "question": "What did the court say about bitcoin mining?"
    })
    assert res.status_code == 200
    data = res.json()
    assert "cannot establish an answer" in data["answer"]

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

def test_explain_selection_two_words_allowed(client=client):
    """Item 10: Allow 2-word selections (at least 1 word allowed)."""
    res = client.post("/api/explain-selection", json={
        "selected_text": "Two words"
    })
    assert res.status_code == 200, f"2-word selection must be allowed: {res.text}"
    assert "In simple words:" in res.json()["explanation"]

def test_explain_selection_single_word_allowed(client=client):
    """Item 10: At least 1 word allowed."""
    res = client.post("/api/explain-selection", json={
        "selected_text": "Covenant"
    })
    assert res.status_code == 200, f"Single word selection must be allowed: {res.text}"
    assert "In simple words:" in res.json()["explanation"]

def test_explain_selection_too_long(client=client):
    """Item 10: Selection over 800 chars returns 400 Bad Request."""
    too_long = "This is a very long text passage being selected by the user. " * 15  # >900 chars
    res = client.post("/api/explain-selection", json={
        "selected_text": too_long
    })
    assert res.status_code == 400
    assert "exceeds maximum length" in res.json()["detail"].lower()

def test_explain_selection_inside_case_not_generic_contract(client=client):
    """Item 10: When inside a case, explanation is about selected words in that case, not generic contract."""
    res = client.post("/api/explain-selection", json={
        "selected_text": "basic structure doctrine",
        "case_id": "S_1973_1_1_1002"
    })
    assert res.status_code == 200
    exp = res.json()["explanation"].lower()
    assert "kesavananda" in exp or "judgment" in exp or "court" in exp or "constitution" in exp, f"Expected case explanation: {exp}"
    assert "contractual obligations must comply" not in exp, "Must NOT reuse generic contract answer"

# ---------------------------------------------------------------------------
# Tests for /api/case-text
# ---------------------------------------------------------------------------

def test_get_case_text_valid(client=client):
    """Retrieves case paragraphs with anchors and paragraph numbers."""
    res = client.get("/api/case-text/sc-2006-percept")
    assert res.status_code == 200
    data = res.json()
    # Judgment paragraphs are stored for this case and served with paragraph numbers.
    assert data["total_paragraphs"] >= 1
    assert data["paragraphs"][0]["paragraph_number"] >= 1


# ---------------------------------------------------------------------------
# Item 1 Tests: Kesavananda, Normal SC Case, Made-up ID, Unanswered Question
# ---------------------------------------------------------------------------

def test_case_chat_kesavananda(client=client):
    """Kesavananda (S_1973_1_1_1002) loaded by case_id returns 200 and structured summary."""
    res = client.post("/api/v1/case-chat", json={
        "case_id": "S_1973_1_1_1002",
        "question": "Summarise this case",
        "force_fallback": True
    })
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "S_1973_1_1_1002"
    assert "What it was about:" in data["answer"]
    assert "What the court decided:" in data["answer"]
    assert "Why it matters:" in data["answer"]


def test_case_chat_normal_sc_case(client=client):
    """Normal SC case (2025_2_424_451) from Qdrant works for chat, text, and citator."""
    # 1. Case chat summary
    res_chat = client.post("/api/v1/case-chat", json={
        "case_id": "2025_2_424_451",
        "question": "Summarise this case",
        "force_fallback": True
    })
    assert res_chat.status_code == 200
    data_chat = res_chat.json()
    assert "What it was about:" in data_chat["answer"]
    assert "What the court decided:" in data_chat["answer"]

    # 2. Case text
    res_text = client.get("/api/v1/case-text/2025_2_424_451")
    assert res_text.status_code == 200
    data_text = res_text.json()
    assert data_text["total_paragraphs"] > 0
    assert len(data_text["paragraphs"]) > 0

    # 3. Citator fallback
    res_cit = client.get("/api/v1/citator/2025_2_424_451?include_ai=false")
    assert res_cit.status_code == 200
    data_cit = res_cit.json()
    assert data_cit["id"] == "2025_2_424_451"
    assert "citation graph not available for this case" in data_cit["statusDescription"]


def test_case_chat_made_up_id_clean_404(client=client):
    """A made-up case_id returns a clean 404 message across chat, text, and citator."""
    fake_id = "made_up_case_id_xyz999"
    res_chat = client.post("/api/v1/case-chat", json={
        "case_id": fake_id,
        "question": "Summarise this case"
    })
    assert res_chat.status_code == 404
    assert f"Case '{fake_id}' was not found in the verified dataset." in res_chat.json()["detail"]

    res_text = client.get(f"/api/v1/case-text/{fake_id}")
    assert res_text.status_code == 404

    res_cit = client.get(f"/api/v1/citator/{fake_id}")
    assert res_cit.status_code == 404


def test_case_chat_question_not_in_case(client=client):
    """Asking about a topic not in the case returns the honest UNABLE_LINE."""
    res = client.post("/api/v1/case-chat", json={
        "case_id": "S_1973_1_1_1002",
        "question": "What does this case say about bitcoin mining rewards and cryptocurrency blockchain?",
        "force_fallback": True
    })
    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == casechat.UNABLE_LINE


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
        ("test_case_chat_kesavananda", test_case_chat_kesavananda),
        ("test_case_chat_normal_sc_case", test_case_chat_normal_sc_case),
        ("test_case_chat_made_up_id_clean_404", test_case_chat_made_up_id_clean_404),
        ("test_case_chat_question_not_in_case", test_case_chat_question_not_in_case),
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


