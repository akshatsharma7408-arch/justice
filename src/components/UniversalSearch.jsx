import React, { useState, useEffect } from 'react';
import { Search, ArrowRight, SlidersHorizontal, ArrowUpRight, Sparkles, Loader2 } from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { searchPrecedentsWithBackend } from '../config/gemini';

export default function UniversalSearch({ onSelectCaseForCitator }) {
  const [query, setQuery] = useState('Section 27 Contract Act post termination non compete enforceability');
  const [courtFilter, setCourtFilter] = useState('ALL');
  const [benchFilter, setBenchFilter] = useState('ALL');
  const [showHyde, setShowHyde] = useState(true);
  const [hydeRatio, setHydeRatio] = useState(
    "Under Indian jurisprudence governing the Indian Contract Act, 1872, the doctrine of restraint of trade (Section 27) applies strictly to all covenants operating post-termination. The Supreme Court of India does not import the English law test of 'reasonableness' for covenants operating after cessation of employment; such covenants are void in toto pursuant to Percept D'Mark v. Zaheer Khan (2006) and Superintendence Co. v. Krishan Murgai (1981)."
  );
  const [results, setResults] = useState(LANDMARK_PRECEDENTS);
  const [isSearching, setIsSearching] = useState(false);

  const sampleQueries = [
    { label: "Non-Compete Enforceability (Sec 27)", text: "Section 27 Contract Act post termination non compete enforceability" },
    { label: "Right to Privacy & Art. 21", text: "Right to privacy under Article 21 proportionality test and state surveillance" },
    { label: "Liquidated Damages as Penalty (Sec 74)", text: "Section 74 Indian Contract Act forfeiture of earnest money without proof of loss" },
    { label: "PMLA Bail & Twin Conditions", text: "Section 45 PMLA twin conditions for bail and supply of ECIR" },
    { label: "Habeas Corpus & Emergency", text: "ADM Jabalpur habeas corpus emergency detention suspension of Article 21" }
  ];

  // Execute search against FastAPI backend
  const executeSearch = async (searchQuery = query, court = courtFilter, bench = benchFilter) => {
    setIsSearching(true);
    try {
      const resp = await searchPrecedentsWithBackend(searchQuery, court, bench, true, 10);
      if (resp && resp.results) {
        setResults(resp.results);
      }
      if (resp && resp.hyde_synthetic_ratio) {
        setHydeRatio(resp.hyde_synthetic_ratio);
        setShowHyde(true);
      }
    } catch (err) {
      console.warn("[UniversalSearch] Backend search failed; using local corpus filter:", err.message);
      // Local fallback filter
      const terms = searchQuery.toLowerCase().split(' ').filter(t => t.length > 2);
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

  // Initial load
  useEffect(() => {
    executeSearch(query, courtFilter, benchFilter);
  }, []);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    executeSearch(query, courtFilter, benchFilter);
  };

  const handleSelectSampleQuery = (sampleText) => {
    setQuery(sampleText);
    executeSearch(sampleText, courtFilter, benchFilter);
  };

  const handleBenchChange = (newBench) => {
    setBenchFilter(newBench);
    executeSearch(query, courtFilter, newBench);
  };

  const handleCourtChange = (newCourt) => {
    setCourtFilter(newCourt);
    executeSearch(query, newCourt, benchFilter);
  };

  return (
    <div className="module-container">
      {/* Editorial Header Section */}
      <div className="editorial-hero-section">
        <div className="editorial-meta-label">COLLECTION 01 / SEMANTIC JURISPRUDENCE &bull; FASTAPI RETRIEVAL</div>
        <h1 className="hero-editorial-title">Universal Search</h1>
        <p className="hero-editorial-subtitle">
          Natural language neural retrieval engineered for Indian constitutional law and commercial precedents. 
          Powered by Gemini 3.8 Flash HyDE synthesis and dual-encoder InLegalBERT retrieval through FastAPI.
        </p>

        {/* Minimalist Stark Search Box */}
        <form onSubmit={handleSearchSubmit} className="editorial-search-bar">
          <div className="search-input-inner">
            <Search className="search-icon-stark" size={18} />
            <input
              type="text"
              className="search-input-field"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search legal issues, statutes, or doctrines in natural English..."
            />
          </div>
          <button type="submit" className="btn-primary search-action-btn" disabled={isSearching}>
            <span>{isSearching ? 'Synthesizing...' : 'Query Precedents'}</span>
            <ArrowRight size={14} />
          </button>
        </form>

        {/* Sample Queries as Minimalist Editorial Chips */}
        <div className="sample-queries-strip">
          <span className="queries-label">EXPLORE TOPICS:</span>
          <div className="queries-buttons-wrap">
            {sampleQueries.map((q, idx) => (
              <button
                key={idx}
                type="button"
                className="query-pill-minimal"
                onClick={() => handleSelectSampleQuery(q.text)}
              >
                {q.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* HyDE Ratio Decidendi Synthetic Preview (Editorial Blockquote) */}
      {showHyde && (
        <div className="editorial-hyde-box">
          <div className="hyde-top-row">
            <span className="editorial-meta-label">
              HYPOTHETICAL JUDICIAL HOLDING &bull; GEMINI 3.8 FLASH HyDE RATIO
            </span>
            <button className="btn-dismiss-text" onClick={() => setShowHyde(false)}>DISMISS</button>
          </div>
          <blockquote className="hyde-quote-text">
            "{hydeRatio}"
          </blockquote>
          <div className="hyde-telemetry-meta">
            <span>MODEL: <strong>gemini-3.8-flash (via FastAPI)</strong></span>
            <span>&bull;</span>
            <span>EMBEDDING: <strong>law-ai/InLegalBERT (768-dim)</strong></span>
            <span>&bull;</span>
            <span>SPARSE LEXICAL: <strong>BM25 + Article 141 NER</strong></span>
          </div>
        </div>
      )}

      {/* Filter and Control Bar */}
      <div className="editorial-filter-bar">
        <div className="filter-count-indicator">
          <span>SHOWING</span>
          <strong>{results.length}</strong>
          <span>AUTHORITATIVE PRECEDENTS {isSearching && '(UPDATING...)'}</span>
        </div>

        <div className="editorial-filter-controls">
          <div className="select-wrapper">
            <label className="select-label">BENCH</label>
            <select value={benchFilter} onChange={(e) => handleBenchChange(e.target.value)}>
              <option value="ALL">All Benches</option>
              <option value="CONSTITUTION">Constitution Bench (5+ Judges)</option>
              <option value="DIVISION">Division Bench (2 Judges)</option>
            </select>
          </div>

          <div className="select-wrapper">
            <label className="select-label">FORUM</label>
            <select value={courtFilter} onChange={(e) => handleCourtChange(e.target.value)}>
              <option value="ALL">All Courts</option>
              <option value="Supreme Court of India">Supreme Court of India</option>
            </select>
          </div>
        </div>
      </div>

      {/* Precedents Grid - Clean Editorial List */}
      <div className="editorial-precedents-list">
        {results.length === 0 ? (
          <div className="editorial-empty-state">
            <div className="empty-title">NO MATCHING PRECEDENTS</div>
            <p className="empty-desc">No authorities match the selected bench criteria. Expand your query or select All Benches.</p>
          </div>
        ) : (
          results.map((precedent) => (
            <article key={precedent.id} className="editorial-precedent-entry">
              <div className="entry-header-row">
                <div className="entry-meta-top">
                  <span className="court-name">{precedent.court}</span>
                  <span className="meta-sep">/</span>
                  <span className="bench-name">{precedent.benchType} ({precedent.benchSize} JUDGES)</span>
                  <span className="meta-sep">/</span>
                  <span className="decision-year">{precedent.decisionYear}</span>
                  {precedent.relevance_score && (
                    <>
                      <span className="meta-sep">/</span>
                      <span className="mono" style={{ fontSize: '11px', color: '#666' }}>
                        SCORE: {Math.round(precedent.relevance_score * 100)}%
                      </span>
                    </>
                  )}
                </div>

                <div className={`editorial-status-tag status-${(precedent.status || 'GREEN').toLowerCase()}`}>
                  <span className="status-mark">
                    {precedent.status === 'GREEN' && '●'}
                    {precedent.status === 'YELLOW' && '▲'}
                    {precedent.status === 'RED' && '✕'}
                  </span>
                  <span>{precedent.statusLabel || precedent.status}</span>
                </div>
              </div>

              <div className="entry-title-row">
                <h2 className="entry-case-title">{precedent.title}</h2>
                <span className="entry-citation-code mono">{precedent.citation}</span>
              </div>

              {/* Statutes Cited */}
              {precedent.statutes && (
                <div className="entry-statutes-strip">
                  {precedent.statutes.map((st, i) => (
                    <span key={i} className="statute-mono-tag">{st}</span>
                  ))}
                </div>
              )}

              {/* Ratio Decidendi */}
              <div className="entry-ratio-block">
                <div className="ratio-caption">RATIO DECIDENDI / LEGAL PRINCIPLE</div>
                <p className="ratio-paragraph">"{precedent.ratioSummary}"</p>
              </div>

              {/* Footer / Actions */}
              <div className="entry-footer-row">
                <div className="coram-info">
                  <span className="coram-label">CORAM:</span>
                  <span className="coram-names">
                    {precedent.judges ? precedent.judges.slice(0, 3).join(', ') : "Coram details in citator"}
                    {precedent.judges && precedent.judges.length > 3 && ` + ${precedent.judges.length - 3} others`}
                  </span>
                </div>

                <button
                  type="button"
                  className="btn-editorial-link"
                  onClick={() => onSelectCaseForCitator(precedent)}
                >
                  <span>Verify in Smart Citator</span>
                  <ArrowUpRight size={14} />
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
