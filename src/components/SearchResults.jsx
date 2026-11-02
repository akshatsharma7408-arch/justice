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
  const [spellingCorrection, setSpellingCorrection] = useState(null);

  // AI Answer Card State
  const [answerData, setAnswerData] = useState(null);
  const [isAnswerLoading, setIsAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState(null);
  const [searchError, setSearchError] = useState(null);
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  // Execute search when initialQuery changes or on initial mount if provided
  useEffect(() => {
    if (initialQuery && initialQuery.trim()) {
      setQuery(initialQuery);
      executeSearch(initialQuery.trim(), courtFilter, benchFilter);
    }
  }, [initialQuery]);

  const handleSearchInstead = (original) => {
    setQuery(original);
    setSpellingCorrection(null);
    executeSearch(original, courtFilter, benchFilter, true);
  };

  const executeSearch = async (searchQuery = query, court = courtFilter, bench = benchFilter, bypassCorrection = false) => {
    const trimmed = (searchQuery || '').trim();
    if (!trimmed) {
      setSearchError("Search query cannot be empty. Please enter a legal question, statute, or case name.");
      setResults([]);
      setIsLoading(false);
      return;
    }
    if (trimmed.length > 300) {
      setSearchError("Please shorten your question. Queries are limited to 300 characters.");
      setResults([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setHasSearched(true);
    setSearchError(null);
    setAnswerError(null);

    const isLookup = isPureCaseLookup(trimmed);
    if (isLookup) {
      setAnswerData(null);
      setIsAnswerLoading(false);
    } else {
      setIsAnswerLoading(true);
    }

    // Parallel execution of precedent search + AI answer synthesis
    const searchPromise = searchPrecedentsWithBackend(trimmed, court, bench, true, 8, bypassCorrection)
      .then(resp => {
        if (resp && resp.has_spelling_correction && resp.corrected_query) {
          setSpellingCorrection({
            corrected: resp.corrected_query,
            original: resp.original_query || trimmed
          });
        } else {
          setSpellingCorrection(null);
        }
        if (resp && resp.results) {
          setResults(resp.results);
        }
        if (resp && resp.model_used) {
          setModelUsed(resp.model_used);
        }
        if (resp && resp.hyde_synthetic_ratio) {
          setHydeRatio(resp.hyde_synthetic_ratio);
        } else {
          setHydeRatio('');
        }
        return resp;
      })
      .catch(err => {
        setSpellingCorrection(null);
        const errText = (typeof err === 'object' && err?.message) ? err.message : String(err || '');
        const sanitized = (!errText || errText === '[object Object]')
          ? "Unable to reach legal database. Please check your connection or query."
          : errText;
        console.warn("[SearchResults] Backend search error:", sanitized);
        setSearchError(sanitized);
        setResults([]);
        return null;
      })
      .finally(() => {
        setIsLoading(false);
      });

    let answerPromise = null;
    if (!isLookup) {
      answerPromise = fetchSearchAnswerWithBackend(trimmed, court, bench, null, false, bypassCorrection)
        .then(ansResp => {
          if (ansResp && ansResp.is_case_lookup) {
            setAnswerData(null);
          } else {
            setAnswerData(ansResp);
          }
          return ansResp;
        })
        .catch(ansErr => {
          console.warn("[SearchResults] Search answer API call failed:", ansErr);
          setAnswerError(ansErr.message || "Failed to load AI answer");
          return null;
        })
        .finally(() => {
          setIsAnswerLoading(false);
        });
    }

    await Promise.allSettled(answerPromise ? [searchPromise, answerPromise] : [searchPromise]);
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

  const isCurrentLookup = isPureCaseLookup(query) || !query || !query.trim();

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
              maxLength={350}
            />
            <button
              type="submit"
              className="module-search-submit-btn"
              disabled={!query.trim() || query.length > 300}
            >
              <span>Search</span>
              <ArrowRight size={15} />
            </button>
          </div>
          {query.length > 300 && (
            <div className="search-char-limit-warning mono">
              Please shorten your question ({query.length}/300 characters)
            </div>
          )}
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
        {/* Friendly Retry Card for Backend or Validation Errors */}
        {searchError && (
          <div className="search-backend-error-card animate-fade-in" role="alert" style={{ marginBottom: '24px' }}>
            <div className="error-card-content">
              <div className="error-card-icon-wrap">
                <AlertCircle size={22} className="text-copper" />
              </div>
              <div className="error-card-text">
                <h3 className="error-card-title font-serif">
                  {typeof searchError === 'string' && searchError.includes("300")
                    ? "Question is too long"
                    : typeof searchError === 'string' && searchError.includes("empty")
                      ? "Search query required"
                      : "Unable to retrieve precedents"}
                </h3>
                <p className="error-card-desc">
                  {typeof searchError === 'string' && searchError.includes("300")
                    ? "Please shorten your question. Queries are limited to 300 characters."
                    : typeof searchError === 'string' && searchError.includes("empty")
                      ? "Please enter a legal question, bare act section, or case title to search."
                      : `${searchError && searchError !== '[object Object]' ? searchError : 'Connection or query error'}. Click Retry to try connecting again.`}
                </p>
              </div>
            </div>
            <div className="error-card-actions">
              <button
                type="button"
                className="btn-friendly-retry mono"
                onClick={() => executeSearch(query, courtFilter, benchFilter)}
              >
                <RefreshCw size={13} className={isLoading ? "spin-icon" : ""} />
                <span>Retry Search</span>
              </button>
            </div>
          </div>
        )}

        {/* Top AI Answer Section: Skeleton / Error / Answer Card (hidden for pure case lookups and blank queries) */}
        {hasSearched && !isCurrentLookup && !searchError && (
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
                      {answerData.tier === 'unreliable' ? 'LEGAL NOTICE' : answerData.tier === 'not_found' ? 'NOT FOUND IN THIS DATABASE' : answerData.tier === 'unverified_ai' ? 'AI-GENERATED ANSWER - NOT CHECKED AGAINST LEGAL SOURCES' : answerData.tier === 'statute_text' ? 'STATUTE TEXT' : (() => { const tl = answerData.tier_label || ''; if (tl.includes('NOT independently verified')) return 'STATUTE TEXT + AI RESTATEMENT (NOT INDEPENDENTLY VERIFIED)'; if (tl.includes('important note')) return 'STATUTE TEXT WITH AN IMPORTANT NOTE'; if (tl.includes('footnote note')) return 'STATUTE TEXT WITH A FOOTNOTE NOTE'; if (tl.includes('written for this app')) return 'STATUTE TEXT AND A SHORT SUMMARY (NOT CHECKED AGAINST THE JUDGMENTS)'; const ex = tl.includes('case excerpt'); const ai = tl.includes('AI explanation'); return ex && ai ? 'STATUTE TEXT, AI EXPLANATION AND CASE EXCERPT' : ex ? 'STATUTE TEXT AND CASE EXCERPT' : ai ? 'STATUTE TEXT AND AI EXPLANATION' : tl === 'Authoritative statutory provision' ? 'STATUTE TEXT' : 'AI SUMMARY'; })()}
                    </span>
                    <div className="answer-badge-wrap">
                      {answerData.hide_badge || answerData.tier === 'unreliable' || answerData.tier === 'not_found' ? null : (
                        <span className={`badge-answer-${answerData.tier === 'tier1' ? 'tier1' : 'tier2'} mono`}>
                          {answerData.tier === 'tier1' ? <ShieldCheck size={13} /> : <Sparkles size={13} />}
                          <span>{answerData.tier_label || (answerData.tier === 'tier1' ? 'AI summary based on the cases below' : 'AI summary, check the cases below')}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Answer Headline */}
                  <h2 className="answer-card-headline font-serif">
                    {query}
                  </h2>

                  {answerData.tier === 'unverified_ai' && (
                    <p className="answer-statute-notice" role="note" style={{ borderLeft: '3px solid #b8860b', background: 'rgba(184,134,11,0.10)', padding: '10px 14px', borderRadius: 6 }}>
                      <strong>{answerData.tier_label || 'AI-generated answer. Not checked against legal sources. May be wrong or outdated.'}</strong>
                    </p>
                  )}
                  {answerData.statute_notice && (
                    <p className="answer-statute-notice" role="note">
                      <strong>Note: </strong>{answerData.statute_notice}
                    </p>
                  )}

                  {/* Answer Body Prose */}
                  <div className="answer-card-prose font-serif">
                    {answerData.ai_answer.split('\n\n').map((paragraph, pIdx) => {
                      const trimmedP = paragraph.trim();
                      if (!trimmedP) return null;
                      if (trimmedP.startsWith('AI RESTATEMENT')) {
                        const _head = trimmedP.split('\n')[0];
                        return (
                          <div key={pIdx} className="answer-law-note" role="note" style={{ margin: '14px 0', padding: '12px 16px', borderLeft: '3px solid #b8860b', background: 'rgba(184,134,11,0.10)', borderRadius: 6 }}>
                            <div className="mono" style={{ fontSize: 11, letterSpacing: '0.08em', color: '#b8860b', marginBottom: 6 }}>{_head.replace(/:$/, '')}</div>
                            <p className="answer-prose-paragraph" style={{ margin: 0, whiteSpace: 'pre-line' }}>{trimmedP.slice(_head.length).trim()}</p>
                          </div>
                        );
                      }
                      if (answerData.tier === 'unreliable' && /https?:\/\//.test(trimmedP)) {
                        return (
                          <p key={pIdx} className="answer-prose-paragraph" style={{ whiteSpace: 'pre-line', wordBreak: 'break-word' }}>
                            {trimmedP.split(/(https?:\/\/[^\s]+)/g).map((seg, k) => /^https?:\/\//.test(seg)
                              ? <a key={k} href={seg} target="_blank" rel="noopener noreferrer" style={{ color: '#7fc4a5', textDecoration: 'underline' }}>{seg}</a>
                              : <span key={k}>{seg}</span>)}
                          </p>
                        );
                      }
                      if (answerData.tier === 'unverified_ai') {
                        return <p key={pIdx} className="answer-prose-paragraph" style={{ whiteSpace: 'pre-line' }}>{trimmedP}</p>;
                      }
                      if (trimmedP.startsWith('NOTE ON WHICH LAW APPLIES')) {
                        return (
                          <div key={pIdx} className="answer-law-note" role="note" style={{ margin: '14px 0', padding: '12px 16px', borderLeft: '3px solid #b8860b', background: 'rgba(184,134,11,0.10)', borderRadius: 6 }}>
                            <div className="mono" style={{ fontSize: 11, letterSpacing: '0.08em', color: '#b8860b', marginBottom: 6 }}>WHICH LAW APPLIES</div>
                            <p className="answer-prose-paragraph" style={{ margin: 0 }}>{trimmedP.replace('NOTE ON WHICH LAW APPLIES:', '').trim()}</p>
                          </div>
                        );
                      }
                      if (trimmedP.startsWith('POSSIBLY RELEVANT PROVISION')) {
                        return (
                          <div key={pIdx} className="mono" style={{ margin: '18px 0 4px', fontSize: 11, letterSpacing: '0.06em', color: '#9aa7a0', lineHeight: 1.5 }}>
                            SUGGESTED PROVISION TEXT - {trimmedP.replace('POSSIBLY RELEVANT PROVISION', '').trim()}
                          </div>
                        );
                      }
                      if (trimmedP.includes('\nEdition: ')) {
                        return (
                          <div key={pIdx} className="answer-statute-block" style={{ margin: '8px 0', padding: '12px 16px', borderLeft: '3px solid #5f8f7a', background: 'rgba(95,143,122,0.08)', borderRadius: 6, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 14, lineHeight: 1.55 }}>
                            {trimmedP}
                          </div>
                        );
                      }
                      const aiPrefix = 'Plain-English explanation (AI-written from the text above; not a verified statement of law):';
                      if (trimmedP.startsWith(aiPrefix) || trimmedP.startsWith('AI explanation unavailable')) {
                        const isExpl = trimmedP.startsWith(aiPrefix);
                        return (
                          <div key={pIdx} className="answer-ai-explainer" style={{ margin: '14px 0', padding: '12px 16px', borderLeft: '3px solid #c97d3c', background: 'rgba(201,125,60,0.08)', borderRadius: 6 }}>
                            <div className="mono" style={{ fontSize: 11, letterSpacing: '0.08em', color: '#c97d3c', marginBottom: 6 }}>
                              {isExpl ? 'AI EXPLANATION - NOT VERIFIED, WRITTEN FROM THE STATUTORY TEXT ABOVE' : 'AI EXPLANATION'}
                            </div>
                            {(isExpl ? trimmedP.slice(aiPrefix.length).trim() : trimmedP).split('\n').filter(l => l.trim()).map((ln, li) => {
                              const isNote = ln.trim().startsWith('(Wording prepared');
                              return <p key={li} className="answer-prose-paragraph" style={isNote ? { margin: '10px 0 0', fontSize: 12, opacity: 0.8, lineHeight: 1.5 } : { margin: li ? '8px 0 0' : 0, lineHeight: 1.6 }}>{ln}</p>;
                            })}
                          </div>
                        );
                      }
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
                      {answerData.tier === 'tier1' && (answerData.no_strong_case_match || !(answerData.source_cases && answerData.source_cases.length))
                        ? 'Statutory text from the verified database; any AI explanation is not verified \u2022 Not formal legal advice'
                        : answerData.tier === 'tier1'
                        ? 'Statute text and case excerpts below; any AI explanation is not verified, and an excerpt is not a verified holding \u2022 Not formal legal advice'
                        : answerData.tier === 'statute_text'
                          ? 'Exact statute wording as quoted in Supreme Court judgments \u2022 Current applicability not verified \u2022 Not legal advice'
                        : answerData.tier === 'unreliable'
                          ? 'No AI explanation available \u2022 Not legal advice \u2022 Check the primary source or a lawyer'
                          : 'General legal information \u2022 Not legal advice \u2022 Verify with a lawyer or primary statute'}
                    </span>
                  </div>
                </TiltCard>
              </motion.div>
            ) : null}
          </div>
        )}

        {/* Spelling Tolerance Banner */}
        {hasSearched && spellingCorrection && (
          <div className="spelling-correction-line" style={{
            fontSize: '0.875rem',
            color: 'var(--text-secondary, #8CA69E)',
            padding: '10px 16px',
            marginBottom: '16px',
            backgroundColor: 'rgba(212, 163, 89, 0.08)',
            border: '1px solid rgba(212, 163, 89, 0.25)',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <span>
              Showing results for <strong style={{ color: 'var(--ivory, #F5F2EB)' }}>{spellingCorrection.corrected}</strong>. Search instead for{' '}
              <button
                type="button"
                onClick={() => handleSearchInstead(spellingCorrection.original)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--copper, #D4A359)',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  padding: 0,
                  font: 'inherit',
                  fontWeight: 600
                }}
              >
                {spellingCorrection.original}
              </button>
            </span>
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
            <h3 className="empty-title font-serif">
              {Boolean(query && query.match(/\b(?:air\s*\d{4}|\(\d{4}\)|\d{4}\s*\d+\s*scc|\b\d{4}\s*insc\b|\bscr\b|\bscale\b|\b\d{4}\b.*\b(?:sc|scc|scr|del|bom)\b)/i))
                ? "No case with this citation in our database"
                : (answerData && answerData.answer_text_present !== false && (answerData.ai_answer || answerData.answer) ? "No matching judgments found for this query" : "No strong match found, try rephrasing")}
            </h3>
            <p className="empty-desc">
              {Boolean(query && query.match(/\b(?:air\s*\d{4}|\(\d{4}\)|\d{4}\s*\d+\s*scc|\b\d{4}\s*insc\b|\bscr\b|\bscale\b|\b\d{4}\b.*\b(?:sc|scc|scr|del|bom)\b)/i))
                ? "This specific citation is not present in our indexed archive of Supreme Court of India and Delhi High Court judgments."
                : (answerData && (answerData.ai_answer || answerData.answer) && answerData.tier_label && answerData.tier !== 'unverified_ai' ? "The statute result above remains available. No judgment met the strict verification threshold for this query; this does not say that no case exists." : "No matching judgments met the strict verification threshold. Try rephrasing your query, searching by case name or citation, or using broader legal terms.")}
            </p>
          </div>
        ) : (
          <div className="results-cards-list">
            <div className="results-count-banner mono">
              <span>{results.length} VERIFIED PRECEDENT{results.length !== 1 ? 'S' : ''} RETRIEVED</span>
            </div>

            {results.map((precedent, index) => {
              const caseIdKey = precedent.id || precedent.case_id || `case-${index}`;
              const isExpanded = expandedCaseId === caseIdKey;
              const relevancePercent = precedent.relevance_score
                ? Math.min(99, Math.max(0, Math.round(precedent.relevance_score * 100)))
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
                        {precedent.leadJudge ? (
                          <>
                            <span className="meta-sep">&bull;</span>
                            <span className="meta-chip lead-judge" title={`Lead Judge: ${precedent.leadJudge}`}>
                              Lead: {precedent.leadJudge}
                            </span>
                          </>
                        ) : null}
                        <span className="meta-sep">&bull;</span>
                        <span className="meta-chip year">{precedent.decisionYear || precedent.year}</span>
                      </div>

                      <div className="meta-right-cluster">
                        {Boolean(
                          precedent.is_verified_ratio ||
                          precedent.retrieval_mode?.includes('sc_judgments') ||
                          precedent.retrieval_mode?.includes('verified_precedents') ||
                          precedent.landmark ||
                          precedent.source_link ||
                          precedent.case_id ||
                          (precedent.year && precedent.court)
                        ) && (
                            <span className="badge-verified">
                              <ShieldCheck size={12} />
                              <span>Verified Citation</span>
                            </span>
                          )}
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
                            <span className="para-num mono">Judicial Holding</span>
                            <p className="para-text font-serif">{precedent.ratioSummary}</p>
                          </div>
                          {precedent.text && precedent.text !== precedent.ratioSummary && (
                            <div className="drawer-para">
                              <span className="para-num mono">Judicial Excerpt</span>
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
