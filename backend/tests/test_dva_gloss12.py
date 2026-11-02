import json
from app.services.llm_service import vetted_clause_explanation

def _s12():
    return json.load(open("app/ingest/dva_corpus.json"))["12"]["body"]

def test_s12_gloss_covers_all_five_clauses_with_dva_note():
    out = vetted_clause_explanation(_s12())
    assert out and "PARTIAL" not in out
    for m in ("(1):", "(2):", "(3):", "(4):", "(5):"):
        assert m in out
    assert "Protection of Women from Domestic Violence Act, 2005" in out and "Legislative Department" not in out

def test_s12_gloss_keeps_qualifiers_parties_and_numbers():
    out = vetted_clause_explanation(_s12())
    for w in ("respondent", "aggrieved person", "ordinarily", "endeavour", "three days", "sixty days", "set off", "decree", "domestic incident report", "Civil Procedure"):
        assert w in out
    assert "abuser" not in out and "victim" not in out

def test_changed_clause_text_drops_gloss():
    t = _s12().replace("three days", "five days")
    out = vetted_clause_explanation(t)
    assert out is None or "(4):" not in out or "PARTIAL" in out


def test_dva_glosses_match_corpus_and_keep_numbers():
    import re
    from app.services.llm_service import split_into_clauses
    import app.services.llm_service as L
    L.vetted_clause_explanation(_s12())
    segs = split_into_clauses(_s12())
    for e in [x for x in L._VETTED_GLOSSES.values() if x.get("act") == "dva"]:
        assert segs[e["clause_index"] - 1] == e["source"]
        nums = lambda t: sorted(re.findall(r"\b\d+\b", re.sub(r"\(\w{1,4}\)", "", t)))
        assert set(nums(e["gloss"])) <= set(nums(e["source"]))
