import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services.llm_service import LLMService

@pytest.mark.parametrize('bad_answer', [
    'The rule is "arrest can be made routinely on a mere allegation".',
    'Article 22(1) requires production before a magistrate within 24 hours.',
])
def test_search_rejects_unverified_model_answer(bad_answer):
    service = LLMService()
    fake_response = SimpleNamespace(text=json.dumps({'answer':bad_answer,'ratio_decidendi':'Procedural safeguards for arrest.','citations':[]}))
    service._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs:fake_response))
    service.model = 'test-model'
    service._filter_topically_relevant_cases = AsyncMock(side_effect=lambda query,cases:cases)
    cases = [{'id':'fixture-arrest','title':'Arrest Safeguards Fixture','citation':'TEST ONLY',
              'decisionYear':2026,'court':'Test court','statutes':[],
              'text':'No arrest can be made routinely on a mere allegation.',
              'ratioSummary':'Procedural safeguards for arrest.'}]
    result = asyncio.run(service.synthesize_search_answer('What protections apply when police arrest someone in India?',cases))
    assert result['model_used'] != 'test-model'
    assert bad_answer not in result['answer']
    assert result.get('tier') == 'deterministic_record'
