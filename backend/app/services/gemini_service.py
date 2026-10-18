"""
JUSTICE Legal AI Backend — Backward-Compatibility Shim
Redirects legacy gemini_service calls to app.services.llm_service (backed by Groq).
"""

from app.services.llm_service import (
    LLMService as GeminiService,
    llm_service as gemini_service,
    ClauseVerificationSchema,
    HyDESchema,
    CitatorAnalysisSchema,
)

__all__ = [
    "GeminiService",
    "gemini_service",
    "ClauseVerificationSchema",
    "HyDESchema",
    "CitatorAnalysisSchema",
]
