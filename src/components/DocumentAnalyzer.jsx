import React, { useState, useEffect, useRef } from 'react';
import { 
  FileText, Upload, ArrowRight, RefreshCw, Check, 
  FileDiff, Play, ArrowUpRight, Cpu, ShieldAlert, Sparkles, AlertTriangle,
  MessageSquare, Send, Quote, ChevronDown, ChevronUp, HelpCircle, Columns, Maximize2,
  AlertCircle, X
} from 'lucide-react';
import { CONTRACT_PRESETS } from '../data/legalCorpus';
import { 
  verifyClauseWithBackend, 
  auditContractWithBackend,
  uploadDocumentForChatWithBackend,
  chatWithDocumentWithBackend 
} from '../config/gemini';

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

  // Document Chat State
  const [rightViewMode, setRightViewMode] = useState('both'); // 'both' | 'audit' | 'chat'
  const [contractDocIds, setContractDocIds] = useState({});
  const [docChatMessages, setDocChatMessages] = useState([
    {
      id: 'welcome-msg',
      sender: 'assistant',
      text: "Ask any question about this agreement. Every claim will quote the exact clause it originates from. If a topic is not covered in the document, I will strictly answer 'not found in this document' without outside speculation.",
      citations: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [docChatInput, setDocChatInput] = useState('');
  const [isDocChatLoading, setIsDocChatLoading] = useState(false);
  const [docChatError, setDocChatError] = useState(null);
  const [expandedCitations, setExpandedCitations] = useState({});
  const chatMessagesEndRef = useRef(null);

  const activeContract = contractsData.find(c => c.id === selectedPresetId) || contractsData[0];
  const activeClause = activeContract.clauses.find(cl => cl.id === selectedClauseId) || activeContract.clauses[0];

  // Auto-scroll chat to bottom
  const scrollToBottom = () => {
    chatMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [docChatMessages, isDocChatLoading]);

  // Index active contract into docchat backend if not yet indexed
  useEffect(() => {
    if (!activeContract) return;
    if (contractDocIds[activeContract.id]) return;

    let isMounted = true;
    const fullText = activeContract.clauses
      .map(c => `${c.title}:\n${c.text}`)
      .join('\n\n');

    uploadDocumentForChatWithBackend(fullText, activeContract.title)
      .then(res => {
        if (!isMounted) return;
        if (res && res.doc_id) {
          setContractDocIds(prev => ({
            ...prev,
            [activeContract.id]: res.doc_id
          }));
        }
      })
      .catch(err => {
        console.warn("[DocumentAnalyzer] Auto-indexing for doc chat note:", err.message);
      });

    return () => {
      isMounted = false;
    };
  }, [activeContract?.id]);

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

  const toggleCitation = (key) => {
    setExpandedCitations(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
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

      // Perform both clause auditing and document vector indexing
      const [auditResponse, chatUploadRes] = await Promise.all([
        auditContractWithBackend(formData, file.name),
        uploadDocumentForChatWithBackend(formData, file.name).catch(err => {
          console.warn("[DocumentAnalyzer] Docchat upload warning:", err.message);
          return null;
        })
      ]);
      
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

      const newContractId = `custom-uploaded-${Date.now()}`;
      const newContract = {
        id: newContractId,
        title: auditResponse.document_title || file.name,
        clauses: parsedClauses.length > 0 ? parsedClauses : activeContract.clauses
      };

      setContractsData(prev => [newContract, ...prev]);
      setSelectedPresetId(newContract.id);
      setSelectedClauseId(newContract.clauses[0]?.id);

      if (chatUploadRes && chatUploadRes.doc_id) {
        setContractDocIds(prev => ({
          ...prev,
          [newContractId]: chatUploadRes.doc_id
        }));
      }

      // Add a system welcome message for the new document
      setDocChatMessages(prev => [
        ...prev,
        {
          id: `upload-notice-${Date.now()}`,
          sender: 'assistant',
          text: `Indexed "${file.name}" with ${parsedClauses.length} clause-aware chunks. Ask any question to inspect its terms.`,
          citations: [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err) {
      console.error("[DocumentAnalyzer] Upload parsing error:", err);
      setUploadError("Could not upload to backend. Switched to sample contract.");
      setSelectedPresetId('preset-tech-consultant');
      setSelectedClauseId('cl-9-3');
    } finally {
      setIsUploading(false);
    }
  };

  // Chat message submission
  const handleSendQuestion = async (queryText) => {
    const question = (queryText || docChatInput).trim();
    if (!question || isDocChatLoading) return;

    setDocChatInput('');
    setDocChatError(null);

    const userMsgId = `user-${Date.now()}`;
    const userMsg = {
      id: userMsgId,
      sender: 'user',
      text: question,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setDocChatMessages(prev => [...prev, userMsg]);
    setIsDocChatLoading(true);

    try {
      let docId = contractDocIds[activeContract.id];

      // If document was not yet indexed, upload its text now
      if (!docId) {
        const fullText = activeContract.clauses
          .map(c => `${c.title}:\n${c.text}`)
          .join('\n\n');
        const uploadRes = await uploadDocumentForChatWithBackend(fullText, activeContract.title);
        docId = uploadRes.doc_id;
        setContractDocIds(prev => ({ ...prev, [activeContract.id]: docId }));
      }

      const res = await chatWithDocumentWithBackend(docId, question);

      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: res.answer,
        citations: res.citations || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setDocChatMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      console.error("[DocumentAnalyzer] Chat with document failed:", err);
      // Offline fallback: check contract text directly
      const qLower = question.toLowerCase();
      let fallbackClause = null;

      if (qLower.includes('notice') || qLower.includes('terminate')) {
        fallbackClause = activeContract.clauses.find(c => 
          c.text.toLowerCase().includes('notice') || c.text.toLowerCase().includes('terminate')
        );
      } else if (qLower.includes('compete') || qLower.includes('restraint')) {
        fallbackClause = activeContract.clauses.find(c => 
          c.text.toLowerCase().includes('compete') || c.text.toLowerCase().includes('restraint')
        );
      } else if (qLower.includes('ip') || qLower.includes('invention') || qLower.includes('moral')) {
        fallbackClause = activeContract.clauses.find(c => 
          c.text.toLowerCase().includes('assign') || c.text.toLowerCase().includes('moral')
        );
      }

      if (fallbackClause) {
        const quote = fallbackClause.text;
        setDocChatMessages(prev => [
          ...prev,
          {
            id: `assistant-fallback-${Date.now()}`,
            sender: 'assistant',
            text: `Under ${fallbackClause.title}, the document stipulates: "${quote}"`,
            citations: [
              {
                clause_number: `Clause ${fallbackClause.number}`,
                heading: fallbackClause.title,
                quoted_text: quote
              }
            ],
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
      } else {
        setDocChatMessages(prev => [
          ...prev,
          {
            id: `assistant-fallback-${Date.now()}`,
            sender: 'assistant',
            text: "not found in this document",
            citations: [],
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
      }
    } finally {
      setIsDocChatLoading(false);
    }
  };

  const quickQuestions = [
    "What is my notice period?",
    "What are the post-termination non-compete restrictions?",
    "How are intellectual property and inventions assigned?",
    "What is the pet policy on bringing dogs to the office?"
  ];

  return (
    <div className="workspace-module-pane">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">DOCUMENT ANALYZER</span>
        </div>
        <h1 className="module-heading font-judicial">Document Analyzer & Free-Form Chat</h1>
        <p className="module-description">
          Autonomous contract compliance auditor and free-form grounded question-answering co-pilot.
          Audits clauses against Section 27 Indian Contract Act 1872 and answers queries quoting exact contract provisions.
        </p>

        {/* Agreement Selection & Upload Bar */}
        <div className="analyzer-controls-bar">
          <div className="preset-selector-group">
            <span className="preset-selector-label">ACTIVE AGREEMENT:</span>
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
            <label className="btn-secondary upload-action-label" id="upload-contract-btn">
              <Upload size={14} />
              <span>{isUploading ? 'PARSING WITH FASTAPI...' : 'Upload Agreement (PDF / DOCX)'}</span>
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
      <div className={`workspace-split-panes ${rightViewMode === 'both' ? 'view-mode-both' : ''}`}>
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

        {/* RIGHT PANES: Intelligence Suite with Tabs / Side-by-Side Panels */}
        <div className="split-pane-right-container">
          {/* View Mode Switcher Header */}
          <div className="pane-title-bar copilot-bar">
            <div className="copilot-bar-left">
              <span className="pane-kicker">INTELLIGENCE SUITE &bull; GEMINI 3.8 FLASH</span>
              <div className="copilot-tabs-strip">
                <button
                  type="button"
                  className={`copilot-view-tab ${rightViewMode === 'both' ? 'active' : ''}`}
                  onClick={() => setRightViewMode('both')}
                  title="Show Clause Auditor & Chat side-by-side"
                >
                  <Columns size={13} />
                  <span>Both Panels</span>
                </button>
                <button
                  type="button"
                  className={`copilot-view-tab ${rightViewMode === 'audit' ? 'active' : ''}`}
                  onClick={() => setRightViewMode('audit')}
                  title="Focus on Clause Audit & Redlines"
                >
                  <ShieldAlert size={13} />
                  <span>Clause Auditor</span>
                </button>
                <button
                  type="button"
                  className={`copilot-view-tab ${rightViewMode === 'chat' ? 'active' : ''}`}
                  onClick={() => setRightViewMode('chat')}
                  title="Focus on Document Chat"
                  id="tab-doc-chat"
                >
                  <MessageSquare size={13} />
                  <span>Chat with Document</span>
                  <span className="tab-pill-badge mono">Grounded</span>
                </button>
              </div>
            </div>

            {rightViewMode !== 'chat' && (
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
            )}
          </div>

          <div className={`copilot-columns-grid ${rightViewMode}`}>
            {/* SUB-PANEL 1: Clause Auditor & Redliner */}
            {(rightViewMode === 'both' || rightViewMode === 'audit') && (
              <div className="copilot-subpanel auditor-subpanel">
                <div className="subpanel-header">
                  <div className="subpanel-title-wrap">
                    <ShieldAlert size={14} className="subpanel-icon saffron" />
                    <h3 className="subpanel-title font-judicial">Clause Auditor & Redliner</h3>
                  </div>
                  <span className="subpanel-meta mono">SECTION 27 ICA</span>
                </div>

                <div className="copilot-scroll-container">
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
            )}

            {/* SUB-PANEL 2: Chat with Document Panel */}
            {(rightViewMode === 'both' || rightViewMode === 'chat') && (
              <div className="copilot-subpanel chat-subpanel" id="doc-chat-panel">
                <div className="subpanel-header">
                  <div className="subpanel-title-wrap">
                    <MessageSquare size={14} className="subpanel-icon saffron" />
                    <h3 className="subpanel-title font-judicial">Chat with Document</h3>
                  </div>
                  <span className="grounding-badge mono">GROUNDED &bull; QUOTES ONLY</span>
                </div>

                {/* Suggested Quick Questions Strip */}
                <div className="docchat-suggestions-strip">
                  <span className="suggestions-label mono">SUGGESTED QUERIES:</span>
                  <div className="suggestions-scroll">
                    {quickQuestions.map((q, idx) => (
                      <button
                        key={idx}
                        type="button"
                        className="suggestion-chip"
                        onClick={() => handleSendQuestion(q)}
                        disabled={isDocChatLoading}
                      >
                        <span>{q}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Messages Container */}
                <div className="docchat-messages-container">
                  {docChatMessages.map((msg) => {
                    const isAssistant = msg.sender === 'assistant';
                    const isNotFound = isAssistant && (
                      msg.text.toLowerCase().includes('not found in this document') ||
                      msg.text.trim().toLowerCase() === 'not found'
                    );

                    return (
                      <div
                        key={msg.id}
                        className={`docchat-message-row ${isAssistant ? 'assistant-row' : 'user-row'}`}
                      >
                        <div className={`docchat-bubble ${isAssistant ? 'assistant-bubble' : 'user-bubble'}`}>
                          <div className="bubble-header-row">
                            <span className="bubble-sender mono">
                              {isAssistant ? 'JUSTICE CO-PILOT' : 'YOU'}
                            </span>
                            <span className="bubble-time mono">{msg.timestamp}</span>
                          </div>

                          {isNotFound ? (
                            <div className="docchat-not-found-card">
                              <div className="not-found-header">
                                <AlertCircle size={14} />
                                <span className="mono">NOT FOUND IN THIS DOCUMENT</span>
                              </div>
                              <p className="not-found-body font-judicial">
                                "not found in this document"
                              </p>
                              <p className="not-found-subtext">
                                The uploaded agreement contains no clauses or covenants addressing this topic. Under strict grounding rules, external legal facts cannot be substituted.
                              </p>
                            </div>
                          ) : (
                            <div className="bubble-body font-judicial">
                              {msg.text}
                            </div>
                          )}

                          {/* Render Citations as Expandable Quote Chips */}
                          {msg.citations && msg.citations.length > 0 && (
                            <div className="docchat-citations-block">
                              <div className="citations-header mono">
                                <Quote size={11} />
                                <span>VERBATIM CLAUSE CITATIONS ({msg.citations.length})</span>
                              </div>

                              <div className="citations-chips-stack">
                                {msg.citations.map((c, cIdx) => {
                                  const citeKey = `${msg.id}-${cIdx}`;
                                  const isExpanded = !!expandedCitations[citeKey];

                                  return (
                                    <div key={citeKey} className="citation-chip-wrap">
                                      <button
                                        type="button"
                                        className={`citation-quote-chip ${isExpanded ? 'active' : ''}`}
                                        onClick={() => toggleCitation(citeKey)}
                                      >
                                        <div className="citation-chip-main">
                                          <span className="citation-badge mono">{c.clause_number}</span>
                                          <span className="citation-heading font-judicial">{c.heading}</span>
                                        </div>
                                        <div className="citation-chip-arrow">
                                          {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                        </div>
                                      </button>

                                      {isExpanded && (
                                        <div className="citation-expanded-quote font-judicial">
                                          <div className="quote-badge mono">EXACT QUOTED TEXT</div>
                                          <blockquote className="quote-text">
                                            "{c.quoted_text}"
                                          </blockquote>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {isDocChatLoading && (
                    <div className="docchat-message-row assistant-row">
                      <div className="docchat-bubble assistant-bubble loading-bubble">
                        <div className="bubble-header-row">
                          <span className="bubble-sender mono">JUSTICE CO-PILOT</span>
                          <span className="bubble-time mono">ANALYZING...</span>
                        </div>
                        <div className="docchat-loading-dots">
                          <span className="loading-dot" />
                          <span className="loading-dot" />
                          <span className="loading-dot" />
                          <span className="loading-text">Embedding query & retrieving grounded clauses...</span>
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={chatMessagesEndRef} />
                </div>

                {/* Chat Input Bar */}
                <form
                  className="docchat-input-bar"
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSendQuestion();
                  }}
                >
                  <input
                    type="text"
                    className="docchat-text-input"
                    id="doc-chat-input"
                    placeholder="Ask a question about this contract (e.g., 'What is my notice period?')..."
                    value={docChatInput}
                    onChange={(e) => setDocChatInput(e.target.value)}
                    disabled={isDocChatLoading}
                  />
                  <button
                    type="submit"
                    className="btn-primary docchat-send-btn"
                    id="doc-chat-send-btn"
                    disabled={!docChatInput.trim() || isDocChatLoading}
                  >
                    <Send size={14} />
                    <span>Ask</span>
                  </button>
                </form>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
