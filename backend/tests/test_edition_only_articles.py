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
    assert "The statute text is shown above; any separately labelled case material below" in d56["ai_answer"] or "Plain-English explanation" in d56["ai_answer"] or d56["tier_label"].startswith("Statute text as stored in this database")
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


def test_case_chat_does_not_reuse_curated_holding():
    import asyncio
    from app.routers import casechat
    casechat._init_case_data()
    curated = [k for k, v in casechat._CASE_METADATA_INDEX.items()
               if v.get("_curated_ratio") and v.get("ratioSummary")]
    assert curated
    for cid in curated[:25]:
        meta = casechat._CASE_METADATA_INDEX[cid]
        assert casechat.is_curated_case_meta(meta)
        paras = casechat.get_case_chunks(cid)
        assert not any(meta["ratioSummary"][:60] in p.get("text", "") for p in paras
                       if "JUDICIAL HOLDING" in p.get("text", "")), cid


def test_case_chat_endpoint_refuses_without_judgment_text():
    import asyncio
    from app.routers import casechat
    casechat._init_case_data()
    cid = next(k for k, v in casechat._CASE_METADATA_INDEX.items()
               if v.get("_curated_ratio") and not casechat.get_case_chunks(k))
    class R: client = type("c", (), {"host": "t"})()
    req = type("Rq", (), {"client": type("c", (), {"host": "testhost"})(), "headers": {}})()
    payload = casechat.CaseChatRequest(case_id=cid, question="Summarise this case", messages=[])
    res = asyncio.run(casechat.post_case_chat(payload, req))
    assert res.model_used == "none"
    assert "not available in this database" in res.answer
    meta = casechat._CASE_METADATA_INDEX[cid]
    assert meta["ratioSummary"][:50] not in res.answer


def _corpus():
    import json, pathlib
    from app.services import llm_service as L
    return json.loads((pathlib.Path(L.__file__).resolve().parents[1] / "ingest" / "constitution_corpus.json").read_text(encoding="utf-8"))


def test_article_22_text_footnotes_and_app_note_are_separate_paragraphs():
    from app.services import llm_service as L
    b = _corpus()["22"]["body"]
    paras = b.split("\n\n")
    assert len(paras) == 4
    text, f1, f2, app = paras
    # article text: original clause (4) runs on into its provisos, with no substitute text spliced in
    assert 'Cl. (4) shall stand substituted' not in text and "two months" not in text
    assert "such detention: Provided that nothing in this sub-clause" in text
    assert "(c) the procedure to be followed by an Advisory Board" in text
    # footnote 1 holds the proposed substitution verbatim; footnote 2 the clause 7 changes
    assert f1.startswith("[Note from the official edition's footnotes (") and "two months" in f1 and "date yet to be notified" in f1
    assert f2.startswith("[Note from the official edition's footnotes (") and "re-lettered as sub-clause (a)" in f2
    assert app.startswith("[NOTE WRITTEN FOR THIS APP") and "does not say which wording" in app
    assert L.ADVERSE_FOOTNOTE_MARKER not in b and "notified). notified)" not in b


def test_footnote_residue_moved_out_of_articles_118_119_208_77():
    c = _corpus()
    b119 = c["119"]["body"]
    assert "Forty-second" not in b119 and b119.endswith("such provision shall prevail.")
    for k in ("118", "208"):
        paras = c[k]["body"].split("\n\n")
        assert len(paras) == 3 and "procedure*" in paras[0], k
        assert "Forty-second" not in paras[0], k
        assert paras[1].startswith("[Note from the official edition's footnotes (") and "Forty-second Amendment" in paras[1]
        assert paras[2].startswith("[NOTE WRITTEN FOR THIS APP")
    assert "the Chairman of the Legislative Council, may make rules as to the procedure" in c["208"]["body"].split("\n\n")[0]
    p77 = c["77"]["body"].split("\n\n")
    assert len(p77) == 3 and "S.O. 2297" not in p77[0] and "S.O. 2297" in p77[1] and "omitted by the Constitution (Forty-fourth" in p77[2]


