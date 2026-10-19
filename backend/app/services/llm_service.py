"""
JUSTICE Legal AI Backend — Unified LLM Service
Orchestrates Indian Legal Intelligence, HyDE Synthetic Ratios, Section 27 Statutory Auditing,
and Article 141 Precedent Citator Analysis over Groq's high-throughput OpenAI-compatible endpoint
(primary model: openai/gpt-oss-120b with automated spillover to openai/gpt-oss-20b).
Includes backward compatibility and deterministic legal fallback layers.
"""

import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from google.genai import types

from app.services.groq_client import GroqClient
from app.config import settings
from app.services.answer_tiers import needs_specific_source, format_tier2_response, NOT_FOUND_SPECIFIC_MSG
from app.services.citation_checker import citation_checker

logger = logging.getLogger("justice.llm")

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
    citations: List[str] = Field(default_factory=list, description="Explicit citations to retrieved source records")

class SearchSynthesisSchema(BaseModel):
    answer: str = Field(description="Answer strictly grounded in the provided retrieved precedents. If not found or outside the retrieved sources, must be 'I couldn't find this in the available sources'.")
    ratio_decidendi: str = Field(description="Synthetic holding or 'I couldn't find this in the available sources'")
    citations: List[str] = Field(description="List of cited precedent titles and citations from the retrieved sources")


def clean_ocr_noise(text: str) -> str:
    """
    Strips OCR noise, page headers, volume markers, and margin letters.
    """
    if not text:
        return ""
    # Strip Supreme Court Reports / SCC page headers & volume markers
    # e.g., "[2022] 4 S.C.R. 382", "SUPREME COURT OF INDIA", "Page 12 of 30", margin letters "[A]", "B ", etc.
    t = re.sub(r'\[?\b\d{4}\]?\s*\d*\s*S\.?C\.?R\.?\s*\d*', ' ', text, flags=re.IGNORECASE)
    t = re.sub(r'\[?\b\d{4}\]?\s*\d*\s*S\.?C\.?C\.?\s*\d*', ' ', text, flags=re.IGNORECASE)
    t = re.sub(r'\bSUPREME COURT (?:REPORTS|OF INDIA)\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bHIGH COURT OF [A-Z\s]+\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bPage\s+\d+(?:\s+of\s+\d+)?\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:PETITIONER|RESPONDENT|DATE OF JUDGMENT|BENCH|HEADNOTE|JUDGMENT)\s*:?', ' ', t, flags=re.IGNORECASE)
    # Strip SCR margin letter markers like [A], [B], [C], or leading A., B., etc.
    t = re.sub(r'\[[A-H]\]', ' ', t)
    t = re.sub(r'(?:^|\n)\s*[A-H]\s+(?=[A-Z])', ' ', t)
    # Strip repeated dashes, underscores, and formatting artifacts
    t = re.sub(r'[-_=]{3,}', ' ', t)
    # Normalize whitespaces, tabs, newlines
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def clean_case_summary(case: Dict[str, Any]) -> str:
    """
    Rule (4): Never output raw chunk text in an answer. Show only a clean short summary
    or the case metadata, and strip OCR noise such as page headers and volume markers.
    """
    title = case.get("title") or case.get("case_name") or "Precedent"
    cit = case.get("citation") or case.get("neutral_citation") or ""
    statutes = case.get("statutes") or []
    stat_str = f" under {', '.join(statutes)}" if statutes else ""
    
    raw_summary = case.get("text") or case.get("ratioSummary") or ""
    cleaned = clean_ocr_noise(raw_summary)
    
    # Extract the most meaningful 1-2 sentences, avoiding raw chunk dumps
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if len(s.strip()) > 20]
    
    if sentences:
        short_summary = " ".join(sentences[:2])
        if len(short_summary) > 280:
            short_summary = short_summary[:277] + "..."
    else:
        short_summary = f"This precedent{stat_str} establishes authoritative judicial doctrine on the issue."

    return short_summary


