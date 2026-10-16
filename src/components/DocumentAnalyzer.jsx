import React, { useState, useEffect } from 'react';
import { 
  FileText, Upload, ArrowRight, RefreshCw, Check, 
  FileDiff, Play, ArrowUpRight, Cpu, ShieldAlert, Sparkles
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
    <div className="module-container">
      {/* Editorial Header Section */}
      <div className="editorial-hero-section">
        <div className="editorial-meta-label">COLLECTION 02 / CONTRACT AUDIT & REDLINE</div>
        <h1 className="hero-editorial-title">Document Analyzer</h1>
        <p className="hero-editorial-subtitle">
          Statutory compliance engine and autonomous clause redliner connected end-to-end to Gemini 3.8 Flash. 
          Audits agreements under Section 27 Indian Contract Act 1872, highlights void covenants, and provides balanced redlines.
        </p>

        {/* Contract Selection & Upload Bar */}
        <div className="editorial-selector-bar">
          <div className="selector-group">
            <span className="selector-label">SAMPLE AGREEMENT:</span>
            <div className="selector-tabs">
              {contractsData.map((c) => (
                <button
                  key={c.id}
                  className={`selector-tab-btn ${c.id === selectedPresetId ? 'active' : ''}`}
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

          <div className="upload-wrapper">
            <label className="btn-secondary upload-label-btn">
              <Upload size={14} />
              <span>{isUploading ? 'PARSING WITH FASTAPI...' : 'UPLOAD CONTRACT'}</span>
              <input type="file" onChange={handleUploadFile} style={{ display: 'none' }} accept=".pdf,.docx,.txt" />
            </label>
          </div>
        </div>

        {uploadError && (
          <div style={{ color: '#d32f2f', fontSize: '12px', marginTop: '6px' }}>
            {uploadError}
          </div>
        )}
      </div>

      {/* Main Split-Pane Workspace: Architectural High-Contrast Canvas */}
      <div className="editorial-split-workspace">
        {/* LEFT PANE: Document Reading Canvas */}
        <div className="editorial-document-column">
          <div className="column-top-header">
            <div>
              <span className="editorial-meta-label">PRIMARY DRAFT TEXT &bull; FASTAPI AUDITED</span>
              <h2 className="column-document-title">{activeContract.title}</h2>
            </div>
            <button
              className={`btn-diff-mode ${diffMode ? 'active' : ''}`}
              onClick={() => setDiffMode(!diffMode)}
            >
              <FileDiff size={14} />
              <span>{diffMode ? 'EXIT DIFF VIEW' : 'SHOW REDLINE DIFFS'}</span>
            </button>
          </div>

          {/* Document Content Sheet */}
          <div className="editorial-document-sheet">
            <div className="document-preamble">
              <div className="preamble-stamp">CONFIDENTIAL DRAFT &bull; JURISDICTION: INDIA</div>
              <h3 className="preamble-heading">CONSULTANCY & RESTRICTIVE COVENANTS AGREEMENT</h3>
              <p className="preamble-text">
                This Agreement is executed in the Republic of India. The parties agree to the terms, restrictive covenants, and statutory undertakings set forth below:
              </p>
            </div>

            {/* Clauses Stream */}
            <div className="editorial-clauses-stream">
              {activeContract.clauses.map((clause) => {
                const isSelected = clause.id === selectedClauseId;
                const isRedlined = !!appliedRedlines[clause.id];
                const cachedAudit = liveAudits[`${selectedPresetId}-${clause.id}`];
                const risk = cachedAudit?.risk_level || clause.riskLevel;

                return (
                  <article
                    key={clause.id}
                    className={`editorial-clause-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedClauseId(clause.id)}
                  >
                    <div className="clause-card-header">
                      <div className="clause-identity">
                        <span className="clause-ordinal">CLAUSE {clause.number}</span>
                        <h4 className="clause-title-text">{clause.title}</h4>
                      </div>

                      <div className={`clause-status-annotation status-${risk.toLowerCase()}`}>
                        <span>
                          {risk === 'CRITICAL' && '✕ CRITICAL'}
                          {risk === 'MODERATE' && '▲ MODERATE'}
                          {risk === 'LOW' && '● COMPLIANT'}
                        </span>
                      </div>
                    </div>

                    {/* Clause Body Text */}
                    <div className="clause-prose-body">
                      {diffMode && (cachedAudit?.balanced_redline || clause.redline) ? (
                        <div className="editorial-diff-container">
                          <div className="diff-strike-row">
                            <span className="diff-indicator">-</span>
                            <span>{clause.text}</span>
                          </div>
                          <div className="diff-add-row">
                            <span className="diff-indicator">+</span>
                            <span>{cachedAudit?.balanced_redline || clause.redline}</span>
                          </div>
                        </div>
                      ) : isRedlined ? (
                        <div className="clause-redline-applied-view">
                          <div className="redline-status-caption">ENFORCEABLE REDLINE APPLIED (SECTION 27 COMPLIANT):</div>
                          <p className="redline-applied-body">{appliedRedlines[clause.id]}</p>
                        </div>
                      ) : (
                        <p className="clause-original-body">{clause.text}</p>
                      )}
                    </div>

                    <div className="clause-card-footer-strip">
                      <span className="inspect-state-text">
                        {isSelected ? '● CURRENTLY INSPECTED IN CO-PILOT' : 'CLICK TO AUDIT →'}
                      </span>
                      {(cachedAudit?.statutory_issue || clause.statutoryIssue) && (
                        <span className="statutory-preview-tag mono">
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

        {/* RIGHT PANE: Legal Co-Pilot & Editorial Auditor */}
        <div className="editorial-copilot-column">
          <div className="column-top-header copilot-header-bar">
            <div>
              <span className="editorial-meta-label">INTELLIGENCE SUITE &bull; GEMINI 3.8 FLASH</span>
              <h2 className="column-document-title">Clause Auditor & Redliner</h2>
            </div>
            <button
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
              <Play size={12} />
              <span>RUN TRACE</span>
            </button>
          </div>

          <div className="copilot-scroll-body">
            {/* Clause Overview */}
            <div className="copilot-editorial-card">
              <div className="copilot-card-meta">
                <span className="editorial-meta-label">
                  CLAUSE {activeClause?.number} AUDIT {isAuditingClause && ' (AUDITING...)'}
                </span>
                <span className={`clause-status-annotation status-${effectiveRiskLevel.toLowerCase()}`}>
                  {effectiveRiskLevel} RISK
                </span>
              </div>
              <h3 className="copilot-active-title">{activeClause?.title}</h3>

              {effectiveStatutoryIssue ? (
                <div className="editorial-alert-block warning">
                  <div className="alert-caption">STATUTORY NON-COMPLIANCE DETECTED (SECTION 27 ICA)</div>
                  <p className="alert-desc">{effectiveStatutoryIssue}</p>
                </div>
              ) : (
                <div className="editorial-alert-block safe">
                  <div className="alert-caption">STATUTORY ASSESSMENT</div>
                  <p className="alert-desc">Complies with prevailing Indian contractual provisions and judicial standards.</p>
                </div>
              )}

              {/* Binding Legal Doctrine */}
              {effectiveLegalDoctrine && (
                <div style={{ marginTop: '12px', fontSize: '13px', lineHeight: '1.5', color: '#222' }}>
                  <strong>LEGAL DOCTRINE:</strong> {effectiveLegalDoctrine}
                </div>
              )}
            </div>

            {/* LAYMAN TRANSLATION */}
            <div className="copilot-editorial-card">
              <div className="copilot-card-meta">
                <span className="editorial-meta-label">LAYMAN TRANSLATION &bull; GRADE 8</span>
              </div>
              <div className="layman-editorial-prose">
                "{effectiveLayman}"
              </div>
              <div className="layman-practical-impact">
                <strong>PRACTICAL SIGNIFICANCE:</strong> {effectiveImpact}
              </div>
            </div>

            {/* CROSS-REFERENCED AUTHORITIES */}
            {effectivePrecedents && effectivePrecedents.length > 0 && (
              <div className="copilot-editorial-card">
                <div className="copilot-card-meta">
                  <span className="editorial-meta-label">BINDING AUTHORITIES (ARTICLE 141)</span>
                </div>
                <div className="precedent-lineage-list">
                  {effectivePrecedents.map((p, idx) => (
                    <div key={idx} className="precedent-lineage-item">
                      <span className="precedent-bullet">&bull;</span>
                      <span className="precedent-text">{p}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ENFORCEABLE REDLINE */}
            {effectiveRedline && (
              <div className="copilot-editorial-card redline-section">
                <div className="copilot-card-meta">
                  <span className="editorial-meta-label">RECOMMENDED ENFORCEABLE REDLINE</span>
                </div>
                <div className="redline-proposal-box">
                  "{effectiveRedline}"
                </div>

                <div className="redline-action-row">
                  {appliedRedlines[activeClause?.id] ? (
                    <button
                      className="btn-secondary"
                      onClick={() => handleResetRedline(activeClause?.id)}
                    >
                      <RefreshCw size={12} />
                      <span>REVERT ORIGINAL</span>
                    </button>
                  ) : (
                    <button
                      className="btn-primary"
                      onClick={() => handleApplyRedline(activeClause?.id, effectiveRedline)}
                    >
                      <Check size={12} />
                      <span>APPLY ENFORCEABLE REDLINE</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
