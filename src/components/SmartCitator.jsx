import React, { useState, useEffect } from 'react';
import { ArrowUpRight, Sparkles, Network, Scale, ShieldCheck } from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { getCitatorCaseWithBackend } from '../config/gemini';

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
    <div className="module-container">
      {/* Editorial Header Section */}
      <div className="editorial-hero-section">
        <div className="editorial-meta-label">COLLECTION 03 / CONSTITUTIONAL SHEPARDIZER &bull; FASTAPI & ARTICLE 141</div>
        <h1 className="hero-editorial-title">Smart Citator</h1>
        <p className="hero-editorial-subtitle">
          Traverses citation lineage across Indian High Courts and the Supreme Court under Article 141. 
          Evaluates bench hierarchy, distinguishes ratio decidendi from obiter dicta, and tracks overruling risks in real time.
        </p>

        {/* Case Switcher - Editorial Horizontal Strip */}
        <div className="editorial-case-picker">
          <span className="picker-label">PRECEDENT ARCHIVE:</span>
          <div className="picker-chips-row">
            {LANDMARK_PRECEDENTS.map((c) => (
              <button
                key={c.id}
                className={`picker-pill ${c.id === selectedCaseId ? 'active' : ''}`}
                onClick={() => setSelectedCaseId(c.id)}
              >
                <span className="picker-status-char">
                  {c.status === 'GREEN' && '●'}
                  {c.status === 'YELLOW' && '▲'}
                  {c.status === 'RED' && '✕'}
                </span>
                <span className="picker-title-text">{c.title.split('v.')[0]}</span>
                <span className="picker-year-mini">({c.decisionYear})</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Precedent Status Summary Card - Stark Architectural Canvas */}
      <div className="editorial-citator-header-card">
        <div className="citator-primary-meta">
          <div className="status-kicker-row">
            <span className={`editorial-status-tag status-${(currentCase.status || 'GREEN').toLowerCase()}`}>
              {currentCase.status === 'GREEN' && '● GOOD LAW (ARTICLE 141 BINDING)'}
              {currentCase.status === 'YELLOW' && '▲ DISTINGUISHED / CAUTION'}
              {currentCase.status === 'RED' && '✕ OVERRULED / VOID'}
            </span>
            <span className="meta-sep">/</span>
            <span className="citation-pill mono">{currentCase.citation}</span>
            {isLoading && <span className="meta-sep" style={{ fontSize: '11px', color: '#888' }}>[FETCHING AI ANALYSIS...]</span>}
          </div>

          <h2 className="citator-case-heading font-judicial">{currentCase.title}</h2>

          <div className="citator-bench-line">
            <span>{currentCase.court}</span>
            <span className="meta-sep">&bull;</span>
            <span>{currentCase.benchType} ({currentCase.benchSize} JUDGES)</span>
            <span className="meta-sep">&bull;</span>
            <span>DECISION YEAR {currentCase.decisionYear}</span>
          </div>
        </div>

        <div className="citator-stats-column">
          <div className="stat-unit">
            <div className="stat-value">{currentCase.citationCount || 34}</div>
            <div className="stat-caption">CITING JUDGMENTS</div>
          </div>
          <div className="stat-unit">
            <div className="stat-value">{currentCase.benchSize}</div>
            <div className="stat-caption">BENCH STRENGTH</div>
          </div>
        </div>
      </div>

      {/* Live AI Analysis Callout (Gemini 3.8 Flash via FastAPI) */}
      {aiAnalysis && (
        <div className="editorial-hyde-box" style={{ marginTop: '20px' }}>
          <div className="hyde-top-row">
            <span className="editorial-meta-label">
              GEMINI 3.8 FLASH CONSTITUTIONAL STANDING SYNTHESIS
            </span>
            <span className="mono" style={{ fontSize: '11px', color: '#666' }}>ARTICLE 141 DAG</span>
          </div>
          <p style={{ margin: '8px 0', fontSize: '14px', lineHeight: '1.6', color: '#111' }}>
            <strong>Executive Holding:</strong> {aiAnalysis.executive_summary}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px', marginTop: '12px', fontSize: '12px', color: '#444' }}>
            <div>
              <strong>Constitutional Standing:</strong> {aiAnalysis.constitutional_standing}
            </div>
            <div>
              <strong>Bench Hierarchy:</strong> {aiAnalysis.bench_strength_assessment}
            </div>
            <div>
              <strong>Overruling Risk:</strong> {aiAnalysis.overruling_risk}
            </div>
          </div>
        </div>
      )}

      {/* Assessment Directive Callout */}
      <div className="editorial-directive-box">
        <div className="directive-label">JUDICIAL STANDING ASSESSMENT</div>
        <p className="directive-text">{currentCase.statusDescription}</p>
        {currentCase.overruledCases && currentCase.overruledCases.length > 0 && (
          <div className="editorial-overruled-notice">
            <span className="overruled-label">EXPLICITLY OVERRULED PRECEDENTS:</span>
            <ul className="overruled-list">
              {currentCase.overruledCases.map((oc, i) => (
                <li key={i}>&bull; {oc}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Citator Sub Navigation Tabs */}
      <div className="editorial-tabs-row">
        <button
          className={`tab-understated-btn ${activeTab === 'treatment' ? 'active' : ''}`}
          onClick={() => setActiveTab('treatment')}
        >
          <span>TREATMENT CHRONOLOGY</span>
        </button>

        <button
          className={`tab-understated-btn ${activeTab === 'bench-eval' ? 'active' : ''}`}
          onClick={() => setActiveTab('bench-eval')}
        >
          <span>ARTICLE 141 BENCH MATRIX</span>
        </button>

        <button
          className={`tab-understated-btn ${activeTab === 'graph' ? 'active' : ''}`}
          onClick={() => setActiveTab('graph')}
        >
          <span>CITATION DAG GRAPH</span>
        </button>
      </div>

      {/* TAB 1: Treatment History */}
      {activeTab === 'treatment' && (
        <div className="editorial-panel-surface">
          <div className="panel-title-group">
            <span className="editorial-meta-label">HISTORICAL CITATION RECORD &bull; FASTAPI KNOWLEDGE GRAPH</span>
            <h3 className="panel-subheading font-judicial">Subsequent Judicial Treatment</h3>
          </div>

          <div className="editorial-timeline">
            {!currentCase.treatmentHistory || currentCase.treatmentHistory.length === 0 ? (
              <p className="timeline-empty">No subsequent negative treatment recorded for this precedent.</p>
            ) : (
              currentCase.treatmentHistory.map((th, idx) => (
                <div key={idx} className="timeline-row-item">
                  <div className="timeline-col-status">
                    <span className={`treatment-mono-tag status-${(th.treatment || '').toLowerCase()}`}>
                      {(th.treatment || '').replace('_', ' ')}
                    </span>
                  </div>

                  <div className="timeline-col-details">
                    <div className="citing-case-line">
                      <h4 className="citing-title font-judicial">{th.case}</h4>
                      <span className="citing-year-code mono">{th.year}</span>
                    </div>
                    <div className="citing-court-name">{th.court}</div>
                    {th.note && (
                      <blockquote className="citing-judicial-quote">
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

      {/* TAB 2: Article 141 Bench Hierarchy Logic */}
      {activeTab === 'bench-eval' && (
        <div className="editorial-panel-surface">
          <div className="panel-title-group">
            <span className="editorial-meta-label">CONSTITUTIONAL BENCH RULES ENGINE</span>
            <h3 className="panel-subheading font-judicial">Precedent Invalidation Criteria</h3>
            <p className="panel-citation-ref">
              Codified pursuant to <em>Central Board of Dawoodi Bohra Community v. State of Maharashtra (2005) 2 SCC 673</em>:
            </p>
          </div>

          <div className="bench-editorial-matrix">
            <div className="matrix-column-card">
              <span className="editorial-meta-label">TARGET BENCH CORAM</span>
              <div className="matrix-number-huge">{currentCase.benchSize}</div>
              <div className="matrix-description">
                <strong>{currentCase.benchType}</strong> comprising {currentCase.benchSize} Supreme Court Justices.
              </div>
            </div>

            <div className="matrix-column-card rules-column">
              <span className="editorial-meta-label">JUDICIAL DISCIPLINE BOUNDARIES</span>
              <div className="bench-rules-editorial-list">
                {rules.map((r, idx) => (
                  <div key={idx} className="bench-rule-item">
                    <span className="rule-marker">0{idx + 1}</span>
                    <div className="rule-content">
                      <strong>{r.level}:</strong> {r.jurisdiction}
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
        <div className="editorial-panel-surface">
          <div className="panel-title-group">
            <span className="editorial-meta-label">TOPOLOGICAL CITATION DAG &bull; ARTICLE 141 LINEAGE</span>
            <h3 className="panel-subheading font-judicial">Precedent Citation Topology</h3>
          </div>

          <div className="editorial-graph-container">
            <svg className="graph-svg" viewBox="0 0 800 340">
              <defs>
                <marker id="arrow-stark" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#000000" />
                </marker>
                <marker id="arrow-gray" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#767676" />
                </marker>
              </defs>

              {/* Connecting Lines */}
              <line x1="400" y1="170" x2="160" y2="80" stroke="#000000" strokeWidth="1.5" strokeDasharray="3" markerEnd="url(#arrow-stark)" />
              <line x1="400" y1="170" x2="640" y2="80" stroke="#767676" strokeWidth="1.5" markerEnd="url(#arrow-gray)" />
              <line x1="400" y1="170" x2="200" y2="270" stroke="#767676" strokeWidth="1.5" markerEnd="url(#arrow-gray)" />
              <line x1="400" y1="170" x2="600" y2="270" stroke="#000000" strokeWidth="1.5" markerEnd="url(#arrow-stark)" />

              {/* Center Node: Current Case */}
              <g transform="translate(400, 170)">
                <rect x="-65" y="-30" width="130" height="60" fill="#000000" stroke="#000000" strokeWidth="1" />
                <text textAnchor="middle" y="-6" fill="#FFFFFF" fontSize="10" fontWeight="600" letterSpacing="1">TARGET PRECEDENT</text>
                <text textAnchor="middle" y="10" fill="#CCCCCC" fontSize="9" fontFamily="monospace">{currentCase.citation?.split(' ')[0]}</text>
                <text textAnchor="middle" y="22" fill="#FFFFFF" fontSize="8">{currentCase.benchSize} Judges</text>
              </g>

              {/* Node Top-Left: Affirmed */}
              <g transform="translate(160, 80)">
                <rect x="-55" y="-25" width="110" height="50" fill="#FFFFFF" stroke="#000000" strokeWidth="1.5" />
                <text textAnchor="middle" y="-2" fill="#000000" fontSize="9" fontWeight="600" letterSpacing="1">AFFIRMED</text>
                <text textAnchor="middle" y="14" fill="#666666" fontSize="8">Supreme Court</text>
              </g>

              {/* Node Top-Right: Relied On */}
              <g transform="translate(640, 80)">
                <rect x="-55" y="-25" width="110" height="50" fill="#FFFFFF" stroke="#767676" strokeWidth="1" />
                <text textAnchor="middle" y="-2" fill="#000000" fontSize="9" fontWeight="600" letterSpacing="1">RELIED ON</text>
                <text textAnchor="middle" y="14" fill="#666666" fontSize="8">Delhi High Court</text>
              </g>

              {/* Node Bottom-Left: Distinguished */}
              <g transform="translate(200, 270)">
                <rect x="-60" y="-25" width="120" height="50" fill="#FFFFFF" stroke="#767676" strokeWidth="1" strokeDasharray="3" />
                <text textAnchor="middle" y="-2" fill="#000000" fontSize="9" fontWeight="600" letterSpacing="1">DISTINGUISHED</text>
                <text textAnchor="middle" y="14" fill="#666666" fontSize="8">Coordinate Bench</text>
              </g>

              {/* Node Bottom-Right: Overruled */}
              <g transform="translate(600, 270)">
                <rect x="-55" y="-25" width="110" height="50" fill="#F0F0F0" stroke="#000000" strokeWidth="1.5" />
                <text textAnchor="middle" y="-2" fill="#000000" fontSize="9" fontWeight="600" letterSpacing="1">OVERRULED</text>
                <text textAnchor="middle" y="14" fill="#666666" fontSize="8">Earlier Benches</text>
              </g>
            </svg>

            <div className="graph-editorial-legend">
              <span className="legend-tag"><strong>SOLID BLACK:</strong> Article 141 Affirmed / Good Law</span>
              <span className="legend-tag"><strong>HAIRLINE GRAY:</strong> Relied Upon / Followed</span>
              <span className="legend-tag"><strong>DASHED:</strong> Distinguished on Facts</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
