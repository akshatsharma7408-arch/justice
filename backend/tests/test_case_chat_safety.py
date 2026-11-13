"""
Safety regression tests for Case Chat deterministic paths.

The deterministic summary/Q&A/explanation paths must never turn metadata or an
arbitrary text chunk into a holding, a binding-precedent claim, or an Article 141
claim. They quote clearly labelled unverified excerpts or decline instead.
"""

import asyncio
import sys
import base64
from pathlib import Path

import socket
import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Blocks all outbound sockets: any model/API call attempt fails loudly,
    proving these deterministic paths make no network calls."""
    def _blocked(*a, **k):
        raise AssertionError("outbound network call attempted during offline safety test")
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)


import pytest

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app, SITE_PASSWORD
from app.routers import casechat

headers = {}
if SITE_PASSWORD:
    b64 = base64.b64encode(f"admin:{SITE_PASSWORD}".encode()).decode()
    headers["Authorization"] = f"Basic {b64}"
client = TestClient(app, headers=headers)

FORBIDDEN = [
    "Binding precedent declared",
    "binding precedent under Article 141",
    "Authoritative adjudication",
    "establishes authoritative binding precedent",
    "The court held:",
    "The Supreme Court held that",
    "this judicial holding is binding precedent",
    "JUDICIAL HOLDING & RATIO DECIDENDI",
    "LEGAL DOCTRINE & APPLICATION",
]

FIXTURE_META = {
    "case_id": "fixture-case-1",
    "title": "Alpha Traders v. State of Testland",
    "citation": "(2020) 1 SCC 999",
    "court": "Supreme Court of India",
    "year": 2020,
    "ratioSummary": "",
    "statutes": ["Section 27 of the Indian Contract Act, 1872"],
    "keywords": ["restraint of trade"],
}

FIXTURE_CHUNKS = [
    {"chunk_id": "fc0", "chunk_index": 0, "case_id": "fixture-case-1",
     "case_name": "Alpha Traders v. State of Testland",
     "text": "The appellant challenged the registration of the impugned order before the tribunal. The facts concern a dealership agreement."},
    {"chunk_id": "fc1", "chunk_index": 1, "case_id": "fixture-case-1",
     "case_name": "Alpha Traders v. State of Testland",
     "text": "The registration issue was procedural. No substantive question of registration law arises here."},
    {"chunk_id": "fc2", "chunk_index": 2, "case_id": "fixture-case-1",
     "case_name": "Alpha Traders v. State of Testland",
     "text": "For the reasons given above, we hold that the clause is void to the extent of the restriction. The appeal is allowed."},
]


def test_decision_excerpt_ignores_registration_substring():
    """'registration' contains 'ratio'; a substring scan must not select it."""
    chunks = FIXTURE_CHUNKS[:2]
    excerpt, idx = casechat.find_decision_excerpt(chunks)
    assert excerpt is None and idx is None


def test_decision_excerpt_finds_real_marker():
    excerpt, idx = casechat.find_decision_excerpt(FIXTURE_CHUNKS)
    assert excerpt is not None
    assert idx == 2
    assert "we hold that the clause is void" in excerpt


def test_deterministic_summary_has_no_fabricated_holding():
    summary = casechat.generate_deterministic_summary(FIXTURE_META, FIXTURE_CHUNKS)
    for phrase in FORBIDDEN:
        assert phrase not in summary, phrase
    # Excerpt is quoted with its unverified label, not asserted as the holding.
    assert "unverified excerpt" in summary
    assert "we hold that the clause is void" in summary
    assert "Auto-generated from stored excerpts; not verified" in summary


def test_deterministic_summary_without_marker_declines():
    summary = casechat.generate_deterministic_summary(FIXTURE_META, FIXTURE_CHUNKS[:2])
    for phrase in FORBIDDEN:
        assert phrase not in summary, phrase
    assert "cannot reliably state what the court decided" in summary


def test_deterministic_qa_decide_branch_labels_excerpt():
    ans, based_on, para_id = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "What did the court decide about the clause and the restriction?")
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase
    assert "unverified excerpt" in ans
    assert "we hold that the clause is void" in ans
    assert based_on == "Paragraph 3"


def test_deterministic_qa_why_and_laws_branches_are_neutral():
    ans, _, _ = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "What is the impact of the clause restriction?")
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase
    assert "does not assess this case's precedent status" in ans

    ans, _, _ = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "Which laws or sections were used for the clause restriction?")
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase
    assert "app metadata" in ans


def test_synthetic_paragraphs_carry_no_doctrine(monkeypatch):
    """Metadata-only fallback paragraphs must not fabricate a holding or Article 141 doctrine."""
    monkeypatch.setattr(casechat, "_DATA_INITIALIZED", True)
    monkeypatch.setattr(casechat, "_CHUNKS_BY_CASE", {})
    monkeypatch.setattr(casechat, "LANDMARK_ID_TO_SC_MAP", {})
    meta = dict(FIXTURE_META, ratioSummary="App-written unchecked summary prose.")
    monkeypatch.setattr(casechat, "_CASE_METADATA_INDEX", {"meta-only-case": meta})
    paras = casechat.get_case_chunks("meta-only-case")
    assert paras, "expected synthetic metadata paragraphs"
    joined = "\n".join(p["text"] for p in paras)
    for phrase in FORBIDDEN:
        assert phrase not in joined, phrase
    assert "APP RECORD - STORED SUMMARY" in joined
    assert "not judgment text" in joined


def test_deterministic_explanation_of_case_text_has_no_holding_claim():
    exp = casechat.generate_deterministic_explanation(
        "the clause in restraint of trade is void", context="Case: Alpha Traders (2020)")
    for phrase in FORBIDDEN:
        assert phrase not in exp["explanation"], phrase
    assert "not verified what the judgment decides" in exp["explanation"]


@pytest.fixture
def fixture_case():
    """Injects a grounded fixture case (metadata + chunks) into the case store,
    so endpoint routing is exercised offline without Qdrant or chunk data."""
    prev_init = casechat._DATA_INITIALIZED
    casechat._DATA_INITIALIZED = True
    casechat._CHUNKS_BY_CASE["fixture-endpoint-case"] = FIXTURE_CHUNKS
    casechat._CASE_METADATA_INDEX["fixture-endpoint-case"] = FIXTURE_META
    yield "fixture-endpoint-case"
    casechat._CHUNKS_BY_CASE.pop("fixture-endpoint-case", None)
    casechat._CASE_METADATA_INDEX.pop("fixture-endpoint-case", None)
    casechat._DATA_INITIALIZED = prev_init


def test_endpoint_fallback_summary_has_no_forbidden_claims(fixture_case):
    res = client.post("/api/case-chat", json={
        "case_id": fixture_case, "question": "Summarise this case", "force_fallback": True})
    assert res.status_code == 200
    data = res.json()
    for phrase in FORBIDDEN:
        assert phrase not in data["answer"], phrase
    assert data["disclaimer"] == "Auto-generated from stored excerpts; not verified. Not legal advice."


def test_endpoint_fallback_decide_question_has_no_forbidden_claims(fixture_case):
    res = client.post("/api/case-chat", json={
        "case_id": fixture_case,
        "question": "What did the court decide about the clause and the restriction?",
        "force_fallback": True})
    assert res.status_code == 200
    data = res.json()
    for phrase in FORBIDDEN:
        assert phrase not in data["answer"], phrase
    assert "unverified excerpt" in data["answer"] or "cannot" in data["answer"]

def test_quick_button_wording_reaches_grounded_handling():
    """Exact quick-button questions must reach grounded deterministic handling even
    though their literal words do not appear in the fixture chunks."""
    ans, _, _ = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "What did the court decide?")
    assert ans != casechat.UNABLE_LINE
    assert "cannot state the decision itself" in ans
    assert "unverified excerpt" in ans
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase

    ans, _, _ = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "Who were the parties?")
    assert ans != casechat.UNABLE_LINE
    assert "Alpha Traders" in ans
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase

    ans, _, _ = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "Why does it matter for ordinary people?")
    assert ans != casechat.UNABLE_LINE
    assert "does not assess this case's precedent status" in ans
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase

    ans, _, _ = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "Which laws or sections were used?")
    assert ans != casechat.UNABLE_LINE
    assert "record lists these laws" in ans
    for phrase in FORBIDDEN:
        assert phrase not in ans, phrase


def test_genuinely_unsupported_question_declines_honestly():
    """Word-overlap failure must not assert judgment silence; it declines honestly."""
    ans, based_on, para_id = casechat.generate_deterministic_case_answer(
        FIXTURE_META, FIXTURE_CHUNKS, "What does this case say about bitcoin custody rules?")
    assert ans == casechat.UNABLE_LINE
    assert "cannot establish an answer" in ans
    assert "does not say that" not in ans



# ---------------------------------------------------------------------------
# Holding-claim quote verification (model path -> deterministic check)
# ---------------------------------------------------------------------------

class _FakeModels:
    def __init__(self, text):
        self._text = text

    def generate_content(self, contents=None, config=None):
        class _Res:
            pass
        r = _Res()
        r.text = self._text
        return r


class _FakeClient:
    def __init__(self, text):
        self.models = _FakeModels(text)


class _FakeLLMService:
    def __init__(self, text):
        self.is_active = True
        self.client = _FakeClient(text)


PARA_MAP = [(c["chunk_index"] + 1, c["text"]) for c in FIXTURE_CHUNKS]


def test_verify_holding_claims_no_claims_passes():
    ok, supporting = casechat.verify_holding_claims(
        "In this case, the appellant was Alpha Traders and the respondent was the State of Testland.",
        PARA_MAP,
    )
    assert ok is True
    assert supporting == []


def test_verify_holding_claims_verbatim_quote_passes():
    ans = ('The court held that the clause was void: '
           '"we hold that the clause is void to the extent of the restriction".')
    ok, supporting = casechat.verify_holding_claims(ans, PARA_MAP)
    assert ok is True
    assert supporting == [3]


def test_verify_holding_claims_fabricated_quote_fails():
    ans = ('The court held that the agreement was unenforceable: '
           '"we hold that the entire agreement is void ab initio".')
    ok, _ = casechat.verify_holding_claims(ans, PARA_MAP)
    assert ok is False


def test_verify_holding_claims_claim_without_quote_fails():
    ans = "The Court held that the clause was a restraint of trade and therefore void under Section 27."
    ok, _ = casechat.verify_holding_claims(ans, PARA_MAP)
    assert ok is False


def test_llm_answer_with_unsupported_holding_falls_back(monkeypatch):
    """A model answer asserting a holding without a verifiable quote must be
    replaced by the honest deterministic limited response, not shown."""
    raw = ("The Court held that the agreement was a restraint of trade and therefore void under Section 27. "
           "The injunction was wrong.\n\nBased on: Paragraphs 2, 3")
    monkeypatch.setattr(casechat, "llm_service", _FakeLLMService(raw))
    ans, based_on, para_id, used_model = asyncio.run(
        casechat.answer_case_question(FIXTURE_META, FIXTURE_CHUNKS, "What did the court decide?")
    )
    assert "The Court held that" not in ans
    assert "unverified excerpt" in ans or "cannot state the decision" in ans
    assert used_model is False


def test_llm_answer_with_verified_quote_passes_and_corrects_badge(monkeypatch):
    """A model answer whose holding claim carries a verbatim quote passes; the
    Based-on badge is corrected to the paragraph actually containing the quote."""
    raw = ('The court held the clause void to a limited extent: '
           '"we hold that the clause is void to the extent of the restriction". '
           'This means only the restricting part falls away.\n\nBased on: Paragraph 1')
    monkeypatch.setattr(casechat, "llm_service", _FakeLLMService(raw))
    ans, based_on, para_id, used_model = asyncio.run(
        casechat.answer_case_question(FIXTURE_META, FIXTURE_CHUNKS, "What did the court decide?")
    )
    assert "we hold that the clause is void to the extent of the restriction" in ans
    assert based_on == "Paragraph 3"
    assert para_id == "chunk-2"
    assert used_model is True


def test_llm_summary_with_unsupported_holding_falls_back(monkeypatch):
    """A model summary whose decided-section asserts an unverifiable holding must
    be replaced by the deterministic summary."""
    fake_summary = (
        "What it was about:\nA dispute about a dealership agreement.\n\n"
        "What the court decided:\nThe Court held that the entire agreement was void and set aside all proceedings.\n\n"
        "Why it matters:\nIt shows clauses can fail.\n\n"
        "Key points:\n- Point one.\n- Point two.\n- Point three."
    )
    monkeypatch.setattr(casechat, "llm_service", _FakeLLMService(fake_summary))
    out, used_model = asyncio.run(casechat.generate_case_summary(FIXTURE_META, FIXTURE_CHUNKS))
    assert "set aside all proceedings" not in out
    assert "not verified" in out or "unverified excerpt" in out or "cannot state" in out
    assert used_model is False


# ---------------------------------------------------------------------------
# Safeguard bypass probes + seed-label qualification + Gemini upload boundary
# ---------------------------------------------------------------------------

def test_bypass_false_claim_with_unrelated_genuine_quote_fails():
    """A false disposition claim accompanied by a genuine but topically
    unrelated verbatim quote (same sentence) must NOT pass verification."""
    ans = ('The court held that the appeal was dismissed for limitation, noting '
           '"we hold that the clause is void to the extent of the restriction".')
    ok, _ = casechat.verify_holding_claims(ans, PARA_MAP)
    assert ok is False


def test_bypass_evasive_disposition_phrasings_require_quotes():
    """Disposition phrasings beyond 'held that' must also require verbatim quotes."""
    for ans in (
        "The court was of the view that the clause is void.",
        "The court found that the contract was unenforceable.",
        "The judges concluded that the agreement was void.",
    ):
        ok, _ = casechat.verify_holding_claims(ans, PARA_MAP)
        assert ok is False, ans


def test_bypass_split_claim_and_quote_fails():
    """Claim in one sentence, genuine quote in another: the claim itself is
    unsupported and must fail verification."""
    ans = ('The court held that the appeal was dismissed for limitation. '
           'Elsewhere the text says "we hold that the clause is void to the extent of the restriction".')
    ok, _ = casechat.verify_holding_claims(ans, PARA_MAP)
    assert ok is False


def test_topically_matching_quote_still_passes():
    ans = ('The court held the clause void to a limited extent: '
           '"we hold that the clause is void to the extent of the restriction".')
    ok, supporting = casechat.verify_holding_claims(ans, PARA_MAP)
    assert ok is True
    assert supporting == [3]


def test_citator_fallback_seed_status_is_qualified():
    """Seeded citator status (GOOD LAW / ARTICLE 141 style claims) must be served
    clearly qualified as unverified app records; raw seed data stays untouched."""
    from app.services import neo4j_service as neo4j_mod
    rec = neo4j_mod.neo4j_service.get_citator_case("sc-2006-percept")
    assert rec is not None
    assert rec["statusLabel"] == "Unverified app record"
    assert rec["statusDescription"].startswith("App seed record - not verified")
    assert "Seed assertion (unverified): GOOD LAW" in rec["statusDescription"]
    assert rec.get("statusVerified") is False
    raw = neo4j_mod.ARTICLE_141_GRAPH_DATA["sc-2006-percept"]
    assert raw["statusLabel"] == "GOOD LAW (ARTICLE 141 BINDING)"


def test_search_results_carry_qualified_seed_status():
    """Search results whose stored payload carries an unqualified seed authority
    label must be served with the label clearly qualified."""
    from app.routers import search as search_router
    results = [{"id": "x", "title": "T", "statusLabel": "GOOD LAW (ARTICLE 141 BINDING)", "ratioSummary": ""}]
    out = search_router._withhold_curated_summaries(results)
    assert out[0]["statusLabel"] == "Unverified app record"
    assert "Seed assertion (unverified): GOOD LAW" in out[0].get("statusDescription", "")
    assert out[0].get("statusVerified") is False


def test_gemini_fallback_never_enabled_for_document_routes():
    """Uploaded documents must never reach Gemini: only the search-answer route
    (typed question + public corpus) may enable the external fallback."""
    import pathlib
    routers_dir = pathlib.Path(casechat.__file__).resolve().parent
    offenders = []
    for f in routers_dir.glob("*.py"):
        if "ALLOW_EXTERNAL_FALLBACK.set(True)" in f.read_text():
            offenders.append(f.name)
    assert offenders == ["search.py"], offenders
    from app.services import groq_client
    assert groq_client.gemini_fallback_available() is False


def test_endpoint_fallback_model_used_provenance(fixture_case):
    """model_used must name the path that actually produced the answer: the
    deterministic path must never be labelled with the model's name."""
    resp = client.post("/api/v1/case-chat", json={
        "case_id": "fixture-endpoint-case",
        "question": "What did the court decide?",
        "force_fallback": True,
    })
    assert resp.status_code == 200
    assert resp.json()["model_used"] == "deterministic_case_chat"


