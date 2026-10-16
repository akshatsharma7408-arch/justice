import React, { useState } from 'react';
import { ChevronDown, ArrowRight } from 'lucide-react';

export default function ManupatraComparison({ onSwitchToWorkspace }) {
  const [activeMode, setActiveMode] = useState('side-by-side'); // 'side-by-side', 'legacy-only', 'antigravity-only'
  const [activeDropdown, setActiveDropdown] = useState(null);
  const [booleanInput, setBooleanInput] = useState('"Section 138" W/5 "Cheque" NOT "Notice"');
  const [simulatedError, setSimulatedError] = useState(false);

  const toggleDropdown = (name) => {
    setActiveDropdown(activeDropdown === name ? null : name);
  };

  const handleBooleanSearch = (e) => {
    e.preventDefault();
    setSimulatedError(true);
  };

  return (
    <div className="module-container">
      {/* Editorial Header Section */}
      <div className="editorial-hero-section">
        <div className="editorial-meta-label">COLLECTION 04 / ARCHITECTURAL COMPARISON</div>
        <h1 className="hero-editorial-title">Manupatra Critique</h1>
        <p className="hero-editorial-subtitle">
          An architectural comparison of legacy legal database paradigms (cascading taxonomies, brittle Boolean syntax, multi-tab fatigue) 
          versus the Justice Editorial Workspace (natural language intent, unified split canvas, and automated Article 141 verification).
        </p>

        {/* View Switcher Tabs */}
        <div className="editorial-mode-selector">
          <button
            className={`mode-pill-btn ${activeMode === 'side-by-side' ? 'active' : ''}`}
            onClick={() => setActiveMode('side-by-side')}
          >
            SIDE-BY-SIDE ARCHITECTURAL AUDIT
          </button>
          <button
            className={`mode-pill-btn ${activeMode === 'legacy-only' ? 'active' : ''}`}
            onClick={() => setActiveMode('legacy-only')}
          >
            LEGACY PARADIGM (MANUPATRA)
          </button>
          <button
            className={`mode-pill-btn ${activeMode === 'antigravity-only' ? 'active' : ''}`}
            onClick={() => setActiveMode('antigravity-only')}
          >
            JUSTICE EDITORIAL WORKSPACE
          </button>
        </div>
      </div>

      {/* Comparison Grid */}
      <div className={`editorial-comparison-grid ${activeMode}`}>
        {/* 1. LEGACY MANUPATRA SIMULATION */}
        {(activeMode === 'side-by-side' || activeMode === 'legacy-only') && (
          <div className="comparison-side-card legacy-card">
            <div className="card-top-tag">
              <span className="editorial-meta-label">LEGACY PARADIGM &bull; DEEP CASCADING TAXONOMY</span>
            </div>

            {/* Simulated Legacy Navbar */}
            <div className="legacy-navbar-box">
              <div className="legacy-top-row">
                <div className="legacy-logo">
                  <span className="legacy-logo-text">manupatra</span>
                  <span className="legacy-logo-tm">&reg;</span>
                </div>

                <div className="legacy-nav-menus">
                  {/* Products */}
                  <div className="legacy-menu-item" onClick={() => toggleDropdown('products')}>
                    <span>Products</span>
                    <ChevronDown size={11} />
                    {activeDropdown === 'products' && (
                      <div className="legacy-dropdown-popover">
                        <div className="dropdown-item">Manupatra Core</div>
                        <div className="dropdown-item">Manucomply (Compliance)</div>
                        <div className="dropdown-item">CaseWatch (Cause Lists)</div>
                        <div className="dropdown-item">LawSkills Academy</div>
                      </div>
                    )}
                  </div>

                  {/* Research */}
                  <div className="legacy-menu-item" onClick={() => toggleDropdown('research')}>
                    <span>Research</span>
                    <ChevronDown size={11} />
                    {activeDropdown === 'research' && (
                      <div className="legacy-dropdown-popover">
                        <div className="dropdown-header">Court Categories</div>
                        <div className="dropdown-item">Supreme Court of India</div>
                        <div className="dropdown-item">High Courts (25 Jurisdictions)</div>
                        <div className="dropdown-item">Tribunals & Commissions</div>
                        <div className="dropdown-divider"></div>
                        <div className="dropdown-header">Statutory Corpus</div>
                        <div className="dropdown-item">Central Bare Acts</div>
                        <div className="dropdown-item">State Legislation</div>
                      </div>
                    )}
                  </div>

                  {/* Knowledge */}
                  <div className="legacy-menu-item" onClick={() => toggleDropdown('knowledge')}>
                    <span>Knowledge</span>
                    <ChevronDown size={11} />
                    {activeDropdown === 'knowledge' && (
                      <div className="legacy-dropdown-popover">
                        <div className="dropdown-item">Legal Articles & Commentary</div>
                        <div className="dropdown-item">Judicial Dictionaries</div>
                        <div className="dropdown-item">Case Comments & Law Review</div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="legacy-auth-area">
                  <span className="legacy-user-text">[Advocate Sign Out]</span>
                </div>
              </div>

              {/* Legacy Boolean Search Bar */}
              <div className="legacy-search-row">
                <form onSubmit={handleBooleanSearch} className="legacy-search-form">
                  <input
                    type="text"
                    className="legacy-search-input"
                    value={booleanInput}
                    onChange={(e) => setBooleanInput(e.target.value)}
                    placeholder='Boolean query (e.g., "Section 138" W/5 "Cheque" NOT "Notice")'
                  />
                  <button type="submit" className="legacy-search-btn">SUBMIT</button>
                </form>
              </div>

              {simulatedError && (
                <div className="legacy-error-banner">
                  <span>BOOLEAN PARSE ERROR: 'W/5' proximity operator requires parenthetical nesting. 0 results returned.</span>
                </div>
              )}
            </div>

            {/* Friction Points */}
            <div className="friction-editorial-block">
              <h3 className="friction-heading font-judicial">Core Architectural Friction Points</h3>
              <div className="friction-list">
                <div className="friction-point">
                  <span className="point-number">01</span>
                  <div className="point-text">
                    <strong>Taxonomy Guesswork:</strong> Advocates must guess whether a precedent is categorized under <em>Research</em>, <em>Statutes</em>, or <em>Knowledge</em> before beginning discovery.
                  </div>
                </div>
                <div className="friction-point">
                  <span className="point-number">02</span>
                  <div className="point-text">
                    <strong>Boolean Operator Brittleness:</strong> A single missing boolean modifier produces zero results or returns thousands of irrelevant unranked cases.
                  </div>
                </div>
                <div className="friction-point">
                  <span className="point-number">03</span>
                  <div className="point-text">
                    <strong>Tab Explosion & Fatigue:</strong> Shepardizing cases and cross-referencing statutes forces 8–15 open tabs, fragmenting legal reasoning.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2. JUSTICE EDITORIAL WORKSPACE */}
        {(activeMode === 'side-by-side' || activeMode === 'antigravity-only') && (
          <div className="comparison-side-card modern-card">
            <div className="card-top-tag">
              <span className="editorial-meta-label">JUSTICE WORKSPACE &bull; UNIFIED INTENT CANVAS</span>
            </div>

            {/* Modern Workspace Simulation */}
            <div className="modern-preview-box">
              <div className="modern-omni-bar">
                <div className="omni-snippet">
                  <span className="omni-kicker">OMNI-INTENT [⌘K]:</span>
                  <span className="omni-sample-query">"Is my 2-year post-termination non-compete enforceable in India?"</span>
                </div>
                <div className="omni-badge-stark">AUTO-ROUTED</div>
              </div>

              {/* Split Canvas Mini */}
              <div className="modern-split-mini">
                <div className="mini-sheet left">
                  <div className="mini-sheet-meta">HIGH-CONTRAST DRAFT SHEET</div>
                  <div className="mini-clause-sample">
                    <strong>Clause 9.3:</strong> Consultant shall not compete anywhere in India for 24 months post termination...
                  </div>
                  <div className="mini-redline-callout">
                    ENFORCEABLE REDLINE: Restrict strictly to trade secret non-solicitation.
                  </div>
                </div>

                <div className="mini-sheet right">
                  <div className="mini-sheet-meta">ARTICLE 141 CITATOR</div>
                  <div className="mini-precedent-entry">
                    <div className="mini-prec-name">● Percept D'Mark v. Zaheer Khan (2006)</div>
                    <div className="mini-prec-desc">2-Judge SC Bench &bull; Affirmed &bull; Section 27 Void ab initio</div>
                  </div>
                  <div className="mini-precedent-entry">
                    <div className="mini-prec-name">● Niranjan Shankar Golikari (1967)</div>
                    <div className="mini-prec-desc">2-Judge SC Bench &bull; Valid only during subsistence of employment</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Architectural Innovations */}
            <div className="friction-editorial-block">
              <h3 className="friction-heading font-judicial">Architectural Paradigm Advantages</h3>
              <div className="friction-list">
                <div className="friction-point">
                  <span className="point-number">01</span>
                  <div className="point-text">
                    <strong>Universal Semantic Intent:</strong> Advocates write questions in plain English; InLegalBERT dual-encoders locate the exact ratio without boolean syntax.
                  </div>
                </div>
                <div className="friction-point">
                  <span className="point-number">02</span>
                  <div className="point-text">
                    <strong>Stark Editorial Ergonomics:</strong> Pure high-contrast canvas with accessible typography eliminates eye strain during lengthy multi-page contract audits.
                  </div>
                </div>
                <div className="friction-point">
                  <span className="point-number">03</span>
                  <div className="point-text">
                    <strong>Live Article 141 Shepardizing:</strong> Evaluates bench strength hierarchy and overruling status directly beside the contractual text.
                  </div>
                </div>
              </div>

              <div className="launch-action-bar">
                <button className="btn-primary" onClick={onSwitchToWorkspace}>
                  <span>OPEN DOCUMENT ANALYZER</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Systematic Feature Comparison Matrix */}
      <div className="editorial-matrix-card">
        <div className="matrix-card-header">
          <span className="editorial-meta-label">SYSTEMATIC FEATURE & ARCHITECTURE MATRIX</span>
          <h3 className="matrix-card-title font-judicial">Comparative Architectural Matrix</h3>
        </div>

        <table className="editorial-matrix-table">
          <thead>
            <tr>
              <th>EVALUATION DIMENSION</th>
              <th>LEGACY SYSTEMS (E.G. MANUPATRA)</th>
              <th>JUSTICE EDITORIAL WORKSPACE</th>
              <th>ARCHITECTURAL ADVANTAGE</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>QUERY INTERACTION</strong></td>
              <td>Brittle Boolean operators (`AND`, `OR`, `W/5`, `NEAR`)</td>
              <td>InLegalBERT Dual-Encoder Neural Search + HyDE Ratios</td>
              <td>Natural English queries; zero boolean syntax failures</td>
            </tr>
            <tr>
              <td><strong>NAVIGATION MODEL</strong></td>
              <td>Cascading multi-tier dropdowns (`Products`, `Research`, `Knowledge`)</td>
              <td>Global Omni-Command Palette (`Ctrl+K`) + Adaptive Canvas</td>
              <td>Zero cognitive friction; instant cross-database discovery</td>
            </tr>
            <tr>
              <td><strong>PRECEDENT VERIFICATION</strong></td>
              <td>Static citation links; manual Shepardizing across tabs</td>
              <td>Article 141 Bench-Aware Graph (Neo4j) with status flags</td>
              <td>Instant constitutional validity check without tab switching</td>
            </tr>
            <tr>
              <td><strong>DOCUMENT INTELLIGENCE</strong></td>
              <td>Passive document viewer; manual copy-pasting</td>
              <td>AST parsing, Layman Translation, and Auto-Redlining</td>
              <td>Automated compliance audit against Indian Contract Act</td>
            </tr>
            <tr>
              <td><strong>VISUAL ERGONOMICS</strong></td>
              <td>Cluttered boxes, blue hyperlinks, dense table grids</td>
              <td>Zara-inspired editorial minimalism; generous white space</td>
              <td>Pure high-contrast reading; clear accessible typography</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
