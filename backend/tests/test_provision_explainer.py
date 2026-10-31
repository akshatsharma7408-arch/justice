import asyncio
from types import SimpleNamespace
from app.services.llm_service import LLMService


def _svc(outputs):
    s = LLMService.__new__(LLMService)
    it = iter(outputs)

    class M:
        def generate_content(self, **kw):
            return SimpleNamespace(text=next(it))

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
