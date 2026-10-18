"""
JUSTICE Legal AI Backend — Statutory Audit Service
Encapsulates rule-based and LLM-assisted clause parsing under Section 27 of the
Indian Contract Act, 1872, bare acts retrieval, and Article 141 precedent classification.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from app.services.statute_service import statute_service
from app.services.llm_service import llm_service

logger = logging.getLogger("justice.audit_service")

# Regex patterns identifying post-employment / post-cessation restrictions
POST_TERM_PATTERNS = [
    r"following\s+(?:the\s+)?termination",
    r"post[\s\-_]?termination",
    r"after\s+(?:the\s+)?(?:termination|expiry|expiration)",
    r"following\s+(?:the\s+)?(?:expiry|expiration)",
    r"post[\s\-_]?cessation",
    r"after\s+(?:the\s+)?cessation",
    r"following\s+(?:the\s+)?cessation",
    r"upon\s+(?:the\s+)?cessation",
    r"post[\s\-_]?employment",
    r"after\s+(?:the\s+)?(?:employment|service|tenure)",
    r"following\s+(?:the\s+)?(?:employment|service|tenure)",
    r"post[\s\-_]?service",
    r"after\s+service",
    r"following\s+service",
    r"post[\s\-_]?separation",
    r"after\s+(?:the\s+)?separation",
    r"following\s+(?:the\s+)?separation",
    r"subsequent\s+to\s+(?:the\s+)?(?:termination|expiry|expiration|cessation|separation|resignation|departure|employment)",
    r"upon\s+(?:the\s+)?(?:termination|expiry|expiration|separation|resignation|departure)",
    r"after\s+(?:the\s+)?(?:resignation|departure|leaving)",
    r"following\s+(?:the\s+)?(?:resignation|departure|leaving)",
    r"survive[s]?\s+(?:the\s+)?(?:termination|expiry|expiration|cessation|cancellation)",
    r"survive[s]?\s+(?:indefinitely|for\s+(?:\d+|[a-zA-Z\-]+)\s+(?:months?|years?))",
    r"for\s+a\s+period\s+of\s+.*?(?:months?|years?)\s+(?:following|after|thereafter|post|subsequent)",
    r"period\s+of\s+.*?\s+(?:months?|years?)\s+following\s+termination",
    r"thereafter\s+for\s+a\s+period",
]

# Regex patterns identifying non-compete, trade restraint, or negative covenants
RESTRAINT_OF_TRADE_PATTERNS = [
    r"non[\s\-_]?compete",
    r"not\s+(?:to\s+)?compete",
    r"restraint\s+of\s+trade",
    r"restrain(?:t|ed|ing)?\s+from",
    r"shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?(?:engage|work|consult|advise|participate|render\s+services|enter|operate)",
    r"not\s+(?:directly\s+or\s+indirectly\s+)?(?:engage|work|consult|advise|participate|render\s+services|enter|operate)",
    r"not\s+enter\s+into\s+any\s+(?:competing\s+)?business",
    r"restrict(?:ed|ing|s)?.*?from\s+(?:practicing|exercising|engaging|working|carrying\s+on)",
    r"shall\s+not\s+work\s+for\s+(?:any\s+)?competitor",
    r"not\s+work\s+for\s+(?:any\s+)?competitor",
    r"shall\s+not\s+(?:be\s+employed|accept\s+employment|join|solicit)",
    r"competing\s+(?:business|firm|company|entity|enterprise|organization|venture|activity|undertaking)",
    r"in\s+(?:direct\s+or\s+indirect\s+)?competition",
    r"rival\s+(?:business|firm|company|entity)",
    r"similar\s+business",
    r"exercise\s+(?:any\s+)?lawful\s+profession,\s+trade\s+or\s+business",
    r"negative\s+covenant",
    r"restrictive\s+covenant",
    r"bar(?:red)?\s+from\s+(?:working|engaging|operating|practicing)",
]

# Regex patterns indicating in-term (active service / subsistence of employment)
IN_TERM_PATTERNS = [
    r"during\s+(?:the\s+)?(?:term|tenure|subsistence|period|course)\s+of\s+(?:employment|service|this\s+agreement|contract|engagement)",
    r"during\s+(?:the\s+)?active\s+(?:employment|service|engagement|tenure)",
    r"during\s+employment",
    r"while\s+employed",
    r"while\s+in\s+(?:active\s+)?service",
    r"subsistence\s+of\s+(?:employment|service|contract|engagement)",
    r"exclusive\s+service",
    r"devote\s+(?:whole|entire|full)\s+time",
]

# Other statutory violation detection patterns
OTHER_VIOLATIONS = [
    {
        "pattern": r"(?:assigns?|waives?)\s+.*?moral\s+rights|irrevocably\s+assigns?.*?all.*?moral\s+rights",
        "statute": "The Copyright Act, 1957",
        "section": "57",
        "heading": "Author's special rights (Moral rights non-waivable)",
        "risk_level": "MODERATE",
        "severity": "MODERATE",
        "precedent": "Amar Nath Sehgal v. Union of India (2005) 30 PTC 253 (Del)",
        "doctrine": "Author's moral rights under Section 57 cannot be completely extinguished or assigned away by contract.",
        "layman": "You are assigning moral rights. Under Indian copyright law, moral rights as an creator/author cannot be completely surrendered.",
        "impact": "Overly broad IP assignment claiming moral rights and personal un-contracted projects should be carved out.",
        "redline": "The Consultant assigns to the Company proprietary rights in Works created strictly within the direct scope of engagement, excluding moral rights protected under Section 57 of the Copyright Act, 1957."
    },
    {
        "pattern": r"liquidated\s+damages\s+equivalent\s+to\s+100%|forfeit.*?entire\s+annual|liquidated\s+damages\s+as\s+penalty|in\s+terrorem",
        "statute": "The Indian Contract Act, 1872",
        "section": "74",
        "heading": "Compensation for breach of contract where penalty stipulated for",
        "risk_level": "CRITICAL",
        "severity": "VOID_AB_INITIO",
        "precedent": "Kailash Nath Associates v. Delhi Development Authority (2015) 4 SCC 136",
        "doctrine": "Under Section 74, penal damages in terrorem are unenforceable. Compensation requires proof of actual loss or genuine pre-estimate.",
        "layman": "The clause seeks 100% contract value forfeiture without proving actual loss. Indian courts will not enforce punitive penalties under Section 74.",
        "impact": "Uncapped liquidated damages without proof of loss create severe monetary exposure and are legally suspect.",
        "redline": "In the event of material default, the aggrieved party shall be entitled to reasonable compensation not exceeding actual proved damages, capped as a genuine pre-estimate of loss."
    },
    {
        "pattern": r"exclusive\s+jurisdiction.*?waives\s+any\s+right\s+to\s+invoke\s+statutory|waives?\s+statutory.*?remedies",
        "statute": "The Indian Contract Act, 1872",
        "section": "28",
        "heading": "Agreements in restraint of legal proceedings, void",
        "risk_level": "MODERATE",
        "severity": "MODERATE",
        "precedent": "A.B.C. Laminart Pvt. Ltd. v. A.P. Agencies (1989) 2 SCC 163",
        "doctrine": "Under Section 28, parties cannot completely oust statutory remedies or jurisdiction of competent courts.",
        "layman": "Attempting to strip your right to approach statutory tribunals or consumer forums is void under Section 28.",
        "impact": "Exclusive jurisdiction clauses are valid between two competent courts, but cannot bar statutory remedies.",
        "redline": "This Agreement shall be subject to the competent jurisdiction of Courts in Bangalore, without prejudice to non-derogable statutory remedies under applicable law."
    }
]


class AuditService:
    def __init__(self):
        pass

    def evaluate_clause_heuristics(self, clause_text: str, clause_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Pure statutory classification engine evaluating clauses under Indian law.
        Guarantees:
        1. Any clause containing post-employment restrictions (e.g. 'following termination',
           'post termination', 'after expiry', 'post-cessation') is strictly classified
           as CRITICAL / VOID AB INITIO under Section 27, citing Percept D'Mark and Krishan Murgai.
        2. Niranjan Shankar Golikari is strictly restricted to in-term (active service) non-competes.
        3. General clauses do not cite Golikari.
        """
        lower = clause_text.lower()
        title_lower = (clause_title or "").lower()
        combined = f"{title_lower} {lower}"

        # 1. Detect post-employment restriction indicators
        is_post_term = any(re.search(p, lower) for p in POST_TERM_PATTERNS)
        
        # 2. Detect restraint of trade / non-compete indicators
        is_restraint = any(re.search(p, lower) for p in RESTRAINT_OF_TRADE_PATTERNS) or any(re.search(p, title_lower) for p in RESTRAINT_OF_TRADE_PATTERNS)

        # 3. Detect in-term indicators
        is_in_term = any(re.search(p, lower) for p in IN_TERM_PATTERNS)

        # Fetch Section 27 dynamically from bare acts DB
        s27 = statute_service.get_provision_by_section("contract-act-1872", "27")
        s27_heading = s27.get("heading") if s27 else "Agreement in restraint of trade, void"
        s27_body = s27.get("body") if s27 else (
            "Every agreement by which any one is restrained from exercising a lawful "
            "profession, trade or business of any kind, is to that extent void."
        )
        s27_statute_name = s27.get("act_title") if s27 else "The Indian Contract Act, 1872"

        # --- CASE 1: POST-EMPLOYMENT RESTRICTION (SECTION 27 VIOLATION) ---
        # Post-employment restrictions on trade, business, profession or competing
        if is_post_term and (is_restraint or "non-compete" in title_lower or "restrictive" in title_lower):
            return {
                "is_violation": True,
                "status": "NON-COMPLIANT",
                "risk_level": "CRITICAL",
                "severity": "VOID_AB_INITIO",
                "statute": s27_statute_name,
                "section": "27",
                "heading": s27_heading,
                "statutory_text": s27_body,
                "statutory_violation": "Section 27, Indian Contract Act, 1872 (Restraint of trade - Void ab initio)",
                "binding_precedent": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246",
                "governing_authorities": [
                    "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227",
                    "Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246",
                    "Section 27, Indian Contract Act, 1872",
                    "Article 19(1)(g) & Article 141, Constitution of India"
                ],
                "legal_doctrine": (
                    "Indian contract law treats post-employment non-compete covenants as void ab initio under Section 27, "
                    "rejecting the English common law 'reasonableness' doctrine."
                ),
                "layman_translation": (
                    "The company is attempting to bar you from working for a competitor or practicing your profession "
                    "after your engagement ends. Under Section 27 of the Indian Contract Act and binding Supreme Court rulings, "
                    "this post-employment restriction is 100% VOID AB INITIO and completely unenforceable in court."
                ),
                "practical_impact": (
                    "Even though this covenant is legally void and unenforceable in court under Percept D'Mark and Krishan Murgai, "
                    "signing it exposes you to vexatious employer notices or withholding of relieving letters. "
                    "Insist on replacing it with an enforceable non-solicitation term."
                ),
                "balanced_redline": (
                    "The Consultant agrees that for a period of twelve (12) months following termination, "
                    "Consultant shall not knowingly solicit existing clients of the Company with whom Consultant had material "
                    "business dealings during the final six (6) months of engagement, nor disclose proprietary trade secrets. "
                    "Nothing herein shall restrict Consultant from pursuing any lawful profession, trade, or employment "
                    "in accordance with Section 27 of the Indian Contract Act, 1872."
                )
            }

        # --- CASE 2: IN-TERM (ACTIVE SERVICE) NON-COMPETE ---
        # Niranjan Shankar Golikari strictly applies ONLY here
        if is_in_term and is_restraint and not is_post_term:
            return {
                "is_violation": False,
                "status": "COMPLIANT",
                "risk_level": "LOW",
                "severity": "CLEAN",
                "statute": s27_statute_name,
                "section": "27",
                "heading": "Permissible In-Term Restraint (Subsistence of Employment)",
                "statutory_text": s27_body,
                "statutory_violation": "Section 27 Caveat (Permissible In-Term Restraint)",
                "binding_precedent": "Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd. (1967) 2 SCR 378",
                "governing_authorities": [
                    "Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd. (1967) 2 SCR 378",
                    "Section 27, Indian Contract Act, 1872 (In-Term Rule)"
                ],
                "legal_doctrine": (
                    "PERMISSIBLE IN-TERM RESTRAINT: Under Niranjan Shankar Golikari (1967), negative covenants "
                    "operating strictly during the active subsistence of the contract/employment to ensure exclusive service "
                    "and prevent conflict of interest do not constitute an unlawful restraint of trade under Section 27. "
                    "NOTE: Niranjan Golikari applies strictly to in-term covenants and cannot be extended to post-employment restrictions."
                ),
                "layman_translation": (
                    "During the active period of your employment, the company can legally require exclusive service "
                    "and prohibit you from working for competitors or taking outside commercial roles."
                ),
                "practical_impact": (
                    "Valid and enforceable in Indian courts during active employment to prevent conflicts of interest."
                ),
                "balanced_redline": None
            }

        # --- CASE 3: OTHER SPECIFIC STATUTORY ISSUES (e.g. Copyright Moral Rights, Section 74, Section 28) ---
        for issue in OTHER_VIOLATIONS:
            if re.search(issue["pattern"], lower):
                return {
                    "is_violation": issue["risk_level"] == "CRITICAL",
                    "status": "NON_COMPLIANT" if issue["risk_level"] == "CRITICAL" else "COMPLIANT",
                    "risk_level": issue["risk_level"],
                    "severity": issue["severity"],
                    "statute": issue["statute"],
                    "section": issue["section"],
                    "heading": issue["heading"],
                    "statutory_text": f"Provisions of {issue['statute']}, Section {issue['section']}.",
                    "statutory_violation": f"{issue['statute']} - Section {issue['section']}",
                    "binding_precedent": issue["precedent"],
                    "governing_authorities": [issue["precedent"], f"{issue['statute']} - Section {issue['section']}"],
                    "legal_doctrine": issue["doctrine"],
                    "layman_translation": issue["layman"],
                    "practical_impact": issue["impact"],
                    "balanced_redline": issue["redline"]
                }

        # --- CASE 4: STANDARD GENERAL CONTRACTUAL CLAUSE ---
        # Compliant clause — does NOT cite Niranjan Shankar Golikari
        return {
            "is_violation": False,
            "status": "COMPLIANT",
            "risk_level": "LOW",
            "severity": "CLEAN",
            "statute": "The Indian Contract Act, 1872",
            "section": "General",
            "heading": "Standard Commercial Undertaking",
            "statutory_text": "Agreements not declared void by law are enforceable according to their terms.",
            "statutory_violation": None,
            "binding_precedent": "Indian Contract Act, 1872 (Freedom of Contract Principles)",
            "governing_authorities": ["The Indian Contract Act, 1872"],
            "legal_doctrine": (
                "Standard contractual term. No prima facie Section 27 restraint of trade or non-derogable "
                "statutory violation detected under prevailing Indian law."
            ),
            "layman_translation": "Standard operational clause governing contractual terms during the active engagement.",
            "practical_impact": "Complies with Indian statutory standards; typical commercial allocation of rights and liabilities.",
            "balanced_redline": None
        }

    async def verify_clause(self, clause_text: str, clause_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes hybrid statutory evaluation:
        1. Evaluates strict Section 27 heuristics and bare acts retrieval.
        2. If post-employment violation is present and Gemini is active, synthesizes rich layman & redline.
        3. Enforces that post-employment covenants always cite Percept D'Mark & Krishan Murgai.
        """
        result = self.evaluate_clause_heuristics(clause_text, clause_title)

        # If it's a Section 27 violation, optionally enhance via LLM if available
        if result["is_violation"] and result["section"] == "27":
            try:
                synthesis = await llm_service.generate_layman_and_redline(
                    clause_text=clause_text,
                    title=clause_title or "Restrictive Covenant"
                )
                if synthesis.get("layman"):
                    result["layman_translation"] = synthesis["layman"]
                if synthesis.get("practical_impact"):
                    result["practical_impact"] = synthesis["practical_impact"]
                if synthesis.get("redline"):
                    result["balanced_redline"] = synthesis["redline"]
            except Exception as e:
                logger.warning(f"LLM enrichment skipped or failed: {e}")

        return result


audit_service = AuditService()
