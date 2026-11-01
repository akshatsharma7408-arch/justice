import pytest
from app.services.llm_service import case_passage_text

def _c(t): return {"title": "A v. B", "citation": "(2000) 1 SCC 1", "text": t}

@pytest.mark.parametrize("t", [
    "We are of the view that the order must be set aside for the reasons given.",
    "The appellant argued that this Court has held that the notice was invalid in every case.",
    "The High Court held that the claim was barred, and the appeal followed in this Court.",
    "It was not held that the tenant could be evicted without notice under the Act.",
    "A letter was addressed by the Executive Engineer to the Registrar of the High Court.",
])
def test_raw_chunk_is_never_called_a_holding(t):
    r = case_passage_text(_c(t))
    assert r is None or ("not a verified holding" in r and "the Supreme Court held" not in r)

def test_mid_sentence_fragment_is_dropped():
    assert case_passage_text(_c("had never opted for pensionary benefits and the period was extended further.")) is None


def test_dynamic_case_routes_do_not_use_ai_summary_badge():
    import re, pathlib
    src = pathlib.Path("app/services/llm_service.py").read_text()
    # every route that builds its case text with case_passage_text must label it an excerpt, not an AI summary
    for m in re.finditer(r"case_passage_text\(c0\)", src):
        window = src[m.end(): m.end() + 900]
        assert "case excerpt (not a verified holding)" in window
        assert "AI summary based on the cases below" not in window.split("else:")[0]


def test_excerpt_carries_scan_error_warning_and_keeps_text_unchanged():
    t = "Every citizen has a mndamental right to have the enjoyment of quality of life under Artkte 21."
    r = case_passage_text(_c(t))
    assert "mndamental" in r and "Artkte" in r  # judgment text is not silently rewritten
    assert "character-recognition errors" in r