# ---------------------------------------------------------------------------
# Search synthesis: holding-claim quote verification + honest Percept framing
# ---------------------------------------------------------------------------

SEARCH_FIXTURE_CASE = {
    "title": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan",
    "citation": "(2006) 4 SCC 227",
    "court": "Supreme Court of India",
    "benchType": "Division Bench",
    "benchSize": 2,
    "decisionYear": 2006,
    "statutes": ["Section 27 Contract Act", "Section 14 Specific Relief Act"],
    "text": ("Held: Contract between the cricketer and the agent was for services which were of "
             "personal, confidential and fiduciary in nature and its specific performance was "
             "barred by Section 14(1)(a), (b) and (d) of Act of 1953. Assuming without admitting "
             "that the negative covenant is not void under Section 27 of the Contract Act."),
}


def _make_search_svc(monkeypatch, model_answer, model_ratio=""):
    """LLMService instance whose client returns a canned structured synthesis."""
    import json as _json
    import types as _types
    from app.services import llm_service as llm_mod
    import app.services.verified_statute_notes as vsn

    monkeypatch.setattr(vsn, "verified_note_for", lambda q: None)
    svc = llm_mod.LLMService()
    payload = _json.dumps({"answer": model_answer, "ratio_decidendi": model_ratio, "citations": []})
    fake_resp = _types.SimpleNamespace(text=payload)
    fake_client = _types.SimpleNamespace(
        models=_types.SimpleNamespace(generate_content=lambda **kw: fake_resp))
    monkeypatch.setattr(svc, "_client", fake_client)
    monkeypatch.setattr(svc, "is_active", True)

    async def _identity(query, cases):
        return cases
    monkeypatch.setattr(svc, "_filter_topically_relevant_cases", _identity)
    return svc