def test_answer_keeps_footnote_notes_as_separate_paragraphs():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for q in ("article 22", "article 208", "article 77"):
        r = c.get("/api/v1/search/answer", params={"q": q})
        assert r.status_code == 200, q
        ans = r.json()["ai_answer"]
        paras = [p for p in ans.split("\n\n") if p.startswith("[Note from the official edition's footnotes")]
        assert paras, q
        for p in paras:
            assert p.endswith("]"), q


def test_page_bottom_footnotes_attached_to_100_102_105_189_191_194_not_101():
    import re
    c = _corpus()
    from app.services.citation_checker import _EDITION_NOTE_RE as rx
    for k in ("100", "102", "105", "189", "191", "194"):
        paras = c[k]["body"].split("\n\n")
        extra = {"105": 1, "191": 2, "194": 1}.get(k, 0)  # further edition footnotes added as their own boxes
        assert len(paras) == 3 + extra, k
        assert "Forty-second" not in paras[0], k
        assert rx.fullmatch(paras[1]) and "Forty-fourth Amendment) Act, 1978, s. 45" in paras[1], k
        for p in paras[2:-1]:
            assert rx.fullmatch(p), k
        assert paras[-1].startswith("[NOTE WRITTEN FOR THIS APP") and "does not say what applies today" in paras[-1], k
    # the 101 footnote on the same PDF page belongs to article 100 clauses 3 and 4, so 101 carries no note
    assert "Note from the official edition" not in c["101"]["body"]
    assert 'w.e.f. 19-6-1979)."' in c["194"]["body"]  # printed as such in the edition; kept verbatim


def test_every_edition_note_in_corpus_parses_whole_and_ends_at_its_own_bracket():
    import re
    from app.services.citation_checker import _EDITION_NOTE_RE
    c = _corpus()
    n = 0
    for k, v in c.items():
        body = v["body"]
        for m in re.finditer(r"\[Note from the official edition's footnotes", body):
            n += 1
            tail = body[m.start():]
            end = tail.index("]") + 1
            parsed = _EDITION_NOTE_RE.match(tail)
            assert parsed and parsed.group(0) == tail[:end], (k, "header/body boundary not parsed or note truncated")
            # the note must end at a real note end: end of body, a new paragraph, or a space then another block
            assert end == len(tail) or tail[end:end + 1] in (" ", "\n"), (k, "text glued to a note end")
    assert n >= 20, n
    # nested parentheses in the header (for example "sub-clause (a)") are accepted
    s = "[Note from the official edition's footnotes (to sub-clause (a) of clause 1, copied): body text.]"
    assert _EDITION_NOTE_RE.match(s).group(0) == s


def test_new_footnote_boxes_are_verbatim_in_the_edition_text():
    """Each edition-footnote box copied for these articles must occur, character for character
    (ignoring spacing and punctuation), in the edition's text. Skipped if the edition text file is absent."""
    import os, re
    path = "/tmp/coi26_layout.txt"
    if not os.path.exists(path):
        import pytest
        pytest.skip("edition layout text not available in this environment")
    E = re.sub(r"[^a-z0-9]", "", open(path, encoding="utf-8").read().lower())
    c = _corpus()
    rx = re.compile(r"\[Note from the official edition's footnotes (?:\((?:[^()]|\([^()]*\))*\))?:\s*(.*?)\]", re.S)
    for k in ("22", "77", "100", "102", "105", "118", "189", "191", "194", "208"):
        found = rx.findall(c[k]["body"])
        assert found, k
        for t in found:
            assert re.sub(r"[^a-z0-9]", "", t.lower()) in E, (k, t[:80])


def test_statute_results_never_get_an_authoritative_badge_and_scope_is_in_the_label():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for q in ("article 119", "article 21", "section 420 ipc"):
        d = c.get("/api/v1/search/answer", params={"q": q}).json()
        tl = (d.get("tier_label") or "").lower()
        assert "authoritative" not in tl, (q, tl)
    d = c.get("/api/v1/search/answer", params={"q": "article 119"}).json()
    assert d["tier_label"].startswith("Statute text as stored in this database")
    assert "not checked against current law" in d["tier_label"]