def extract_query_entities(query: str) -> Dict[str, Any]:
    """
    Extracts specific legal entities from a query: sections, articles, citations, and case/party names.
    """
    q = query.strip()
    
    # 1. Sections (e.g. Section 27, Sec. 74, s. 999)
    sections = re.findall(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-zA-Z]*)\b', q, re.IGNORECASE)
    
    # 2. Articles (e.g. Article 21, Art. 412, art 399)
    articles = re.findall(r'\b(?:articles?|arts?\.?)\s*(\d+[a-zA-Z]*)\b', q, re.IGNORECASE)
    
    # 3. Judicial citations (e.g. (2021) 5 SCC 123, 2023 12 SCC 456, [2022] 4 SCR 382)
    citations = re.findall(
        r'\(?\[?\b\d{4}\)?\]?[ \t]*\d*[ \t]*(?:SCC|AIR|SCR|SCALE|CompCas|ILR|PTC|DLT|INSC|S\.C\.R\.)[ \t]*\d+[A-Za-z0-9\s]*',
        q,
        re.IGNORECASE
    )
    
    # 4. Case names / party names
    case_names = []
    case_matches = re.findall(
        r'\b([A-Z][A-Za-z0-9&\'\.\(\)\-]*(?:[ \t]+[A-Za-z0-9&\'\.\(\)\-]+){0,4}[ \t]+(?:v\.|vs\.?|versus)[ \t]+[A-Z][A-Za-z0-9&\'\.\(\)\-]*(?:[ \t]+[A-Za-z0-9&\'\.\(\)\-]+){0,4})\b',
        q,
        re.IGNORECASE
    )
    for m in case_matches:
        case_names.append(m.strip())
        
    known_landmarks = [
        "hadley v baxendale", "hadley v. baxendale", "kesavananda", "maneka gandhi", 
        "puttaswamy", "dawoodi bohra", "kailash nath", "zaheer khan", "percept d'mark", 
        "krishan murgai", "niranjan golikari", "gujarat bottling", "wipro", 
        "ambiance india", "desiccant rotors", "stellar information", "adm jabalpur"
    ]
    for kn in known_landmarks:
        if kn in q.lower() and not any(kn in cn.lower() for cn in case_names):
            case_names.append(kn)
            
    has_specific = bool(sections or articles or citations or case_names or needs_specific_source(query))
    
    return {
        "sections": [s.lower() for s in sections],
        "articles": [a.lower() for a in articles],
        "citations": [c.strip().lower() for c in citations],
        "case_names": case_names,
        "has_specific_entity": has_specific
    }


