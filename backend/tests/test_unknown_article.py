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
    for a in ("124", "124A", "124B", "124C", "127", "128", "217", "222", "224", "224A", "231", "31C", "370", "368", "371D"):
        d = c.post("/api/v1/search/answer", json={"query": f"article {a}"}, auth=("u", "x")).json()
        t = d["ai_answer"]
        assert t.startswith("Important: the official edition's footnotes say"), a
        assert "Note from the official edition's footnotes:" in t, a  # must survive the citation sentence filter
        assert "unconstitutional and void" in t or a != "371D", a
        assert "Plain-English explanation" not in t, a
        assert "No AI explanation is shown for this article" in t, a
        assert "AI explanation" not in (d.get("tier_label") or ""), (a, d.get("tier_label"))


def test_330a_332a_never_get_ai_explanation_and_point_to_334a():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for a in ("330A", "332A"):
        d = c.post("/api/v1/search/answer", json={"query": f"article {a}"}, auth=("u", "x")).json()
        t = d["ai_answer"]
        assert "334A" in t and "Plain-English explanation" not in t and "No AI explanation is shown" in t, a


def test_scoped_edition_footnote_articles_show_note_and_withhold_explanation():
    import os
    os.environ["QDRANT_URL"] = "http://localhost:1"
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    want = {
        "367": ["C.O. 272", "Appendix II", "(w.e.f. 5-8-2019)"],
        "371A": ["Removal of Difficulties) Order No. X", "1-12-1963", "Minister for Tuensang affairs", "does not say whether that Order is in force today"],
        "239A": ["made applicable to Union Territory of Jammu and Kashmir", "34 of 2019", "31-10-2019"],
    }
    for a, frags in want.items():
        t = c.post("/api/v1/search/answer", json={"query": f"article {a}"}, auth=("u", "x")).json()["ai_answer"]
        assert "Note from the official edition's footnotes (reference to another instrument):" in t, a
        for f in frags:
            assert f in t, (a, f)
        assert "No AI explanation is shown for this article" in t, a
        assert "Plain-English explanation" not in t and "AI RESTATEMENT" not in t, a
        assert "struck down" not in t.split("Note from the official edition")[0], a  # no inherited struck-down lead
        assert "Important: the official edition's footnotes say part of this article's wording was struck down" not in t, a


def test_124_keeps_njac_note_and_adds_thirty_three_pointer():
    import os
    os.environ["QDRANT_URL"] = "http://localhost:1"
    from fastapi.testclient import TestClient
    from app.main import app
    t = TestClient(app).post("/api/v1/search/answer", json={"query": "article 124"}, auth=("u", "x")).json()["ai_answer"]
    assert "AIR 2016 SC 117" in t and "Important: the official edition's footnotes say" in t
    assert "Now thirty-three vide the Supreme Court (Number of Judges) Amendment Act, 2019 (37 of 2019)" in t
    assert "That Act has not been checked here" in t
    assert "No AI explanation is shown for this article" in t


def test_106th_insertion_date_notes_and_exact_334a_wording():
    import os
    os.environ["QDRANT_URL"] = "http://localhost:1"
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    q = "shall come into effect after an exercise of delimitation is undertaken for this purpose after the relevant figures for the first census taken after commencement of the Constitution (One Hundred and Sixth Amendment) Act, 2023 have been published and shall cease to have effect on the expiration of a period of fifteen years from such commencement"
    for a, sec in (("330A", "s. 3"), ("332A", "s. 4"), ("334A", "s. 5"), ("239AA", "s. 2")):
        t = c.post("/api/v1/search/answer", json={"query": f"article {a}"}, auth=("u", "x")).json()["ai_answer"]
        assert "Note from the official edition's footnotes (insertion date):" in t, a
        assert sec + " (w.e.f. 16-4-2026)" in t, a
        assert "does not say when any seat is reserved" in t, a
        assert "The Gazette notification was not read as a PDF" in t, a
        assert "No AI explanation is shown for this article" in t, a
        assert "Plain-English explanation" not in t and "AI RESTATEMENT" not in t, a
        if a in ("330A", "332A"):
            assert q in t and "Important: this article does not say by itself when it takes effect" in t, a


def test_239aa_served_from_edition_text_not_handwritten_summary():
    import os
    os.environ["QDRANT_URL"] = "http://localhost:1"
    from fastapi.testclient import TestClient
    from app.main import app
    t = TestClient(app).post("/api/v1/search/answer", json={"query": "article 239AA"}, auth=("u", "x")).json()
    a = t["ai_answer"]
    assert t["tier_label"] == "Edition text with a footnote note (see the text)"
    assert "(ba) Seats shall be reserved for women in the Legislative Assembly of the National Capital Territory of Delhi" in a
    assert "(bc) As nearly as may be, one-third of the total number of seats to be filled by direct election" in a
    assert "clauses (ba), (bb) and (bc) were inserted by the Constitution (One Hundred and Sixth Amendment) Act, 2023, s. 2 (w.e.f. 16-4-2026)" in a
    assert "No AI explanation is shown for this article" in a
    assert "GNCTD" not in a and "8 SCC 501" not in a and "constitutional morality" not in a