def test_frontend_no_explanation_block_is_neutral_not_orange():
    import pathlib
    s = (pathlib.Path(__file__).resolve().parents[2] / "src/components/SearchResults.jsx").read_text(encoding="utf-8")
    assert "NO AI EXPLANATION SHOWN" in s
    assert "_noExpl ? '#8a9a93'" in s
    assert "'STATUTE TEXT AS STORED (NOT CHECKED AGAINST CURRENT LAW)'" in s


def test_page_boundary_word_order_repairs_243P_and_243Y():
    c = _corpus()
    assert "means an institution of self-government constituted under article 243Q; (f)" in c["243P"]["body"]
    assert "(iii) the grants-in-aid to the Municipalities from the Consolidated Fund of the State; (b)" in c["243Y"]["body"]
    assert "means an constituted" not in c["243P"]["body"]
    assert "Consolidated Fund of the State; the Municipalities from the" not in c["243Y"]["body"]


def test_article_330_does_not_contain_the_text_of_330A_and_330A_keeps_its_own():
    c = _corpus()
    assert "330A. Reservation of seats for women" not in c["330"]["body"]
    assert "shall be reserved for women" not in c["330"]["body"].split("[2001] census.]")[-1]
    assert c["330"]["body"].rstrip().endswith("[2001] census.]")
    b = c["330A"]["body"]
    assert b.startswith("(1) Seats shall be reserved for women in the House of the People.")
    assert "Note from the official edition's footnotes (footnote 1 to the heading of this article" in b
    assert "w.e.f. 16-4-2026" in b
    # article 332 and 332A are already separate entries in the same shape
    assert c["332"]["body"].rstrip().endswith("shall be maintained.]")
    assert "332A. Reservation" not in c["332"]["body"]
    assert c["332A"]["body"].startswith("(1) Seats shall be reserved for women in the Legislative Assembly of every State.")


def test_106th_amendment_insertion_footnote_boxes_are_verbatim_and_app_text_is_separate():
    import re
    c = _corpus()
    expect = {
        "330A": "Ins. by the Constitution (One Hundred and Sixth Amendment) Act, 2023, s.3 (w.e.f. 16-4-2026).",
        "332A": "Ins. by the Constitution (One Hundred and Sixth Amendment) Act, 2023, s.4 (w.e.f. 16-4-2026).",
        "334A": "Ins. by the Constitution (One Hundred and Sixth Amendment) Act, 2023, s.5 (w.e.f. 16-4-2026).",
        "239AA": "Ins. by the Constitution (One Hundred and Sixth Amendment) Act, 2023,s. 2 (w.e.f. 16-4-2026).",
    }
    for k, text in expect.items():
        b = c[k]["body"]
        boxes = re.findall(r"\[Note from the official edition's footnotes \((?:[^()]|\([^()]*\))*\): (.*?)\]\n\n", b, re.S)
        assert boxes == [text], (k, boxes)
        assert "footnote 1 says" not in b and "footnote 2 says" not in b
        assert "This answer does not say" not in b and "Gazette notification was not read" not in b
        apps = re.findall(r"\[NOTE WRITTEN FOR THIS APP[^\]]*\]", b)
        assert len(apps) == 1 and b.rstrip().endswith(apps[0]), k
        assert "not a statement of when any seat is reserved" in apps[0]
        assert "does not say what applies today" in apps[0]
        assert "[Note on when this takes effect" not in b
    import os
    if os.path.exists("/tmp/coi26_layout.txt"):
        flat = re.sub(r"\s+", "", open("/tmp/coi26_layout.txt", encoding="utf-8").read())
        for text in expect.values():
            assert re.sub(r"\s+", "", text) in flat, text


