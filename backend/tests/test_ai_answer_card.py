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
from app.services.llm_service import check_tier2_prohibited_entities
from app.services.answer_tiers import format_tier2_response, UNRELIABLE_TIER2_MSG

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)

def test_blank_query_no_ai_card():
    """Blank query must not synthesize or return an AI answer card."""
    # POST /api/v1/search/answer with blank query
    resp = client.post("/api/v1/search/answer", json={"query": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_case_lookup"] is True
    assert data["ai_answer"] is None
    assert data["ratio_decidendi"] is None
    assert data["hide_badge"] is True

    # Whitespace only
    resp_ws = client.post("/api/v1/search/answer", json={"query": "   \n\t  "})
    assert resp_ws.status_code == 200
    data_ws = resp_ws.json()
    assert data_ws["is_case_lookup"] is True
    assert data_ws["ai_answer"] is None
    assert data_ws["hide_badge"] is True

    # GET /api/v1/search/answer with blank query
    resp_get = client.get("/api/v1/search/answer?query=")
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert data_get["is_case_lookup"] is True
    assert data_get["ai_answer"] is None
    assert data_get["hide_badge"] is True

def test_pure_case_lookup_no_ai_card():
    """Pure case name or citation lookup returns is_case_lookup=True with ai_answer=None."""
    resp = client.post("/api/v1/search/answer", json={"query": "Kesavananda Bharati v. State of Kerala"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_case_lookup"] is True
    assert data["ai_answer"] is None

    resp_cit = client.post("/api/v1/search/answer", json={"query": "AIR 1973 SC 1461"})
    assert resp_cit.status_code == 200
    data_cit = resp_cit.json()
    assert data_cit["is_case_lookup"] is True
    assert data_cit["ai_answer"] is None

def test_tier2_no_repeated_start_label():
    """format_tier2_response must not repeat 'AI answer, not verified' in the body."""
    raw = "You have the right to demand that an arresting officer explain the basis for detention."
    formatted = format_tier2_response(raw)
    assert "AI answer, not verified against a legal database." not in formatted
    assert "You have the right" in formatted
    assert "This is general information, not legal advice" in formatted

def test_tier2_ratio_decidendi_is_none():
    """ratio_decidendi must be None for Tier 2 answers (kept only for verified Tier 1)."""
    resp = client.post("/api/v1/search/answer", json={
        "query": "What are my rights if an officer arrests me without a warrant?",
        "force_fallback": True
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "tier2"
    assert data["ratio_decidendi"] is None
    assert data["ai_answer"] is not None
    assert "AI answer, not verified against a legal database." not in data["ai_answer"]

def test_check_tier2_prohibited_entities():
    """Prohibited entity checker detects cases, sections, articles, and citations."""
    # Case pattern
    assert check_tier2_prohibited_entities("In State of Kerala v. Union of India the court held") is not None
    # Famous landmark
    assert check_tier2_prohibited_entities("According to Kesavananda Bharati doctrine") is not None
    # Section
    assert check_tier2_prohibited_entities("Under Section 27 all post-employment contracts are void") is not None
    # Article
    assert check_tier2_prohibited_entities("Under Article 21 privacy is guaranteed") is not None
    # Clean conceptual text passes
    assert check_tier2_prohibited_entities("Under criminal procedure laws, the person has a right to be informed.") is None
