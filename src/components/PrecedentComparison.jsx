import React, { useState, useMemo, useRef, useEffect } from 'react';
import { 
  ArrowRight, 
  Scale, 
  BookOpen, 
  ShieldCheck, 
  AlertTriangle, 
  CheckCircle2, 
  ChevronRight, 
  ArrowLeftRight, 
  Search, 
  X, 
  Check, 
  Calendar, 
  Users, 
  HelpCircle 
} from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';

function getVerifiedTreatment(c1, c2) {
  if (!c1 || !c2 || c1.id === c2.id) {
    return "Treatment not established from the available records";
  }

  // Check if c1 overruled c2
  const c1Overruled = c1.overruledCases?.find(oc => 
    oc.toLowerCase().includes(c2.title.toLowerCase().slice(0, 14)) ||
    (c2.citation && oc.toLowerCase().includes(c2.citation.toLowerCase()))
  );
  if (c1Overruled) {
    return `${c1.title} (${c1.decisionYear}) expressly overruled ${c2.title} (${c2.decisionYear}).`;
  }

  // Check if c2 overruled c1
  const c2Overruled = c2.overruledCases?.find(oc => 
    oc.toLowerCase().includes(c1.title.toLowerCase().slice(0, 14)) ||
    (c1.citation && oc.toLowerCase().includes(c1.citation.toLowerCase()))
  );
  if (c2Overruled) {
    return `${c2.title} (${c2.decisionYear}) expressly overruled ${c1.title} (${c1.decisionYear}).`;
  }

  // Check c1's treatmentHistory for c2
  const t1 = c1.treatmentHistory?.find(th => 
    th.case.toLowerCase().includes(c2.title.toLowerCase().slice(0, 14)) ||
    c2.title.toLowerCase().includes(th.case.toLowerCase().slice(0, 14))
  );
  if (t1) {
    const verb = t1.treatment === 'AFFIRMED' ? 'affirmed' : 
                 t1.treatment === 'DISTINGUISHED' ? 'distinguished' : 
                 t1.treatment === 'RELIED_ON' ? 'relied on' :
                 t1.treatment === 'OVERRULED' ? 'overruled' : t1.treatment.toLowerCase();
    return `${c1.title} was ${verb} in ${t1.case} (${t1.year})${t1.note ? `: ${t1.note}` : ''}.`;
  }

  // Check c2's treatmentHistory for c1
  const t2 = c2.treatmentHistory?.find(th => 
    th.case.toLowerCase().includes(c1.title.toLowerCase().slice(0, 14)) ||
    c1.title.toLowerCase().includes(th.case.toLowerCase().slice(0, 14))
  );
  if (t2) {
    const verb = t2.treatment === 'AFFIRMED' ? 'affirmed' : 
                 t2.treatment === 'DISTINGUISHED' ? 'distinguished' : 
                 t2.treatment === 'RELIED_ON' ? 'relied on' :
                 t2.treatment === 'OVERRULED' ? 'overruled' : t2.treatment.toLowerCase();
    return `${c2.title} was ${verb} in ${t2.case} (${t2.year})${t2.note ? `: ${t2.note}` : ''}.`;
  }

  return "Treatment not established from the available records";
}

/**
 * Searchable Case Picker Component
 */
