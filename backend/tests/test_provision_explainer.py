import asyncio
from types import SimpleNamespace
from app.services.llm_service import LLMService


def _svc(outputs):
    s = LLMService.__new__(LLMService)
    seq = list(outputs)

    class M:
        def generate_content(self, **kw):
            return SimpleNamespace(text=seq.pop(0) if len(seq) > 1 else seq[0])

    s._client = SimpleNamespace(models=M())
    s.is_active = True
    s.api_key = "x"
    s.model = "m"
    return s


def run(s, **kw):
    return asyncio.run(s.explain_provision_ai("Article 300A of the Constitution (Property)", "No person shall be deprived of his property save by authority of law.", **kw))


def test_accepts_plain_explanation():
    assert run(_svc(["The State cannot take your property unless a law allows it.", "1 | No person shall be deprived of his property | OK\nVERDICT | SUPPORTED"])) == "The State cannot take your property unless a law allows it."


def test_rejects_case_names_and_foreign_numbers_then_none():
    assert run(_svc(["In Kesavananda v. State of Kerala it was held", "See Article 21 and (2017) 10 SCC 1"])) is None


def test_retry_recovers():
    assert run(_svc(["Under Section 99 you can sue.", "Property can be taken only under a law.", "1 | No person shall be deprived of his property | OK\nVERDICT | SUPPORTED"])) == "Property can be taken only under a law."


def test_force_fallback_returns_none():
    assert run(_svc(["x"]), force_fallback=True) is None


def test_unsupported_claim_rejected_by_verifier():
    assert run(_svc(["Property can be taken after a court order.", "1 | No person shall be deprived of his property | OK\nVERDICT | UNSUPPORTED", "Property can be taken after a court order.", "1 | No person shall be deprived of his property | OK\nVERDICT | UNSUPPORTED"])) is None


def test_grounded_check_requires_literal_quotes_and_ok():
    src = "No person shall be deprived of his property save by authority of law."
    s = _svc(["No person.\nNo person | No person shall be deprived | OK\n"])
    s2 = LLMService.__new__(LLMService)
    from types import SimpleNamespace as NS

    def mk(txt):
        class M:
            def generate_content(self, **kw):
                return NS(text=txt)
        o = LLMService.__new__(LLMService)
        o._client = NS(models=M()); o.is_active = True; o.api_key = "x"; o.model = "m"
        return o

    ex = "Nobody can lose property without a law."
    assert asyncio.run(mk("1 | No person shall be deprived of his property | OK")._explanation_is_grounded(src, ex)) is True
    assert asyncio.run(mk("1 | an officer may seize property | OK")._explanation_is_grounded(src, ex)) is False
    assert asyncio.run(mk("1 | No person shall be deprived of his property | CHANGED")._explanation_is_grounded(src, ex)) is False


def test_explainer_has_a_time_budget(monkeypatch):
    import app.services.llm_service as m
    s = _svc(["x"])
    async def slow(*a, **k):
        await asyncio.sleep(5)
        return "late"
    s._explain_provision_ai_uncached = slow
    real = asyncio.wait_for
    async def fast_wait_for(coro, timeout):
        return await real(coro, timeout=0.05)
    monkeypatch.setattr(m.asyncio, "wait_for", fast_wait_for)
    assert run(s) is None


def test_merged_verifier_uses_one_call_per_attempt():
    calls = []
    s = _svc(["The State cannot take your property unless a law allows it.",
              "1 | No person shall be deprived of his property | OK\nVERDICT | SUPPORTED"])
    orig = s._client.models.generate_content
    def counting(**kw):
        calls.append(1)
        return orig(**kw)
    s._client.models.generate_content = counting
    assert run(s) == "The State cannot take your property unless a law allows it."
    assert len(calls) == 2  # one generation + one merged verification


def test_merged_verifier_rejects_missing_verdict_changed_and_bad_quote():
    src = "No person shall be deprived of his property save by authority of law."
    ex = "Nobody can lose property without a law."
    def v(txt):
        s = _svc([txt])
        return asyncio.run(s._explanation_verified_merged(src, ex))
    assert v("1 | No person shall be deprived of his property | OK\nVERDICT | SUPPORTED") is True
    assert v("1 | No person shall be deprived of his property | OK") is False
    assert v("1 | No person shall be deprived of his property | CHANGED\nVERDICT | SUPPORTED") is False
    assert v("1 | an officer may seize property | OK\nVERDICT | SUPPORTED") is False
    assert v("1 | No person shall be deprived of his property | OK\nVERDICT | UNSUPPORTED") is False
