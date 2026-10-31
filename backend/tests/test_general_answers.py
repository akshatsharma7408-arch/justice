import asyncio
from types import SimpleNamespace as NS
from app.services.llm_service import LLMService, _tier2_numeric_claim
from app.services.answer_tiers import needs_specific_source


def test_numeric_claim_detected():
    assert _tier2_numeric_claim("File within 30 days of the notice.")
    assert _tier2_numeric_claim("The fine is Rs. 500.")
    assert _tier2_numeric_claim("It depends on the specific law and State.") is None


def test_in_india_is_not_a_landmark_case_request():
    assert needs_specific_source("can my landlord keep my security deposit in india") is False
    assert needs_specific_source("indira gandhi vs raj narain") is True


def _svc(text):
    class M:
        def generate_content(self, **kw):
            return NS(text=text)
    o = LLMService.__new__(LLMService)
    o._client = NS(models=M()); o.is_active = True; o.api_key = "x"; o.model = "m"
    return o


def test_relevance_gate_keeps_only_listed_and_fails_closed():
    cases = [{"title": "A", "ratioSummary": "x"}, {"title": "B", "ratioSummary": "y"}]
    assert asyncio.run(_svc("2")._filter_topically_relevant_cases("q", cases)) == [cases[1]]
    assert asyncio.run(_svc("NONE")._filter_topically_relevant_cases("q", cases)) == []
    o = LLMService.__new__(LLMService); o._client = None; o.is_active = False; o.api_key = ""
    assert asyncio.run(o._filter_topically_relevant_cases("q", cases)) == []


def test_multi_article_split_and_bare_article():
    from app.routers.search import split_multi_article, resolve_bare_article
    assert split_multi_article("article 14 or 15") == ["14", "15"]
    assert split_multi_article("articles 14, 15 and 16") == ["14", "15", "16"]
    assert split_multi_article("article 21") is None
    assert resolve_bare_article("300A") == "article 300A"
    assert resolve_bare_article("what is 21A") == "article 21A"
    assert resolve_bare_article("498A") == "498A"
    assert resolve_bare_article("what is bail") == "what is bail"


def test_forum_claims_rejected_and_bullets_split():
    from app.services.llm_service import _tier2_with_gap_note
    assert _tier2_numeric_claim("You can approach the consumer forum.")
    assert _tier2_numeric_claim("File a suit in the civil court.")
    assert _tier2_numeric_claim("Check which forum applies and ask a lawyer.") is None
    out = _tier2_with_gap_note("- One thing. - Another thing.")
    assert "\n\n- Another" in out


def test_summary_usable_rejects_ocr_junk():
    from app.services.llm_service import summary_is_usable
    assert not summary_is_usable("430 A B c D E F G H (1992) 3 S.C.R.")
    assert not summary_is_usable("This precedent establishes authoritative judicial doctrine on the issue.")
    assert summary_is_usable("The protection of this Article is available to any person including a legal person.")


def test_timing_expiry_not_rewritten_as_after():
    src = "The President may at any time and shall, at the expiration of ten years from the commencement, appoint a Commission."
    o = _svc("1 | The President may at any time | OK")
    assert asyncio.run(o._explanation_is_grounded(src, "The President must act after ten years from the start.")) is False