def test_search_synthesis_unsupported_holding_falls_back(monkeypatch):
    """A search answer that asserts a holding without a verbatim quote from the
    retrieved text must be replaced by the deterministic honest synthesis."""
    svc = _make_search_svc(
        monkeypatch,
        "In Percept D'Mark, the Supreme Court held that all post-termination restraints are void ab initio under Section 27.",
    )
    out = asyncio.run(svc.synthesize_search_answer("restraint of trade", [SEARCH_FIXTURE_CASE]))
    assert "held that all post-termination restraints are void" not in out["answer"]
    assert out["model_used"] != svc.model


def test_search_synthesis_with_verified_quote_passes(monkeypatch):
    """A search answer whose holding claim carries a verbatim quote from the
    retrieved precedent text is served as a model answer."""
    svc = _make_search_svc(
        monkeypatch,
        ('The Court held that specific performance was barred, stating "its specific '
         'performance was barred by Section 14(1)(a), (b) and (d)".'),
    )
    out = asyncio.run(svc.synthesize_search_answer("restraint of trade", [SEARCH_FIXTURE_CASE]))
    assert out["model_used"] == svc.model
    assert "specific performance was barred" in out["answer"]


def test_search_synthesis_deterministic_s27_is_honest(monkeypatch):
    """The deterministic Section 27 fallback must not assert that Percept D'Mark
    ruled post-termination restraints void ab initio."""
    svc = _make_search_svc(monkeypatch, "not_found")
    out = asyncio.run(svc.synthesize_search_answer("restraint of trade", [SEARCH_FIXTURE_CASE]))
    assert "void ab initio" not in out["answer"]
    assert "assuming without admitting" in out["answer"]
    assert "not verified" in out["answer"]


