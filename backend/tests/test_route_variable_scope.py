"""
Regression coverage for route-scoped variables in synthesize_search_answer.

Background: a patch applied with a repeated str.replace anchor inserted a
reference to `has_unresolved_caveat` (defined only in the statutory section
route) into the Constitution article route's matching-cases branch, causing
UnboundLocalError (HTTP 500) for article answers with matching precedents in
production. The full endpoint suite did not catch it because no test exercised
the article route's matching-cases branch directly.

These tests call the service with fabricated retrieval results so BOTH the
matching-cases and no-matching-cases branches of the article route AND the
section route (including its caveat-bearing paths) are executed
deterministically. Any undefined route variable raises and fails the test.
"""
import asyncio

from app.services.llm_service import LLMService


def _fabricated_case(statutes):
    return {
        "title": "Fabricated Route Test v. State",
        "citation": "(2026) 1 SCC 999",
        "statutes": statutes,
        "keywords": [],
        "aliases": [],
        "ratioSummary": "Fabricated ratio used only to exercise route branches.",
        "text": "Fabricated judgment body used only to exercise route branches.",
    }


def _ask(query, retrieved_cases):
    svc = LLMService()
    return asyncio.run(svc.synthesize_search_answer(query, retrieved_cases))


def test_article_route_with_matching_cases():
    # Article 14: not one of the special-cased articles (21/56/141), so it
    # exercises the generic in-force article branch WITH matching precedents -
    # the exact branch that 500'd in production.
    res = _ask(
        "What does Article 14 of the Constitution of India say?",
        [_fabricated_case(["Constitution of India Article 14"])],
    )
    assert isinstance(res, dict) and res.get("answer")
    assert res.get("results"), "matching-cases branch was not exercised"
    assert "Article 14" in res["answer"]


def test_article_route_without_matching_cases():
    res = _ask("What does Article 14 of the Constitution of India say?", [])
    assert isinstance(res, dict) and res.get("answer")
    assert "Article 14" in res["answer"]


def test_section_route_caveat_with_matching_cases():
    # BNS s.14 carries an unresolved verification caveat (Layout/Provenance
    # note). With matching precedents this exercises has_unresolved_caveat=True
    # in the matching-cases branch.
    res = _ask(
        "What is Section 14 of the Bharatiya Nyaya Sanhita?",
        [_fabricated_case(["Bharatiya Nyaya Sanhita Section 14"])],
    )
    assert isinstance(res, dict) and res.get("answer")
    assert res.get("results"), "matching-cases branch was not exercised"
    # Caveat-bearing text must stay reference-only even with precedents:
    # the answer must carry the caveat/reliance warning, not a confident label.
    assert "not authoritative" in res["answer"] or "reference only" in res["answer"]


def test_section_route_caveat_without_matching_cases():
    res = _ask("What is Section 14 of the Bharatiya Nyaya Sanhita?", [])
    assert isinstance(res, dict) and res.get("answer")
    assert res.get("tier_label") != "Authoritative statutory provision"
    assert "not authoritative" in res["answer"] or "reference only" in res["answer"]


def test_section_route_clean_provision_with_matching_cases():
    # BNSS s.35 is gazette-verified (no caveat): matching-cases branch with
    # has_unresolved_caveat=False.
    res = _ask(
        "What is Section 35 of the Bharatiya Nagarik Suraksha Sanhita?",
        [_fabricated_case(["Bharatiya Nagarik Suraksha Sanhita Section 35"])],
    )
    assert isinstance(res, dict) and res.get("answer")
    assert res.get("results"), "matching-cases branch was not exercised"
