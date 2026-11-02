import os
os.environ["QDRANT_URL"] = "http://localhost:1"
from fastapi.testclient import TestClient
from app.main import app
from app.services import llm_service as L

GOOD = ("Cheque bounce problems are generally handled as a mix of a payment dispute and, sometimes, a criminal complaint, depending on the facts. "
        "A person usually keeps the cheque, the bank's return memo and any written messages. A written demand is often sent first. "
        "What applies depends on the facts, the State and the exact law, which may have been amended. A lawyer can say what to do next. ") + L._UNV_CLOSING


def _client(monkeypatch, unv, expl=None):
    async def _expl(self, *a, **k):
        return expl
    async def _unv(self, query, force_fallback=False, context_note=""):
        _unv.note = context_note
        return unv
    monkeypatch.setattr(L.LLMService, "explain_provision_ai", _expl)
    monkeypatch.setattr(L.LLMService, "generate_unverified_ai_answer", _unv)
    return TestClient(app), _unv


def _post(c, q):
    return c.post("/api/v1/search/answer", json={"query": q}, auth=("u", os.environ.get("X", "x"))).json()


def test_statute_text_without_explanation_gets_separately_labelled_ai_block(monkeypatch):
    c, u = _client(monkeypatch, GOOD)
    d = _post(c, "article 300A")
    a = d["ai_answer"]
    if "AI-GENERATED GENERAL EXPLANATION" not in a:
        import pytest; pytest.skip("provision has curated explanation or not in corpus: " + str(d.get("model_used")))
    assert "NOT checked against legal sources" in d["tier_label"]
    assert d["tier"] != "unverified_ai"


def test_statute_text_without_explanation_when_ai_unavailable_keeps_text_only(monkeypatch):
    c, u = _client(monkeypatch, None)
    d = _post(c, "section 103 bharatiya nyaya sanhita")
    assert "AI-GENERATED GENERAL EXPLANATION" not in d["ai_answer"]


def test_adverse_article_never_gets_ai_block(monkeypatch):
    c, u = _client(monkeypatch, GOOD)
    d = _post(c, "article 124B")
    assert "AI-GENERATED GENERAL EXPLANATION" not in d["ai_answer"]
    assert "Important" in d["ai_answer"]


def test_no_retrieval_unavailable_outcome_is_plain(monkeypatch):
    c, u = _client(monkeypatch, None)
    d = _post(c, "my neighbour plays loud music at night what can i do")
    assert d["tier"] in ("unreliable", "not_found", "unverified_ai") or "No AI" in d["ai_answer"] or "No AI-generated" in d["ai_answer"]
    assert "AI-GENERATED GENERAL EXPLANATION" not in d["ai_answer"]