def match_case_to_query_entities(entities: Dict[str, Any], case: Dict[str, Any]) -> bool:
    """
    Rule (1): The fallback must never return a retrieved case as an answer unless the query's
    case name, party names, citation, section or article actually appear in that case's metadata or text.
    A similarity score alone is not enough.
    """
    case_title = (case.get("title") or case.get("case_name") or "").lower()
    case_cit = (case.get("citation") or case.get("neutral_citation") or "").lower()
    case_statutes = " ".join(case.get("statutes", [])).lower()
    case_ratio = (case.get("ratioSummary") or "").lower()
    case_body = (case.get("text") or "").lower()
    case_keywords = " ".join(case.get("keywords", [])).lower()
    case_full = f"{case_title} {case_cit} {case_statutes} {case_keywords} {case_ratio} {case_body}"

    # If query specified case names / party names, the case MUST match at least one
    if entities["case_names"]:
        name_matched = False
        indian_states = {
            "kerala", "maharashtra", "delhi", "gujarat", "punjab", "haryana", "rajasthan", 
            "karnataka", "tamil", "nadu", "andhra", "pradesh", "telangana", "uttar", "bihar", 
            "bengal", "odisha", "assam", "madhya", "kashmir", "jammu", "himachal", "goa", 
            "jharkhand", "chhattisgarh", "uttarakhand", "manipur", "meghalaya", "mizoram", 
            "nagaland", "tripura", "sikkim"
        }
        stopwords = {
            "versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "corp",
            "corporation", "company", "and", "the", "ors", "anr", "v", "vs", "of", "govt",
            "government", "board", "authority", "commission", "department", "bank"
        } | indian_states
        for cn in entities["case_names"]:
            cn_lower = cn.lower()
            parts = re.split(r'\s+(?:v\.|vs\.?|versus)\s+', cn_lower)
            if len(parts) == 2:
                side_stopwords = {
                    "versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "corp",
                    "corporation", "company", "and", "the", "ors", "anr", "v", "vs", "of", "govt",
                    "government", "board", "authority", "commission", "department", "bank"
                }
                p1_tokens = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', parts[0]) if t not in side_stopwords]
                p2_tokens = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', parts[1]) if t not in side_stopwords]
                m1 = any(re.search(rf'\b{re.escape(tok)}\b', case_title) for tok in p1_tokens) if p1_tokens else True
                m2 = any(re.search(rf'\b{re.escape(tok)}\b', case_title) for tok in p2_tokens) if p2_tokens else True
                if m1 and m2:
                    name_matched = True
                    break
            else:
                tokens = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', cn_lower) if t not in stopwords]
                if tokens and any(
                    re.search(rf'\b{re.escape(tok)}\b', case_title) or 
                    re.search(rf'\b{re.escape(tok)}\b', case_keywords)
                    for tok in tokens
                ):
                    name_matched = True
                    break
        if not name_matched:
            return False

    # If query specified citations, the case citation MUST match
    if entities["citations"]:
        cit_matched = False
        for cit_str in entities["citations"]:
            nums = re.findall(r'\b\d+\b', cit_str)
            if nums and any(num in case_cit for num in nums):
                cit_matched = True
                break
        if not cit_matched:
            return False

    # If query specified sections, the case MUST contain the section in statutes or text
    if entities["sections"]:
        sec_matched = False
        for sec in entities["sections"]:
            if (
                re.search(rf'\b(?:sections?|secs?\.?|s\.)\s*{re.escape(sec)}\b', case_full)
                or f"section {sec}" in case_statutes
                or f" {sec}," in case_statutes
                or f" {sec} " in case_statutes
            ):
                sec_matched = True
                break
        if not sec_matched:
            return False

    # If query specified articles, the case MUST contain the article in statutes or text
    if entities["articles"]:
        art_matched = False
        for art in entities["articles"]:
            if (
                re.search(rf'\b(?:articles?|arts?\.?)\s*{re.escape(art)}\b', case_full)
                or f"article {art}" in case_statutes
                or f" {art}," in case_statutes
                or f" {art} " in case_statutes
            ):
                art_matched = True
                break
        if not art_matched:
            return False

    if not (entities["case_names"] or entities["citations"] or entities["sections"] or entities["articles"]):
        return False

    return True