function SearchableCasePicker({ 
  label, 
  selectedCase, 
  onSelectCase, 
  otherCaseId, 
  roleTag 
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const wrapperRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filteredCandidates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return LANDMARK_PRECEDENTS;
    return LANDMARK_PRECEDENTS.filter(c => {
      const matchTitle = c.title.toLowerCase().includes(q);
      const matchCite = (c.citation || '').toLowerCase().includes(q);
      const matchYear = String(c.decisionYear || '').includes(q);
      const matchStat = (c.statutes || []).some(s => s.toLowerCase().includes(q));
      const matchRatio = (c.ratioSummary || '').toLowerCase().includes(q);
      return matchTitle || matchCite || matchYear || matchStat || matchRatio;
    });
  }, [searchQuery]);

  return (
    <div className="case-picker-card" ref={wrapperRef}>
      <div className="picker-card-header">
        <span className="picker-role-tag mono">{roleTag}</span>
        <span className="picker-field-label mono">{label}</span>
      </div>

      {/* Selected Case Summary Card */}
      {selectedCase && (
        <div className="selected-case-summary">
          <div className="summary-title-row">
            <h3 className="summary-case-title font-serif">{selectedCase.title}</h3>
            <span className="summary-citation mono">{selectedCase.citation}</span>
          </div>

          <div className="summary-meta-row mono">
            <span className="meta-badge"><Users size={12} /> {selectedCase.benchSize || 2} Judges ({selectedCase.benchType || 'Bench'})</span>
            <span className="meta-badge"><Calendar size={12} /> {selectedCase.decisionYear}</span>
            <span className="meta-court">{selectedCase.court}</span>
          </div>

          <div className="summary-ratio-box">
            <span className="ratio-label mono">CORE RATIO DECIDENDI:</span>
            <p className="ratio-text font-serif">"{selectedCase.ratioSummary}"</p>
          </div>

          <div className="summary-statutes-row">
            {(selectedCase.statutes || []).map((s, idx) => (
              <span key={idx} className="statute-pill mono">{s}</span>
            ))}
          </div>

          <div className="picker-action-bar">
            <button
              type="button"
              className="btn-change-case"
              onClick={() => {
                setIsOpen(prev => !prev);
                setSearchQuery('');
              }}
            >
              <Search size={14} />
              <span>{isOpen ? 'Close Search' : 'Change Case'}</span>
            </button>
          </div>
        </div>
      )}

      {/* Dropdown Search Popover */}
      {isOpen && (
        <div className="picker-dropdown-popover animate-fade-in">
          <div className="picker-search-bar">
            <Search size={16} className="picker-search-icon" />
            <input
              type="text"
              autoFocus
              className="picker-search-input"
              placeholder="Search by case title, citation, year, or statute..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button 
                type="button" 
                className="picker-clear-btn" 
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <div className="picker-results-list">
            {filteredCandidates.length === 0 ? (
              <div className="picker-no-results mono">
                No matching precedents found in landmark archive.
              </div>
            ) : (
              filteredCandidates.map((c) => {
                const isCurrent = c.id === selectedCase?.id;
                const isOther = c.id === otherCaseId;
                const isDisabled = isCurrent || isOther;

                return (
                  <button
                    key={c.id}
                    type="button"
                    disabled={isDisabled}
                    className={`picker-candidate-item ${isCurrent ? 'is-selected' : ''} ${isOther ? 'is-disabled' : ''}`}
                    onClick={() => {
                      if (!isDisabled) {
                        onSelectCase(c.id);
                        setIsOpen(false);
                      }
                    }}
                  >
                    <div className="candidate-header">
                      <span className="candidate-title font-serif">{c.title}</span>
                      <span className="candidate-citation mono">{c.citation}</span>
                    </div>
                    <div className="candidate-meta mono">
                      <span>{c.decisionYear} &bull; {c.benchSize} Judges ({c.benchType})</span>
                      {isCurrent && <span className="candidate-badge-active"><Check size={11} /> Selected</span>}
                      {isOther && <span className="candidate-badge-other">Already chosen in other slot</span>}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PrecedentComparison({ onSwitchToWorkspace }) {
  const [case1Id, setCase1Id] = useState('sc-2006-percept');
  const [case2Id, setCase2Id] = useState('sc-1967-niranjan-golikari');
  const [selectionWarning, setSelectionWarning] = useState(null);

  const case1 = LANDMARK_PRECEDENTS.find(c => c.id === case1Id) || LANDMARK_PRECEDENTS[0];
  const case2 = LANDMARK_PRECEDENTS.find(c => c.id === case2Id) || LANDMARK_PRECEDENTS[1];

  const presetPairs = [
    {
      label: "Section 27: Post-Service vs During-Service",
      c1: 'sc-2006-percept',
      c2: 'sc-1967-niranjan-golikari'
    },
    {
      label: "Article 21: Privacy Recognized vs Emergency Suspension",
      c1: 'sc-2017-puttaswamy',
      c2: 'sc-1976-adm-jabalpur'
    },
    {
      label: "Section 377: Decriminalization vs Recriminalization",
      c1: 'sc-2018-navtej-johar',
      c2: 'sc-2014-suresh-koushal'
    },
    {
      label: "Tenancy: Section 106 Notice vs Mesne Profits",
      c1: 'sc-1979-dhanapal-chettiar',
      c2: 'sc-2005-atma-ram'
    },
    {
      label: "Section 27: Division Bench (2006) vs 3-Judge Bench (1981)",
      c1: 'sc-2006-percept',
      c2: 'sc-1981-superintendence'
    }
  ];

  const handleSelectCase1 = (id) => {
    if (id === case2Id) {
      setSelectionWarning("Cannot compare a case against itself. Please choose a different precedent.");
      setTimeout(() => setSelectionWarning(null), 3500);
      return;
    }
    setSelectionWarning(null);
    setCase1Id(id);
  };

  const handleSelectCase2 = (id) => {
    if (id === case1Id) {
      setSelectionWarning("Cannot compare a case against itself. Please choose a different precedent.");
      setTimeout(() => setSelectionWarning(null), 3500);
      return;
    }
    setSelectionWarning(null);
    setCase2Id(id);
  };

  const handleSwapCases = () => {
    setCase1Id(case2Id);
    setCase2Id(case1Id);
  };

  // Treatment Relationship text
  const treatmentText = useMemo(() => {
    return getVerifiedTreatment(case1, case2);
  }, [case1, case2]);

  // Bench Hierarchy comparison text
  const benchComparison = useMemo(() => {
    const b1 = case1.benchSize || 2;
    const b2 = case2.benchSize || 2;
    if (b1 > b2) {
      return {
        c1Text: `${b1} Judges (${case1.benchType || 'Bench'}) — Higher bench authority; binds coordinate and smaller benches under Article 141`,
        c2Text: `${b2} Judges (${case2.benchType || 'Bench'}) — Smaller bench strength relative to Case A`,
        relationship: `Case A (${b1} Judges) holds superior precedential weight over Case B (${b2} Judges) under Article 141 doctrine of stare decisis.`
      };
    } else if (b2 > b1) {
      return {
        c1Text: `${b1} Judges (${case1.benchType || 'Bench'}) — Smaller bench strength relative to Case B`,
        c2Text: `${b2} Judges (${case2.benchType || 'Bench'}) — Higher bench authority; binds coordinate and smaller benches under Article 141`,
        relationship: `Case B (${b2} Judges) holds superior precedential weight over Case A (${b1} Judges) under Article 141 doctrine of stare decisis.`
      };
    } else {
      return {
        c1Text: `${b1} Judges (${case1.benchType || 'Bench'}) — Coordinate bench`,
        c2Text: `${b2} Judges (${case2.benchType || 'Bench'}) — Coordinate bench`,
        relationship: `Equal bench strength (${b1} Judges). Rulings stand as coordinate authorities governed by chronology and subsequent bench review.`
      };
    }
  }, [case1, case2]);

  return (
    <div className="workspace-module-pane precedent-comparison-container animate-fade-in">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">PRECEDENT COMPARISON</span>
        </div>
        <h1 className="module-heading font-serif">Precedent Comparison & Doctrine Matrix</h1>
        <p className="module-description">
          Side-by-side comparative jurisprudence of authoritative Supreme Court decisions. Inspect bench strength, ratio decidendi differences, statutory provisions, and verified treatment relationships.
        </p>

        {/* Featured Comparison Presets Strip */}
        <div className="comparison-presets-bar">
          <span className="presets-label mono">FEATURED COMPARISONS:</span>
          <div className="presets-chips-row">
            {presetPairs.map((p, idx) => {
              const isActive = (case1Id === p.c1 && case2Id === p.c2) || (case1Id === p.c2 && case2Id === p.c1);
              return (
                <button
                  key={idx}
                  type="button"
                  className={`preset-pair-chip ${isActive ? 'is-active' : ''}`}
                  onClick={() => {
                    setCase1Id(p.c1);
                    setCase2Id(p.c2);
                  }}
                >
                  <span>{p.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Warning Alert if same case attempted */}
      {selectionWarning && (
        <div className="comparison-warning-banner animate-fade-in">
          <AlertTriangle size={16} className="warning-icon" />
          <span className="warning-text mono">{selectionWarning}</span>
        </div>
      )}

      {/* Searchable Case Pickers Section */}
      <div className="comparison-pickers-section">
        <SearchableCasePicker
          label="PRIMARY PRECEDENT"
          roleTag="CASE A"
          selectedCase={case1}
          onSelectCase={handleSelectCase1}
          otherCaseId={case2Id}
        />

        <div className="comparison-swap-container">
          <button
            type="button"
            className="btn-swap-cases"
            onClick={handleSwapCases}
            title="Swap Case A and Case B"
            aria-label="Swap Case A and Case B"
          >
            <ArrowLeftRight size={18} />
            <span className="swap-btn-label mono">SWAP</span>
          </button>
        </div>

        <SearchableCasePicker
          label="COMPARATOR PRECEDENT"
          roleTag="CASE B"
          selectedCase={case2}
          onSelectCase={handleSelectCase2}
          otherCaseId={case1Id}
        />
      </div>

      {/* Verified Treatment Relationship Callout */}
      <div className="verified-treatment-callout">
        <div className="treatment-callout-header">
          <Scale size={16} className="treatment-icon" />
          <span className="treatment-kicker mono">DIRECT JUDICIAL TREATMENT RELATIONSHIP</span>
        </div>
        <div className={`treatment-callout-body font-serif ${treatmentText.includes('Treatment not established') ? 'is-unestablished' : 'is-established'}`}>
          {treatmentText}
        </div>
        {treatmentText.includes('Treatment not established') && (
          <div className="treatment-honesty-note mono">
            Note: Justice only records verified citation citations and treatment links from primary law reports. Where two rulings address different areas of law or separate questions, no treatment relationship is synthesized.
          </div>
        )}
      </div>

      {/* DOCTRINE MATRIX TABLE */}
      <div className="doctrine-matrix-card">
        <div className="matrix-header-row">
          <div>
            <h2 className="matrix-heading font-serif">Doctrine Matrix</h2>
            <p className="matrix-subheading">Systematic comparative evaluation across constitutional and statutory axes</p>
          </div>
          {onSwitchToWorkspace && (
            <button
              type="button"
              className="btn-matrix-switch"
              onClick={onSwitchToWorkspace}
            >
              <span>Apply to Documents Workspace</span>
              <ArrowRight size={14} />
            </button>
          )}
        </div>

        <div className="doctrine-table-wrapper">
          <table className="doctrine-matrix-table" role="table">
            <thead>
              <tr>
                <th className="th-axis mono">LEGAL AXIS</th>
                <th className="th-case font-serif">{case1.title} <span className="th-cite mono">({case1.citation})</span></th>
                <th className="th-case font-serif">{case2.title} <span className="th-cite mono">({case2.citation})</span></th>
              </tr>
            </thead>
            <tbody>
              {/* Row 1: Bench Strength & Article 141 Hierarchy */}
              <tr>
                <td className="td-axis mono">
                  <div className="axis-title">Bench Strength & Article 141</div>
                  <div className="axis-desc">Precedential authority and judicial discipline</div>
                </td>
                <td className="td-val font-serif">
                  <div className="bench-pill mono">{case1.benchSize || 2} Judges &bull; {case1.benchType || 'Bench'}</div>
                  <p className="bench-prose">{benchComparison.c1Text}</p>
                </td>
                <td className="td-val font-serif">
                  <div className="bench-pill mono">{case2.benchSize || 2} Judges &bull; {case2.benchType || 'Bench'}</div>
                  <p className="bench-prose">{benchComparison.c2Text}</p>
                </td>
              </tr>

              {/* Row 2: Chronology & Decision Year */}
              <tr>
                <td className="td-axis mono">
                  <div className="axis-title">Decision Year & Chronology</div>
                  <div className="axis-desc">Temporal development of jurisprudence</div>
                </td>
                <td className="td-val font-serif">
                  <span className="val-highlight mono">{case1.decisionYear}</span>
                  <div className="td-subtext">{case1.court}</div>
                </td>
                <td className="td-val font-serif">
                  <span className="val-highlight mono">{case2.decisionYear}</span>
                  <div className="td-subtext">{case2.court}</div>
                </td>
              </tr>

              {/* Row 3: Statutory Provisions */}
              <tr>
                <td className="td-axis mono">
                  <div className="axis-title">Statutory Provisions</div>
                  <div className="axis-desc">Enacted statutes interpreted by the court</div>
                </td>
                <td className="td-val">
                  <div className="statute-tags-list">
                    {(case1.statutes || []).map((s, idx) => (
                      <span key={idx} className="matrix-statute-pill mono">{s}</span>
                    ))}
                  </div>
                </td>
                <td className="td-val">
                  <div className="statute-tags-list">
                    {(case2.statutes || []).map((s, idx) => (
                      <span key={idx} className="matrix-statute-pill mono">{s}</span>
                    ))}
                  </div>
                </td>
              </tr>

              {/* Row 4: Core Ratio Decidendi */}
              <tr>
                <td className="td-axis mono">
                  <div className="axis-title">Ratio Decidendi</div>
                  <div className="axis-desc">Authoritative binding principle of law</div>
                </td>
                <td className="td-val font-serif">
                  <blockquote className="matrix-quote">"{case1.ratioSummary}"</blockquote>
                </td>
                <td className="td-val font-serif">
                  <blockquote className="matrix-quote">"{case2.ratioSummary}"</blockquote>
                </td>
              </tr>

              {/* Row 5: Current Precedent Status */}
              <tr>
                <td className="td-axis mono">
                  <div className="axis-title">Precedent Standing</div>
                  <div className="axis-desc">Current validity and binding status</div>
                </td>
                <td className="td-val font-serif">
                  <span className={`status-standing-badge status-${case1.status?.toLowerCase() || 'green'} mono`}>
                    {case1.statusLabel}
                  </span>
                  <p className="standing-desc">{case1.statusDescription}</p>
                </td>
                <td className="td-val font-serif">
                  <span className={`status-standing-badge status-${case2.status?.toLowerCase() || 'green'} mono`}>
                    {case2.statusLabel}
                  </span>
                  <p className="standing-desc">{case2.statusDescription}</p>
                </td>
              </tr>

              {/* Row 6: Treatment Relationship */}
              <tr>
                <td className="td-axis mono">
                  <div className="axis-title">Treatment Relationship</div>
                  <div className="axis-desc">Downstream inter-case judicial interaction</div>
                </td>
                <td colSpan={2} className="td-val-colspan font-serif">
                  <div className="matrix-treatment-box">
                    <div className="treatment-text">{treatmentText}</div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
