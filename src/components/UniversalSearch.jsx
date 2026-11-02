import React, { useState, useEffect } from 'react';
import { Search, ArrowRight, ArrowUpRight, Sparkles, SlidersHorizontal, Scale, MessageSquare, ChevronDown, ChevronUp } from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { searchPrecedentsWithBackend } from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

const ROTATING_PLACEHOLDERS = [
  "Section 27 Contract Act post termination non compete enforceability",
  "What are my rights if an officer arrests me without a warrant?",
  "Can my landlord evict me without notice?",
  "What should I do if a police officer asks for a bribe?",
  "What are my rights when stopped on my bike?",
  "Are non-compete clauses valid after I quit my job?"
];

export default function UniversalSearch({ onSelectCaseForCitator, onOpenCaseChat }) {
  const [query, setQuery] = useState('');
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [placeholderFade, setPlaceholderFade] = useState(false);
  const [courtFilter, setCourtFilter] = useState('ALL');
  const [benchFilter, setBenchFilter] = useState('ALL');
  const [showHyde, setShowHyde] = useState(false);
  const [hydeRatio, setHydeRatio] = useState('');
  const [results, setResults] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [expandedCaseId, setExpandedCaseId] = useState(null);
  const [modelUsed, setModelUsed] = useState('openai/gpt-oss-120b');
  const [isSearching, setIsSearching] = useState(false);

  // Rotating placeholders every 4 seconds with smooth fade transition
  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderFade(true);
      setTimeout(() => {
        setPlaceholderIndex((prev) => (prev + 1) % ROTATING_PLACEHOLDERS.length);
        setPlaceholderFade(false);
      }, 350);
    }, 4000);

    return () => clearInterval(interval);
  }, []);

  const sampleQueries = [
    { label: "Arrested without a warrant", text: "What to do if police arrest me without a warrant" },
    { label: "Landlord eviction notice", text: "Can my landlord evict me without notice" },
    { label: "Police asking for a bribe", text: "What should I do if a police officer asks for a bribe" },
    { label: "Rights when stopped by traffic police", text: "What are my rights when stopped by traffic police on the road" },
    { label: "Non-Compete Enforceability (Sec 27)", text: "Section 27 Contract Act post termination non compete enforceability" },
    { label: "Right to Privacy & Art. 21", text: "Right to privacy under Article 21 proportionality test and state surveillance" }
  ];
  const [spellingCorrection, setSpellingCorrection] = useState(null);

  const handleSearchInstead = (original) => {
    setQuery(original);
    setSpellingCorrection(null);
    executeSearch(original, courtFilter, benchFilter, true);
  };

  // Execute search against FastAPI backend - only runs on non-empty query
  const executeSearch = async (searchQuery = query, court = courtFilter, bench = benchFilter, bypassCorrection = false) => {
    const trimmed = searchQuery ? searchQuery.trim() : '';
    if (!trimmed) {
      return;
    }
    setIsSearching(true);
    setHasSearched(true);
    try {
      const resp = await searchPrecedentsWithBackend(trimmed, court, bench, true, 8, bypassCorrection);
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
        setShowHyde(true);
      } else {
        setShowHyde(false);
      }
    } catch (err) {
      setSpellingCorrection(null);
      console.warn("[UniversalSearch] Backend search failed; using local corpus filter:", err.message);
      // Local fallback filter
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
    } finally {
      setIsSearching(false);
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    executeSearch(trimmed, courtFilter, benchFilter);
  };

  const handleSelectSampleQuery = (sampleText) => {
    setQuery(sampleText);
    executeSearch(sampleText, courtFilter, benchFilter);
  };

  const handleBenchChange = (newBench) => {
    setBenchFilter(newBench);
    if (query && query.trim()) {
      executeSearch(query.trim(), courtFilter, newBench);
    }
  };

  const handleCourtChange = (newCourt) => {
    setCourtFilter(newCourt);
    if (query && query.trim()) {
      executeSearch(query.trim(), newCourt, benchFilter);
    }
  };

  return (
    <div className="workspace-module-pane">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">UNIVERSAL SEARCH</span>
        </div>
        <h1 className="module-heading font-judicial">Universal Search</h1>
        <p className="module-description">
          Natural language jurisprudence retrieval across Indian Supreme Court judgments.
          Synthesized with neural HyDE reasoning and dense-sparse hybrid retrieval.
        </p>

        {/* Clean Workspace Search Bar */}
        <form onSubmit={handleSearchSubmit} className="workspace-search-bar">
          <div className="search-input-wrapper">
            <Search className="search-input-icon" size={18} />
            <input
              type="text"
              className="search-input-field"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder=""
              aria-label="Search Indian Supreme Court judgments"
            />
            {!query && (
              <span
                className={`search-rotating-placeholder ${placeholderFade ? 'is-fading' : ''}`}
                aria-hidden="true"
              >
                {ROTATING_PLACEHOLDERS[placeholderIndex]}
              </span>
            )}
          </div>
          <button
            type="submit"
            className="btn-primary search-action-btn"
            disabled={isSearching || !query.trim()}
          >
            <span>{isSearching ? 'Synthesizing...' : 'Search Precedents'}</span>
            <ArrowRight size={15} />
          </button>
        </form>

        {/* Topic Suggestion Chips */}
        <div className="search-topics-strip">
          <span className="topics-label">POPULAR QUERIES:</span>
          <div className="topics-list">
            {sampleQueries.map((q, idx) => (
              <button
                key={idx}
                type="button"
                className="topic-chip"
                onClick={() => handleSelectSampleQuery(q.text)}
              >
                {q.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* HyDE Ratio Decidendi Synthetic Preview Box */}
      {showHyde && (
        <div className="workspace-callout-card hyde-callout">
          <div className="callout-header">
            <div className="callout-title-wrap">
              <Sparkles size={14} className="callout-icon" />
              <span className="callout-title">HYDE RATIO DECIDENDI &bull; NEURAL REASONING</span>
            </div>
            <button 
              type="button" 
              className="btn-text-subtle" 
              onClick={() => setShowHyde(false)}
            >
              Dismiss
            </button>
          </div>
          <blockquote className="hyde-quote font-judicial">
            {renderWithBadges(hydeRatio)}
          </blockquote>
          <div className="callout-footer-meta">
            <span className="meta-tag">Model: <strong>{modelUsed}</strong></span>
            <span className="meta-sep">&bull;</span>
            <span className="meta-tag">Retrieval: <strong>HyDE Dense + BM25 Lexical</strong></span>
          </div>
        </div>
      )}

      {/* Filter and Control Bar */}
      <div className="workspace-filter-row">
        <div className="filter-summary">
          {hasSearched ? (
            <>
              <span className="filter-count">{results.length}</span>
              <span className="filter-label">
                precedents retrieved {isSearching && '(updating...)'}
              </span>
            </>
          ) : (
            <span className="filter-label">
              Awaiting query &mdash; choose a topic chip or enter your question
            </span>
          )}
        </div>

        <div className="filter-dropdowns">
          <div className="dropdown-control">
            <label className="dropdown-label">BENCH:</label>
            <select 
              value={benchFilter} 
              onChange={(e) => handleBenchChange(e.target.value)}
              className="workspace-select"
            >
              <option value="ALL">All Benches</option>
              <option value="CONSTITUTION">Constitution Bench (5+ Judges)</option>
              <option value="DIVISION">Division Bench (2 Judges)</option>
            </select>
          </div>

          <div className="dropdown-control">
            <label className="dropdown-label">COURT:</label>
            <select 
              value={courtFilter} 
              onChange={(e) => handleCourtChange(e.target.value)}
              className="workspace-select"
            >
              <option value="ALL">All Jurisdictions</option>
              <option value="Supreme Court of India">Supreme Court of India</option>
            </select>
          </div>
        </div>
      </div>

      {/* Spelling Tolerance Line: Showing results for <corrected>. Search instead for <original> */}
      {hasSearched && spellingCorrection && (
        <div className="spelling-correction-line" style={{
          fontSize: '0.92rem',
          color: 'var(--text-secondary, #8CA69E)',
          padding: '10px 16px',
          margin: '0 0 16px 0',
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

      {/* Precedents Card Results List */}
      <div className="precedents-card-list">
        {/* SKELETON LOADING STATE */}
        {isSearching ? (
          <div className="skeleton-cards-stack">
            {[1, 2, 3].map((n) => (
              <div key={n} className="skeleton-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '40%' }} />
                  <div className="skeleton-badge skeleton-shimmer" />
                </div>
                <div className="skeleton-title skeleton-shimmer" />
                <div className="skeleton-line skeleton-shimmer" style={{ width: '25%' }} />
                <div className="skeleton-block skeleton-shimmer" />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '30%' }} />
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '20%' }} />
                </div>
              </div>
            ))}
          </div>
        ) : !hasSearched ? (
          <div className="workspace-empty-card initial-search-prompt">
            <Scale size={36} className="empty-icon" />
            <h3 className="empty-heading font-judicial">Ready to Search Supreme Court Judgments</h3>
            <p className="empty-text">
              Type an everyday question or legal doctrine above, or click any popular query chip to retrieve verified Supreme Court precedents.
            </p>
          </div>
        ) : results.length === 0 ? (
          <div className="workspace-empty-card">
            <Scale size={32} className="empty-icon" />
            <h3 className="empty-heading font-judicial">No matching precedents found</h3>
            <p className="empty-text">
              Try adjusting your bench or jurisdiction filters, or query using different legal doctrines.
            </p>
          </div>
        ) : (
          results.map((precedent) => (
            <article key={precedent.id} className="precedent-result-card">
              {/* Meta Row: Court, Bench, Year, Relevance, Status */}
              <div className="card-meta-row">
                <div className="card-meta-left">
                  <span className="court-chip">{precedent.court}</span>
                  <span className="meta-dot">&bull;</span>
                  <span className="bench-chip">{precedent.benchType || 'Bench'} ({precedent.benchSize || 2} Judges)</span>
                  {precedent.leadJudge ? (
                    <>
                      <span className="meta-dot">&bull;</span>
                      <span className="lead-judge-chip" title={`Lead Judge: ${precedent.leadJudge}`}>Lead: {precedent.leadJudge}</span>
                    </>
                  ) : null}
                  <span className="meta-dot">&bull;</span>
                  <span className="year-chip">{precedent.decisionYear || precedent.year}</span>

                  {/* Subtle Relevance Indicator */}
                  {precedent.relevance_score && (
                    <>
                      <span className="meta-dot">&bull;</span>
                      <span className="relevance-score-badge mono">
                        Match {Math.min(99, Math.max(0, Math.round(precedent.relevance_score * 100)))}%
                      </span>
                    </>
                  )}

                  {/* Retrieval Mode Badge (Vector vs Local Index Fallback) */}
                  {precedent.retrieval_mode && (
                    <>
                      <span className="meta-dot">&bull;</span>
                      <span className={`retrieval-mode-badge mono ${precedent.retrieval_mode.includes('fallback') ? 'is-fallback' : 'is-vector'}`}>
                        {precedent.retrieval_mode.includes('fallback') ? 'LOCAL INDEX' : 'QDRANT VECTOR'}
                      </span>
                    </>
                  )}
                </div>

                {/* Citator Status Pill */}
                <div className={`status-pill status-${(precedent.status || 'GREEN').toLowerCase()}`}>
                  <span className="status-dot-indicator" />
                  <span className="status-pill-text">{precedent.statusLabel || precedent.status}</span>
                </div>
              </div>

              {/* Case Title & Citation */}
              <div className="card-title-row">
                <h2 className="case-title-heading font-judicial">{precedent.title}</h2>
                <span className="citation-code-badge mono">{precedent.citation}</span>
              </div>

              {/* Statutory Provisions Chips */}
              {precedent.statutes && (
                <div className="card-statutes-row">
                  {precedent.statutes.map((st, i) => (
                    <span key={i} className="statute-chip mono">{st}</span>
                  ))}
                </div>
              )}

              {/* Ratio Decidendi */}
              <div className="card-ratio-box">
                <div className="ratio-header-label">CASE SUMMARY WRITTEN FOR THIS APP (NOT JUDGMENT TEXT; NOT VERIFIED)</div>
                <p className="ratio-text font-judicial">"{precedent.ratioSummary}"</p>
              </div>

              {/* Optional Expanded Judgment Section */}
              {expandedCaseId === precedent.id && (
                <div className="card-expanded-judgment-drawer animate-fade-in">
                  <div className="expanded-judgment-header">
                    <span className="expanded-kicker mono">RECORDED JUDGMENT EXCERPTS</span>
                    <span className="active-chat-pill">
                      <Sparkles size={12} />
                      <span>Case Chat Active</span>
                    </span>
                  </div>

                  <div className="expanded-paragraphs-stack">
                    <div id="chunk-0" className="expanded-para-item">
                      <div className="para-index-line mono">{precedent.is_verified_ratio ? 'Paragraph 1 (Holding & Ratio)' : 'Paragraph 1'}</div>
                      <p className="para-content font-judicial">{precedent.ratioSummary}</p>
                    </div>
                    {precedent.text && precedent.text !== precedent.ratioSummary && (
                      <div id="chunk-1" className="expanded-para-item">
                        <div className="para-index-line mono">Paragraph 2 (Court Analysis)</div>
                        <p className="para-content font-judicial">{precedent.text}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Card Footer: Coram & Actions */}
              <div className="card-footer-row">
                <div className="coram-details">
                  <span className="coram-label">Coram:</span>
                  <span className="coram-names">
                    {precedent.judges ? precedent.judges.slice(0, 3).join(', ') : "Coram details in citator"}
                    {precedent.judges && precedent.judges.length > 3 && ` + ${precedent.judges.length - 3} others`}
                  </span>
                </div>

                <div className="card-actions-cluster">
                  <button
                    type="button"
                    className={`btn-card-chat-action ${expandedCaseId === precedent.id ? 'active' : ''}`}
                    onClick={() => {
                      const nextId = expandedCaseId === precedent.id ? null : precedent.id;
                      setExpandedCaseId(nextId);
                      if (onOpenCaseChat) {
                        onOpenCaseChat(nextId ? precedent : null);
                      }
                    }}
                    title="Open Case Chat scoped to this precedent"
                    aria-label="Ask about this case in Case Chat"
                  >
                    <MessageSquare size={13} />
                    <span>{expandedCaseId === precedent.id ? 'Close Chat' : 'Ask about this case'}</span>
                    {expandedCaseId === precedent.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>

                  <button
                    type="button"
                    className="btn-card-action"
                    onClick={() => onSelectCaseForCitator(precedent)}
                  >
                    <span>Verify in Smart Citator</span>
                    <ArrowUpRight size={14} />
                  </button>
                </div>
              </div>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