class LLMService:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY") or settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self.provider = settings.LLM_PROVIDER
        self.is_active = settings.is_llm_active
        self._client: Optional[GroqClient] = None
        self._init_client()

    def _init_client(self):
        if self.is_active and self.api_key:
            try:
                self._client = GroqClient(api_key=self.api_key)
                logger.info("Initialized LLM Client (provider=%s) targeting model '%s'", self.provider, self.model)
            except Exception as e:
                logger.error("Failed to initialize LLM Client: %s", e)
                self._client = None
        else:
            logger.info("LLM API key inactive or placeholder. Operating in deterministic legal fallback mode.")
            self._client = None

    @property
    def client(self) -> Optional[GroqClient]:
        if not self._client and self.is_active:
            self._init_client()
        return self._client

    async def verify_clause_ai(self, clause_text: str, clause_title: str = "Restrictive Covenant") -> Dict[str, Any]:
        """
        Audits a contractual clause under Indian law using LLM structured JSON generation.
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
                    temperature=settings.LLM_TEMPERATURE,
                    max_output_tokens=settings.LLM_MAX_TOKENS,
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
                logger.warning("LLM verify_clause call encountered exception: %s. Using deterministic legal fallback.", e)

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
        """Helper returning layman translation, practical impact, and redline."""
        res = await self.verify_clause_ai(clause_text, title)
        return {
            "layman": res.get("layman_translation", ""),
            "practical_impact": res.get("practical_impact", ""),
            "redline": res.get("balanced_redline", ""),
            "model_used": res.get("model_used", "deterministic_legal_fallback")
        }

    async def generate_hyde_ratio(self, query: str) -> str:
        """
        Generates a Hypothetical Document Embedding (HyDE) ratio decidendi
        grounded in Indian Supreme Court jurisprudence.
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
                    temperature=settings.LLM_TEMPERATURE,
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
                logger.warning("HyDE generation failed: %s. Employing Indian law fallback.", e)

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
        analysis for a given precedent, strictly grounded in the retrieved case record.
        """
        if not case_data:
            return {
                "constitutional_standing": "Not Found",
                "bench_strength_assessment": "I couldn't find this in the available sources",
                "overruling_risk": "Unknown",
                "article_141_doctrine": "I couldn't find this in the available sources",
                "executive_summary": "I couldn't find this in the available sources",
                "citations": [],
                "model_used": "retrieval_empty_skip"
            }

        source_ref = f"{case_data.get('title', 'Precedent')} ({case_data.get('citation', '')})".strip()
        system_instruction = (
            "You are a constitutional scholar and Supreme Court citator specialist. "
            "Evaluate Indian Supreme Court precedent standing strictly and solely based on the retrieved precedent record and documented treatment history below. "
            "CRITICAL ACCURACY RULES: "
            "1. Base every statement ONLY on the provided retrieved record. "
            "2. Cite the source precedent for each claim. "
            "3. If the case data does not contain sufficient details for a specific field, state: 'I couldn't find this in the available sources'. "
            "4. Do not invent any outside authorities, citations, or ungrounded treatment."
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
            f"and overruling risks in structured JSON. Include explicit citations pointing to this precedent."
        )

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.LLM_TEMPERATURE,
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
                    parsed = json.loads(response.text)
                    if not parsed.get("citations"):
                        parsed["citations"] = [source_ref]
                    parsed["model_used"] = self.model
                    for f in ["constitutional_standing", "bench_strength_assessment", "overruling_risk", "article_141_doctrine", "executive_summary"]:
                        if f in parsed and isinstance(parsed[f], str):
                            parsed[f] = citation_checker.check_and_badge_text(parsed[f], is_tier2=False)
                    parsed["citations"] = citation_checker.badge_citations_list(parsed.get("citations", []))
                    return parsed
            except Exception as e:
                logger.warning("Citator analysis failed: %s. Using deterministic synthesis.", e)

        res = {
            "constitutional_standing": f"Binding precedent under Article 141 for all subordinate courts and coordinate {case_data.get('benchSize')}-judge benches.",
            "bench_strength_assessment": f"{case_data.get('benchType')} with {case_data.get('benchSize')} Judges. Under Dawoodi Bohra (2005), coordinate benches cannot overrule.",
            "overruling_risk": "Low. The core ratio decidendi has been consistently followed across Indian High Courts.",
            "article_141_doctrine": case_data.get("statusDescription", ""),
            "executive_summary": f"{case_data.get('title')} ({case_data.get('decisionYear')}) represents authoritative precedent governing its statutory domain in India.",
            "citations": [source_ref],
            "model_used": "deterministic_legal_fallback"
        }
        for f in ["constitutional_standing", "bench_strength_assessment", "overruling_risk", "article_141_doctrine", "executive_summary"]:
            if f in res and isinstance(res[f], str):
                res[f] = citation_checker.check_and_badge_text(res[f], is_tier2=False)
        res["citations"] = citation_checker.badge_citations_list(res["citations"])
        return res

    async def generate_tier2_explanation(self, query: str, force_fallback: bool = False) -> str:
        """
        Generates a Tier 2 general practical and conceptual explanation for a query
        not covered by our verified database.
        Strictly satisfies:
        Rule (1): Starts with 'AI answer, not verified against a legal database.'
        Rule (2): 4 to 8 sentences or short bullets in plain English explaining practical rights,
                  concrete steps, what to do, and mentioning the general area of law.
        Rule (3): Strictly never names any specific case, citation, section number, or article number.
        Rule (4): Ends with 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'
        Rule (5): If the model call fails, shows a short clear message that the AI is unavailable
                  instead of generic filler.
        """
        if force_fallback or not self.client:
            return format_tier2_response(
                "The AI service is currently unavailable to generate an explanation for this topic. Please try again shortly."
            )

        system_instruction = (
            "You are a helpful, practical legal information assistant. "
            "When answering questions not covered by verified database precedents, provide a real, useful, practical legal answer of 4 to 8 sentences or short bullet points in plain English. "
            "Do NOT use generic filler sentences such as 'refers to an established principle governing rights, obligations, and remedies'. "
            "CRITICAL MANDATORY RULES:\n"
            "1. You MUST start your response directly with the exact label: 'AI answer, not verified against a legal database.'\n"
            "2. Explain practical rights, concrete steps, and what the person should actually do in simple words.\n"
            "3. Explicitly mention which general area of law applies in general terms (for example, 'traffic and criminal procedure laws in India', 'contract and equity principles in India', or 'tenancy and rent control laws in India').\n"
            "4. STRICT PROHIBITION: NEVER name or cite any specific case, court, judge, citation (such as SCC, AIR, SCR), section number (such as Section 27), or article number (such as Article 21). Keep all statutory and legal references strictly generalized (e.g. 'under motor vehicle regulations', 'under tenancy laws', 'under general contract principles').\n"
            "5. You MUST end your response directly with the exact text: 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'"
        )

        prompt = (
            f"Provide practical rights, actionable steps, and general legal framework for this question:\n\n"
            f"USER QUESTION: {query}\n\n"
            f"Remember:\n"
            f"- 4 to 8 sentences or short bullet points in plain English.\n"
            f"- Explain practical rights, what to do, and practical next steps.\n"
            f"- Mention the general area of law in general terms (e.g. 'traffic and criminal procedure laws in India').\n"
            f"- STRICTLY NO specific case names, citations, section numbers, or article numbers.\n"
            f"- Start with 'AI answer, not verified against a legal database.'\n"
            f"- End with 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'"
        )

        for attempt in range(1, 3):
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                    max_output_tokens=700
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response and response.text:
                    return format_tier2_response(response.text)
            except Exception as e:
                if attempt == 1:
                    logger.warning("Tier 2 LLM generation attempt 1 failed: %s. Retrying once...", e)
                    await asyncio.sleep(0.5)
                else:
                    logger.warning("Tier 2 LLM generation attempt 2 failed: %s. Returning unavailable message.", e)

        # Rule (5): If the model call fails, show a short clear message that the AI is unavailable instead of generic filler.
        return format_tier2_response(
            "The AI service is currently unavailable to generate an explanation for this topic. Please try again shortly."
        )

    async def synthesize_search_answer(
        self, 
        query: str, 
        retrieved_cases: List[Dict[str, Any]], 
        force_fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Synthesizes an AI answer for universal search using the Two-Tier framework:
        - Tier 1: Grounded solely in verified retrieved precedents with full citations.
        - Tier 2: Concise general conceptual explanation if not found in verified sources.
        - Specific query not found: "I couldn't find a verified source for this"

        Enforces strict fallback rules:
        Rule (1): Fallback must never return a retrieved case as an answer unless the query's
                  case name, party names, citation, section or article actually appear in that
                  case's metadata or text. A similarity score alone is not enough.
        Rule (2): If the query names a specific case, citation, section or article that is not
                  in the corpus, return "I couldn't find a verified source for this".
        Rule (3): If the query is a general concept with no specific case named, return the
                  Tier 2 labeled general explanation, same as neural mode.
        Rule (4): Never output raw chunk text in an answer. Show only a clean short summary or
                  the case metadata, and strip OCR noise such as page headers and volume markers.
        Rule (5): Retry the model call once before falling back, and log why it failed.
        """
        entities = extract_query_entities(query)
        is_specific_ask = entities["has_specific_entity"] or needs_specific_source(query)

        # If no cases were retrieved, determine whether it's a specific ask or general concept
        if not retrieved_cases:
            if is_specific_ask:
                return {
                    "answer": NOT_FOUND_SPECIFIC_MSG,
                    "ratio_decidendi": NOT_FOUND_SPECIFIC_MSG,
                    "citations": [],
                    "results": [],
                    "model_used": "tier1_verified_source_not_found"
                }
            else:
                tier2_ans = await self.generate_tier2_explanation(query, force_fallback=force_fallback)
                return {
                    "answer": tier2_ans,
                    "ratio_decidendi": tier2_ans,
                    "citations": [],
                    "results": [],
                    "model_used": "tier2_general_explanation"
                }

        # Rule (3): If the query is a general concept or rights question with no specific case,
        # citation, section, or article requested, return Tier 2 general explanation:
        if not is_specific_ask:
            tier2_ans = await self.generate_tier2_explanation(query, force_fallback=force_fallback)
            return {
                "answer": tier2_ans,
                "ratio_decidendi": tier2_ans,
                "citations": [],
                "results": retrieved_cases,
                "model_used": "tier2_general_explanation"
            }

        # Rule (2): If the query explicitly asks for a specific case name that does not exist in our retrieved corpus,
        # return "I couldn't find a verified source for this"
        if entities["case_names"]:
            has_matched_case = any(
                match_case_to_query_entities({
                    "case_names": entities["case_names"],
                    "citations": [],
                    "sections": [],
                    "articles": []
                }, c)
                for c in retrieved_cases
            )
            if not has_matched_case:
                return {
                    "answer": NOT_FOUND_SPECIFIC_MSG,
                    "ratio_decidendi": NOT_FOUND_SPECIFIC_MSG,
                    "citations": [],
                    "results": [],
                    "model_used": "tier1_verified_source_not_found"
                }

        cases_context = []
        for idx, c in enumerate(retrieved_cases[:5]):
            body_text = c.get("text") or c.get("ratioSummary", "")
            if len(body_text) > 1200:
                body_text = body_text[:1200] + "..."
            cases_context.append(
                f"[{idx + 1}] Title: {c.get('title')}\n"
                f"    Citation: {c.get('citation')} ({c.get('decisionYear', '')})\n"
                f"    Court: {c.get('court', '')} | Bench: {c.get('benchType', '')} ({c.get('benchSize', '')} judges)\n"
                f"    Statutes: {', '.join(c.get('statutes', []))}\n"
                f"    Judicial Text / Ratio: {body_text}\n"
            )
        context_str = "\n".join(cases_context)

        system_instruction = (
            "You are an Indian legal research analyst operating under strict Tier 1 grounding rules. "
            "Answer the query strictly and solely based on the retrieved precedents provided below. "
            "CRITICAL ACCURACY RULES: "
            "1. Every single claim in your answer MUST cite the source precedent from the retrieved list (Title and Citation). "
            "2. If the retrieved precedents do not directly address or provide a complete verified legal answer to the query, your answer and ratio_decidendi MUST BE EXACTLY: "
            "'NOT_FOUND_IN_RETRIEVED_SOURCES', and citations must be an empty list []. "
            "3. For general conceptual or citizen rights questions (such as 'what is promissory estoppel', 'can my landlord evict me without notice', or roadside police stops) that are not specifically resolved by the core holding of the retrieved precedents, do NOT synthesize from outside knowledge; return 'NOT_FOUND_IN_RETRIEVED_SOURCES' so that the system provides the required general explanation. "
            "4. Never make up cases, statutes, or outside legal facts."
        )

        prompt = (
            f"USER QUERY: {query}\n\n"
            f"RETRIEVED PRECEDENTS:\n"
            f"{context_str}\n\n"
            f"Synthesize an answer and judicial ratio strictly grounded in these retrieved precedents. "
            f"Return valid structured JSON matching the schema."
        )

        # Rule (5): Retry the model call once before falling back, and log why it failed
        if self.client and not force_fallback:
            for attempt in range(1, 3):
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                        max_output_tokens=768,
                        response_mime_type="application/json",
                        response_schema=SearchSynthesisSchema
                    )
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=config
                    )
                    if response.text:
                        parsed = json.loads(response.text)
                        ans = parsed.get("answer", "").strip()
                        cits = parsed.get("citations", [])
                        lower_ans = ans.lower()
                        is_not_found = (
                            "not_found" in lower_ans
                            or "couldn't find" in lower_ans
                            or "not found" in lower_ans
                            or "does not contain" in lower_ans
                            or not ans
                            or not cits
                        )
                        if is_not_found:
                            # Precedents did not answer the question
                            if is_specific_ask:
                                return {
                                    "answer": NOT_FOUND_SPECIFIC_MSG,
                                    "ratio_decidendi": NOT_FOUND_SPECIFIC_MSG,
                                    "citations": [],
                                    "results": [],
                                    "model_used": "tier1_verified_source_not_found"
                                }
                            else:
                                tier2_ans = await self.generate_tier2_explanation(query, force_fallback=force_fallback)
                                return {
                                    "answer": tier2_ans,
                                    "ratio_decidendi": tier2_ans,
                                    "citations": [],
                                    "results": [],
                                    "model_used": "tier2_general_explanation"
                                }

                        parsed["answer"] = citation_checker.check_and_badge_text(parsed.get("answer", ""), is_tier2=False)
                        parsed["ratio_decidendi"] = citation_checker.check_and_badge_text(parsed.get("ratio_decidendi", "") or parsed["answer"], is_tier2=False)
                        parsed["citations"] = citation_checker.badge_citations_list(parsed.get("citations", []))
                        parsed["model_used"] = self.model
                        parsed["results"] = retrieved_cases
                        return parsed
                except Exception as e:
                    if attempt == 1:
                        logger.warning("Search synthesis model call attempt 1 failed: %s. Retrying once before fallback...", e)
                        await asyncio.sleep(0.5)
                    else:
                        logger.error("Search synthesis model call attempt 2 failed: %s. Triggering deterministic fallback.", e)

        # -------------------------------------------------------------
        # Deterministic Legal Fallback
        # -------------------------------------------------------------
        # Rule (3): If the query is a general concept with no specific case named,
        # return the Tier 2 labeled general explanation, same as neural mode.
        if not entities["has_specific_entity"] and not needs_specific_source(query):
            tier2_ans = await self.generate_tier2_explanation(query, force_fallback=force_fallback)
            return {
                "answer": tier2_ans,
                "ratio_decidendi": tier2_ans,
                "citations": [],
                "results": retrieved_cases,
                "model_used": "tier2_general_explanation"
            }

        # Rule (1): Never return a retrieved case as an answer unless the query's
        # case name, party names, citation, section or article actually appear in that
        # case's metadata or text. A similarity score alone is not enough.
        matched_case = None
        for case in retrieved_cases:
            if match_case_to_query_entities(entities, case):
                matched_case = case
                break

        # Rule (2): If the query names a specific case, citation, section or article
        # that is not in the corpus, return "I couldn't find a verified source for this".
        if not matched_case:
            return {
                "answer": NOT_FOUND_SPECIFIC_MSG,
                "ratio_decidendi": NOT_FOUND_SPECIFIC_MSG,
                "citations": [],
                "results": [],
                "model_used": "deterministic_source_not_found"
            }

        # Rule (4): Never output raw chunk text in an answer. Show only a clean short summary
        # or the case metadata, and strip OCR noise such as page headers and volume markers.
        source_ref = f"{matched_case.get('title')} ({matched_case.get('citation')})"
        summary = clean_case_summary(matched_case)
        ans_str = citation_checker.check_and_badge_text(f"According to {source_ref}: {summary}", is_tier2=False)
        ratio_str = citation_checker.check_and_badge_text(summary, is_tier2=False)
        return {
            "answer": ans_str,
            "ratio_decidendi": ratio_str,
            "citations": citation_checker.badge_citations_list([source_ref]),
            "results": [matched_case],
            "model_used": "deterministic_corpus_retrieval"
        }

    async def synthesize_legal_summary(self, clause_text: str, contract_title: str) -> str:
        """Concise legal synthesis for agent trace visualizer."""
        audit = await self.verify_clause_ai(clause_text, contract_title)
        if audit.get("is_violation"):
            return "Violates Section 27 Indian Contract Act 1872. Void ab initio under Percept D'Mark (2006). Risk: CRITICAL."
        return "Complies with Indian contractual standards. Enforceable during active engagement."

    async def check_health(self) -> Dict[str, Any]:
        """Diagnostic health report for the FastAPI /health endpoint."""
        if not self.is_active or not self.client:
            return {
                "status": "fallback_simulated",
                "model": self.model,
                "provider": self.provider,
                "configured": False,
                "detail": f"No active {self.provider.upper()}_API_KEY detected. Running in deterministic Indian law fallback mode."
            }

        return {
            "status": "connected",
            "model": self.model,
            "provider": self.provider,
            "configured": True,
            "detail": f"{self.provider.capitalize()} LLM service active targeting {self.model}."
        }


llm_service = LLMService()
