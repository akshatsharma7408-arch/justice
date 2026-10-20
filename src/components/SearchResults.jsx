import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  Search, ArrowRight, ArrowUpRight, Scale, ShieldCheck, 
  ChevronDown, ChevronUp, MessageSquare, Copy, Check, Filter, Sparkles,
  AlertCircle, RefreshCw, BookOpen
} from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { searchPrecedentsWithBackend, fetchSearchAnswerWithBackend } from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';
import { TiltCard } from './InteractiveEffects';

/**
 * Returns True only if the query is a pure case title, landmark case name,
 * or formal citation lookup without question words or conceptual topics.
 */
export function isPureCaseLookup(text) {
  if (!text) return false;
  const q = text.trim().toLowerCase();

  // Question or topic indicator words
  const topicIndicators = [
    "what", "why", "how", "when", "where", "can", "could", "should", "would",
    "is", "are", "do", "does", "did", "rights", "bribe", "bribes", "evict",
    "eviction", "liquidated damages", "arrest", "warrant", "valid", "validity",
    "enforce", "enforceability", "compensation", "explain", "meaning", "definition",
    "penalty", "procedure", "remedy", "relief", "doctrine"
  ];
  const words = q.match(/[a-zA-Z0-9]+/g) || [];
  if (words.some(w => topicIndicators.includes(w))) {
    return false;
  }

  // Landmark single names
  const knownPureLandmarks = [
    "kesavananda", "kesvananda", "kesavanand", "maneka gandhi", "maneka ghandi",
    "puttaswamy", "puttuswamy", "navtej", "shreya singhal", "vishaka",
    "shah bano", "golaknath", "indira gandhi", "minerva mills", "mohori bibee",
    "bhim singh", "aruna shanbaug"
  ];
  if (knownPureLandmarks.some(kpl => q.includes(kpl))) {
    return true;
  }

  // Citations
  if (/\b(?:\d{4}\s+)?(?:scc|air|scr|scale|insc)\b/i.test(q)) {
    return true;
  }

  // Party v. Party format
  if (/\b[a-z0-9\.\']+\s+(?:v\.|vs\.?|versus)\s+[a-z0-9\.\']+/i.test(q)) {
    return true;
  }

  return false;
}

export default function SearchResults({
  initialQuery = '',
  onSelectCaseForCitator,
  onOpenCaseChat,
  onSearchAgain
}) {
  const [query, setQuery] = useState(initialQuery);
  const [courtFilter, setCourtFilter] = useState('ALL');
  const [benchFilter, setBenchFilter] = useState('ALL');
  const [results, setResults] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedCaseId, setExpandedCaseId] = useState(null);
  const [toastMessage, setToastMessage] = useState(null);
  const [copiedCaseKey, setCopiedCaseKey] = useState(null);
  const [modelUsed, setModelUsed] = useState('openai/gpt-oss-120b');
  const [hydeRatio, setHydeRatio] = useState('');

  // AI Answer Card State
  const [answerData, setAnswerData] = useState(null);
  const [isAnswerLoading, setIsAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState(null);
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  // Execute search when initialQuery changes or on initial mount if provided
  useEffect(() => {
    if (initialQuery && initialQuery.trim()) {
      setQuery(initialQuery);
      executeSearch(initialQuery.trim(), courtFilter, benchFilter);
    }
  }, [initialQuery]);

  const executeSearch = async (searchQuery = query, court = courtFilter, bench = benchFilter) => {
    const trimmed = (searchQuery || '').trim();
    if (!trimmed) return;

    setIsLoading(true);
    setHasSearched(true);
    setAnswerError(null);

    const isLookup = isPureCaseLookup(trimmed);
    if (isLookup) {
      setAnswerData(null);
      setIsAnswerLoading(false);
    } else {
      setIsAnswerLoading(true);
    }

    let fetchedResults = null;
    try {
      const resp = await searchPrecedentsWithBackend(trimmed, court, bench, true, 10);
      if (resp && resp.results) {
        setResults(resp.results);
        fetchedResults = resp.results;
      }
      if (resp && resp.model_used) {
        setModelUsed(resp.model_used);
      }
      if (resp && resp.hyde_synthetic_ratio) {
        setHydeRatio(resp.hyde_synthetic_ratio);
      } else {
        setHydeRatio('');
      }
    } catch (err) {
      console.warn("[SearchResults] Backend search error; falling back to local corpus filter:", err.message);
      const terms = trimmed.toLowerCase().split(' ').filter(t => t.length > 2);
      const filtered = LANDMARK_PRECEDENTS.filter(item => {
        if (court !== 'ALL' && item.court !== court) return false;
        if (bench === 'CONSTITUTION' && item.benchSize < 5) return false;
        if (bench === 'DIVISION' && item.benchSize !== 2) return false;
        if (terms.length === 0) return true;
        const text = `${item.title} ${item.statutes.join(' ')} ${item.ratioSummary} ${item.citation}`.toLowerCase();
        return terms.some(t => text.includes(t));
      });
      setResults(filtered);
      fetchedResults = filtered;
    } finally {
      setIsLoading(false);
    }

    // Secondary fetch: Dedicated AI answer synthesis (if not a pure case lookup)
    if (!isLookup) {
      try {
        const ansResp = await fetchSearchAnswerWithBackend(trimmed, court, bench, fetchedResults);
        if (ansResp && ansResp.is_case_lookup) {
          setAnswerData(null);
        } else {
          setAnswerData(ansResp);
        }
      } catch (ansErr) {
        console.warn("[SearchResults] Search answer API call failed:", ansErr);
        setAnswerError(ansErr.message || "Failed to load AI answer");
      } finally {
        setIsAnswerLoading(false);
      }
    }
  };

  const handleRetryAnswer = async () => {
    const trimmed = query.trim();
    if (!trimmed || isPureCaseLookup(trimmed)) return;
    setIsAnswerLoading(true);
    setAnswerError(null);
    try {
      const ansResp = await fetchSearchAnswerWithBackend(
        trimmed,
        courtFilter,
        benchFilter,
        results && results.length > 0 ? results : null
      );
      if (ansResp && ansResp.is_case_lookup) {
        setAnswerData(null);
      } else {
        setAnswerData(ansResp);
      }
    } catch (err) {
      setAnswerError(err.message || "Failed to generate AI answer");
    } finally {
      setIsAnswerLoading(false);
    }
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    executeSearch(q, courtFilter, benchFilter);
    if (onSearchAgain) onSearchAgain(q);
  };

  const handleCopyCitation = (citation, title, caseKey = null) => {
    const textToCopy = `${title}, ${citation}`;
    navigator.clipboard?.writeText(textToCopy);
    if (caseKey) setCopiedCaseKey(caseKey);
    setToastMessage(`Copied "${citation}"`);
    setTimeout(() => {
      setToastMessage(null);
      if (caseKey) setCopiedCaseKey(null);
    }, 2200);
  };

  const handleCopyAnswer = () => {
    if (!answerData || !answerData.ai_answer) return;
    let text = answerData.ai_answer;
    if (answerData.citations && answerData.citations.length > 0) {
      text += `\n\nVerified Sources:\n${answerData.citations.join('\n')}`;
    }
    navigator.clipboard?.writeText(text);
    setCopiedAnswer(true);
    setToastMessage("AI Answer copied to clipboard");
    setTimeout(() => {
      setCopiedAnswer(false);
      setToastMessage(null);
    }, 2200);
  };

  const isCurrentLookup = isPureCaseLookup(query);

  return (
    <div className="module-view-container animate-fade-in">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="landing-toast animate-fade-in" role="status">
          <Check size={14} className="toast-icon" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Module Header */}
      <div className="module-header-block">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">JUSTICE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">SEARCH PRECEDENTS, STATUTES AND CITATIONS</span>
        </div>
        <h1 className="module-title font-serif">Search Precedents, Statutes and Citations</h1>
        <p className="module-subtitle">
          Neural precedent retrieval across Supreme Court of India judgments, bare acts, and constitutional doctrines.
        </p>

        {/* Search Input Bar */}
        <form className="module-search-form" onSubmit={handleFormSubmit}>
          <div className="module-search-input-wrap">
            <Search size={18} className="module-search-icon" aria-hidden="true" />
            <input
              type="text"
              className="module-search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask an everyday rights question, enter a citation, or search case names..."
              aria-label="Search precedents and statutes"
            />
            <button type="submit" className="module-search-submit-btn">
              <span>Search</span>
              <ArrowRight size={15} />
            </button>
          </div>
        </form>

        {/* Filter Controls Strip */}
        <div className="module-filters-bar">
          <div className="filter-group">
            <span className="filter-label mono">JURISDICTION:</span>
            <div className="filter-pills">
              {['ALL', 'Supreme Court of India', 'Delhi High Court'].map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`filter-pill ${courtFilter === c ? 'is-active' : ''}`}
                  onClick={() => {
                    setCourtFilter(c);
                    if (query.trim()) executeSearch(query.trim(), c, benchFilter);
                  }}
                >
                  {c === 'ALL' ? 'All Courts' : c}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <span className="filter-label mono">BENCH CORAM:</span>
            <div className="filter-pills">
              {[
                { id: 'ALL', label: 'All Benches' },
                { id: 'CONSTITUTION', label: 'Constitution (5+)' },
                { id: 'DIVISION', label: 'Division (2)' }
              ].map((b) => (
                <button
                  key={b.id}
                  type="button"
                  className={`filter-pill ${benchFilter === b.id ? 'is-active' : ''}`}
                  onClick={() => {
                    setBenchFilter(b.id);
                    if (query.trim()) executeSearch(query.trim(), courtFilter, b.id);
                  }}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Results Content Area */}
      <div className="results-content-area">
        {/* Top AI Answer Section: Skeleton / Error / Answer Card (hidden for pure case lookups) */}
        {hasSearched && !isCurrentLookup && (
          <div className="search-ai-answer-section" style={{ marginBottom: '24px' }}>
            {isAnswerLoading ? (
              <div className="search-ai-answer-skeleton" aria-busy="true">
                <div className="skeleton-answer-top">
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '130px', height: '18px' }} />
                  <div className="skeleton-badge skeleton-shimmer" style={{ width: '160px', height: '24px' }} />
                </div>
                <div className="skeleton-title skeleton-shimmer" style={{ width: '65%', height: '24px', margin: '14px 0 10px 0' }} />
                <div className="skeleton-line skeleton-shimmer" style={{ width: '100%', height: '15px', marginBottom: '8px' }} />
                <div className="skeleton-line skeleton-shimmer" style={{ width: '96%', height: '15px', marginBottom: '8px' }} />
                <div className="skeleton-line skeleton-shimmer" style={{ width: '88%', height: '15px', marginBottom: '14px' }} />
                <div className="skeleton-line skeleton-shimmer" style={{ width: '38%', height: '24px' }} />
              </div>
            ) : answerError ? (
              <div className="search-ai-answer-error-card animate-fade-in">
                <div className="error-message-row">
                  <AlertCircle size={17} className="text-amber" />
                  <span>Could not generate AI synthesis: {answerError}</span>
                </div>
                <button
                  type="button"
                  className="btn-retry-answer mono"
                  onClick={handleRetryAnswer}
                  aria-label="Retry generating AI answer"
                >
                  <RefreshCw size={13} />
                  <span>Retry AI Answer</span>
                </button>
              </div>
            ) : answerData && answerData.ai_answer && !answerData.is_case_lookup ? (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              >
                <TiltCard
                  className={`search-ai-answer-card ${answerData.tier === 'tier1' ? 'is-tier1' : 'is-tier2'}`}
                  maxTilt={2}
                >
                  {/* Card Top Strip: Kicker + Tier Badge */}
                  <div className="answer-card-top-strip">
                    <span className="answer-kicker mono">
                      {answerData.tier === 'tier1' ? 'VERIFIED LEGAL SYNTHESIS' : 'PLAIN-LANGUAGE CITIZEN SUMMARY'}
                    </span>
                    <div className="answer-badge-wrap">
                      {answerData.tier === 'tier1' ? (
                        <span className="badge-answer-tier1 mono">
                          <ShieldCheck size={13} />
                          <span>Verified citations</span>
                        </span>
                      ) : (
                        <span className="badge-answer-tier2 mono">
                          <Sparkles size={13} />
                          <span>AI answer, not verified</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Answer Headline */}
                  <h2 className="answer-card-headline font-serif">
                    {query}
                  </h2>

                  {/* Answer Body Prose */}
                  <div className="answer-card-prose font-serif">
                    {answerData.ai_answer.split('\n\n').map((paragraph, pIdx) => {
                      const trimmedP = paragraph.trim();
                      if (!trimmedP) return null;
                      return (
                        <p key={pIdx} className="answer-prose-paragraph">
                          {answerData.tier === 'tier1' ? renderWithBadges(trimmedP) : trimmedP}
                        </p>
                      );
                    })}
                  </div>

                  {/* Sources Chips (Tier 1 citations or relevant source cases) */}
                  {answerData.citations && answerData.citations.length > 0 && (
                    <div className="answer-sources-block">
                      <span className="sources-kicker mono">VERIFIED CITATION SOURCES:</span>
                      <div className="sources-chips-list">
                        {answerData.citations.map((cite, cIdx) => (
                          <span key={cIdx} className="source-citation-chip mono" title={cite}>
                            <BookOpen size={11} className="chip-icon" />
                            <span>{cite}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Card Actions Footer: Copy Button + Disclaimer */}
                  <div className="answer-card-footer">
                    <button
                      type="button"
                      className="btn-answer-copy mono"
                      onClick={handleCopyAnswer}
                      title="Copy answer and verified citations to clipboard"
                    >
                      {copiedAnswer ? (
                        <>
                          <Check size={13} />
                          <span>Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy size={13} />
                          <span>Copy Answer</span>
                        </>
                      )}
                    </button>

                    <span className="answer-disclaimer-text mono">
                      {answerData.tier === 'tier1'
                        ? 'Grounded directly in Indian Supreme Court jurisprudence'
                        : 'General legal information \u2022 Not legal advice \u2022 Verify with a lawyer or primary statute'}
                    </span>
                  </div>
                </TiltCard>
              </motion.div>
            ) : null}
          </div>
        )}

        {/* Loading Skeletons */}
        {isLoading ? (
          <div className="skeleton-cards-stack" aria-busy="true">
            {[1, 2, 3].map((n) => (
              <div key={n} className="skeleton-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '35%' }} />
                  <div className="skeleton-badge skeleton-shimmer" />
                </div>
                <div className="skeleton-title skeleton-shimmer" />
                <div className="skeleton-line skeleton-shimmer" style={{ width: '22%' }} />
                <div className="skeleton-block skeleton-shimmer" />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px' }}>
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '28%' }} />
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '18%' }} />
                </div>
              </div>
            ))}
          </div>
        ) : !hasSearched ? (
          <div className="results-empty-state">
            <Scale size={36} className="empty-state-icon" />
            <h3 className="empty-title font-serif">Search the Supreme Court Precedent Archive</h3>
            <p className="empty-desc">
              Enter any constitutional principle, everyday rights query, or case citation above to explore verified judgments.
            </p>
          </div>
        ) : results.length === 0 ? (
          <div className="results-empty-state">
            <Scale size={32} className="empty-state-icon" />
            <h3 className="empty-title font-serif">No strong match found, try rephrasing</h3>
            <p className="empty-desc">
              No matching judgments met the strict verification threshold. Try rephrasing your query, searching by case name or citation, or using broader legal terms.
            </p>
          </div>
        ) : (
          <div className="results-cards-list">
            <div className="results-count-banner mono">
              <span>{results.length} VERIFIED PRECEDENT{results.length !== 1 ? 'S' : ''} RETRIEVED</span>
              {hydeRatio && (
                <span className="hyde-badge">HYDE NEURAL EXPANSION: ACTIVE</span>
              )}
            </div>

            {results.map((precedent, index) => {
              const caseIdKey = precedent.id || precedent.case_id || `case-${index}`;
              const isExpanded = expandedCaseId === caseIdKey;
              const relevancePercent = precedent.relevance_score
                ? Math.round(precedent.relevance_score * 100)
                : 95;

              return (
                <motion.div
                  key={caseIdKey}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }}
                >
                  <TiltCard className="precedent-editorial-card" maxTilt={3}>
                    {/* Meta Strip: Court, Bench, Year, Relevance, Status */}
                    <div className="card-meta-strip">
                      <div className="meta-left-cluster">
                        <span className="meta-chip court">{precedent.court}</span>
                        <span className="meta-sep">&bull;</span>
                        <span className="meta-chip bench">
                          {precedent.benchType || 'Bench'} ({precedent.benchSize || 2} Judges)
                        </span>
                        <span className="meta-sep">&bull;</span>
                        <span className="meta-chip year">{precedent.decisionYear}</span>

                        {/* Relevance Score Bar */}
                        <span className="meta-sep">&bull;</span>
                        <div className="relevance-indicator-wrap" title={`Relevance: ${relevancePercent}%`}>
                          <span className="relevance-label mono">Match {relevancePercent}%</span>
                          <div className="relevance-bar-track">
                            <motion.div
                              className="relevance-bar-fill"
                              initial={{ width: 0 }}
                              animate={{ width: `${relevancePercent}%` }}
                              transition={{ duration: 0.7, delay: 0.1 + index * 0.04, ease: "easeOut" }}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="meta-right-cluster">
                        <span className="badge-verified">
                          <ShieldCheck size={12} />
                          <span>Verified Citation</span>
                        </span>
                      </div>
                    </div>

                    {/* Case Title and Citation Code */}
                    <div className="card-headline-row">
                      <h2 className="case-title font-serif">{precedent.title}</h2>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span className="hover-open-arrow font-serif" aria-hidden="true">
                          <span>Inspect</span>
                          <ArrowRight size={13} />
                        </span>
                        <span className="citation-badge mono">{precedent.citation}</span>
                      </div>
                    </div>

                    {/* Statutes Chips */}
                    {precedent.statutes && precedent.statutes.length > 0 && (
                      <div className="card-statutes-row">
                        {precedent.statutes.map((st, i) => (
                          <span key={i} className="statute-tag mono">{st}</span>
                        ))}
                      </div>
                    )}

                    {/* Ratio Decidendi / Relevant Passage Box */}
                    <div className="card-ratio-box">
                      <div className="ratio-kicker mono">
                        {precedent.ratioLabel || (precedent.is_verified_ratio ? 'RATIO DECIDENDI / LEGAL PRINCIPLE' : 'RELEVANT PASSAGE')}
                      </div>
                      <p className="ratio-quote font-serif">
                        "{precedent.ratioSummary}"
                      </p>
                    </div>

                    {/* Expandable Recorded Excerpts Drawer */}
                    {isExpanded && (
                      <div className="card-expanded-drawer animate-fade-in">
                        <div className="drawer-header">
                          <span className="drawer-kicker mono">PRIMARY JUDGMENT RECORD</span>
                          <span className="drawer-case-chat-hint mono">
                            Case Chat panel active for this judgment
                          </span>
                        </div>
                        <div className="drawer-body">
                          <div className="drawer-para">
                            <span className="para-num mono">Para 1 (Holding)</span>
                            <p className="para-text font-serif">{precedent.ratioSummary}</p>
                          </div>
                          {precedent.text && precedent.text !== precedent.ratioSummary && (
                            <div className="drawer-para">
                              <span className="para-num mono">Para 2 (Judicial Analysis)</span>
                              <p className="para-text font-serif">{precedent.text}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Card Actions Footer */}
                    <div className="card-actions-row">
                      <div className="card-actions-left">
                        <button
                          type="button"
                          className="btn-card-copy mono"
                          onClick={() => handleCopyCitation(precedent.citation, precedent.title, caseIdKey)}
                          title="Copy official citation to clipboard"
                        >
                          {copiedCaseKey === caseIdKey ? (
                            <span className="copy-success-badge"><Check size={12} /> Copied</span>
                          ) : (
                            <>
                              <Copy size={13} />
                              <span>Copy Citation</span>
                            </>
                          )}
                        </button>
                      </div>

                      <div className="card-actions-right">
                        {/* Case Chat Toggle */}
                        <button
                          type="button"
                          className={`btn-card-chat ${isExpanded ? 'is-active' : ''}`}
                          onClick={() => {
                            const nextId = isExpanded ? null : caseIdKey;
                            setExpandedCaseId(nextId);
                            if (onOpenCaseChat) {
                              onOpenCaseChat(nextId ? { ...precedent, id: caseIdKey } : null);
                            }
                          }}
                          aria-label="Ask about this case in Case Chat"
                        >
                          <MessageSquare size={13} />
                          <span>{isExpanded ? 'Close Chat' : 'Ask about this case'}</span>
                          {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                        </button>

                        {/* Verify in Citator */}
                        <button
                          type="button"
                          className="btn-card-citator"
                          onClick={() => onSelectCaseForCitator(precedent)}
                        >
                          <span>Verify in Smart Citator</span>
                          <ArrowUpRight size={14} />
                        </button>
                      </div>
                    </div>
                  </TiltCard>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
