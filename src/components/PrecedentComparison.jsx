import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
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
  HelpCircle,
  Loader2
} from 'lucide-react';

function getVerifiedTreatment(c1, c2) {
  if (!c1 || !c2 || c1.id === c2.id) {
    return "Treatment not established from the available records";
  }

  const c1Title = (c1.title || '').toLowerCase();
  const c2Title = (c2.title || '').toLowerCase();
  const c1Cite = (c1.citation || '').toLowerCase();
  const c2Cite = (c2.citation || '').toLowerCase();

  // 1. Check if c1 overruled c2
  const c1Overruled = (c1.overruledCases || []).find(oc => {
    const ocLow = oc.toLowerCase();
    return (c2Title.length > 5 && ocLow.includes(c2Title.slice(0, 14))) ||
      (c2Cite && ocLow.includes(c2Cite));
  });
  if (c1Overruled) {
    return `${c1.title} (${c1.decisionYear || 'SC'}) expressly overruled ${c2.title} (${c2.decisionYear || 'SC'}).`;
  }

  // 2. Check if c2 overruled c1
  const c2Overruled = (c2.overruledCases || []).find(oc => {
    const ocLow = oc.toLowerCase();
    return (c1Title.length > 5 && ocLow.includes(c1Title.slice(0, 14))) ||
      (c1Cite && ocLow.includes(c1Cite));
  });
  if (c2Overruled) {
    return `${c2.title} (${c2.decisionYear || 'SC'}) expressly overruled ${c1.title} (${c1.decisionYear || 'SC'}).`;
  }

  // 3. Check c1's treatmentHistory for c2
  const t1 = (c1.treatmentHistory || []).find(th => {
    const thCase = (th.case || '').toLowerCase();
    return (c2Title.length > 5 && thCase.includes(c2Title.slice(0, 14))) ||
      (thCase.length > 5 && c2Title.includes(thCase.slice(0, 14)));
  });
  if (t1) {
    const verb = t1.treatment === 'AFFIRMED' ? 'affirmed' :
      t1.treatment === 'DISTINGUISHED' ? 'distinguished' :
        t1.treatment === 'RELIED_ON' ? 'relied on' :
          t1.treatment === 'OVERRULED' ? 'overruled' : t1.treatment.toLowerCase();
    return `${c1.title} was ${verb} in ${t1.case} (${t1.year})${t1.note ? `: ${t1.note}` : ''}.`;
  }

  // 4. Check c2's treatmentHistory for c1
  const t2 = (c2.treatmentHistory || []).find(th => {
    const thCase = (th.case || '').toLowerCase();
    return (c1Title.length > 5 && thCase.includes(c1Title.slice(0, 14))) ||
      (thCase.length > 5 && c1Title.includes(thCase.slice(0, 14)));
  });
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
 * Searchable Case Picker Component with real backend search API
 */
function SearchableCasePicker({
  label,
  selectedCase,
  isLoadingCase,
  caseError,
  onSelectCase,
  otherCaseId,
  roleTag
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const wrapperRef = useRef(null);
  const changeButtonRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const requestIdRef = useRef(0);

  // Close popover when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch candidates from real backend API with debounce and stale-request cancellation
  useEffect(() => {
    if (!isOpen) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const currentReqId = ++requestIdRef.current;

    setIsSearching(true);
    const timer = setTimeout(async () => {
      try {
        const queryParam = encodeURIComponent(searchQuery.trim());
        const res = await fetch(`/api/v1/cases/search?q=${queryParam}&limit=25`, {
          signal: controller.signal
        });
        if (!res.ok) throw new Error(`Search failed: ${res.status}`);
        const data = await res.json();
        if (currentReqId === requestIdRef.current) {
          setCandidates(data.cases || []);
          setHighlightedIndex(0);
          setIsSearching(false);
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Case search failed:', err);
          if (currentReqId === requestIdRef.current) {
            setCandidates([]);
            setIsSearching(false);
          }
        }
      }
    }, 200);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [isOpen, searchQuery]);

  // Handle focus when popover opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Keyboard navigation for combobox
  const handleKeyDown = (e) => {
    if (!isOpen) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightedIndex(prev => (prev + 1) % Math.max(1, candidates.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex(prev => (prev - 1 + candidates.length) % Math.max(1, candidates.length));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const current = candidates[highlightedIndex];
      if (current && current.id !== otherCaseId && current.id !== selectedCase?.id) {
        onSelectCase(current.id);
        setIsOpen(false);
        if (changeButtonRef.current) changeButtonRef.current.focus();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setIsOpen(false);
      if (changeButtonRef.current) changeButtonRef.current.focus();
    }
  };

  return (
    <div className="case-picker-card" ref={wrapperRef}>
      <div className="picker-card-header">
        <span className="picker-role-tag mono">{roleTag}</span>
        <span className="picker-field-label mono">{label}</span>
      </div>

      {/* Loading state for selected case */}
      {isLoadingCase && (
        <div className="selected-case-loading mono">
          <Loader2 size={16} className="animate-spin" />
          <span>Fetching case source record...</span>
        </div>
      )}

      {/* Error state if case lookup fails honestly */}
      {!isLoadingCase && caseError && (
        <div className="selected-case-error mono">
          <AlertTriangle size={16} />
          <span>{caseError}</span>
        </div>
      )}

      {/* Selected Case Summary Card */}
      {!isLoadingCase && !caseError && selectedCase && (
        <div className="selected-case-summary">
          <div className="summary-title-row">
            <h3 className="summary-case-title font-serif">{selectedCase.title}</h3>
            {selectedCase.citation ? (
              <span className="summary-citation mono">{selectedCase.citation}</span>
            ) : (
              <span className="summary-citation mono is-missing">[Citation not available]</span>
            )}
          </div>

          <div className="summary-meta-row mono">
            <span className="meta-badge">
              <Users size={12} /> {selectedCase.benchSize ? `${selectedCase.benchSize} Judges` : 'Bench unrecorded'} ({selectedCase.benchType || 'Bench'})
            </span>
            <span className="meta-badge">
              <Calendar size={12} /> {selectedCase.decisionYear || 'Year unrecorded'}
            </span>
            <span className="meta-court">{selectedCase.court || 'Supreme Court of India'}</span>
          </div>

          <div className="summary-ratio-box">
            <span className="ratio-label mono">CORE RATIO DECIDENDI / LEGAL PRINCIPLE:</span>
            <p className="ratio-text font-serif">
              "{selectedCase.ratioSummary || 'Ratio summary not recorded in available archive'}"
            </p>
          </div>

          <div className="summary-statutes-row">
            {selectedCase.statutes && selectedCase.statutes.length > 0 ? (
              selectedCase.statutes.map((s, idx) => (
                <span key={idx} className="statute-pill mono">{s}</span>
              ))
            ) : (
              <span className="statute-pill-empty mono">No specific statutes cited in available record</span>
            )}
          </div>

          <div className="picker-action-bar">
            <button
              ref={changeButtonRef}
              type="button"
              className="btn-change-case"
              aria-haspopup="listbox"
              aria-expanded={isOpen}
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
        <div
          className="picker-dropdown-popover animate-fade-in"
          role="region"
          aria-label="Precedent Search"
          onKeyDown={handleKeyDown}
        >
          <div className="picker-search-bar">
            <Search size={16} className="picker-search-icon" />
            <input
              ref={inputRef}
              type="text"
              className="picker-search-input"
              placeholder="Search by case title, partial name, citation, or year..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search case collection"
              role="combobox"
              aria-expanded={isOpen}
              aria-controls="picker-candidates-list"
            />
            {isSearching && (
              <Loader2 size={14} className="animate-spin text-muted" />
            )}
            {searchQuery && !isSearching && (
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

          <div
            id="picker-candidates-list"
            className="picker-results-list"
            role="listbox"
          >
            {isSearching && candidates.length === 0 ? (
              <div className="picker-searching-notice mono">
                Searching 1,740+ Supreme Court & High Court cases...
              </div>
            ) : candidates.length === 0 ? (
              <div className="picker-no-results mono">
                No matching precedents found for "{searchQuery}" in available archive.
              </div>
            ) : (
              candidates.map((c, index) => {
                const isCurrent = c.id === selectedCase?.id;
                const isOther = c.id === otherCaseId;
                const isDisabled = isCurrent || isOther;
                const isHighlighted = index === highlightedIndex;

                return (
                  <button
                    key={c.id}
                    type="button"
                    role="option"
                    aria-selected={isCurrent}
                    disabled={isDisabled}
                    className={`picker-candidate-item ${isCurrent ? 'is-selected' : ''} ${isOther ? 'is-disabled' : ''} ${isHighlighted ? 'is-highlighted' : ''}`}
                    onClick={() => {
                      if (!isDisabled) {
                        onSelectCase(c.id);
                        setIsOpen(false);
                        if (changeButtonRef.current) changeButtonRef.current.focus();
                      }
                    }}
                    onMouseEnter={() => setHighlightedIndex(index)}
                  >
                    <div className="candidate-header">
                      <span className="candidate-title font-serif">{c.title}</span>
                      <span className="candidate-citation mono">{c.citation || '[No citation recorded]'}</span>
                    </div>
                    <div className="candidate-meta mono">
                      <span>{c.decisionYear || 'Year unrecorded'} &bull; {c.benchSize ? `${c.benchSize} Judges` : 'Bench unrecorded'} ({c.benchType || 'Bench'})</span>
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
  // Stable case IDs across the 1,740+ collection
  const [case1Id, setCase1Id] = useState('sc-2006-percept');
  const [case2Id, setCase2Id] = useState('sc-1967-niranjan');

  const [case1Data, setCase1Data] = useState(null);
  const [case2Data, setCase2Data] = useState(null);
  const [loading1, setLoading1] = useState(true);
  const [loading2, setLoading2] = useState(true);
  const [error1, setError1] = useState(null);
  const [error2, setError2] = useState(null);

  const [selectionWarning, setSelectionWarning] = useState(null);

  // Fetch Case 1 by ID from real backend
  useEffect(() => {
    let isCancelled = false;
    setLoading1(true);
    setError1(null);

    fetch(`/api/v1/cases/${encodeURIComponent(case1Id)}`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`Case '${case1Id}' not found in archive (${res.status})`);
        }
        return res.json();
      })
      .then(data => {
        if (!isCancelled) {
          setCase1Data(data);
          setLoading1(false);
        }
      })
      .catch(err => {
        if (!isCancelled) {
          console.error("Error loading Case 1:", err);
          setError1(`Could not load precedent '${case1Id}'. Record unavailable in archive.`);
          setCase1Data(null);
          setLoading1(false);
        }
      });

    return () => { isCancelled = true; };
  }, [case1Id]);

  // Fetch Case 2 by ID from real backend
  useEffect(() => {
    let isCancelled = false;
    setLoading2(true);
    setError2(null);

    fetch(`/api/v1/cases/${encodeURIComponent(case2Id)}`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`Case '${case2Id}' not found in archive (${res.status})`);
        }
        return res.json();
      })
      .then(data => {
        if (!isCancelled) {
          setCase2Data(data);
          setLoading2(false);
        }
      })
      .catch(err => {
        if (!isCancelled) {
          console.error("Error loading Case 2:", err);
          setError2(`Could not load precedent '${case2Id}'. Record unavailable in archive.`);
          setCase2Data(null);
          setLoading2(false);
        }
      });

    return () => { isCancelled = true; };
  }, [case2Id]);

  // Featured comparisons using real stable IDs
  const presetPairs = [
    {
      label: "Section 27: Post-Service vs During-Service",
      c1: 'sc-2006-percept',
      c2: 'sc-1967-niranjan'
    },
    {
      label: "Article 21: Privacy Recognized vs Emergency Suspension",
      c1: 'sc-2017-puttaswamy',
      c2: 'sc-1976-admjabalpur'
    },
    {
      label: "Tenancy: Section 106 Notice vs Mesne Profits",
      c1: 'sc-1979-dhanapal',
      c2: 'sc-2005-atmaram'
    },
    {
      label: "Section 27: Division Bench (2006) vs 3-Judge Bench (1980)",
      c1: 'sc-2006-percept',
      c2: 'sc-1980-superintendence'
    },
    {
      label: "Article 21: Live-in Protection vs Domestic Violence Definition",
      c1: 'sc-2010-khushboo',
      c2: 'sc-2010-velusamy'
    }
  ];

  const handleSelectCase1 = useCallback((id) => {
    if (id === case2Id) {
      setSelectionWarning("Cannot compare a case against itself. Please choose a different precedent.");
      setTimeout(() => setSelectionWarning(null), 3500);
      return;
    }
    setSelectionWarning(null);
    setCase1Id(id);
  }, [case2Id]);

  const handleSelectCase2 = useCallback((id) => {
    if (id === case1Id) {
      setSelectionWarning("Cannot compare a case against itself. Please choose a different precedent.");
      setTimeout(() => setSelectionWarning(null), 3500);
      return;
    }
    setSelectionWarning(null);
    setCase2Id(id);
  }, [case1Id]);

  const handleSwapCases = () => {
    setCase1Id(case2Id);
    setCase2Id(case1Id);
    setCase1Data(case2Data);
    setCase2Data(case1Data);
    setError1(error2);
    setError2(error1);
  };

  // Treatment Relationship text
  const treatmentText = useMemo(() => {
    return getVerifiedTreatment(case1Data, case2Data);
  }, [case1Data, case2Data]);

  // Bench Hierarchy comparison text
  const benchComparison = useMemo(() => {
    if (!case1Data || !case2Data) {
      return {
        c1Text: "Bench details pending load",
        c2Text: "Bench details pending load",
        relationship: "Select both precedents to compute Article 141 hierarchy."
      };
    }
    const b1 = case1Data.benchSize;
    const b2 = case2Data.benchSize;

    if (!b1 || !b2) {
      return {
        c1Text: b1 ? `${b1} Judges (${case1Data.benchType || 'Bench'})` : 'Bench size not recorded in archive',
        c2Text: b2 ? `${b2} Judges (${case2Data.benchType || 'Bench'})` : 'Bench size not recorded in archive',
        relationship: 'Article 141 comparison requires recorded bench strengths for both decisions.'
      };
    }

    if (b1 > b2) {
      return {
        c1Text: `${b1} Judges (${case1Data.benchType || 'Bench'}) — Higher bench authority; binds coordinate and smaller benches under Article 141`,
        c2Text: `${b2} Judges (${case2Data.benchType || 'Bench'}) — Smaller bench strength relative to Case A`,
        relationship: `Case A (${b1} Judges) holds superior precedential weight over Case B (${b2} Judges) under Article 141 doctrine of stare decisis.`
      };
    } else if (b2 > b1) {
      return {
        c1Text: `${b1} Judges (${case1Data.benchType || 'Bench'}) — Smaller bench strength relative to Case B`,
        c2Text: `${b2} Judges (${case2Data.benchType || 'Bench'}) — Higher bench authority; binds coordinate and smaller benches under Article 141`,
        relationship: `Case B (${b2} Judges) holds superior precedential weight over Case A (${b1} Judges) under Article 141 doctrine of stare decisis.`
      };
    } else {
      return {
        c1Text: `${b1} Judges (${case1Data.benchType || 'Bench'}) — Coordinate bench`,
        c2Text: `${b2} Judges (${case2Data.benchType || 'Bench'}) — Coordinate bench`,
        relationship: `Equal bench strength (${b1} Judges). Rulings stand as coordinate authorities governed by chronology and subsequent bench review.`
      };
    }
  }, [case1Data, case2Data]);

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
          Side-by-side comparative jurisprudence across the entire archive of 1,740+ Supreme Court and High Court decisions. Inspect bench strength, ratio decidendi differences, statutory provisions, and verified treatment relationships.
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
        <div className="comparison-warning-banner animate-fade-in" role="alert">
          <AlertTriangle size={16} className="warning-icon" />
          <span className="warning-text mono">{selectionWarning}</span>
        </div>
      )}

      {/* Searchable Case Pickers Section */}
      <div className="comparison-pickers-section">
        <SearchableCasePicker
          label="PRIMARY PRECEDENT"
          roleTag="CASE A"
          selectedCase={case1Data}
          isLoadingCase={loading1}
          caseError={error1}
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
          selectedCase={case2Data}
          isLoadingCase={loading2}
          caseError={error2}
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
            Note: Justice records verified citations and treatment links from primary law reports. Where two rulings address different areas of law or separate questions, no treatment relationship is synthesized.
          </div>
        )}
      </div>

      {/* DOCTRINE MATRIX TABLE */}
      {case1Data && case2Data && (
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
                  <th className="th-case font-serif">
                    {case1Data.title} <span className="th-cite mono">({case1Data.citation || 'Citation unrecorded'})</span>
                  </th>
                  <th className="th-case font-serif">
                    {case2Data.title} <span className="th-cite mono">({case2Data.citation || 'Citation unrecorded'})</span>
                  </th>
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
                    <div className="bench-pill mono">
                      {case1Data.benchSize ? `${case1Data.benchSize} Judges` : 'Bench unrecorded'} &bull; {case1Data.benchType || 'Bench'}
                    </div>
                    <p className="bench-prose">{benchComparison.c1Text}</p>
                  </td>
                  <td className="td-val font-serif">
                    <div className="bench-pill mono">
                      {case2Data.benchSize ? `${case2Data.benchSize} Judges` : 'Bench unrecorded'} &bull; {case2Data.benchType || 'Bench'}
                    </div>
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
                    <span className="val-highlight mono">{case1Data.decisionYear || 'Unrecorded'}</span>
                    <div className="td-subtext">{case1Data.court}</div>
                  </td>
                  <td className="td-val font-serif">
                    <span className="val-highlight mono">{case2Data.decisionYear || 'Unrecorded'}</span>
                    <div className="td-subtext">{case2Data.court}</div>
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
                      {case1Data.statutes && case1Data.statutes.length > 0 ? (
                        case1Data.statutes.map((s, idx) => (
                          <span key={idx} className="matrix-statute-pill mono">{s}</span>
                        ))
                      ) : (
                        <span className="statute-pill-empty mono">No specific statutes cited in available record</span>
                      )}
                    </div>
                  </td>
                  <td className="td-val">
                    <div className="statute-tags-list">
                      {case2Data.statutes && case2Data.statutes.length > 0 ? (
                        case2Data.statutes.map((s, idx) => (
                          <span key={idx} className="matrix-statute-pill mono">{s}</span>
                        ))
                      ) : (
                        <span className="statute-pill-empty mono">No specific statutes cited in available record</span>
                      )}
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
                    <blockquote className="matrix-quote">"{case1Data.ratioSummary}"</blockquote>
                  </td>
                  <td className="td-val font-serif">
                    <blockquote className="matrix-quote">"{case2Data.ratioSummary}"</blockquote>
                  </td>
                </tr>

                {/* Row 5: Current Precedent Status */}
                <tr>
                  <td className="td-axis mono">
                    <div className="axis-title">Precedent Standing</div>
                    <div className="axis-desc">Current validity and binding status</div>
                  </td>
                  <td className="td-val font-serif">
                    <span className={`status-standing-badge status-${case1Data.status?.toLowerCase() || 'green'} mono`}>
                      {case1Data.statusLabel || 'Good Law / Binding'}
                    </span>
                    <p className="standing-desc">
                      {case1Data.statusDescription || 'Authoritative precedent of the Supreme Court of India.'}
                    </p>
                  </td>
                  <td className="td-val font-serif">
                    <span className={`status-standing-badge status-${case2Data.status?.toLowerCase() || 'green'} mono`}>
                      {case2Data.statusLabel || 'Good Law / Binding'}
                    </span>
                    <p className="standing-desc">
                      {case2Data.statusDescription || 'Authoritative precedent of the Supreme Court of India.'}
                    </p>
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
      )}
    </div>
  );
}
