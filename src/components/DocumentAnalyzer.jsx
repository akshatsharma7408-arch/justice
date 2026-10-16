import React, { useState, useEffect } from 'react';
import { 
  FileText, Upload, ArrowRight, RefreshCw, Check, 
  FileDiff, Play, ArrowUpRight, Cpu, ShieldAlert, Sparkles, AlertTriangle
} from 'lucide-react';
import { CONTRACT_PRESETS } from '../data/legalCorpus';
import { verifyClauseWithBackend, auditContractWithBackend } from '../config/gemini';

export default function DocumentAnalyzer({ onTriggerAgentAnalysis }) {
  const [selectedPresetId, setSelectedPresetId] = useState('preset-tech-consultant');
  const [contractsData, setContractsData] = useState(CONTRACT_PRESETS);
  const [selectedClauseId, setSelectedClauseId] = useState('cl-9-3');
  const [diffMode, setDiffMode] = useState(false);
  const [appliedRedlines, setAppliedRedlines] = useState({});
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  
  // Cache of live audits from FastAPI backend: { [clauseId]: auditData }
  const [liveAudits, setLiveAudits] = useState({});
  const [isAuditingClause, setIsAuditingClause] = useState(false);

  const activeContract = contractsData.find(c => c.id === selectedPresetId) || contractsData[0];
  const activeClause = activeContract.clauses.find(cl => cl.id === selectedClauseId) || activeContract.clauses[0];

  // Trigger live backend verification on selected clause
  useEffect(() => {
    if (!activeClause) return;
    const clauseKey = `${selectedPresetId}-${activeClause.id}`;
    if (liveAudits[clauseKey]) return; // already cached

    let isMounted = true;
    setIsAuditingClause(true);

    verifyClauseWithBackend(activeClause.text, activeClause.title)
      .then(res => {
        if (!isMounted) return;
        setLiveAudits(prev => ({
          ...prev,
          [clauseKey]: res
        }));
      })
      .catch(err => {
        console.warn("[DocumentAnalyzer] Backend clause audit failed:", err.message);
      })
      .finally(() => {
        if (isMounted) setIsAuditingClause(false);
      });

    return () => {
      isMounted = false;
    };
  }, [activeClause?.id, selectedPresetId]);

  // Merge live audit data with clause
  const activeAudit = liveAudits[`${selectedPresetId}-${activeClause?.id}`];
  const effectiveRiskLevel = activeAudit?.risk_level || activeClause?.riskLevel || 'LOW';
  const effectiveLayman = activeAudit?.layman_translation || activeClause?.layman || '';
  const effectiveImpact = activeAudit?.practical_impact || (
    effectiveRiskLevel === 'CRITICAL' 
      ? "Under Section 27, this post-termination restraint is void in law. However, retaining it in the signed draft invites vexatious litigation. It should be replaced with an enforceable non-solicitation term."
      : "Standard contractual covenant. Ensure commercial caps and notice periods reflect agreed business terms."
  );
  const effectivePrecedents = activeAudit?.precedents 
    || (activeAudit?.binding_precedent ? [activeAudit.binding_precedent] : activeClause?.precedents) 
    || ["Section 27, Indian Contract Act 1872"];
  const effectiveRedline = activeAudit?.balanced_redline || activeClause?.redline;
  const effectiveLegalDoctrine = activeAudit?.legal_doctrine;
  const effectiveStatutoryIssue = activeAudit?.statutory_issue || activeClause?.statutoryIssue;

  const handleApplyRedline = (clauseId, redlineText) => {
    setAppliedRedlines(prev => ({
      ...prev,
      [clauseId]: redlineText
    }));
  };

  const handleResetRedline = (clauseId) => {
    setAppliedRedlines(prev => {
      const next = { ...prev };
      delete next[clauseId];
      return next;
    });
  };

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name);

      const auditResponse = await auditContractWithBackend(formData, file.name);
      
      // Transform backend ClauseAuditResult into UI schema
      const parsedClauses = auditResponse.clauses.map((c, idx) => ({
        id: `upload-cl-${c.clause_index}`,
        number: `${c.clause_index}`,
        title: c.title,
        text: c.original_text,
        riskLevel: c.is_violation ? 'CRITICAL' : (c.severity === 'MODERATE' ? 'MODERATE' : 'LOW'),
        statutoryIssue: c.statutory_violation,
        legalDoctrine: c.legal_assessment,
        layman: c.layman_translation,
        practicalImpact: c.practical_impact,
        precedents: c.governing_authorities,
        redline: c.balanced_redline
      }));

      const newContract = {
        id: `custom-uploaded-${Date.now()}`,
        title: auditResponse.document_title || file.name,
        clauses: parsedClauses.length > 0 ? parsedClauses : activeContract.clauses
      };

      setContractsData(prev => [newContract, ...prev]);
      setSelectedPresetId(newContract.id);
      setSelectedClauseId(newContract.clauses[0]?.id);
    } catch (err) {
      console.error("[DocumentAnalyzer] Upload parsing error:", err);
      setUploadError("Could not upload to backend. Switched to sample contract.");
      setSelectedPresetId('preset-tech-consultant');
      setSelectedClauseId('cl-9-3');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="workspace-module-pane">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">DOCUMENT ANALYZER</span>
        </div>
        <h1 className="module-heading font-judicial">Document Analyzer</h1>
        <p className="module-description">
          Autonomous contract compliance auditor and clause redliner powered by Gemini 3.8 Flash.
          Evaluates restrictive covenants against Section 27 Indian Contract Act 1872 and generates binding, enforceable redlines.
        </p>

        {/* Agreement Selection & Upload Bar */}
        <div className="analyzer-controls-bar">
          <div className="preset-selector-group">
            <span className="preset-selector-label">SAMPLE AGREEMENT:</span>
            <div className="preset-buttons-row">
              {contractsData.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`preset-tab-btn ${c.id === selectedPresetId ? 'active' : ''}`}
                  onClick={() => {
                    setSelectedPresetId(c.id);
                    setSelectedClauseId(c.clauses[0]?.id || 'cl-9-3');
                  }}
                >
                  <span>{c.title}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="analyzer-upload-btn-wrap">
            <label className="btn-secondary upload-action-label">
              <Upload size={14} />
              <span>{isUploading ? 'PARSING WITH FASTAPI...' : 'Upload Agreement'}</span>
              <input type="file" onChange={handleUploadFile} style={{ display: 'none' }} accept=".pdf,.docx,.txt" />
            </label>
          </div>
        </div>

        {uploadError && (
          <div className="analyzer-error-alert">
            <AlertTriangle size={14} />
            <span>{uploadError}</span>
          </div>
        )}
      </div>

      {/* Main Split-Pane Workspace */}
      <div className="workspace-split-panes">
        {/* LEFT PANE: Document Reading Canvas */}
        <div className="split-pane-left">
          <div className="pane-title-bar">
            <div>
              <span className="pane-kicker">PRIMARY DRAFT TEXT</span>
              <h2 className="pane-heading font-judicial">{activeContract.title}</h2>
            </div>
            <button
              type="button"
              className={`btn-diff-toggle ${diffMode ? 'active' : ''}`}
              onClick={() => setDiffMode(!diffMode)}
            >
              <FileDiff size={14} />
              <span>{diffMode ? 'Exit Diff View' : 'Show Redline Diffs'}</span>
            </button>
          </div>

          {/* Document Content Sheet */}
          <div className="document-sheet-surface">
            <div className="document-preamble-box">
              <div className="preamble-badge mono">CONFIDENTIAL DRAFT &bull; JURISDICTION: INDIA</div>
              <h3 className="preamble-title font-judicial">CONSULTANCY & RESTRICTIVE COVENANTS AGREEMENT</h3>
              <p className="preamble-desc">
                This Agreement is executed in the Republic of India. The parties agree to the terms, restrictive covenants, and statutory undertakings set forth below:
              </p>
            </div>

            {/* Clauses Stream */}
            <div className="clauses-cards-stream">
              {activeContract.clauses.map((clause) => {
                const isSelected = clause.id === selectedClauseId;
                const isRedlined = !!appliedRedlines[clause.id];
                const cachedAudit = liveAudits[`${selectedPresetId}-${clause.id}`];
                const risk = cachedAudit?.risk_level || clause.riskLevel;

                return (
                  <article
                    key={clause.id}
                    className={`clause-review-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedClauseId(clause.id)}
                  >
                    <div className="clause-header-row">
                      <div className="clause-title-wrap">
                        <span className="clause-badge mono">CLAUSE {clause.number}</span>
                        <h4 className="clause-name font-judicial">{clause.title}</h4>
                      </div>

                      <div className={`status-pill status-${risk.toLowerCase()}`}>
                        <span className="status-dot-indicator" />
                        <span className="status-pill-text">
                          {risk === 'CRITICAL' && 'CRITICAL RISK'}
                          {risk === 'MODERATE' && 'MODERATE RISK'}
                          {risk === 'LOW' && 'COMPLIANT'}
                        </span>
                      </div>
                    </div>

                    {/* Clause Body Text */}
                    <div className="clause-text-area">
                      {diffMode && (cachedAudit?.balanced_redline || clause.redline) ? (
                        <div className="clause-diff-view">
                          <div className="diff-row-strike">
                            <span className="diff-sign">-</span>
                            <span>{clause.text}</span>
                          </div>
                          <div className="diff-row-add">
                            <span className="diff-sign">+</span>
                            <span>{cachedAudit?.balanced_redline || clause.redline}</span>
                          </div>
                        </div>
                      ) : isRedlined ? (
                        <div className="clause-applied-box">
                          <div className="applied-badge mono">
                            <Check size={12} />
                            <span>ENFORCEABLE REDLINE APPLIED (SECTION 27 COMPLIANT)</span>
                          </div>
                          <p className="applied-text font-judicial">{appliedRedlines[clause.id]}</p>
                        </div>
                      ) : (
                        <p className="clause-original-text font-judicial">{clause.text}</p>
                      )}
                    </div>

                    <div className="clause-footer-strip">
                      <span className="clause-inspect-hint">
                        {isSelected ? '● CURRENTLY AUDITED IN CO-PILOT' : 'CLICK TO AUDIT →'}
                      </span>
                      {(cachedAudit?.statutory_issue || clause.statutoryIssue) && (
                        <span className="statutory-preview-chip mono">
                          {(cachedAudit?.statutory_issue || clause.statutoryIssue).split('(')[0]}
                        </span>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </div>

        {/* RIGHT PANE: Legal Co-Pilot & Clause Auditor */}
        <div className="split-pane-right">
          <div className="pane-title-bar copilot-bar">
            <div>
              <span className="pane-kicker">INTELLIGENCE SUITE &bull; GEMINI 3.8 FLASH</span>
              <h2 className="pane-heading font-judicial">Clause Auditor & Redliner</h2>
            </div>
            <button
              type="button"
              className="btn-primary btn-run-agent"
              onClick={() => onTriggerAgentAnalysis({
                ...activeClause,
                riskLevel: effectiveRiskLevel,
                statutoryIssue: effectiveStatutoryIssue,
                layman: effectiveLayman,
                redline: effectiveRedline
              }, activeContract.title)}
              title="Launch autonomous LangGraph execution"
            >
              <Play size={13} />
              <span>RUN TRACE</span>
            </button>
          </div>

          <div className="copilot-scroll-container">
            {/* SKELETON LOADING STATE FOR AUDIT */}
            {isAuditingClause ? (
              <div className="skeleton-cards-stack">
                <div className="skeleton-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div className="skeleton-badge skeleton-shimmer" />
                    <div className="skeleton-line skeleton-shimmer" style={{ width: '60px' }} />
                  </div>
                  <div className="skeleton-title skeleton-shimmer" />
                  <div className="skeleton-block skeleton-shimmer" />
                </div>
                <div className="skeleton-card">
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '40%' }} />
                  <div className="skeleton-block skeleton-shimmer" />
                </div>
              </div>
            ) : (
              <>
                {/* Active Clause Overview Card */}
                <div className="copilot-card">
                  <div className="copilot-card-top">
                    <span className="copilot-kicker mono">
                      CLAUSE {activeClause?.number} AUDIT
                    </span>
                    <span className={`status-pill status-${effectiveRiskLevel.toLowerCase()}`}>
                      <span className="status-dot-indicator" />
                      <span className="status-pill-text">{effectiveRiskLevel} RISK</span>
                    </span>
                  </div>

                  <h3 className="copilot-clause-title font-judicial">{activeClause?.title}</h3>

                  {effectiveStatutoryIssue ? (
                    <div className="alert-box alert-warning">
                      <div className="alert-title-line">
                        <ShieldAlert size={14} />
                        <span>STATUTORY NON-COMPLIANCE DETECTED (SECTION 27 ICA)</span>
                      </div>
                      <p className="alert-content">{effectiveStatutoryIssue}</p>
                    </div>
                  ) : (
                    <div className="alert-box alert-safe">
                      <div className="alert-title-line">
                        <Check size={14} />
                        <span>STATUTORY ASSESSMENT COMPLIANT</span>
                      </div>
                      <p className="alert-content">Complies with prevailing Indian contractual provisions and judicial standards.</p>
                    </div>
                  )}

                  {effectiveLegalDoctrine && (
                    <div className="doctrine-callout">
                      <span className="doctrine-label">LEGAL DOCTRINE:</span>{' '}
                      <span className="doctrine-text">{effectiveLegalDoctrine}</span>
                    </div>
                  )}
                </div>

                {/* Layman Translation Card */}
                <div className="copilot-card">
                  <div className="copilot-card-top">
                    <span className="copilot-kicker mono">LAYMAN TRANSLATION &bull; GRADE 8</span>
                  </div>
                  <div className="layman-quote font-judicial">
                    "{effectiveLayman}"
                  </div>
                  <div className="layman-impact-box">
                    <span className="impact-label">PRACTICAL SIGNIFICANCE:</span>{' '}
                    <span className="impact-text">{effectiveImpact}</span>
                  </div>
                </div>

                {/* Cross-Referenced Authorities Card */}
                {effectivePrecedents && effectivePrecedents.length > 0 && (
                  <div className="copilot-card">
                    <div className="copilot-card-top">
                      <span className="copilot-kicker mono">BINDING AUTHORITIES (ARTICLE 141)</span>
                    </div>
                    <div className="authorities-list">
                      {effectivePrecedents.map((p, idx) => (
                        <div key={idx} className="authority-row">
                          <span className="authority-bullet">&bull;</span>
                          <span className="authority-name">{p}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Enforceable Redline Card */}
                {effectiveRedline && (
                  <div className="copilot-card redline-card">
                    <div className="copilot-card-top">
                      <span className="copilot-kicker mono">RECOMMENDED ENFORCEABLE REDLINE</span>
                    </div>
                    <div className="redline-proposal-box font-judicial">
                      "{effectiveRedline}"
                    </div>

                    <div className="redline-btn-row">
                      {appliedRedlines[activeClause?.id] ? (
                        <button
                          type="button"
                          className="btn-secondary btn-revert"
                          onClick={() => handleResetRedline(activeClause?.id)}
                        >
                          <RefreshCw size={13} />
                          <span>Revert Original</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn-primary btn-apply"
                          onClick={() => handleApplyRedline(activeClause?.id, effectiveRedline)}
                        >
                          <Check size={13} />
                          <span>Apply Enforceable Redline</span>
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
