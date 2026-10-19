import React, { useState, useEffect } from 'react';
import { 
  Search, ArrowRight, ArrowUpRight, Scale, ShieldCheck, 
  ChevronDown, ChevronUp, MessageSquare, Copy, Check, Filter, Sparkles 
} from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { searchPrecedentsWithBackend } from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

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
  const [modelUsed, setModelUsed] = useState('openai/gpt-oss-120b');
  const [hydeRatio, setHydeRatio] = useState('');

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

    try {
      const resp = await searchPrecedentsWithBackend(trimmed, court, bench, true, 10);
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
    } finally {
      setIsLoading(false);
    }
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    executeSearch(q, courtFilter, benchFilter);
    if (onSearchAgain) onSearchAgain(q);
  };

  const handleCopyCitation = (citation, title) => {
    const textToCopy = `${title}, ${citation}`;
    navigator.clipboard?.writeText(textToCopy);
    setToastMessage(`Copied "${citation}"`);
    setTimeout(() => setToastMessage(null), 2200);
  };

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
            <h3 className="empty-title font-serif">No Precedents Found</h3>
            <p className="empty-desc">
              No matching judgments met the strict verification threshold. Try broadening your bench filters or searching by statutory sections.
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
              const isExpanded = expandedCaseId === precedent.id;
              const relevancePercent = precedent.relevance_score
                ? Math.round(precedent.relevance_score * 100)
                : 95;

              return (
                <article
                  key={precedent.id || index}
                  className="precedent-editorial-card animate-stagger"
                  style={{ animationDelay: `${index * 60}ms` }}
                >
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
                          <div
                            className="relevance-bar-fill"
                            style={{ width: `${relevancePercent}%` }}
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
                    <span className="citation-badge mono">{precedent.citation}</span>
                  </div>

                  {/* Statutes Chips */}
                  {precedent.statutes && precedent.statutes.length > 0 && (
                    <div className="card-statutes-row">
                      {precedent.statutes.map((st, i) => (
                        <span key={i} className="statute-tag mono">{st}</span>
                      ))}
                    </div>
                  )}

                  {/* Ratio Decidendi Box */}
                  <div className="card-ratio-box">
                    <div className="ratio-kicker mono">RATIO DECIDENDI / LEGAL PRINCIPLE</div>
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
                        onClick={() => handleCopyCitation(precedent.citation, precedent.title)}
                        title="Copy official citation to clipboard"
                      >
                        <Copy size={13} />
                        <span>Copy Citation</span>
                      </button>
                    </div>

                    <div className="card-actions-right">
                      {/* Case Chat Toggle */}
                      <button
                        type="button"
                        className={`btn-card-chat ${isExpanded ? 'is-active' : ''}`}
                        onClick={() => {
                          const nextId = isExpanded ? null : precedent.id;
                          setExpandedCaseId(nextId);
                          if (onOpenCaseChat) {
                            onOpenCaseChat(nextId ? precedent : null);
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
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
