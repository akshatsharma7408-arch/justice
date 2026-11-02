import os
os.environ.setdefault("QDRANT_URL", "http://localhost:1")
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def _ans(a):
    return c.post("/api/v1/search/answer", json={"query": f"article {a}"}, auth=("u", "x")).json()["ai_answer"]


def test_56_edition_text_only():
    t = _ans("56")
    assert "five years from the date on which he enters upon his office" in t
    assert "Speaker of the House of the People" in t
    assert "Key constitutional parameters" not in t
    assert "Solely" not in t and "[Note written for this app" not in t


def test_239ab_edition_text_only():
    t = _ans("239AB")
    assert "for such period and subject to such conditions as may be specified in such law" in t
    assert "article 239 and article 239AA" in t
    assert "emergency mechanisms" not in t and "[Note written for this app" not in t


def test_14_no_handwritten_summary():
    t = _ans("14")
    assert "equality before the law or the equal protection of the laws" in t
    assert "As authoritatively held" not in t and "Royappa" not in t and "AI summary" not in t
