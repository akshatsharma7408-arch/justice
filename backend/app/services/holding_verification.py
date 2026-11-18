"""Deterministic verification of model holding claims against retrieved text.

Shared by case chat and search synthesis. A holding claim (held/declared/void/...)
must carry a verbatim quotation from the text the model actually saw; otherwise
the caller falls back to an honest deterministic response.
"""
import re
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Holding-claim quote verification (model output -> deterministic check)
# ---------------------------------------------------------------------------
# A sentence that asserts what a court held/decided/declared (a "holding
# claim") must carry an exact word-for-word quotation from the retrieved case
# paragraphs. The check is deterministic: the quoted span must appear verbatim
# (whitespace/case-normalised) in the retrieved text. Claims that cannot be
# verified this way are unsupported; the caller then returns the honest
# deterministic limited response instead of the unsupported claim.
_HOLDING_CLAIM_RE = re.compile(
    r"(held that|court held|declared|overruled|upheld|set aside|dismissed|"
    r"allowed the appeal|found that|of the view|concluded that|came to the conclusion|"
    r"binding|unconstitutional|"
    r"(?:is|was|were|be|been|held|found)\s+void)",
    re.IGNORECASE,
)
_QUOTE_RE = re.compile(r'["\u201c]([^"\u201c\u201d]{20,})["\u201d]')
_CLAIM_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "had",
    "was", "were", "are", "been", "being", "which", "who", "whom", "whose",
    "their", "there", "then", "than", "thus", "also", "such", "said", "says",
    "court", "held", "noting", "noted", "because", "therefore", "hence",
    "appeal", "appeals", "appellant", "appellants", "respondent", "respondents",
}


def _content_stems(text: str) -> set:
    """Rough content-word stems (len>=4, light suffix stripping) for topical-overlap checks."""
    stems = set()
    for w in re.findall(r"[a-z]{4,}", text.lower()):
        if w in _CLAIM_STOPWORDS:
            continue
        for suf in ("ations", "ation", "tion", "sion", "ness", "ment", "ally", "ies", "ing", "ied", "es", "ed", "ly", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        stems.add(w)
    return stems


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _split_sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


def verify_holding_claims(answer: str, paragraphs: List[Tuple[int, str]]) -> Tuple[bool, List[int]]:
    """Check holding-claim sentences in a model answer against retrieved paragraphs.

    paragraphs: list of (paragraph_number, paragraph_text) as shown to the model.
    Returns (ok, supporting_paragraph_numbers):
    - ok=True with [] when the answer makes no holding claims (nothing to verify).
    - ok=True with the paragraph numbers containing the verified quotes when every
      holding-claim sentence carries a verbatim quotation from the retrieved text.
    - ok=False when any holding-claim sentence lacks a verifiable quotation.
    """
    # Quotations are source claims even when the surrounding sentence avoids
    # holding verbs. Check them BEFORE the no-holding-claims early return.
    norm_paras = [(n, _normalize_ws(t)) for n, t in paragraphs]
    for quote in _QUOTE_RE.findall(answer):
        normalized = _normalize_ws(quote)
        matches = []
        for _, text in norm_paras:
            start = text.find(normalized)
            while start >= 0:
                # A substring can be exact yet reverse polarity by starting
                # immediately after "no" or "not". Do not accept that clipping.
                prefix = re.split(r"[.!?;:]", text[:start])[-1].split()[-3:]
                clipped_negation = any(w in {"no", "not", "never", "cannot"} for w in prefix)
                if not clipped_negation:
                    matches.append(True)
                start = text.find(normalized, start + 1)
        if not matches:
            return False, []

    # Article 22(1) concerns grounds and counsel, not the production deadline.
    # Reject a blended attribution rather than silently editing legal advice.
    # Source: Constitution of India, Article 22 clauses (1) and (2).
    for sentence in _split_sentences(answer):
        if (re.search(r"article\s*22\s*\(\s*1\s*\)", sentence, re.I)
                and re.search(r"magistrate|twenty[- ]four|24\s*hours", sentence, re.I)
                and not re.search(r"22\s*\(\s*2\s*\)", sentence)):
            return False, []

    claims = [s for s in _split_sentences(answer) if _HOLDING_CLAIM_RE.search(s)]
    if not claims:
        return True, []
    norm_paras = [(n, _normalize_ws(t)) for n, t in paragraphs]
    supporting: List[int] = []
    for sent in claims:
        claim_stems = _content_stems(_QUOTE_RE.sub(" ", sent))
        verified = False
        for q in _QUOTE_RE.findall(sent):
            nq = _normalize_ws(q)
            if not (claim_stems & _content_stems(q)):
                # A genuine but topically unrelated quote does not support the claim.
                continue
            for n, t in norm_paras:
                if nq and nq in t:
                    verified = True
                    supporting.append(n)
                    break
            if verified:
                break
        if not verified:
            return False, []
    return True, sorted(set(supporting))