def test_additional_edition_footnotes_105_191_194_are_verbatim_and_attached_boxes_precede_app_note():
    import os, re
    c = _corpus()
    expect = {
        "105": ["Subs. by the Constitution (Forty-fourth Amendment) Act, 1978, s. 15, for certain words (w.e.f. 20-6-1979)."],
        "191": ['Subs. by the Constitution (Fifty-second Amendment) Act, 1985, s. 5, for "(2) For the purposes of this article" (w.e.f. 1-3-1985).',
                "Ins. by s. 5, ibid. (w.e.f. 1-3-1985)."],
        "194": ["Subs. by the Constitution (Forty-fourth Amendment) Act, 1978, s. 26, for certain words (w.e.f. 20-6-1979)."],
    }
    flat = None
    if os.path.exists("/tmp/coi26_layout.txt"):
        flat = re.sub(r"\s+", "", open("/tmp/coi26_layout.txt", encoding="utf-8").read())
    for k, texts in expect.items():
        b = c[k]["body"]
        boxes = re.findall(r"\[Note from the official edition's footnotes \((?:[^()]|\([^()]*\))*\): (.*?)\]\n\n", b + "\n\n", re.S)
        for t in texts:
            assert t in boxes, (k, t)
            if flat:
                assert re.sub(r"\s+", "", t) in flat, t
        apps = re.findall(r"\[NOTE WRITTEN FOR THIS APP[^\]]*\]", b)
        assert len(apps) == 1 and b.rstrip().endswith(apps[0]), k
        assert "The footnotes in the boxes above" in apps[0]
    # 192's footnote 4 (printed on the same page as 191) must not be imported into 191
    assert "art. 192" not in c["191"]["body"]


def test_bracketed_articles_without_footnote_boxes_say_footnotes_are_not_shown():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    ans = c.get("/api/v1/search/answer", params={"q": "article 276"}).json()["ai_answer"]
    assert "Note from the official edition's footnotes" not in ans
    assert "This card does not show those footnotes" in ans
    assert "[NOTE WRITTEN FOR THIS APP - not part of the official text and not checked against current law: Square brackets" in ans
    # articles that already carry footnote boxes do not get the generic note
    ans105 = c.get("/api/v1/search/answer", params={"q": "article 105"}).json()["ai_answer"]
    assert "This card does not show those footnotes" not in ans105


def test_footnote_boxes_13_15_16_19_30_are_verbatim_in_edition_and_complete_for_bracketed_text():
    import os, re
    c = _corpus()
    counts = {"13": 1, "15": 3, "16": 5, "19": 7, "30": 1}
    flat = None
    if os.path.exists("/tmp/coi26_layout.txt"):
        flat = re.sub(r"\s+", "", open("/tmp/coi26_layout.txt", encoding="utf-8").read())
    for k, n in counts.items():
        b = c[k]["body"]
        boxes = re.findall(r"\[Note from the official edition's footnotes \((?:[^()]|\([^()]*\))*\): (.*?)\]\n\n", b + "\n\n", re.S)
        assert len(boxes) == n, (k, len(boxes))
        if flat:
            for t in boxes:
                assert re.sub(r"\s+", "", t) in flat, (k, t)
        apps = re.findall(r"\[NOTE WRITTEN FOR THIS APP[^\]]*\]", b)
        assert len(apps) == 1 and b.rstrip().endswith(apps[0]), k
    # the sub-heading footnote printed on the same page as 30(1A) is not an article 30 footnote
    assert "Right to Property" not in c["30"]["body"]


def test_footnote_boxes_1_and_3_are_verbatim_in_edition():
    import os, re
    c = _corpus()
    counts = {"1": 2, "3": 3, "112": 1, "31A": 7, "372": 2, "372A": 2}
    flat = None
    if os.path.exists("/tmp/coi26_layout.txt"):
        flat = re.sub(r"\s+", "", open("/tmp/coi26_layout.txt", encoding="utf-8").read())
    for k, n in counts.items():
        b = c[k]["body"]
        boxes = re.findall(r"\[Note from the official edition's footnotes \((?:[^()]|\([^()]*\))*\): (.*?)\]\n\n", b + "\n\n", re.S)
        assert len(boxes) == n, (k, len(boxes))
        if flat:
            for t in boxes:
                assert re.sub(r"\s+", "", t) in flat, (k, t)
        apps = re.findall(r"\[NOTE WRITTEN FOR THIS APP[^\]]*\]", b)
        assert len(apps) == 1 and b.rstrip().endswith(apps[0]), k