def test_no_hardcoded_percept_void_assertions_in_source():
    """Source must not hardcode the materially wrong Percept holding."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    llm_src = (root / "app" / "services" / "llm_service.py").read_text()
    assert "Post-termination non-competes are never enforceable" not in llm_src
    assert "admits no exception of reasonableness" not in llm_src
    assert "Void ab initio under Percept" not in llm_src


def test_comparison_and_chat_ui_have_no_unqualified_authority_defaults():
    """Frontend must not default to 'Good Law / Binding' or claim AI authorship
    for deterministic answers."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    comparison = (root / "src" / "components" / "PrecedentComparison.jsx").read_text()
    assert "Good Law / Binding" not in comparison
    assert "Authoritative precedent of the Supreme Court of India" not in comparison
    panel = (root / "src" / "components" / "CaseChatPanel.jsx").read_text()
    assert "AI answer, not legal advice &bull; Strictly grounded" not in panel


def test_generic_deterministic_synthesis_does_not_assert_holdings(monkeypatch):
    """The generic deterministic synthesis must present stored summaries as
    unverified app records, never as what the Supreme Court held."""
    svc = _make_search_svc(monkeypatch, "not_found")
    case = dict(SEARCH_FIXTURE_CASE)
    case["ratioSummary"] = "The appeal was disposed of in terms of the settlement recorded between the parties."
    case["title"] = "Some Other Case v. State"
    out = asyncio.run(svc.synthesize_search_answer("adverse possession requirements", [case]))
    assert "the Supreme Court held that" not in out["answer"]
    assert "the Court affirmed that" not in out["answer"]
    assert "not verified against the judgment" in out["answer"]
    assert out["model_used"] == "deterministic_precedent_synthesis"
    assert out["tier"] == "deterministic_record"
    assert "no AI used" in out["tier_label"]
