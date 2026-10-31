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


def test_cheque_bounce_returns_verbatim_statute_not_model_text():
    from app.services.verified_statute_notes import verified_note_for
    n = verified_note_for("my cheque bounced what can i do")
    assert n and "within thirty days of the receipt of information" in n["answer"]
    assert "within fifteen days of the receipt of the said notice" in n["answer"]
    assert "within one month of the date on which the cause of action arises" in n["answer"]
    assert verified_note_for("cheque book request letter") is None
    assert verified_note_for("article 14") is None


def test_cheque_route_in_synthesis_skips_llm():
    import asyncio
    from app.services.llm_service import LLMService
    s = LLMService.__new__(LLMService)
    r = asyncio.run(s.synthesize_search_answer("cheque bounce notice period", []))
    assert r["model_used"] == "verified_statute_text" and "Dishonour of cheque" in r["answer"]


def test_summary_fragments_are_not_usable():
    from app.services.llm_service import summary_is_usable
    assert not summary_is_usable("or (b) the use of wells, tanks, bathing ghats, roads and places of public resort maintained wholly")
    assert not summary_is_usable("(a) access to shops, public restaurants, hotels and places of public entertainment; or (b) the use")
    assert summary_is_usable("Equality and arbitrariness are sworn enemies; an act that is arbitrary necessarily violates equality.")


def test_cheque_note_flags_current_applicability_unverified():
    from app.services.verified_statute_notes import verified_note_for
    a = verified_note_for("cheque bounce")["answer"]
    assert "CURRENT APPLICABILITY NOT VERIFIED" in a and "three months" in a and "rbi.org.in" in a


def test_unavailable_explanation_is_not_cached():
    import inspect
    from app.routers import search
    src = inspect.getsource(search.search_answer_post)
    assert 'temporarily )?unavailable' in src


def test_tpd_429_trips_breaker_and_changes_note():
    import app.services.llm_service as m
    m._RL_UNTIL = 0.0
    assert "faithfulness" in m.explanation_unavailable_note()
    m._note_rate_limit(Exception("429 Rate limit reached ... on tokens per day (TPD): Limit 200000"))
    try:
        assert m.model_rate_limited()
        assert "usage limit" in m.explanation_unavailable_note()
    finally:
        m._RL_UNTIL = 0.0


def test_explanation_numbers_must_come_from_source():
    from app.services.llm_service import explanation_numbers_ok as ok
    src = "The President shall, at the expiration of ten years, appoint a Commission."
    assert ok(src, "The President must appoint a commission at the end of ten years.")
    assert ok(src, "Appoint a commission after 10 years.")
    assert not ok(src, "The commission must report within two years.")
    assert not ok(src, "Appoint within 30 days.")
    assert ok("any person within 6 months", "Within six months any person may act.")


def test_pronoun_one_is_not_a_number():
    from app.services.llm_service import explanation_numbers_ok as ok
    assert ok("No person shall be deprived of his property save by authority of law.", "No one can be deprived of property unless a law allows it.")
