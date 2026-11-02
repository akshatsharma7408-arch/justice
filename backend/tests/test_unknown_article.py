from app.services.llm_service import unknown_article_message, _edit1

def test_edit1():
    assert _edit1("339AA", "239AA") and _edit1("339AA", "339A") and not _edit1("339AA", "340")

def test_339aa_not_found_lists_one_char_neighbours_without_substituting():
    m = unknown_article_message("339AA")
    assert m and "Article 339AA was not found" in m and "Nothing has been substituted" in m
    assert "Article 239AA" in m and "Delhi" in m
    assert "1 May 2026" in m

def test_existing_article_returns_none():
    assert unknown_article_message("339") is None and unknown_article_message("239AA") is None

def test_far_number_has_no_neighbours():
    m = unknown_article_message("9999")
    assert m and "one character away" not in m


def test_router_keeps_unknown_article_message_whole(monkeypatch):
    import os
    os.environ["QDRANT_URL"] = "http://localhost:1"
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for q in ("article 9999", "whats article 339AA"):
        d = c.post("/api/v1/search/answer", json={"query": q}, auth=("u", "x")).json()
        assert d["ai_answer"].startswith(f"Article {q.split()[-1]} was not found in the Constitution text held in this database")
        assert d["tier"] == "not_found"


def test_corpus_has_330a_124c_and_njac_note():
    import json, os
    d = json.load(open(os.path.join(os.path.dirname(__file__), "..", "app", "ingest", "constitution_corpus.json")))
    assert d["330A"]["body"].startswith("(1) Seats shall be reserved for women in the House of the People.")
    assert "124C" in d and d["124C"]["body"].startswith("Parliament may, by law, regulate")
    assert "124C." not in d["124B"]["body"]
    for k in ("124", "124A", "124B", "124C", "127", "128", "217", "222", "224", "224A", "231"):
        assert "struck down by the Supreme Court" in d[k]["body"] and "AIR 2016 SC 117" in d[k]["body"]
    assert "339AA" not in d


def test_njac_articles_never_get_ai_explanation():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for a in ("124", "124A", "124B", "124C", "127", "128", "217", "222", "224", "224A", "231", "31C"):
        d = c.post("/api/v1/search/answer", json={"query": f"article {a}"}, auth=("u", "x")).json()
        t = d["ai_answer"]
        assert t.startswith("Important: the official edition's footnotes say"), a
        assert "Plain-English explanation" not in t, a
        assert "No AI explanation is shown for this article" in t, a
        assert "AI explanation" not in (d.get("tier_label") or ""), (a, d.get("tier_label"))
