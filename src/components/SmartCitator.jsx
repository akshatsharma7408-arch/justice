import React, { useState, useEffect, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';
import { 
  ArrowUpRight, Sparkles, Scale, ShieldCheck, GitFork, 
  Network, BookOpen, ChevronRight, X, Info, MessageSquare, Check,
  Search, Loader2 
} from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';
import { getCitatorCaseWithBackend, fetchCaseText, searchPrecedentsWithBackend } from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

// Graph nodes definition for topological Article 141 DAG
const CITATION_GRAPH_NODES = [
  {
    id: 'node-target',
    name: "Percept D'Mark v. Zaheer Khan",
    shortName: "Percept v. Zaheer Khan",
    citation: "(2006) 4 SCC 227",
    court: "Supreme Court of India",
    bench: "Division Bench (2 Judges)",
    benchSize: 2,
    year: 2006,
    status: "TARGET",
    statusLabel: "Target Precedent",
    x: 400,
    y: 175,
    ratio: "Post-employment non-compete covenants are completely void under Section 27. Doctrine of restraint of trade applies strictly post-service."
  },
  {
    id: 'node-affirmed',
    name: "Superintendence Co. v. Krishan Murgai",
    shortName: "Superintendence Co.",
    citation: "(1981) 2 SCC 246",
    court: "Supreme Court of India",
    bench: "3-Judge Bench",
    benchSize: 3,
    year: 1980,
    status: "AFFIRMED",
    statusLabel: "Affirmed / Followed",
    x: 630,
    y: 85,
    ratio: "Restraints post-service cannot be justified by reasonableness under Indian law; Section 27 admits no exception except sale of goodwill."
  },
  {
    id: 'node-distinguished-golikari',
    name: "Niranjan Shankar Golikari v. Century Spg.",
    shortName: "Niranjan Golikari",
    citation: "(1967) 2 SCR 378",
    court: "Supreme Court of India",
    bench: "Division Bench (2 Judges)",
    benchSize: 2,
    year: 1967,
    status: "DISTINGUISHED",
    statusLabel: "Distinguished (In-Service)",
    x: 170,
    y: 85,
    ratio: "Negative covenants operating during the period of employment do not attract Section 27, whereas post-service covenants are void."
  },
  {
    id: 'node-relied-wipro',
    name: "Wipro Ltd. v. Beckman Coulter International",
    shortName: "Wipro v. Beckman Coulter",
    citation: "(2006) 131 DLT 681",
    court: "Delhi High Court",
    bench: "Single Judge",
    benchSize: 1,
    year: 2006,
    status: "RELIED_ON",
    statusLabel: "Relied On / Applied",
    x: 400,
    y: 285,
    ratio: "Applied Percept D'Mark in holding non-solicitation and restrictive covenants operating post-contract to be barred under Section 27."
  }
];

export default function SmartCitator({ initialCaseId, onActiveCaseChange }) {
  const [selectedCaseId, setSelectedCaseId] = useState(initialCaseId || 'sc-2006-percept');
  const [activeTab, setActiveTab] = useState('graph'); // default to 'graph' for immediate wow, or 'treatment', 'bench-eval', 'judgment'
  const [liveCase, setLiveCase] = useState(null);
  const [paragraphs, setParagraphs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // Interactive Graph state
  const [hoveredNodeId, setHoveredNodeId] = useState(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState(null);

  // Citator Dataset Search state
  const [citatorSearchQuery, setCitatorSearchQuery] = useState('');
  const [citatorSearchResults, setCitatorSearchResults] = useState([]);
  const [isCitatorSearching, setIsCitatorSearching] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchTimeoutRef = useRef(null);
  const searchContainerRef = useRef(null);

  const fallbackCase = LANDMARK_PRECEDENTS.find(c => c.id === selectedCaseId) || LANDMARK_PRECEDENTS[0];

  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    getCitatorCaseWithBackend(selectedCaseId)
      .then(data => {
        if (!isMounted) return;
        setLiveCase(data);
      })
      .catch(err => {
        console.warn("[SmartCitator] Backend citator fetch warning:", err.message);
        if (isMounted) setLiveCase(fallbackCase);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    fetchCaseText(selectedCaseId)
      .then(data => {
        if (isMounted) setParagraphs(data?.paragraphs || []);
      })
      .catch(err => {
        console.warn("[SmartCitator] fetchCaseText error:", err);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedCaseId]);

  const currentCase = liveCase || fallbackCase;

  // Sync active case to parent App for Case Chat scoping
  useEffect(() => {
    if (onActiveCaseChange && currentCase) {
      onActiveCaseChange({
        id: currentCase.id || selectedCaseId,
        title: currentCase.title,
        citation: currentCase.citation
      });
    }
  }, [currentCase, selectedCaseId, onActiveCaseChange]);

  // Handle case search in dataset
  const handleSearchInputChange = (text) => {
    setCitatorSearchQuery(text);
    if (!text.trim()) {
      setCitatorSearchResults([]);
      setSearchOpen(false);
      setIsCitatorSearching(false);
      return;
    }

    setIsCitatorSearching(true);
    setSearchOpen(true);

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const query = text.trim();
        const localMatches = LANDMARK_PRECEDENTS.filter(p =>
          p.title.toLowerCase().includes(query.toLowerCase()) ||
          (p.citation && p.citation.toLowerCase().includes(query.toLowerCase())) ||
          (p.keywords && p.keywords.some(k => k.toLowerCase().includes(query.toLowerCase())))
        );

        let backendResults = [];
        try {
          const resp = await searchPrecedentsWithBackend(query, 'ALL', 'ALL', false, 8, true);
          backendResults = resp.results || [];
        } catch (e) {
          console.warn("[SmartCitator] dataset search fallback:", e.message);
        }

        const combined = [...localMatches];
        const seenIds = new Set(localMatches.map(m => m.id));

        for (const br of backendResults) {
          if (!seenIds.has(br.id)) {
            seenIds.add(br.id);
            combined.push({
              id: br.id,
              title: br.title,
              citation: br.citation,
              court: br.court || 'Supreme Court of India',
              benchType: br.benchType || br.bench_type || 'Division Bench',
              benchSize: br.benchSize || br.bench_size || 2,
              decisionYear: br.decisionYear || br.year,
              ratioSummary: br.snippet || br.ratioSummary || ''
            });
          }
        }

        setCitatorSearchResults(combined.slice(0, 8));
      } catch (err) {
        console.warn("[SmartCitator] Search error:", err);
      } finally {
        setIsCitatorSearching(false);
      }
    }, 280);
  };

  const handleSelectCaseFromSearch = (caseItem) => {
    setSelectedCaseId(caseItem.id);
    setLiveCase(caseItem);
    setSelectedGraphNode(null);
    setCitatorSearchResults([]);
    setCitatorSearchQuery('');
    setSearchOpen(false);
  };

  // Jump to paragraph event handler
  useEffect(() => {
    const handleJump = (e) => {
      const targetId = e.detail?.paragraphId;
      if (targetId) {
        setActiveTab('judgment');
        setTimeout(() => {
          const el = document.getElementById(targetId);
          if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('paragraph-highlight-pulse');
            setTimeout(() => el.classList.remove('paragraph-highlight-pulse'), 2500);
          }
        }, 120);
      }
    };
    window.addEventListener('justice:scroll-to-paragraph', handleJump);
    return () => window.removeEventListener('justice:scroll-to-paragraph', handleJump);
  }, []);

  const rules = currentCase?.article141Evaluation?.rules || [
    { level: "Division Bench (2 Judges)", jurisdiction: "Bindingly bound. Lacks jurisdiction to overrule or modify this ratio.", status: "BOUND" },
    { level: `Coordinate Bench (${currentCase.benchSize || 2} Judges)`, jurisdiction: "Cannot overrule. Must refer to CJI for larger bench reference.", status: "REFERENCE_REQUIRED" },
    { level: `Larger Bench (${(currentCase.benchSize || 2) + 1}+ Judges)`, jurisdiction: "Holds plenary jurisdiction under Article 141 to review or overrule.", status: "COMPETENT_TO_OVERRULE" }
  ];

  // Dynamic Graph Nodes and Edges for the selected case
  const activeGraphNodes = useMemo(() => {
    if (selectedCaseId === 'sc-2006-percept') {
      return CITATION_GRAPH_NODES;
    }
    const cleanTitle = (currentCase.title || 'Supreme Court Precedent').trim();
    const shortTitle = cleanTitle.split('v.')[0].trim() + (cleanTitle.includes('v.') ? ' v. ...' : '');
    const target = {
      id: 'node-target',
      name: cleanTitle,
      shortName: shortTitle,
      citation: currentCase.citation || 'Supreme Court Judgment',
      court: currentCase.court || 'Supreme Court of India',
      bench: currentCase.benchType || `${currentCase.benchSize || 2} Judges Bench`,
      benchSize: currentCase.benchSize || 2,
      year: currentCase.decisionYear || currentCase.year || 2024,
      status: 'TARGET',
      statusLabel: 'Target Precedent',
      x: 400,
      y: 175,
      ratio: currentCase.ratioSummary || currentCase.aiAnalysis?.executive_summary || currentCase.snippet || "Primary ratio decidendi under Article 141 of the Constitution of India."
    };

    if (currentCase.treatmentHistory && currentCase.treatmentHistory.length > 0) {
      const positions = [
        { x: 170, y: 85 },
        { x: 630, y: 85 },
        { x: 170, y: 275 },
        { x: 630, y: 275 }
      ];
      const related = currentCase.treatmentHistory.slice(0, 4).map((th, idx) => {
        const caseTitle = th.case || 'Precedent Treatment';
        const yearMatch = caseTitle.match(/\((\d{4})\)/) || [null, th.year];
        const year = yearMatch[1] || th.year;
        const cleanName = caseTitle.replace(/\s*\(\d{4}\)/, '').trim();
        const shortRelName = cleanName.split('v.')[0].trim() + (cleanName.includes('v.') ? ' v. ...' : '');

        return {
          id: `node-${idx}`,
          name: cleanName,
          shortName: shortRelName,
          citation: th.citation || (year ? `(${year})` : 'Citation on Record'),
          court: th.court || 'Supreme Court of India',
          bench: th.bench || 'Appellate Bench',
          benchSize: th.benchSize || 2,
          year: year || currentCase.decisionYear,
          status: (th.treatment || 'AFFIRMED').toUpperCase(),
          statusLabel: th.treatment ? th.treatment.replace('_', ' ') : 'Affirmed',
          x: positions[idx].x,
          y: positions[idx].y,
          ratio: th.note || `Judicial treatment: ${th.treatment || 'Cited'}`
        };
      });
      return [target, ...related];
    }

    return [target];
  }, [selectedCaseId, currentCase]);

  const activeGraphEdges = useMemo(() => {
    return activeGraphNodes
      .filter(n => n.id !== 'node-target')
      .map((n) => {
        let stroke = '#4CAF7D';
        let dash = 'none';
        if (n.status === 'RELIED_ON') stroke = '#9AA79F';
        else if (n.status === 'DISTINGUISHED') { stroke = '#E0A030'; dash = '4 4'; }
        else if (n.status === 'OVERRULED' || n.status === 'COMPETENT_TO_OVERRULE') stroke = '#D9534F';

        return {
          id: `edge-${n.id}`,
          from: 'node-target',
          to: n.id,
          x1: 400,
          y1: 175,
          x2: n.x,
          y2: n.y,
          stroke,
          dash
        };
      });
  }, [activeGraphNodes]);

  return (
    <div className="module-view-container animate-fade-in">
      {/* Module Header */}
      <div className="module-header-block">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">JUSTICE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">SMART CITATOR</span>
        </div>
        <h1 className="module-title font-serif">Smart Citator</h1>
        <p className="module-subtitle">
          Maps judicial lineage, bench strength and treatment relationships across the indexed corpus of Supreme Court and High Court decisions. Treatment signals reflect available indexed data; always verify against the official report before citing.
        </p>

        {/* Dataset Case Lookup & Precedent Selector */}
        <div className="citator-precedent-bar">
          <div className="citator-search-wrapper" ref={searchContainerRef}>
            <div className="citator-search-box">
              <Search size={16} className="citator-search-icon" aria-hidden="true" />
              <input
                type="text"
                placeholder="Search any case in dataset (e.g. Arnesh Kumar, Puttaswamy, Percept, citation...)"
                value={citatorSearchQuery}
                onChange={(e) => handleSearchInputChange(e.target.value)}
                onFocus={() => { if (citatorSearchResults.length > 0) setSearchOpen(true); }}
                className="citator-search-input"
                aria-label="Look up any Supreme Court case"
              />
              {isCitatorSearching && (
                <span className="citator-search-status mono">
                  <Loader2 size={13} className="spin-inline" /> Searching...
                </span>
              )}
              {citatorSearchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setCitatorSearchQuery('');
                    setCitatorSearchResults([]);
                    setSearchOpen(false);
                  }}
                  className="citator-search-clear"
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            {searchOpen && citatorSearchResults.length > 0 && (
              <div className="citator-search-dropdown animate-fade-in">
                <div className="citator-dropdown-header mono">
                  MATCHING CASES IN DATASET ({citatorSearchResults.length})
                </div>
                {citatorSearchResults.map((res) => {
                  const isLandmark = LANDMARK_PRECEDENTS.some(p => p.id === res.id);
                  return (
                    <button
                      key={res.id}
                      type="button"
                      className="citator-search-item"
                      onClick={() => handleSelectCaseFromSearch(res)}
                    >
                      <div className="citator-search-item-top">
                        <span className="citator-search-item-title font-serif">{res.title}</span>
                        <span className={`citator-dataset-badge mono ${isLandmark ? 'is-landmark' : 'is-sc'}`}>
                          {isLandmark ? 'LANDMARK' : 'SUPREME COURT'}
                        </span>
                      </div>
                      <div className="citator-search-item-meta mono">
                        <span>{res.citation || 'SC Judgment'}</span>
                        {res.decisionYear && <span>&bull; {res.decisionYear}</span>}
                        {res.benchType && <span>&bull; {res.benchType}</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="citator-chips-header-row">
            <span className="picker-label mono">OR CHOOSE LANDMARK PRECEDENT:</span>
            {currentCase && !LANDMARK_PRECEDENTS.some(p => p.id === currentCase.id) && (
              <span className="citator-current-loaded-badge mono">
                Active Case: {currentCase.title.split('v.')[0]} ({currentCase.decisionYear || currentCase.year})
              </span>
            )}
          </div>

          <div className="citator-chips-flow">
            {LANDMARK_PRECEDENTS.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`citator-chip ${c.id === selectedCaseId ? 'is-active' : ''}`}
                onClick={() => {
                  setSelectedCaseId(c.id);
                  setSelectedGraphNode(null);
                }}
              >
                <span className={`citator-chip-dot status-${(c.status || 'GREEN').toLowerCase()}`} />
                <span className="citator-chip-name font-serif">{c.title.split('v.')[0]}</span>
                <span className="citator-chip-year mono">({c.decisionYear})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="module-tabs-strip">
          {[
            { id: 'graph', label: 'Citation DAG Network' },
            { id: 'treatment', label: 'Article 141 Lineage' },
            { id: 'bench-eval', label: 'Bench Strength Rules' },
            { id: 'judgment', label: 'Verified Primary Judgment' }
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`module-tab-btn ${activeTab === tab.id ? 'is-active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span>{tab.label}</span>
              {activeTab === tab.id && <span className="tab-copper-line" />}
            </button>
          ))}
        </div>
      </div>

      {/* Main Tab Panels */}
      <div className="citator-tab-content">
        {/* =========================================================================
            TAB 1: INTERACTIVE CITATION GRAPH (Hover highlights, Click opens detail)
            ========================================================================= */}
        {activeTab === 'graph' && (
          <div className="citator-graph-card animate-fade-in">
            <div className="graph-header-row">
              <div>
                <span className="graph-kicker mono">PRECEDENT CITATION & TREATMENT GRAPH</span>
                <h3 className="graph-title font-serif">
                  Precedent Citation Topology: {currentCase.title}
                </h3>
                <p className="graph-desc">
                  Hover over connected cases to trace precedent linkages; click any node to inspect its ratio decidendi and judicial treatment.
                </p>
              </div>
              <span className="citator-caveat-note text-xs text-muted font-mono">
                Treatment based on available data; verify before citing
              </span>
            </div>

            {/* Check if verified relationship data exists */}
            {activeGraphNodes.length <= 1 ? (
              <div className="citator-empty-treatment-card">
                <div className="empty-treatment-icon-wrap">
                  <Info size={24} className="text-muted" />
                </div>
                <h4 className="empty-treatment-title font-serif">
                  No direct treatment relationship recorded in current archive
                </h4>
                <p className="empty-treatment-text font-serif">
                  While <em>{currentCase.title}</em> is an indexed decision, no downstream treatment links (affirmations, distinctions, or overrulings) have been entered into the active index for this precedent yet.
                </p>
              </div>
            ) : (
              /* SVG Interactive Canvas */
              <div className="graph-canvas-wrap">
                <svg className="graph-svg-canvas" viewBox="0 0 800 350">
                  <defs>
                    <marker id="arrow-copper" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#E0955A" />
                    </marker>
                    <marker id="arrow-muted" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#24403A" />
                    </marker>
                  </defs>

                  {/* Connecting Edges */}
                  {activeGraphEdges.map((edge) => {
                    const isHighlighted = hoveredNodeId === edge.to || hoveredNodeId === 'node-target' || selectedGraphNode?.id === edge.to;
                    return (
                      <line
                        key={edge.id}
                        x1={edge.x1}
                        y1={edge.y1}
                        x2={edge.x2}
                        y2={edge.y2}
                        stroke={isHighlighted ? '#E0955A' : edge.stroke}
                        strokeWidth={isHighlighted ? 2.5 : 1.25}
                        strokeDasharray={edge.dash || 'none'}
                        opacity={hoveredNodeId && !isHighlighted ? 0.25 : 0.8}
                        markerEnd={isHighlighted ? 'url(#arrow-copper)' : 'url(#arrow-muted)'}
                        style={{ transition: 'all 200ms ease' }}
                      />
                    );
                  })}

                  {/* Nodes */}
                  {activeGraphNodes.map((node) => {
                    const isTarget = node.id === 'node-target';
                    const isHovered = hoveredNodeId === node.id;
                    const isSelected = selectedGraphNode?.id === node.id;
                    const isDimmed = hoveredNodeId && hoveredNodeId !== node.id && !isTarget;

                    let borderColor = '#24403A';
                    let statusBg = '#12261F';
                    let statusColor = '#EFE8D6';

                    if (node.status === 'TARGET') {
                      borderColor = '#C77B3A';
                      statusBg = '#17302A';
                      statusColor = '#E0955A';
                    } else if (node.status === 'AFFIRMED') {
                      borderColor = '#4CAF7D';
                      statusColor = '#4CAF7D';
                    } else if (node.status === 'RELIED_ON') {
                      borderColor = '#9AA79F';
                      statusColor = '#D9D3C2';
                    } else if (node.status === 'DISTINGUISHED') {
                      borderColor = '#E0A030';
                      statusColor = '#E0A030';
                    } else if (node.status === 'OVERRULED') {
                      borderColor = '#D9534F';
                      statusColor = '#D9534F';
                    }

                    return (
                      <g
                        key={node.id}
                        transform={`translate(${node.x}, ${node.y})`}
                        className={`graph-node-group ${isHovered ? 'is-hovered' : ''}`}
                        onMouseEnter={() => setHoveredNodeId(node.id)}
                        onMouseLeave={() => setHoveredNodeId(null)}
                        onClick={() => setSelectedGraphNode(node)}
                        style={{
                          cursor: 'pointer',
                          opacity: isDimmed ? 0.35 : 1,
                          transition: 'opacity 200ms ease'
                        }}
                      >
                        <rect
                          x="-95"
                          y="-35"
                          width="190"
                          height="70"
                          rx="12"
                          fill={isHovered || isSelected ? '#17302A' : statusBg}
                          stroke={isHovered || isSelected ? '#E0955A' : borderColor}
                          strokeWidth={isHovered || isSelected ? 2.5 : 1}
                          style={{ transition: 'stroke 150ms ease, fill 150ms ease, stroke-width 150ms ease' }}
                        />
                        <text textAnchor="middle" y="-18" fill={statusColor} fontSize="8" fontWeight="700" letterSpacing="0.05em" fontFamily="Inter, sans-serif">
                          {node.statusLabel.toUpperCase()}
                        </text>
                        <text textAnchor="middle" y="-2" fill="#FFFFFF" fontSize="10.5" fontWeight="600" fontFamily="Playfair Display, Georgia, serif">
                          {(node.shortName || node.name).length > 25 ? (node.shortName || node.name).slice(0, 24) + '…' : (node.shortName || node.name)}
                        </text>
                        <text textAnchor="middle" y="13" fill="#D4AF37" fontSize="9" fontWeight="500" fontFamily="JetBrains Mono, monospace">
                          {node.citation && node.citation.length > 24 ? node.citation.slice(0, 23) + '…' : node.citation}
                        </text>
                        <text textAnchor="middle" y="25" fill="#9AA79F" fontSize="8" fontFamily="Inter, sans-serif">
                          {node.court.split(' ')[0]} {node.court.includes('High') ? 'HC' : 'SC'} • {node.year}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                {/* Legend Strip */}
                <div className="graph-legend-bar">
                  <span className="legend-entry"><span className="legend-dot green" /> Affirmed</span>
                  <span className="legend-entry"><span className="legend-dot grey" /> Relied Upon</span>
                  <span className="legend-entry"><span className="legend-dot amber" /> Distinguished</span>
                  <span className="legend-entry"><span className="legend-dot red" /> Overruled</span>
                </div>
              </div>
            )}

            {/* Click-to-Open Case Detail Panel Drawer */}
            {selectedGraphNode && (
              <div className="node-detail-drawer animate-fade-in">
                <div className="node-detail-header">
                  <div className="node-detail-title-cluster">
                    <span className="node-detail-tag mono">{selectedGraphNode.statusLabel}</span>
                    <h4 className="node-detail-name font-serif">{selectedGraphNode.name}</h4>
                    <span className="node-detail-citation mono">{selectedGraphNode.citation} &bull; {selectedGraphNode.court}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-close-detail"
                    onClick={() => setSelectedGraphNode(null)}
                    aria-label="Close Case Detail"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="node-detail-body">
                  <div className="detail-ratio-box">
                    <div className="ratio-label mono">HOLDING PRINCIPLE / RATIO:</div>
                    <p className="ratio-prose font-serif">"{selectedGraphNode.ratio}"</p>
                  </div>
                  <div className="detail-meta-grid mono">
                    <div><strong>Bench:</strong> {selectedGraphNode.bench}</div>
                    <div><strong>Decision Year:</strong> {selectedGraphNode.year}</div>
                    <div><strong>Jurisdiction:</strong> {selectedGraphNode.court}</div>
                  </div>
                </div>

                <div className="node-detail-footer">
                  <button
                    type="button"
                    className="btn-detail-target"
                    onClick={() => {
                      if (selectedGraphNode.id !== 'node-target') {
                        const targetId = selectedGraphNode.caseId || (selectedGraphNode.id.startsWith('sc-') ? selectedGraphNode.id : null);
                        if (targetId) setSelectedCaseId(targetId);
                        setSelectedGraphNode(null);
                      }
                    }}
                  >
                    <span>Focus Precedent</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            TAB 2: LINEAGE & SHEPARDIZER LIST
            ========================================================================= */}
        {activeTab === 'treatment' && (
          <div className="citator-treatment-panel animate-fade-in">
            <div className="treatment-panel-header">
              <span className="treatment-kicker mono">PRECEDENT CITATION & TREATMENT HISTORY</span>
              <h3 className="treatment-title font-serif">Judicial Treatment History</h3>
              <p className="treatment-desc">
                How subsequent High Court and Supreme Court benches have treated <em>{currentCase.title}</em>:
              </p>
            </div>

            <div className="treatment-items-list">
              {(() => {
                const treatments = (currentCase.subsequentTreatments && currentCase.subsequentTreatments.length > 0)
                  ? currentCase.subsequentTreatments
                  : (currentCase.treatmentHistory && currentCase.treatmentHistory.length > 0)
                    ? currentCase.treatmentHistory.map(th => ({
                        caseName: th.case,
                        citation: `(${th.year})`,
                        court: th.court || 'Supreme Court of India',
                        treatmentType: (th.treatment || 'AFFIRMED').toUpperCase(),
                        treatmentSummary: th.note || `Judicial treatment of precedent: ${th.treatment}`
                      }))
                    : [];

                if (treatments.length === 0) {
                  return (
                    <div className="citator-empty-treatment-card">
                      <div className="empty-treatment-icon-wrap">
                        <Info size={24} className="text-muted" />
                      </div>
                      <h4 className="empty-treatment-title font-serif">
                        No direct treatment relationship recorded in current archive
                      </h4>
                      <p className="empty-treatment-text font-serif">
                        No downstream judicial treatment records are currently catalogued for <em>{currentCase.title}</em>. Verify primary law reports before citing.
                      </p>
                    </div>
                  );
                }

                return treatments.map((t, idx) => (
                  <div key={idx} className="treatment-card">
                    <div className="treatment-card-header">
                      <span className={`treatment-badge mono ${(t.treatmentType || 'AFFIRMED').toLowerCase()}`}>
                        {(t.treatmentType || 'AFFIRMED').replace('_', ' ')}
                      </span>
                      <span className="treatment-citation mono">{t.citation}</span>
                    </div>
                    <h4 className="treatment-case-name font-serif">{t.caseName}</h4>
                    <p className="treatment-case-summary font-serif">"{t.treatmentSummary}"</p>
                  </div>
                ));
              })()}
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 3: ARTICLE 141 BENCH RULES ENGINE
            ========================================================================= */}
        {activeTab === 'bench-eval' && (
          <div className="citator-treatment-panel animate-fade-in">
            <div className="treatment-panel-header">
              <span className="treatment-kicker mono">CONSTITUTIONAL BENCH RULES ENGINE</span>
              <h3 className="treatment-title font-serif">Precedent Invalidation Criteria</h3>
              <p className="treatment-desc">
                Codified pursuant to <em>Central Board of Dawoodi Bohra Community v. State of Maharashtra (2005) 2 SCC 673</em>:
              </p>
            </div>

            <div className="bench-matrix-layout">
              <div className="bench-coram-card">
                <div className="coram-label mono">TARGET BENCH STRENGTH</div>
                <div className="coram-number font-serif">{currentCase.benchSize}</div>
                <div className="coram-desc">
                  <strong>{currentCase.benchType}</strong> comprising {currentCase.benchSize} Supreme Court Justices.
                </div>
              </div>

              <div className="bench-rules-card">
                <div className="rules-card-label mono">ARTICLE 141 DISCIPLINE BOUNDARIES</div>
                <div className="rules-stack">
                  {rules.map((r, i) => (
                    <div key={i} className="rule-item-row">
                      <span className="rule-num mono">0{i + 1}</span>
                      <div className="rule-content">
                        <strong className="rule-level font-serif">{r.level}:</strong>{' '}
                        <span className="rule-jurisdiction">{r.jurisdiction}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 4: VERIFIED PRIMARY JUDGMENT TEXT
            ========================================================================= */}
        {activeTab === 'judgment' && (
          <div className="citator-treatment-panel animate-fade-in">
            <div className="treatment-panel-header">
              <span className="treatment-kicker mono">VERIFIED PRIMARY SOURCE TEXT</span>
              <h3 className="treatment-title font-serif">Recorded Judgment Excerpts & Paragraphs</h3>
              <p className="treatment-desc">
                Authentic recorded text of {currentCase.title} ({currentCase.citation}). Click "Based on: Paragraph X" in Case Chat to jump directly to any paragraph.
              </p>
            </div>

            <div className="judgment-paras-stream">
              {paragraphs.length === 0 ? (
                <div className="empty-paras-note mono">Loading authentic judgment paragraphs...</div>
              ) : (
                paragraphs.map((p) => (
                  <article key={p.id} id={p.id} className="judgment-para-block">
                    <div className="para-header mono">
                      <span className="para-index-tag">{p.id.toUpperCase()}</span>
                      {p.anchor && <span className="para-anchor-tag">{p.anchor}</span>}
                    </div>
                    <p className="para-body font-serif">{p.text}</p>
                  </article>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