def test_article_and_section_match_uses_token_boundary_not_prefix():
    from app.services.llm_service import match_case_to_query_entities as m
    case = {"title": "X v. Y", "statutes": ["Article 141, Constitution of India", "Article 145(3), Constitution of India", "Section 124, IPC"]}
    ents = lambda **k: dict({"case_names": [], "citations": [], "sections": [], "articles": []}, **k)
    assert m(ents(articles=["1"]), case) is False
    assert m(ents(articles=["14"]), case) is False
    assert m(ents(articles=["145"]), case) is True
    assert m(ents(articles=["141"]), case) is True
    assert m(ents(sections=["12"]), case) is False
    assert m(ents(sections=["124"]), case) is True
    assert m({"case_names": [], "citations": [], "sections": [], "articles": ["14"]}, {"title": "Z", "statutes": ["Article 14(1), Constitution of India"]}) is True
    assert m({"case_names": [], "citations": [], "sections": [], "articles": ["21"]}, {"title": "Z", "statutes": ["Article 21A, Constitution of India"]}) is False


def test_token_boundary_matrix_keeps_variant_true_matches():
    from app.services.llm_service import match_case_to_query_entities as m
    E = lambda **k: dict({"case_names": [], "citations": [], "sections": [], "articles": []}, **k)
    keep = [  # (statute string, query kind, number) that must still match
        ("Article 14, Constitution of India", "articles", "14"), ("Article 14(1), Constitution of India", "articles", "14"),
        ("Article 19(1)(a)", "articles", "19"), ("Article 21A", "articles", "21A"), ("Article 14-A", "articles", "14"),
        ("Article 14/15", "articles", "14"), ("Article 14 of the Constitution", "articles", "14"),
        ("Section 124A IPC", "sections", "124A"), ("Section 124, IPC", "sections", "124"), ("Section 304B IPC", "sections", "304B"),
        ("Sec. 124 IPC", "sections", "124"), ("s. 124 IPC", "sections", "124"),
    ]
    for st, kind, n in keep:
        assert m(E(**{kind: [n.lower()]}), {"title": "Z v. Q", "statutes": [st]}) is True, (st, n)
    drop = [("Article 14, Constitution of India", "articles", "1"), ("Article 19(1)(a)", "articles", "1"), ("Article 21A", "articles", "21"),
            ("Article 14/15", "articles", "1"), ("Section 124A IPC", "sections", "124"), ("Section 124A IPC", "sections", "12"), ("Section 304B IPC", "sections", "304")]
    for st, kind, n in drop:
        assert m(E(**{kind: [n.lower()]}), {"title": "Z v. Q", "statutes": [st]}) is False, (st, n)


def test_31A_body_keeps_clause_1_label_and_bracket_and_tenure_holder_hyphen():
    c = _corpus()
    b = c["31A"]["body"]
    assert b.startswith("[(1) Notwithstanding anything contained in article 13")
    assert "tenure-holder, [raiyat, under-raiyat]" in b and "tenureholder" not in b
    assert b.count("[(1) ") == 1
    assert "the bracketed clause 1 of the article" in b


def test_line_end_hyphen_compounds_are_not_joined_in_bodies():
    import re
    c = _corpus()
    joined = ["AuditorGeneral", "AngloIndian", "Fiftyseventh", "HyderabadKarnataka", "Ninetyseventh", "Thirtysixth",
              "twentysixth", "VicePresident", "allIndia", "fortysix", "grantsin-aid", "interState", "nonacceptance",
              "nonagricultural", "socioeconomic", "subclause", "twothirds"]
    for k, v in c.items():
        for w in joined:
            assert not re.search(r"(?<![A-Za-z-])" + w, v["body"]), (k, w)
    assert "Auditor-General of India" in c["151"]["body"] and "Vice-President shall act as President" in c["65"]["body"]
    assert "sub-clause (a) or sub-clause (b) of clause (2)" in c["244A"]["body"]


def test_372_has_no_stray_next_article_opener_and_two_boxes():
    b = _corpus()["372"]["body"]
    main = b.split("\n\n[Note from")[0]
    assert not main.rstrip().endswith("[") and main.rstrip().endswith("beyond the said period.")
    assert "1[" not in b and "Adaptation of Laws Order, 1950" in b
