import json, re, hashlib, os, asyncio
from app.services.llm_service import vetted_clause_explanation, split_into_clauses, LLMService

DATA = os.path.join(os.path.dirname(__file__), "..", "app", "data")
CORPUS = json.load(open(os.path.join(DATA, "..", "ingest", "constitution_corpus.json")))
G = json.load(open(os.path.join(DATA, "..", "ingest", "vetted_clause_glosses.json")))
MODALS = ("shall", "may", "must", "nothing", "not ", "no ")

def test_each_gloss_keeps_numbers_and_negation_of_its_clause():
    for e in [x for x in G.values() if "article" in x]:
        s, g = e["source"].lower(), e["gloss"].lower()
        assert not re.findall(r"\b\d+\b", re.sub(r"\(\w+\)", "", s)) and not re.findall(r"\b\d+\b", re.sub(r"\(\w+\)", "", g))
        for w in ("six", "fourteen"):
            assert (w in s) == (w in g)
        assert ("nothing" in s) == ("does not" in g or "do not" in g)
        for t in ("sovereignty", "humanism", "composite", "scheduled tribe", "defamation", "contempt of court"):
            assert (t in s) == (t in g), (e["article"], e["clause_index"], t)

def test_glosses_match_current_corpus_text():
    for e in [x for x in G.values() if "article" in x]:
        segs = split_into_clauses(CORPUS[e["article"]]["body"])
        assert segs[e["clause_index"] - 1] == e["source"]

def test_art_51a_full_and_art_19_partial_names_omitted():
    a = vetted_clause_explanation(CORPUS["51A"]["body"])
    assert a and "PARTIAL" not in a and "(k):" in a
    b = vetted_clause_explanation(CORPUS["19"]["body"])
    assert b and "PARTIAL EXPLANATION" in b and "(6)" in b.split("PARTIAL EXPLANATION")[1] and "(i)" in b.split("PARTIAL EXPLANATION")[1]

def test_changed_source_is_not_explained():
    body = CORPUS["51A"]["body"].replace("six and fourteen", "six and sixteen")
    out = vetted_clause_explanation(body)
    assert out and "PARTIAL EXPLANATION" in out and "(k)" in out.split("PARTIAL EXPLANATION")[1]

def test_works_with_no_llm():
    svc = LLMService()
    out = asyncio.run(svc.explain_provision_ai("Article 51A", CORPUS["51A"]["body"]))
    assert out and "(c): to uphold and protect the sovereignty" in out

def test_note_states_edition_and_review_limits():
    out = vetted_clause_explanation(CORPUS["19"]["body"])
    assert "May 2022" in out and "no lawyer has reviewed" in out and "not explained here" in out


def test_case_header_debris_is_not_a_usable_summary():
    from app.services.llm_service import summary_is_usable
    bad = "NA VEEN JINDAL [ V.N. KHARE, CJ.] 1069 Part III of the Constitution of India, apart from clauses 2 to 4 and 6 of Article A 19 of the Constitution of India."
    assert not summary_is_usable(bad)
    assert summary_is_usable("The Court held that a statute violating a fundamental right is void to the extent of the inconsistency.")


def test_summary_about_a_different_article_is_withheld():
    from app.services.llm_service import summary_is_about_other_article as f
    s = "the level of nutrition and the standard of living and to improve the public health. Under Article 48, the State is duty bound to endeavour to organise agriculture."
    assert f(s, "51A")
    assert not f(s, "48")
    assert not f("The Court held duties under Article 51A are enforceable alongside Article 48.", "51A")
    assert not f("The Court held that the right is not absolute.", "51A")
    assert f("Duties under Article 51A are enforceable.", "51")
