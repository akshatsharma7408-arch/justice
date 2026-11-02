import asyncio
from types import SimpleNamespace
from app.services import llm_service as L
import pytest

@pytest.fixture(autouse=True)
def _reset():
    L._UNV_STATE['total']=0; L._UNV_STATE['window']=[]
    yield

BASE = " This is general information about how such situations usually work in India and what a person can check. " * 4


def test_validator_rejects_whole_answer_not_strips():
    f = L.unverified_answer_problem
    assert f(BASE) is None
    assert f(BASE + "See Maneka Gandhi v. Union of India") is not None
    assert f(BASE + "under Section 138") is not None
    assert f(BASE + "pay Rs 5000") is not None
    assert f(BASE + "within 30 days") is not None
    assert f(BASE + "under the Industrial Relations Act") is not None
    assert f(BASE + "under the Consumer Protection Act, 2019") is None
    assert f("short") is not None


def test_adverse_context_reaches_model_for_njac():
    assert "struck down" in L.adverse_context_for("what happened to NJAC")
    assert L.adverse_context_for("my landlord deposit") == ""


def _svc(texts):
    class _S(L.LLMService):
        client = None
        model = "x"
    svc = _S.__new__(_S)
    seen = {}
    it = iter(texts)

    def gen(model=None, contents="", config=None):
        seen["system"] = getattr(config, "system_instruction", "")
        return SimpleNamespace(text=next(it))
    _S.client = SimpleNamespace(models=SimpleNamespace(generate_content=gen))
    return svc, seen


def test_route_returns_valid_answer_with_closing_and_none_when_answer_bad():
    good = BASE
    svc, seen = _svc([good])
    out = asyncio.run(svc.generate_unverified_ai_answer("what happened to NJAC"))
    assert out and out.endswith(L._UNV_CLOSING)
    assert "struck down" in seen["system"]
    svc, _ = _svc([BASE + "Section 12", BASE + "Section 13"])
    assert asyncio.run(svc.generate_unverified_ai_answer("q")) is None


def test_route_never_runs_without_client_or_for_force_fallback():
    svc, _ = _svc([BASE])
    assert asyncio.run(svc.generate_unverified_ai_answer("q", force_fallback=True)) is None
    type(svc).client = None
    assert asyncio.run(svc.generate_unverified_ai_answer("q")) is None


def test_single_attempt_only_no_amplification():
    calls = []
    class _S(L.LLMService):
        client = None; model = "x"
    svc = _S.__new__(_S)
    def gen(model=None, contents="", config=None):
        calls.append(1); return SimpleNamespace(text=BASE + "Section 12")
    _S.client = SimpleNamespace(models=SimpleNamespace(generate_content=gen))
    assert asyncio.run(svc.generate_unverified_ai_answer("q")) is None
    assert len(calls) == 1


def test_budget_cap_and_rate_exhaust_without_real_quota(monkeypatch):
    monkeypatch.setenv("UNVERIFIED_AI_PER_MIN", "2")
    svc, _ = _svc([BASE, BASE, BASE, BASE])
    assert asyncio.run(svc.generate_unverified_ai_answer("q"))
    assert asyncio.run(svc.generate_unverified_ai_answer("q"))
    assert asyncio.run(svc.generate_unverified_ai_answer("q")) is None  # per-minute limit
    monkeypatch.setenv("UNVERIFIED_AI_PER_MIN", "100"); monkeypatch.setenv("UNVERIFIED_AI_PROCESS_CAP", "2")
    L._UNV_STATE["window"] = []
    assert asyncio.run(svc.generate_unverified_ai_answer("q")) is None  # process cap (resets on restart)


def test_topic_rules_block_known_forum_errors_and_garble():
    f = L.unverified_answer_problem
    assert f(BASE + " Seek a protection order from a family court.", "violence")
    assert f(BASE + " Approach a magistrate.", "violence")
    assert f(BASE + " Under the Payment of Wages Act you can claim.", "labour")
    assert f(BASE + " The appropriate labour court may handle it depending on the State.", "labour") is None
    assert f(BASE + " Complain to the State Human Rights Commission.", "arrest")
    assert f(BASE + " Go to the District Consumer Disputes Redressal Forum.", "consumer")
    assert f(BASE + " You bought a directive phone.", "general")
    assert f(BASE + " A consumer commission may handle it.", "consumer") is None
    assert f(BASE + " A civil court may handle it, depending on your State.", "general") is None
    assert L._unv_topic("my husband beats me") == "violence"
    assert L._unv_topic("employer not paying salary") == "labour"
    assert L._unv_topic("police arrested me without warrant") == "arrest"
    assert L._unv_topic("defective phone refund") == "consumer"


def test_topic_rule_reaches_model_prompt():
    svc, seen = _svc([BASE])
    asyncio.run(svc.generate_unverified_ai_answer("my husband beats me"))
    assert "Do not name any Act, court" in seen["system"]


def test_context_note_for_statute_text_passes_but_does_not_quote():
    svc, seen = _svc([BASE])
    out = asyncio.run(svc.generate_unverified_ai_answer("cheque bounce", context_note="Section 138 of the NI Act"))
    assert out and "Do not quote" in seen["system"]
