import json
from pathlib import Path

CORPUS = json.loads((Path(__file__).resolve().parents[1] / "app" / "ingest" / "dva_corpus.json").read_text(encoding="utf-8"))


def test_dva_corpus_has_all_37_sections_clean():
    assert sorted(map(int, CORPUS)) == list(range(1, 38))
    for k, v in CORPUS.items():
        assert v["heading"] and len(v["body"]) > 60, k
        assert "CHAPTER" not in v["body"] and "indiacode" not in v["body"].lower(), k


def test_dva_key_sections_text_and_amendment_note():
    assert "thirty days" in CORPUS["29"]["body"] and "Court of Session" in CORPUS["29"]["body"]
    assert "Jammu and Kashmir" in CORPUS["1"]["body"] and "Act 34 of 2019" in CORPUS["1"]["body"]
    assert "Jammu" not in CORPUS["2"]["body"]  # footnote text is not part of s.2
    assert "26 October 2006" in CORPUS["1"]["caveat"]
    assert "shared household" in CORPUS["2"]["body"] and "Protection Officer" in CORPUS["2"]["body"]


def test_dva_lookup_and_qualified_label():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.statute_service import statute_service
    p = statute_service.get_provision("protection-of-women-from-domestic-violence-act-2005", "29")
    assert p and "Appeal" in p["heading"]
    j = TestClient(app).post("/api/v1/search/answer", json={"query": "section 29 of the protection of women from domestic violence act 2005", "force_fallback": True}).json()
    assert "Court of Session" in j["ai_answer"]
    assert "later amendments not checked" in j["tier_label"].lower()
    assert "authoritative" not in j["tier_label"].lower()
    assert j.get("statute_notice") and "India Code" in j["statute_notice"]
