import asyncio
from types import SimpleNamespace
from app.services import llm_service as L

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


def test_route_returns_valid_answer_with_closing_and_none_when_both_attempts_bad():
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
