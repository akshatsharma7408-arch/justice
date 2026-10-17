"""
JUSTICE Legal AI Backend — Official Google GenAI SDK Service
Orchestrates Indian Legal Intelligence, HyDE Synthetic Ratios, Section 27 Statutory Auditing,
and Article 141 Precedent Citator Analysis using Google GenAI SDK.
Strictly enforced model: gemini-3.8-flash.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from google.genai import types

from app.services.groq_client import GroqClient

from app.config import settings

logger = logging.getLogger("justice.gemini")

# Pydantic schemas for structured JSON responses
class ClauseVerificationSchema(BaseModel):
    status: str = Field(description="'NON-COMPLIANT' or 'COMPLIANT'")
    risk_level: str = Field(description="'CRITICAL', 'MODERATE', or 'LOW'")
    is_violation: bool = Field(description="Whether the clause violates Indian statutes")
    statute: str = Field(description="Governing statute name")
    section: str = Field(description="Section number or identifier")
    heading: str = Field(description="Statutory heading")
    binding_precedent: str = Field(description="Binding Article 141 Supreme Court precedent citations")
    legal_doctrine: str = Field(description="Detailed legal doctrine analysis under Indian law")
    layman_translation: str = Field(description="Plain English translation at Grade 8 reading level")
    practical_impact: str = Field(description="Practical real-world advice for the signatory")
    balanced_redline: Optional[str] = Field(None, description="Enforceable replacement clause compliant with Section 27")

class HyDESchema(BaseModel):
    ratio_decidendi: str = Field(description="Judicial holding synthesizing Indian Supreme Court jurisprudence")
    statutes_involved: List[str] = Field(description="Relevant statutory provisions")
    binding_precedent_hint: str = Field(description="Key landmark case")

class CitatorAnalysisSchema(BaseModel):
    constitutional_standing: str = Field(description="Article 141 binding standing")
    bench_strength_assessment: str = Field(description="Bench hierarchy review under Dawoodi Bohra")
    overruling_risk: str = Field(description="Risk assessment of reconsideration or overruling")
    article_141_doctrine: str = Field(description="Detailed judicial doctrine summary")
    executive_summary: str = Field(description="2-3 sentence executive synthesis")


class GeminiService:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY") or settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL  # strictly "gemini-3.8-flash"
        self.is_active = settings.is_gemini_active
        self._client: Optional[GroqClient] = None
        self._init_client()

    def _init_client(self):
        if self.is_active and self.api_key:
            try:
                self._client = GroqClient(api_key=self.api_key)
                logger.info(f"Initialized official google-genai Client targeting model '{self.model}'")
            except Exception as e:
                logger.error(f"Failed to initialize google-genai Client: {e}")
                self._client = None
        else:
            logger.info("Gemini API key inactive or placeholder. GenAI Client initialized in fallback mode.")
            self._client = None

    @property
    def client(self) -> Optional[GroqClient]:
        if not self._client and self.is_active:
            self._init_client()
        return self._client

    async def verify_clause_ai(self, clause_text: str, clause_title: str = "Restrictive Covenant") -> Dict[str, Any]:
        """
        Audits a contractual clause under Indian law using Gemini 3.8 Flash structured JSON generation.
        Strictly enforces:
        - Post-employment restrictions: status 'NON-COMPLIANT', risk_level 'CRITICAL',
          doctrine void ab initio under Section 27 rejecting English reasonableness,
          precedents Percept D'Mark (2006) 4 SCC 227 & Krishan Murgai (1981) 2 SCC 246.
        - Niranjan Shankar Golikari (1967) valid ONLY for in-term (active employment).
        """
        system_instruction = (
            "You are a Justice of the Supreme Court of India and authoritative Indian legal scholar. "
            "Analyze contracts strictly under Indian jurisprudence, specifically the Indian Contract Act 1872 "
            "and Constitution of India Article 141 precedents. "
            "CRITICAL LEGAL DOCTRINE RULES: "
            "1. Any clause containing post-termination restrictions, client restrictions, or non-compete barriers "
            "following termination/employment cessation MUST be classified as status='NON-COMPLIANT' and risk_level='CRITICAL'. "
            "2. Under Section 27 of the Indian Contract Act 1872, post-employment restrictive covenants are VOID AB INITIO in India. "
            "The English common law doctrine of 'reasonableness' or 'partial restraint' DOES NOT apply in India. "
            "3. The binding Supreme Court Article 141 precedents for post-employment non-compete voidness are: "
            "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246. "
            "4. Niranjan Shankar Golikari (1967) applies EXCLUSIVELY to covenants during the active term of employment, NEVER post-termination. "
            "You must return a valid structured JSON object matching the requested schema."
        )

        prompt = (
            f"Perform a statutory compliance audit on this clause governed by Indian law:\n"
            f"Clause Title: {clause_title}\n"
            f"Clause Text: \"{clause_text}\"\n\n"
            f"Evaluate Section 27 Indian Contract Act 1872 and Article 141 binding precedents. "
            f"Provide a plain-English translation at Grade 8 reading level, practical impact advice, "
            f"and an enforceable redline replacing void post-service non-compete terms with enforceable non-solicitation."
        )

        # Check post-term indicators defensively
        lower = clause_text.lower()
        title_lower = clause_title.lower()
        is_post_term = any(w in lower for w in [
            "following termination", "post-termination", "post termination", "after termination",
            "after expiry", "following expiry", "after cessation", "post-cessation", "post employment",
            "post-employment", "after employment", "post service", "post-service", "following separation",
            "after separation", "survive termination", "survives termination", "thereafter for a period"
        ])
        is_restraint = any(w in lower for w in [
            "compete", "restraint", "shall not engage", "not engage", "not work", "not consult",
            "competing business", "rival", "lawful profession, trade or business", "prohibited from"
        ]) or "non-compete" in title_lower or "restraint" in title_lower

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.GEMINI_TEMPERATURE,
                    max_output_tokens=settings.GEMINI_MAX_TOKENS,
                    response_mime_type="application/json",
                    response_schema=ClauseVerificationSchema
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response.text:
                    parsed = json.loads(response.text)
                    # Enforce strict doctrine guardrails on model output
                    if is_post_term and is_restraint:
                        parsed["status"] = "NON-COMPLIANT"
                        parsed["risk_level"] = "CRITICAL"
                        parsed["is_violation"] = True
                        parsed["binding_precedent"] = "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246"
                        parsed["legal_doctrine"] = "Indian contract law treats post-employment non-compete covenants as void ab initio under Section 27, rejecting the English common law 'reasonableness' doctrine."
                    parsed["model_used"] = self.model
                    return parsed
            except Exception as e:
                logger.warning(f"Gemini 3.8 Flash structured verify_clause call encountered exception: {e}. Using deterministic legal fallback.")

        # Authoritative deterministic Indian law fallback
        if is_post_term and is_restraint:
            return {
                "status": "NON-COMPLIANT",
                "risk_level": "CRITICAL",
                "is_violation": True,
                "model_used": "deterministic_legal_fallback",
                "statute": "The Indian Contract Act, 1872",
                "section": "27",
                "heading": "Agreement in restraint of trade, void",
                "binding_precedent": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246",
                "legal_doctrine": "Indian contract law treats post-employment non-compete covenants as void ab initio under Section 27, rejecting the English common law 'reasonableness' doctrine.",
                "layman_translation": (
                    "This clause attempts to prevent you from working for a competitor or engaging in your profession "
                    "after your contract ends. Under Section 27 of the Indian Contract Act, 1872, all post-employment restrictions "
                    "are 100% void ab initio and completely unenforceable in Indian courts."
                ),
                "practical_impact": (
                    "Even though this covenant is legally void and unenforceable in court under Percept D'Mark and Krishan Murgai, "
                    "an employer may still issue legal notices or withhold relieving letters. It is essential to negotiate "
                    "this clause out and replace it with a standard, enforceable non-solicitation provision."
                ),
                "balanced_redline": (
                    "The Consultant agrees that for a period of twelve (12) months following termination, "
                    "Consultant shall not knowingly solicit existing clients of the Company with whom Consultant had material "
                    "business dealings during the final six (6) months of engagement, nor disclose proprietary trade secrets. "
                    "Nothing herein shall restrict Consultant from pursuing gainful profession, trade, or employment "
                    "in accordance with Section 27 of the Indian Contract Act, 1872."
                )
            }
        else:
            return {
                "status": "COMPLIANT",
                "risk_level": "LOW",
                "is_violation": False,
                "model_used": "deterministic_legal_fallback",
                "statute": "The Indian Contract Act, 1872",
                "section": "27",
                "heading": "Standard In-Term Covenant / General Terms",
                "binding_precedent": "Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd. (1967) 2 SCR 378",
                "legal_doctrine": (
                    "Under Niranjan Shankar Golikari (1967), covenants operating strictly during the active subsistence "
                    "of employment are valid to prevent conflict of interest. Clause does not impose impermissible post-employment restraints."
                ),
                "layman_translation": "This clause governs conduct during the active term of the engagement and complies with Indian law.",
                "practical_impact": "Standard commercial risk. Fully enforceable during the term of active engagement.",
                "balanced_redline": None
            }

    async def generate_layman_and_redline(self, clause_text: str, title: str = "Restrictive Covenant") -> Dict[str, str]:
        """Backward-compatible helper returning layman translation, practical impact, and redline."""
        res = await self.verify_clause_ai(clause_text, title)
        return {
            "layman": res.get("layman_translation", ""),
            "practical_impact": res.get("practical_impact", ""),
            "redline": res.get("balanced_redline", "")
        }

    async def generate_hyde_ratio(self, query: str) -> str:
        """
        Generates a Hypothetical Document Embedding (HyDE) ratio decidendi
        grounded in Indian Supreme Court jurisprudence using gemini-3.8-flash.
        """
        system_instruction = (
            "You are a Justice of the Supreme Court of India. "
            "Synthesize an authoritative judicial ratio decidendi (holding statement) summarizing "
            "the governing Indian law, constitutional precedents under Article 141, and relevant statutes for the given query."
        )

        prompt = (
            f"LEGAL QUERY: {query}\n\n"
            f"Draft a hypothetical ratio decidendi statement reflecting binding Supreme Court of India jurisprudence. "
            f"If the query pertains to Section 27 non-compete, emphasize voidness ab initio post-employment under Percept D'Mark. "
            f"If it pertains to Article 21 privacy, ground it in the 9-Judge bench holding of Puttaswamy (2017). "
            f"Return a structured JSON with 'ratio_decidendi', 'statutes_involved', and 'binding_precedent_hint'."
        )

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.GEMINI_TEMPERATURE,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                    response_schema=HyDESchema
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response.text:
                    parsed = json.loads(response.text)
                    return parsed.get("ratio_decidendi", "")
            except Exception as e:
                logger.warning(f"HyDE generation via gemini-3.8-flash failed: {e}. Employing Indian law fallback.")

        # Fallback ratio decidendi
        q_lower = query.lower()
        if "non-compete" in q_lower or "27" in q_lower or "restraint" in q_lower:
            return (
                "Under Indian jurisprudence governing the Indian Contract Act, 1872, the doctrine of restraint of trade "
                "(Section 27) applies strictly to all covenants operating post-termination. The Supreme Court of India "
                "does not import the English law test of 'reasonableness' for covenants operating after cessation of employment; "
                "such covenants are void in toto pursuant to Percept D'Mark v. Zaheer Khan (2006) and Superintendence Co. v. Krishan Murgai (1981)."
            )
        elif "privacy" in q_lower or "21" in q_lower:
            return (
                "The right to privacy is an intrinsic part of the right to life and personal liberty guaranteed under "
                "Article 21 and the foundational freedoms of Part III of the Constitution of India. As held by the 9-Judge "
                "Constitution Bench in Justice K.S. Puttaswamy v. Union of India (2017), any state encroachment must satisfy "
                "the three-fold test of legality, legitimate state aim, and proportionality."
            )
        return (
            "Under Article 141 of the Constitution of India, the law declared by the Supreme Court is binding on all courts "
            "within the territory of India. Statutory provisions must be interpreted in light of the constitutional bench "
            "precedence hierarchy established in Dawoodi Bohra (2005)."
        )

    async def generate_citator_analysis(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates deep neural Shepardization and Article 141 constitutional standing
        analysis for a given precedent using gemini-3.8-flash.
        """
        system_instruction = (
            "You are a constitutional scholar and Supreme Court citator specialist. "
            "Evaluate Indian Supreme Court precedent standing under Article 141 and Dawoodi Bohra bench rules."
        )

        prompt = (
            f"Precedent Title: {case_data.get('title')}\n"
            f"Citation: {case_data.get('citation')}\n"
            f"Court: {case_data.get('court')}\n"
            f"Bench Strength: {case_data.get('benchSize')} Judges ({case_data.get('benchType')})\n"
            f"Decision Year: {case_data.get('decisionYear')}\n"
            f"Status: {case_data.get('statusLabel')}\n"
            f"Treatment History: {json.dumps(case_data.get('treatmentHistory', []))}\n"
            f"Ratio Summary: {case_data.get('statusDescription', '')}\n\n"
            f"Analyze the binding nature under Article 141, Dawoodi Bohra coordinate bench limits, "
            f"and overruling risks in structured JSON."
        )

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.GEMINI_TEMPERATURE,
                    max_output_tokens=768,
                    response_mime_type="application/json",
                    response_schema=CitatorAnalysisSchema
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response.text:
                    return json.loads(response.text)
            except Exception as e:
                logger.warning(f"Citator analysis via gemini-3.8-flash failed: {e}. Using deterministic synthesis.")

        return {
            "constitutional_standing": f"Binding precedent under Article 141 for all subordinate courts and coordinate {case_data.get('benchSize')}-judge benches.",
            "bench_strength_assessment": f"{case_data.get('benchType')} with {case_data.get('benchSize')} Judges. Under Dawoodi Bohra (2005), coordinate benches cannot overrule.",
            "overruling_risk": "Low. The core ratio decidendi has been consistently followed across Indian High Courts.",
            "article_141_doctrine": case_data.get("statusDescription", ""),
            "executive_summary": f"{case_data.get('title')} ({case_data.get('decisionYear')}) represents authoritative precedent governing its statutory domain in India."
        }

    async def synthesize_legal_summary(self, clause_text: str, contract_title: str) -> str:
        """Concise legal synthesis for agent trace visualizer."""
        audit = await self.verify_clause_ai(clause_text, contract_title)
        if audit.get("is_violation"):
            return f"Violates Section 27 Indian Contract Act 1872. Void ab initio under Percept D'Mark (2006). Risk: CRITICAL."
        return f"Complies with Indian contractual standards. Enforceable during active engagement."

    async def check_health(self) -> Dict[str, Any]:
        """Diagnostic health report for the FastAPI /health endpoint."""
        if not self.is_active or not self.client:
            return {
                "status": "fallback_simulated",
                "model": self.model,
                "sdk": "groq-openai-compatible",
                "configured": False,
                "detail": "No active GEMINI_API_KEY detected. Running in deterministic Indian law fallback mode."
            }

        return {
            "status": "connected",
            "model": self.model,
            "sdk": "groq-openai-compatible",
            "configured": True,
            "detail": f"google-genai Client active targeting {self.model}."
        }


gemini_service = GeminiService()

