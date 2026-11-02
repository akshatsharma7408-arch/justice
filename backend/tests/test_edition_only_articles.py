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


def test_article_token_boundaries():
    from app.services.qdrant_service import _ref_in, _ss_in
    assert not _ref_in("article", "14", "Article 141, Constitution of India")
    assert not _ref_in("article", "14", "Article 14A")
    assert _ref_in("article", "14", "Article 14(1)")
    assert _ref_in("article", "21", "Articles 14, 19 and 21")
    assert _ref_in("article", "14", "article 19 and 14")
    assert not _ref_in("section", "4", "Section 41 CrPC")
    assert _ref_in("section", "41", "sec. 41(1)(b)")
    assert not _ss_in("article 14", "article 141 binding") and _ss_in("article 14", "see article 14, x")


def test_14_no_unchecked_note_and_no_article_141_case():
    d = c.post("/api/v1/search/answer", json={"query": "article 14"}, auth=("u", "x")).json()
    t = d["ai_answer"]
    assert "Dalmia" not in t and "[Note written for this app" not in t
    assert "Dawoodi" not in t
    assert all("Dawoodi" not in (x.get("title") or "") for x in d.get("matching_cases", []) or d.get("cases", []) or [])
