import React, { useState } from 'react';
import { ChevronDown, ArrowRight, CheckCircle2, XCircle } from 'lucide-react';

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
    <div className="workspace-module-pane">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">ARCHITECTURAL COMPARISON</span>
        </div>
        <h1 className="module-heading font-judicial">System Comparison & Critique</h1>
        <p className="module-description">
          An architectural critique comparing legacy legal database paradigms (cascading taxonomies, brittle Boolean queries, multi-tab cognitive fatigue) 
          with the JUSTICE Legal Research Workspace (unified natural language intent, automated Article 141 verification, and embedded redlining).
        </p>

        {/* View Switcher Tabs */}
        <div className="comparison-mode-tabs">
          <button
            type="button"
            className={`mode-tab-btn ${activeMode === 'side-by-side' ? 'active' : ''}`}
            onClick={() => setActiveMode('side-by-side')}
          >
            SIDE-BY-SIDE ARCHITECTURAL AUDIT
          </button>
          <button
            type="button"
            className={`mode-tab-btn ${activeMode === 'legacy-only' ? 'active' : ''}`}
            onClick={() => setActiveMode('legacy-only')}
          >
            LEGACY PARADIGM (MANUPATRA)
          </button>
          <button
            type="button"
            className={`mode-tab-btn ${activeMode === 'antigravity-only' ? 'active' : ''}`}
            onClick={() => setActiveMode('antigravity-only')}
          >
            JUSTICE WORKSPACE
          </button>
        </div>
      </div>

      {/* Comparison Grid */}
      <div className={`comparison-cards-grid ${activeMode}`}>
        {/* 1. LEGACY MANUPATRA SIMULATION */}
        {(activeMode === 'side-by-side' || activeMode === 'legacy-only') && (
          <div className="comparison-side-card legacy-surface">
            <div className="card-kicker-strip">
              <span className="card-kicker-text">LEGACY PARADIGM &bull; CASCADING TAXONOMY</span>
            </div>

            {/* Simulated Legacy Navbar */}
            <div className="legacy-mock-header">
              <div className="legacy-brand-row">
                <div className="legacy-logo">
                  <span className="legacy-logo-text">manupatra</span>
                  <span className="legacy-logo-tm">&reg;</span>
                </div>

                <div className="legacy-nav-items">
                  {/* Products */}
                  <div className="legacy-menu-trigger" onClick={() => toggleDropdown('products')}>
                    <span>Products</span>
                    <ChevronDown size={11} />
                    {activeDropdown === 'products' && (
                      <div className="legacy-dropdown-menu">
                        <div className="dropdown-row">Manupatra Core</div>
                        <div className="dropdown-row">Manucomply (Compliance)</div>
                        <div className="dropdown-row">CaseWatch (Cause Lists)</div>
                        <div className="dropdown-row">LawSkills Academy</div>
                      </div>
                    )}
                  </div>

                  {/* Research */}
                  <div className="legacy-menu-trigger" onClick={() => toggleDropdown('research')}>
                    <span>Research</span>
                    <ChevronDown size={11} />
                    {activeDropdown === 'research' && (
                      <div className="legacy-dropdown-menu">
                        <div className="dropdown-sec-header">Court Categories</div>
                        <div className="dropdown-row">Supreme Court of India</div>
                        <div className="dropdown-row">High Courts (25 Jurisdictions)</div>
                        <div className="dropdown-row">Tribunals & Commissions</div>
                        <div className="dropdown-divider-line" />
                        <div className="dropdown-sec-header">Statutory Corpus</div>
                        <div className="dropdown-row">Central Bare Acts</div>
                        <div className="dropdown-row">State Legislation</div>
                      </div>
                    )}
                  </div>

                  {/* Knowledge */}
                  <div className="legacy-menu-trigger" onClick={() => toggleDropdown('knowledge')}>
                    <span>Knowledge</span>
                    <ChevronDown size={11} />
                    {activeDropdown === 'knowledge' && (
                      <div className="legacy-dropdown-menu">
                        <div className="dropdown-row">Legal Articles & Commentary</div>
                        <div className="dropdown-row">Judicial Dictionaries</div>
                        <div className="dropdown-row">Case Comments & Law Review</div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="legacy-user-badge">
                  <span>[Advocate Sign Out]</span>
                </div>
              </div>

              {/* Legacy Boolean Search Bar */}
              <div className="legacy-search-box">
                <form onSubmit={handleBooleanSearch} className="legacy-form">
                  <input
                    type="text"
                    className="legacy-text-input mono"
                    value={booleanInput}
                    onChange={(e) => setBooleanInput(e.target.value)}
                    placeholder='Boolean query (e.g., "Section 138" W/5 "Cheque" NOT "Notice")'
                  />
                  <button type="submit" className="legacy-submit-btn">SUBMIT</button>
                </form>
              </div>

              {simulatedError && (
                <div className="legacy-error-alert">
                  <span>BOOLEAN PARSE ERROR: 'W/5' proximity operator requires parenthetical nesting. 0 results returned.</span>
                </div>
              )}
            </div>

            {/* Friction Points */}
            <div className="friction-points-section">
              <h3 className="friction-title font-judicial">Core Architectural Friction Points</h3>
              <div className="friction-list">
                <div className="friction-item">
                  <div className="friction-icon-num">01</div>
                  <div className="friction-desc">
                    <strong>Taxonomy Guesswork:</strong> Advocates must pre-determine whether an authority is filed under <em>Research</em>, <em>Statutes</em>, or <em>Knowledge</em> before initiating discovery.
                  </div>
                </div>
                <div className="friction-item">
                  <div className="friction-icon-num">02</div>
                  <div className="friction-desc">
                    <strong>Boolean Operator Brittleness:</strong> A single missing proximity operator or quotes returns 0 results or floods the user with thousands of unranked cases.
                  </div>
                </div>
                <div className="friction-item">
                  <div className="friction-icon-num">03</div>
                  <div className="friction-desc">
                    <strong>Tab Explosion & Fatigue:</strong> Shepardizing cases and cross-referencing statutes forces 8–15 open tabs, fragmenting legal concentration and workflow.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2. JUSTICE WORKSPACE SIMULATION */}
        {(activeMode === 'side-by-side' || activeMode === 'antigravity-only') && (
          <div className="comparison-side-card modern-surface">
            <div className="card-kicker-strip modern-strip">
              <span className="card-kicker-text">JUSTICE WORKSPACE &bull; UNIFIED INTENT CANVAS</span>
            </div>

            {/* Modern Workspace Simulation */}
            <div className="modern-mock-box">
              <div className="modern-omni-header">
                <div className="omni-query-preview">
                  <span className="omni-pill mono">INTENT:</span>
                  <span className="omni-query-text">"Is my 2-year post-termination non-compete enforceable in India?"</span>
                </div>
                <span className="omni-routed-badge">AUTO-ROUTED</span>
              </div>

              {/* Split Canvas Mini */}
              <div className="modern-mini-canvas">
                <div className="mini-card mini-left">
                  <div className="mini-card-kicker">DRAFT AUDIT CANVAS</div>
                  <div className="mini-clause-text font-judicial">
                    <strong>Clause 9.3:</strong> Consultant shall not compete anywhere in India for 24 months post termination...
                  </div>
                  <div className="mini-redline-pill">
                    <strong>Enforceable Redline:</strong> Restrict strictly to trade secret non-solicitation.
                  </div>
                </div>

                <div className="mini-card mini-right">
                  <div className="mini-card-kicker">ARTICLE 141 CITATOR</div>
                  <div className="mini-case-item">
                    <div className="mini-case-name font-judicial">● Percept D'Mark v. Zaheer Khan (2006)</div>
                    <div className="mini-case-meta">2-Judge SC Bench &bull; Affirmed &bull; Section 27 Void ab initio</div>
                  </div>
                  <div className="mini-case-item">
                    <div className="mini-case-name font-judicial">● Niranjan Shankar Golikari (1967)</div>
                    <div className="mini-case-meta">2-Judge SC Bench &bull; Valid only during subsistence of employment</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Architectural Innovations */}
            <div className="friction-points-section">
              <h3 className="friction-title font-judicial">Architectural Paradigm Advantages</h3>
              <div className="friction-list">
                <div className="friction-item modern-item">
                  <div className="friction-icon-num modern-num">01</div>
                  <div className="friction-desc">
                    <strong>Universal Semantic Intent:</strong> Advocates ask questions in plain English; InLegalBERT dual-encoders retrieve the exact ratio without boolean syntax.
                  </div>
                </div>
                <div className="friction-item modern-item">
                  <div className="friction-icon-num modern-num">02</div>
                  <div className="friction-desc">
                    <strong>Ergonomic Workspace Layout:</strong> Warm paper background (#FAF8F4) and Fraunces typography eliminate glare during multi-hour contract review.
                  </div>
                </div>
                <div className="friction-item modern-item">
                  <div className="friction-icon-num modern-num">03</div>
                  <div className="friction-desc">
                    <strong>Live Article 141 Shepardizing:</strong> Evaluates bench strength hierarchy and overruling status directly beside the draft text.
                  </div>
                </div>
              </div>

              <div className="comparison-cta-box">
                <button type="button" className="btn-primary" onClick={onSwitchToWorkspace}>
                  <span>OPEN DOCUMENT ANALYZER</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Systematic Feature Comparison Matrix */}
      <div className="workspace-matrix-card">
        <div className="matrix-header-wrap">
          <span className="matrix-kicker mono">EVALUATION BENCHMARK</span>
          <h3 className="matrix-title font-judicial">Comparative Architectural Matrix</h3>
        </div>

        <div className="table-responsive-wrapper">
          <table className="comparison-matrix-table">
            <thead>
              <tr>
                <th>EVALUATION DIMENSION</th>
                <th>LEGACY SYSTEMS (E.G. MANUPATRA)</th>
                <th>JUSTICE WORKSPACE</th>
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
                <td>Global Omni-Command Palette (`Ctrl+K`) + Workspace Sidebar</td>
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
                <td>Warm paper palette, white surfaces, Fraunces serif</td>
                <td>Reduced eye strain during lengthy judicial drafting</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
