import React, { useState, useEffect } from 'react';
import { ArrowUpRight, Sparkles, Scale, ShieldCheck, GitFork, Network } from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { getCitatorCaseWithBackend } from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

export default function SmartCitator({ initialCaseId }) {
  const [selectedCaseId, setSelectedCaseId] = useState(initialCaseId || 'sc-2006-percept');
  const [activeTab, setActiveTab] = useState('treatment'); // 'treatment', 'bench-eval', 'graph'
  const [liveCase, setLiveCase] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Fallback case from corpus
  const fallbackCase = LANDMARK_PRECEDENTS.find(c => c.id === selectedCaseId) || LANDMARK_PRECEDENTS[0];

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    getCitatorCaseWithBackend(selectedCaseId)
      .then(data => {
        if (!isMounted) return;
        setLiveCase(data);
      })
      .catch(err => {
        console.warn("[SmartCitator] Backend citator fetch failed; using fallback corpus:", err.message);
        if (isMounted) setLiveCase(fallbackCase);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedCaseId]);

  const currentCase = liveCase || fallbackCase;
  const aiAnalysis = currentCase?.aiAnalysis;
  const rules = currentCase?.article141Evaluation?.rules || [
    { level: "Division Bench (2 Judges)", jurisdiction: "Bindingly bound. Lacks jurisdiction to overrule or modify this ratio.", status: "BOUND" },
    { level: `Coordinate Bench (${currentCase.benchSize} Judges)`, jurisdiction: "Cannot overrule. Must refer to CJI for larger bench reference.", status: "REFERENCE_REQUIRED" },
    { level: `Larger Bench (${currentCase.benchSize + 1}+ Judges)`, jurisdiction: "Holds plenary jurisdiction under Article 141 to review or overrule.", status: "COMPETENT_TO_OVERRULE" }
  ];

  return (
    <div className="workspace-module-pane">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">SMART CITATOR</span>
        </div>
        <h1 className="module-heading font-judicial">Smart Citator</h1>
        <p className="module-description">
          Automated Article 141 constitutional Shepardizer. Maps judicial lineage across the Supreme Court and High Courts,
          evaluates bench strength hierarchy, and flags overruling risks in real time.
        </p>

        {/* Precedent Archive Switcher Bar */}
        <div className="citator-picker-bar">
          <span className="picker-title-label">SELECT PRECEDENT:</span>
          <div className="picker-chips-container">
            {LANDMARK_PRECEDENTS.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`citator-picker-chip ${c.id === selectedCaseId ? 'active' : ''}`}
                onClick={() => setSelectedCaseId(c.id)}
              >
                <span className={`picker-dot status-${(c.status || 'GREEN').toLowerCase()}`} />
                <span className="picker-chip-name">{c.title.split('v.')[0]}</span>
                <span className="picker-chip-year mono">({c.decisionYear})</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* SKELETON LOADING STATE FOR CITATOR SUMMARY */}
      {isLoading ? (
        <div className="skeleton-card" style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="skeleton-badge skeleton-shimmer" style={{ width: '120px' }} />
            <div className="skeleton-line skeleton-shimmer" style={{ width: '80px' }} />
          </div>
          <div className="skeleton-title skeleton-shimmer" style={{ width: '80%', height: '28px' }} />
          <div className="skeleton-line skeleton-shimmer" style={{ width: '45%' }} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '12px' }}>
            <div className="skeleton-block skeleton-shimmer" />
            <div className="skeleton-block skeleton-shimmer" />
          </div>
        </div>
      ) : (
        /* Precedent Master Summary Card */
        <div className="citator-summary-card">
          <div className="citator-summary-main">
            <div className="citator-header-kicker">
              <span className={`status-pill status-${(currentCase.status || 'GREEN').toLowerCase()}`}>
                <span className="status-dot-indicator" />
                <span className="status-pill-text">
                  {currentCase.status === 'GREEN' && 'GOOD LAW — ARTICLE 141 BINDING'}
                  {currentCase.status === 'YELLOW' && 'DISTINGUISHED / CAUTION'}
                  {currentCase.status === 'RED' && 'OVERRULED / VOID IN TOTO'}
                </span>
              </span>

              <span className="citation-code-badge mono">{currentCase.citation}</span>
            </div>

            <h2 className="citator-case-title font-judicial">{currentCase.title}</h2>

            <div className="citator-meta-row">
              <span className="meta-item-bold">{currentCase.court}</span>
              <span className="meta-dot">&bull;</span>
              <span className="meta-item">{currentCase.benchType} ({currentCase.benchSize} Justices)</span>
              <span className="meta-dot">&bull;</span>
              <span className="meta-item">Decision Year {currentCase.decisionYear}</span>
            </div>
          </div>

          <div className="citator-summary-stats">
            <div className="stat-box">
              <div className="stat-number">{currentCase.citationCount || 34}</div>
              <div className="stat-label">CITING JUDGMENTS</div>
            </div>
            <div className="stat-box">
              <div className="stat-number">{currentCase.benchSize}</div>
              <div className="stat-label">BENCH STRENGTH</div>
            </div>
          </div>
        </div>
      )}

      {/* Neural Constitutional Standing Synthesis Callout */}
      {aiAnalysis && (
        <div className="workspace-callout-card citator-ai-callout">
          <div className="callout-header">
            <div className="callout-title-wrap">
              <Sparkles size={14} className="callout-icon" />
              <span className="callout-title">
                {aiAnalysis.model_used && !aiAnalysis.model_used.includes('fallback')
                  ? `NEURAL CONSTITUTIONAL STANDING SYNTHESIS [${aiAnalysis.model_used}]`
                  : 'CONSTITUTIONAL STANDING SYNTHESIS (STATUTORY BASELINE)'}
              </span>
            </div>
            <span className="meta-tag mono">ARTICLE 141 DAG</span>
          </div>

          <p className="callout-summary-text">
            <strong>Executive Holding:</strong> {renderWithBadges(aiAnalysis.executive_summary)}
          </p>

          <div className="callout-grid-three">
            <div className="callout-grid-item">
              <div className="grid-item-label">CONSTITUTIONAL STANDING</div>
              <div className="grid-item-value">{renderWithBadges(aiAnalysis.constitutional_standing)}</div>
            </div>
            <div className="callout-grid-item">
              <div className="grid-item-label">BENCH HIERARCHY</div>
              <div className="grid-item-value">{renderWithBadges(aiAnalysis.bench_strength_assessment)}</div>
            </div>
            <div className="callout-grid-item">
              <div className="grid-item-label">OVERRULING RISK</div>
              <div className="grid-item-value">{renderWithBadges(aiAnalysis.overruling_risk)}</div>
            </div>
          </div>
        </div>
      )}

      {/* Judicial Assessment Directive Box */}
      <div className="citator-directive-card">
        <div className="directive-header-label">JUDICIAL STANDING ASSESSMENT</div>
        <p className="directive-body-text">{currentCase.statusDescription}</p>
        {currentCase.overruledCases && currentCase.overruledCases.length > 0 && (
          <div className="overruled-callout-sub">
            <span className="overruled-title">EXPLICITLY OVERRULED PRECEDENTS:</span>
            <ul className="overruled-items-list">
              {currentCase.overruledCases.map((oc, i) => (
                <li key={i}>&bull; {oc}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Citator Sub Navigation Tabs */}
      <div className="citator-nav-tabs">
        <button
          type="button"
          className={`citator-tab-btn ${activeTab === 'treatment' ? 'active' : ''}`}
          onClick={() => setActiveTab('treatment')}
        >
          <span>TREATMENT CHRONOLOGY</span>
        </button>

        <button
          type="button"
          className={`citator-tab-btn ${activeTab === 'bench-eval' ? 'active' : ''}`}
          onClick={() => setActiveTab('bench-eval')}
        >
          <span>ARTICLE 141 BENCH MATRIX</span>
        </button>

        <button
          type="button"
          className={`citator-tab-btn ${activeTab === 'graph' ? 'active' : ''}`}
          onClick={() => setActiveTab('graph')}
        >
          <span>CITATION DAG GRAPH</span>
        </button>
      </div>

      {/* TAB 1: Subsequent Judicial Treatment */}
      {activeTab === 'treatment' && (
        <div className="citator-panel-card">
          <div className="panel-header-row">
            <div>
              <span className="panel-kicker">HISTORICAL CITATION RECORD</span>
              <h3 className="panel-title font-judicial">Subsequent Judicial Treatment</h3>
            </div>
          </div>

          <div className="treatment-timeline-list">
            {!currentCase.treatmentHistory || currentCase.treatmentHistory.length === 0 ? (
              <div className="treatment-empty-note">
                No subsequent negative treatment recorded for this precedent.
              </div>
            ) : (
              currentCase.treatmentHistory.map((th, idx) => (
                <div key={idx} className="treatment-card-row">
                  <div className="treatment-status-col">
                    <span className={`treatment-badge status-${(th.treatment || '').toLowerCase()}`}>
                      {(th.treatment || '').replace('_', ' ')}
                    </span>
                  </div>

                  <div className="treatment-details-col">
                    <div className="treatment-title-line">
                      <h4 className="treatment-case-name font-judicial">{th.case}</h4>
                      <span className="treatment-case-year mono">{th.year}</span>
                    </div>
                    <div className="treatment-court-line">{th.court}</div>
                    {th.note && (
                      <blockquote className="treatment-quote font-judicial">
                        "{th.note}"
                      </blockquote>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 2: Article 141 Bench Rules Engine */}
      {activeTab === 'bench-eval' && (
        <div className="citator-panel-card">
          <div className="panel-header-row">
            <div>
              <span className="panel-kicker">CONSTITUTIONAL BENCH RULES ENGINE</span>
              <h3 className="panel-title font-judicial">Precedent Invalidation Criteria</h3>
              <p className="panel-desc">
                Codified pursuant to <em>Central Board of Dawoodi Bohra Community v. State of Maharashtra (2005) 2 SCC 673</em>:
              </p>
            </div>
          </div>

          <div className="bench-matrix-grid">
            <div className="matrix-target-card">
              <div className="matrix-target-label">TARGET BENCH CORAM</div>
              <div className="matrix-target-number">{currentCase.benchSize}</div>
              <div className="matrix-target-desc">
                <strong>{currentCase.benchType}</strong> comprising {currentCase.benchSize} Supreme Court Justices.
              </div>
            </div>

            <div className="matrix-rules-card">
              <div className="matrix-rules-label">JUDICIAL DISCIPLINE BOUNDARIES</div>
              <div className="matrix-rules-list">
                {rules.map((r, idx) => (
                  <div key={idx} className="bench-rule-row">
                    <span className="rule-idx">0{idx + 1}</span>
                    <div className="rule-text-wrap">
                      <span className="rule-level">{r.level}:</span>{' '}
                      <span className="rule-jurisdiction">{r.jurisdiction}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Citation Network Graph Visualizer */}
      {activeTab === 'graph' && (
        <div className="citator-panel-card">
          <div className="panel-header-row">
            <div>
              <span className="panel-kicker">TOPOLOGICAL CITATION DAG</span>
              <h3 className="panel-title font-judicial">Precedent Citation Topology</h3>
            </div>
            {currentCase.dataSource && (
              <span className={`graph-source-badge mono ${currentCase.dataSource === 'neo4j' ? 'is-live' : 'is-fallback'}`}>
                {currentCase.dataSource === 'neo4j' ? 'GRAPH: NEO4J LIVE' : 'GRAPH: IN-MEMORY ARTICLE 141 DAG'}
              </span>
            )}
          </div>

          <div className="citator-graph-card">
            <svg className="graph-svg" viewBox="0 0 800 340">
              <defs>
                <marker id="arrow-saffron" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#C2410C" />
                </marker>
                <marker id="arrow-gray" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#8E9AA8" />
                </marker>
              </defs>

              {/* Connecting Lines */}
              <line x1="400" y1="170" x2="160" y2="80" stroke="#C2410C" strokeWidth="1.5" strokeDasharray="3" markerEnd="url(#arrow-saffron)" />
              <line x1="400" y1="170" x2="640" y2="80" stroke="#8E9AA8" strokeWidth="1.5" markerEnd="url(#arrow-gray)" />
              <line x1="400" y1="170" x2="200" y2="270" stroke="#8E9AA8" strokeWidth="1.5" markerEnd="url(#arrow-gray)" />
              <line x1="400" y1="170" x2="600" y2="270" stroke="#C2410C" strokeWidth="1.5" markerEnd="url(#arrow-saffron)" />

              {/* Center Node: Target Precedent */}
              <g transform="translate(400, 170)">
                <rect x="-70" y="-32" width="140" height="64" rx="8" fill="#16213E" stroke="#C2410C" strokeWidth="2" />
                <text textAnchor="middle" y="-8" fill="#FFFFFF" fontSize="10" fontWeight="600" letterSpacing="0.05em">TARGET PRECEDENT</text>
                <text textAnchor="middle" y="10" fill="#FFEDD5" fontSize="9" fontFamily="monospace">{currentCase.citation?.split(' ')[0]}</text>
                <text textAnchor="middle" y="23" fill="#D1D5DB" fontSize="8">{currentCase.benchSize} Justices</text>
              </g>

              {/* Node Top-Left: Affirmed */}
              <g transform="translate(160, 80)">
                <rect x="-60" y="-26" width="120" height="52" rx="8" fill="#FFFFFF" stroke="#BBF7D0" strokeWidth="1.5" />
                <text textAnchor="middle" y="-4" fill="#15803D" fontSize="10" fontWeight="600">AFFIRMED</text>
                <text textAnchor="middle" y="14" fill="#5A6A85" fontSize="8.5">Supreme Court</text>
              </g>

              {/* Node Top-Right: Relied On */}
              <g transform="translate(640, 80)">
                <rect x="-60" y="-26" width="120" height="52" rx="8" fill="#FFFFFF" stroke="#E8E3DA" strokeWidth="1.5" />
                <text textAnchor="middle" y="-4" fill="#16213E" fontSize="10" fontWeight="600">RELIED ON</text>
                <text textAnchor="middle" y="14" fill="#5A6A85" fontSize="8.5">Delhi High Court</text>
              </g>

              {/* Node Bottom-Left: Distinguished */}
              <g transform="translate(200, 270)">
                <rect x="-65" y="-26" width="130" height="52" rx="8" fill="#FFFFFF" stroke="#FDE68A" strokeWidth="1.5" strokeDasharray="3" />
                <text textAnchor="middle" y="-4" fill="#B45309" fontSize="10" fontWeight="600">DISTINGUISHED</text>
                <text textAnchor="middle" y="14" fill="#5A6A85" fontSize="8.5">Coordinate Bench</text>
              </g>

              {/* Node Bottom-Right: Overruled */}
              <g transform="translate(600, 270)">
                <rect x="-60" y="-26" width="120" height="52" rx="8" fill="#FFF8F8" stroke="#FECACA" strokeWidth="1.5" />
                <text textAnchor="middle" y="-4" fill="#B91C1C" fontSize="10" fontWeight="600">OVERRULED</text>
                <text textAnchor="middle" y="14" fill="#5A6A85" fontSize="8.5">Earlier Benches</text>
              </g>
            </svg>

            <div className="graph-legend-strip">
              <span className="legend-item"><span className="legend-dot green" /> Article 141 Affirmed (Good Law)</span>
              <span className="legend-item"><span className="legend-dot gray" /> Relied Upon / Followed</span>
              <span className="legend-item"><span className="legend-dot amber" /> Distinguished on Facts</span>
              <span className="legend-item"><span className="legend-dot red" /> Overruled / Void</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
