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
    assert "Solely" not in t and "NOTE WRITTEN FOR THIS APP" not in t


def test_239ab_edition_text_only():
    t = _ans("239AB")
    assert "for such period and subject to such conditions as may be specified in such law" in t
    assert "article 239 and article 239AA" in t
    assert "emergency mechanisms" not in t and "NOTE WRITTEN FOR THIS APP" not in t


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
    assert "Dalmia" not in t and "NOTE WRITTEN FOR THIS APP" not in t
    assert "Dawoodi" not in t
    r = c.post("/api/v1/search", json={"query": "article 14"}, auth=("u", "x")).json()
    assert all("Dawoodi" not in (x.get("title") or "") for x in r.get("results", []))
    assert not any("Dawoodi" in s for s in r.get("citations", []))
    # legitimate article 141 query still finds it
    r2 = c.post("/api/v1/search", json={"query": "article 141"}, auth=("u", "x")).json()
    assert any("Dawoodi" in (x.get("title") or "") for x in r2.get("results", []))


def test_multiarticle_case_still_matches_article_14():
    from app.services.qdrant_service import _ref_in
    statutes = ["Article 21", "Article 14", "Article 19", "Passports Act 1967"]
    assert any(_ref_in("article", "14", s) for s in statutes)
    assert not any(_ref_in("article", "14", s) for s in ["Article 141, Constitution of India", "Article 145(3), Constitution of India"])


def test_curated_notes_are_source_scoped():
    t21, t32, t141 = _ans("21"), _ans("32"), _ans("141")
    assert "[NOTE WRITTEN FOR THIS APP" in t21 and "headnote" in t21 and "rejecting narrow literalism" not in t21
    assert "emerges primarily from the guarantee of life and personal liberty" in t21
    assert "the very soul of the Constitution and the very heart of it" in t32
    assert "heart and soul" not in t32
    assert "binding on any subsequent Bench of lesser or coequal strength" in t141
    assert "Constitutional foundation of stare decisis" not in t141
    for a in ("356", "368"):
        t = _ans(a)
        assert "authoritatively held" not in t and "damaging, emasculating" not in t


def test_labels_match_content_for_notes_and_curated_summaries():
    d = c.post("/api/v1/search/answer", json={"query": "article 32"}, auth=("u", "x")).json()
    assert d["tier_label"].startswith("Statutory text + note written for this app")
    assert d["tier_label"] != "Authoritative statutory provision"
    assert "\n\n[NOTE WRITTEN FOR THIS APP" in d["ai_answer"]
    d56 = c.post("/api/v1/search/answer", json={"query": "article 56"}, auth=("u", "x")).json()
    assert "The statute text is shown above; any separately labelled case material below" in d56["ai_answer"] or "Plain-English explanation" in d56["ai_answer"] or d56["tier_label"] == "Authoritative statutory provision"
    from app.services.llm_service import case_passage_text
    cur = {"title": "X v. Y", "citation": "(2000) 1 SCC 1", "ratioSummary": "The Court explained the rule in plain words here.", "landmark": True}
    cp = case_passage_text(cur)
    assert cp.startswith("Case in this database tagged to this provision") and "plain words" not in cp
    raw = {"title": "X v. Y", "citation": "(2000) 1 SCC 1", "ratioSummary": "The Court explained the rule in plain words here."}
    assert "an excerpt from the judgment" in case_passage_text(raw)


def test_initials_do_not_truncate_case_summary():
    from app.services.llm_service import clean_case_summary
    s = clean_case_summary({"title": "K v. U", "ratioSummary": "The right to privacy is a fundamental right intrinsic to Article 21. The nine-judge bench expressly overruled M.P. Sharma (1954) to the extent they denied that status."})
    assert "M.P. Sharma" in s


def test_curated_case_prose_withheld_in_answer_and_cards_but_citation_kept():
    from app.services.qdrant_service import withhold_curated_summaries, WITHHELD_SUMMARY_LABEL
    cur = {"title": "K v. U", "citation": "(2017) 10 SCC 1", "ratioSummary": "Stored holding prose.", "ratioLabel": "CASE SUMMARY WRITTEN FOR THIS APP (NOT JUDGMENT TEXT; NOT VERIFIED)", "is_verified_ratio": True, "statutes": ["Article 21"]}
    raw = {"title": "A v. B", "citation": "(2000) 1 SCC 1", "ratioSummary": "Raw chunk text from the judgment.", "ratioLabel": "RELEVANT PASSAGE"}
    out = withhold_curated_summaries([cur, raw])
    assert out[0]["ratioLabel"] == WITHHELD_SUMMARY_LABEL and "Stored holding" not in out[0]["ratioSummary"]
    assert out[0]["citation"] == "(2017) 10 SCC 1" and out[0]["statutes"] == ["Article 21"]
    assert out[1] == raw
    d = c.post("/api/v1/search/answer", json={"query": "article 21"}, auth=("u", "x")).json()
    assert "proportionality test for state interference" not in d["ai_answer"]
    assert all("proportionality test" not in (x.get("ratioSummary") or "") for x in d["source_cases"])
    assert any("Puttaswamy" in (x.get("title") or "") for x in d["source_cases"])
    r = c.post("/api/v1/search", json={"query": "article 21"}, auth=("u", "x")).json()
    assert all("proportionality test" not in (x.get("ratioSummary") or "") for x in r["results"])
