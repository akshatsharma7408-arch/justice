import asyncio
from types import SimpleNamespace
from app.services.llm_service import LLMService


def _svc(outputs):
    s = LLMService.__new__(LLMService)
    async def _g(src, out):
        return True
    s._explanation_is_grounded = _g
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
    assert run(_svc(["The State cannot take your property unless a law allows it.", "SUPPORTED"])) == "The State cannot take your property unless a law allows it."


def test_rejects_case_names_and_foreign_numbers_then_none():
    assert run(_svc(["In Kesavananda v. State of Kerala it was held", "See Article 21 and (2017) 10 SCC 1"])) is None


def test_retry_recovers():
    assert run(_svc(["Under Section 99 you can sue.", "Property can be taken only under a law.", "SUPPORTED"])) == "Property can be taken only under a law."


def test_force_fallback_returns_none():
    assert run(_svc(["x"]), force_fallback=True) is None


def test_unsupported_claim_rejected_by_verifier():
    assert run(_svc(["Property can be taken after a court order.", "UNSUPPORTED", "Property can be taken after a court order.", "UNSUPPORTED"])) is None


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


def _clause_svc(gen, ver):
    seq = [gen, ver]
    class M:
        def generate_content(self, **kw):
            return SimpleNamespace(text=seq.pop(0))
    s = LLMService.__new__(LLMService)
    s._client = SimpleNamespace(models=M()); s.is_active = True; s.api_key = "x"; s.model = "m"
    return s

CL_SRC = "It shall be the duty of every citizen of India\u2014 (a) to safeguard public property and to abjure violence; (b) to protect the natural environment."


def test_split_into_clauses():
    from app.services.llm_service import split_into_clauses
    segs = split_into_clauses(CL_SRC)
    assert len(segs) == 3 and segs[1].startswith("(a)") and segs[2].startswith("(b)")


def test_clause_explainer_accepts_faithful_reworded():
    s = _clause_svc("1 | Every citizen has these duties.\n2 | Look after public property and avoid violence.\n3 | Take care of the natural environment.",
                    "1 | OK\n2 | OK\n3 | OK")
    out = asyncio.run(s.explain_provision_by_clause("Article 51A", CL_SRC))
    assert [m for m, _ in out] == ["", "(a)", "(b)"]


def test_clause_explainer_rejects_changed_missing_and_timing():
    s = _clause_svc("1 | Every citizen has these duties.\n2 | Look after public property and avoid violence.\n3 | Take care of the natural environment.",
                    "1 | OK\n2 | CHANGED\n3 | OK")
    assert asyncio.run(s.explain_provision_by_clause("Article 51A", CL_SRC)) is None
    s = _clause_svc("1 | Every citizen has these duties.\n2 | Look after public property.", "1 | OK\n2 | OK")
    # two attempts consume the same text, then fail on line count
    s2 = LLMService.__new__(LLMService)
    from types import SimpleNamespace as NS
    class M:
        def generate_content(self, **kw):
            return NS(text="1 | Every citizen has these duties.\n2 | Look after public property.")
    s2._client = NS(models=M()); s2.is_active = True; s2.api_key = "x"; s2.model = "m"
    assert asyncio.run(s2.explain_provision_by_clause("Article 51A", CL_SRC)) is None
    src339 = "(1) The President may at any time and shall, at the expiration of ten years from the commencement of this Constitution by order appoint a Commission. (2) The executive power of the Union shall extend to directions."
    class M2:
        def generate_content(self, **kw):
            return NS(text="1 | The President can appoint a Commission any time and must do so after ten years.\n2 | The Union can give directions.")
    s3 = LLMService.__new__(LLMService)
    s3._client = NS(models=M2()); s3.is_active = True; s3.api_key = "x"; s3.model = "m"
    assert asyncio.run(s3.explain_provision_by_clause("Article 339", src339)) is None
