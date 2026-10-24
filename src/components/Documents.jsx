import React, { useState, useEffect, useRef } from 'react';
import {
  FileText, Upload, ArrowRight, RefreshCw, Check,
  FileDiff, Play, ArrowUpRight, Cpu, ShieldAlert, Sparkles, AlertTriangle,
  MessageSquare, Send, Quote, ChevronDown, ChevronUp, HelpCircle, Columns, Maximize2,
  AlertCircle, X, Trash2, Edit3, Image as ImageIcon, Eye, FileCheck
} from 'lucide-react';
import {
  uploadDocumentForChatWithBackend,
  chatWithDocumentWithBackend
} from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

const GENERIC_PROMPTS = [
  "Summarise this document",
  "What are the key obligations and deadlines?",
  "Are there any one-sided or risky clauses?",
  "Who are the parties and what are their rights?",
  "What happens if either party terminates?"
];

export default function Documents({ onTriggerAgentAnalysis }) {
  // Document state (Clean start: null)
  const [docData, setDocData] = useState(null);
  const [selectedClauseId, setSelectedClauseId] = useState(null);
  const [diffMode, setDiffMode] = useState(false);
  const [appliedRedlines, setAppliedRedlines] = useState({});

  // Upload & Multi-image staging state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [uploadError, setUploadError] = useState(null);
  const [pendingImages, setPendingImages] = useState([]); // [{ file, previewUrl, name }]
  const fileInputRef = useRef(null);

  // Editable text state
  const [isEditingText, setIsEditingText] = useState(false);
  const [editedText, setEditedText] = useState('');
  const [isTextExpanded, setIsTextExpanded] = useState(false);
  const [isReanalyzing, setIsReanalyzing] = useState(false);

  // View Layout state
  const [viewMode, setViewMode] = useState('both'); // 'both' | 'analysis' | 'chat'
  const [mobileTab, setMobileTab] = useState('analysis'); // 'analysis' | 'chat'

  // Document versioning & generation guards
  const [docVersion, setDocVersion] = useState(1);
  const docVersionRef = useRef(1);
  const activeChatAbortRef = useRef(null);

  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [chatError, setChatError] = useState(null);
  const [expandedCitations, setExpandedCitations] = useState({});
  const chatMessagesEndRef = useRef(null);

  const activeClause = docData?.clauses?.find(cl => cl.chunk_id === selectedClauseId || cl.id === selectedClauseId)
    || docData?.clauses?.[0]
    || null;

  // Auto-scroll chat to bottom
  const scrollToBottom = () => {
    chatMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, isChatLoading]);

  // Handle stage image selection
  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setUploadError(null);

    const imageExts = ['jpg', 'jpeg', 'png', 'webp', 'heic'];
    const isImageFile = (f) => imageExts.includes(f.name.split('.').pop().toLowerCase());

    const allImages = files.every(isImageFile);

    if (allImages) {
      if (files.length > 10) {
        setUploadError("Maximum 10 images allowed per upload.");
        return;
      }
      // Create previews
      const staged = files.map((file, idx) => ({
        id: `img-${Date.now()}-${idx}`,
        file,
        name: file.name,
        previewUrl: URL.createObjectURL(file)
      }));
      setPendingImages(staged);
    } else {
      // Direct upload for single PDF/DOCX/TXT
      const file = files[0];
      if (file.size > 10 * 1024 * 1024) {
        setUploadError(`File '${file.name}' exceeds 10MB limit.`);
        return;
      }
      await uploadFilesDirectly([file], file.name);
    }
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // Upload staged images or files
  const uploadFilesDirectly = async (filesToUpload, docTitle) => {
    setIsUploading(true);
    setUploadProgress(filesToUpload.length > 1 ? `Preparing ${filesToUpload.length} images...` : 'Reading document...');
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append('title', docTitle);

      if (filesToUpload.length === 1) {
        formData.append('file', filesToUpload[0]);
      } else {
        filesToUpload.forEach((f, idx) => {
          formData.append('files', f);
        });
      }

      setUploadProgress(filesToUpload.length > 1 ? `Running OCR across ${filesToUpload.length} pages...` : 'Parsing clauses and running statutory audit...');
      const resp = await uploadDocumentForChatWithBackend(formData, docTitle);

      if (!resp || !resp.doc_id) {
        throw new Error("Invalid response from document processing service.");
      }

      // Abort any in-flight chat query and increment version
      if (activeChatAbortRef.current) {
        activeChatAbortRef.current.abort();
        activeChatAbortRef.current = null;
      }
      const newVersion = docVersionRef.current + 1;
      docVersionRef.current = newVersion;
      setDocVersion(newVersion);

      // Initialize clean chat history grounded in this document version
      const initialChat = [
        {
          id: `welcome-v${newVersion}`,
          sender: 'assistant',
          text: `I've read and analyzed "${resp.title}". Ask any question about this document. Every claim will quote the exact clause it originates from.`,
          citations: [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ];

      setDocData(resp);
      setEditedText(resp.raw_text || '');
      setSelectedClauseId(resp.clauses?.[0]?.chunk_id || 1);
      setChatMessages(initialChat);
      setExpandedCitations({});
      setPendingImages([]);
      setAppliedRedlines({});
    } catch (err) {
      console.error("[Documents] Upload error:", err);
      setUploadError(err.message || "Failed to process document. Please try a clearer file.");
    } finally {
      setIsUploading(false);
      setUploadProgress('');
    }
  };

  const handleStartStagedUpload = async () => {
    if (!pendingImages.length) return;
    const files = pendingImages.map(p => p.file);
    const title = `${pendingImages.length} Uploaded Pages`;
    await uploadFilesDirectly(files, title);
  };

  const handleRemoveStagedImage = (idToRemove) => {
    setPendingImages(prev => prev.filter(img => img.id !== idToRemove));
  };

  const handleMoveStagedImage = (index, direction) => {
    const targetIdx = index + direction;
    if (targetIdx < 0 || targetIdx >= pendingImages.length) return;
    setPendingImages(prev => {
      const next = [...prev];
      const temp = next[index];
      next[index] = next[targetIdx];
      next[targetIdx] = temp;
      return next;
    });
  };

  // Re-run analysis on edited text
  const handleRerunAnalysis = async () => {
    if (!editedText.trim() || !docData?.doc_id) return;
    setIsReanalyzing(true);
    setUploadError(null);

    // Abort any in-flight chat query
    if (activeChatAbortRef.current) {
      activeChatAbortRef.current.abort();
      activeChatAbortRef.current = null;
    }

    try {
      const formData = new FormData();
      formData.append('text', editedText);
      formData.append('title', docData.title || "Edited Agreement");
      formData.append('doc_id', docData.doc_id);

      const resp = await uploadDocumentForChatWithBackend(formData, docData.title, docData.doc_id);

      const newVersion = docVersionRef.current + 1;
      docVersionRef.current = newVersion;
      setDocVersion(newVersion);

      setDocData(resp);
      setSelectedClauseId(resp.clauses?.[0]?.chunk_id || 1);
      setIsEditingText(false);
      setExpandedCitations({});

      // Reset chat messages and citations to version message so stale Q&A from previous text is not preserved
      setChatMessages([
        {
          id: `update-v${newVersion}`,
          sender: 'assistant',
          text: `Document text updated (v${newVersion}). Chat history and clause citations have been reset to match your latest edits. Ask any question about this edited version.`,
          citations: [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err) {
      console.error("[Documents] Re-run error:", err);
      setUploadError(err.message || "Failed to re-analyze edited text.");
    } finally {
      setIsReanalyzing(false);
    }
  };

  // Remove document / Reset to clean state
  const handleRemoveDocument = () => {
    if (activeChatAbortRef.current) {
      activeChatAbortRef.current.abort();
      activeChatAbortRef.current = null;
    }
    const newVersion = docVersionRef.current + 1;
    docVersionRef.current = newVersion;
    setDocVersion(newVersion);

    setDocData(null);
    setSelectedClauseId(null);
    setEditedText('');
    setIsEditingText(false);
    setChatMessages([]);
    setExpandedCitations({});
    setPendingImages([]);
    setUploadError(null);
  };

  // Send question in Document Chat with AbortController and generation guards
  const handleSendQuestion = async (queryText) => {
    const trimmed = (queryText || chatInput).trim();
    if (!trimmed || !docData?.doc_id || isChatLoading) return;

    // Abort previous in-flight chat query if any
    if (activeChatAbortRef.current) {
      activeChatAbortRef.current.abort();
    }
    const abortController = new AbortController();
    activeChatAbortRef.current = abortController;
    const currentVersion = docVersionRef.current;

    const userMsg = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsChatLoading(true);
    setChatError(null);

    try {
      const data = await chatWithDocumentWithBackend(docData.doc_id, trimmed, abortController.signal);
      // Generation guard: ignore if request was aborted or document was modified while in-flight
      if (abortController.signal.aborted || currentVersion !== docVersionRef.current) {
        return;
      }
      const assistantMsg = {
        id: `asst-${Date.now()}`,
        sender: 'assistant',
        text: data.answer || "I couldn't find this in the available sources.",
        citations: data.citations || [],
        model_used: data.model_used,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setChatMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      if (abortController.signal.aborted || currentVersion !== docVersionRef.current) {
        return;
      }
      console.error("[Documents] Chat error:", err);
      setChatError(err.message || "Failed to query document. Please try again.");
    } finally {
      if (currentVersion === docVersionRef.current) {
        setIsChatLoading(false);
        if (activeChatAbortRef.current === abortController) {
          activeChatAbortRef.current = null;
        }
      }
    }
  };

  const handleApplyRedline = (clauseId) => {
    setAppliedRedlines(prev => ({
      ...prev,
      [clauseId]: !prev[clauseId]
    }));
  };

  // Determine file type badge
  const getDocTypeBadge = (title = '') => {
    const ext = title.split('.').pop().toLowerCase();
    if (ext === 'pdf') return 'PDF Document';
    if (ext === 'docx') return 'DOCX Word';
    if (ext === 'txt') return 'Plain Text';
    if (['jpg', 'jpeg', 'png', 'webp', 'heic'].includes(ext) || title.includes('Pages')) return 'OCR Scanned Image';
    return 'Legal Document';
  };

  return (
    <div className="module-view-container animate-fade-in documents-workspace-container">
      {/* Header Block */}
      <div className="module-header-block">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">JUSTICE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">DOCUMENTS &bull; CLAUSE AUDIT &amp; GROUNDED CHAT</span>
        </div>
        <div className="documents-title-strip">
          <div>
            <h1 className="module-title font-serif">Documents Workspace</h1>
            <p className="module-subtitle">
              Single unified workspace for contract clause risk auditing and free-form grounded document Q&amp;A.
            </p>
          </div>

          {/* Desktop Layout Switcher */}
          {docData && (
            <div className="doc-layout-switcher hide-on-mobile">
              <button
                type="button"
                className={`btn-layout-toggle ${viewMode === 'both' ? 'is-active' : ''}`}
                onClick={() => setViewMode('both')}
                title="Side-by-side Analysis and Chat"
              >
                <Columns size={14} />
                <span>Side by Side</span>
              </button>
              <button
                type="button"
                className={`btn-layout-toggle ${viewMode === 'analysis' ? 'is-active' : ''}`}
                onClick={() => setViewMode('analysis')}
                title="Analysis Only"
              >
                <ShieldAlert size={14} />
                <span>Analysis</span>
              </button>
              <button
                type="button"
                className={`btn-layout-toggle ${viewMode === 'chat' ? 'is-active' : ''}`}
                onClick={() => setViewMode('chat')}
                title="Chat Only"
              >
                <MessageSquare size={14} />
                <span>Chat</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Upload Error Banner */}
      {uploadError && (
        <div className="search-backend-error-card animate-fade-in" style={{ marginBottom: '20px' }}>
          <div className="error-card-content">
            <AlertCircle size={20} className="text-copper" />
            <p className="error-card-desc">{uploadError}</p>
          </div>
          <button
            type="button"
            className="btn-friendly-retry mono"
            onClick={() => setUploadError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* STATE 1: NO DOCUMENT UPLOADED (CLEAN START) */}
      {!docData && (
        <div className="documents-clean-empty-workspace animate-fade-in">
          {/* Staging Area for Multi-Image uploads */}
          {pendingImages.length > 0 ? (
            <div className="documents-staged-images-card">
              <div className="staged-header">
                <div>
                  <h3 className="staged-title font-serif">
                    {pendingImages.length} Image{pendingImages.length !== 1 ? 's' : ''} Ready for OCR
                  </h3>
                  <p className="staged-desc">
                    Reorder pages using arrows or remove blurry photos before extracting text.
                  </p>
                </div>
                <div className="staged-actions">
                  <button
                    type="button"
                    className="btn-cancel-staged mono"
                    onClick={() => setPendingImages([])}
                    disabled={isUploading}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn-run-ocr mono"
                    onClick={handleStartStagedUpload}
                    disabled={isUploading}
                  >
                    {isUploading ? (
                      <>
                        <RefreshCw size={14} className="spin-icon" />
                        <span>{uploadProgress || 'Running OCR...'}</span>
                      </>
                    ) : (
                      <>
                        <Play size={14} />
                        <span>Run OCR &amp; Audit</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Thumbnails Grid */}
              <div className="staged-thumbnails-grid">
                {pendingImages.map((img, idx) => (
                  <div key={img.id} className="staged-thumbnail-item">
                    <div className="thumbnail-page-badge mono">Page {idx + 1}</div>
                    <img src={img.previewUrl} alt={`Page ${idx + 1}`} className="thumbnail-img" />
                    <div className="thumbnail-overlay">
                      <span className="thumbnail-name" title={img.name}>{img.name}</span>
                      <div className="thumbnail-controls">
                        <button
                          type="button"
                          disabled={idx === 0 || isUploading}
                          onClick={() => handleMoveStagedImage(idx, -1)}
                          title="Move Left"
                        >
                          &larr;
                        </button>
                        <button
                          type="button"
                          disabled={idx === pendingImages.length - 1 || isUploading}
                          onClick={() => handleMoveStagedImage(idx, 1)}
                          title="Move Right"
                        >
                          &rarr;
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveStagedImage(img.id)}
                          disabled={isUploading}
                          className="btn-remove-thumb"
                          title="Remove image"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* Clean Dropzone */
            <div
              className={`documents-dropzone-hero ${isUploading ? 'is-uploading' : ''}`}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.webp,.heic"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
                disabled={isUploading}
              />
              <div className="dropzone-icon-wrap">
                {isUploading ? (
                  <RefreshCw size={36} className="spin-icon text-copper" />
                ) : (
                  <Upload size={36} className="text-copper" />
                )}
              </div>
              <h2 className="dropzone-heading font-serif">
                {isUploading ? "Processing Document..." : "No document yet"}
              </h2>
              <p className="dropzone-sub">
                {isUploading
                  ? uploadProgress || "Extracting text, analyzing statutory compliance, and embedding clauses..."
                  : "Upload a contract, notice, or legal document to begin."}
              </p>

              <div className="dropzone-formats-strip mono">
                <span>PDF</span> &bull;
                <span>DOCX</span> &bull;
                <span>TXT</span> &bull;
                <span>JPG / PNG / WEBP / HEIC (Up to 10 photos)</span>
              </div>

              <button
                type="button"
                className="btn-dropzone-browse mono"
                disabled={isUploading}
              >
                <span>Select Document or Photos</span>
                <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* STATE 2: ACTIVE DOCUMENT WORKSPACE */}
      {docData && (
        <div className="documents-active-workspace animate-fade-in">
          {/* Active File Bar */}
          <div className="documents-active-file-bar">
            <div className="file-bar-left">
              <FileCheck size={20} className="text-copper" />
              <div className="file-info-cluster">
                <div className="file-title-row">
                  <span className="file-title font-serif">{docData.title}</span>
                  <span className="file-type-badge mono">{getDocTypeBadge(docData.title)}</span>
                </div>
                <div className="file-stats-row mono">
                  <span>{docData.chunks_count || docData.clauses?.length || 0} Clauses Identified</span>
                  <span>&bull;</span>
                  <span>{docData.char_count || docData.raw_text?.length || 0} characters</span>
                  {docData.page_count && docData.page_count > 1 && (
                    <>
                      <span>&bull;</span>
                      <span>{docData.page_count} Pages</span>
                    </>
                  )}
                  {docData.audit_results?.void_clauses_count > 0 && (
                    <>
                      <span>&bull;</span>
                      <span className="badge-risk-critical mono">
                        {docData.audit_results.void_clauses_count} Void Clause{docData.audit_results.void_clauses_count !== 1 ? 's' : ''} Flagged
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="file-bar-actions">
              <button
                type="button"
                className="btn-file-action mono"
                onClick={() => setIsTextExpanded(!isTextExpanded)}
                title="Inspect or edit extracted text"
              >
                <Edit3 size={13} />
                <span>{isTextExpanded ? "Hide Extracted Text" : "View / Edit Text"}</span>
              </button>
              <button
                type="button"
                className="btn-file-action mono"
                onClick={() => fileInputRef.current?.click()}
                title="Replace with new document"
              >
                <RefreshCw size={13} />
                <span>Replace Document</span>
              </button>
              <button
                type="button"
                className="btn-file-action btn-danger mono"
                onClick={handleRemoveDocument}
                title="Close document and return to start"
              >
                <Trash2 size={13} />
                <span>Remove</span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.webp,.heic"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
                disabled={isUploading}
              />
            </div>
          </div>

          {/* Collapsible Extracted Text Editor */}
          {isTextExpanded && (
            <div className="extracted-text-pane animate-fade-in">
              <div className="extracted-text-pane-header">
                <div className="pane-title mono">EXTRACTED DOCUMENT TEXT ({editedText.length} chars)</div>
                <div className="pane-actions">
                  {isEditingText ? (
                    <>
                      <button
                        type="button"
                        className="btn-pane-action mono"
                        onClick={() => {
                          setEditedText(docData.raw_text || '');
                          setIsEditingText(false);
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="btn-pane-action btn-save mono"
                        onClick={handleRerunAnalysis}
                        disabled={isReanalyzing || !editedText.trim()}
                      >
                        {isReanalyzing ? (
                          <>
                            <RefreshCw size={12} className="spin-icon" />
                            <span>Re-analyzing...</span>
                          </>
                        ) : (
                          <>
                            <Check size={12} />
                            <span>Re-run Analysis</span>
                          </>
                        )}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn-pane-action mono"
                      onClick={() => setIsEditingText(true)}
                    >
                      <Edit3 size={12} />
                      <span>Edit Text</span>
                    </button>
                  )}
                </div>
              </div>

              {isEditingText ? (
                <textarea
                  className="extracted-text-editor font-mono"
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  placeholder="Paste or correct OCR extracted contract text..."
                  rows={10}
                />
              ) : (
                <pre className="extracted-text-display font-mono">
                  {docData.raw_text || editedText || "No text available."}
                </pre>
              )}
            </div>
          )}

          {/* Mobile Tab Switcher */}
          <div className="documents-mobile-tabs hide-on-desktop">
            <button
              type="button"
              className={`mobile-tab-btn ${mobileTab === 'analysis' ? 'is-active' : ''}`}
              onClick={() => setMobileTab('analysis')}
            >
              <ShieldAlert size={14} />
              <span>Analysis &amp; Clauses</span>
            </button>
            <button
              type="button"
              className={`mobile-tab-btn ${mobileTab === 'chat' ? 'is-active' : ''}`}
              onClick={() => setMobileTab('chat')}
            >
              <MessageSquare size={14} />
              <span>Document Chat</span>
            </button>
          </div>

          {/* Unified Body Grid (Desktop: Side-by-Side or Selected Mode; Mobile: Tabs) */}
          <div className={`documents-workspace-grid view-${viewMode}`}>
            {/* COLUMN 1: CLAUSE ANALYSIS & REDLINING */}
            <div className={`doc-col-analysis ${mobileTab !== 'analysis' ? 'hide-on-mobile' : ''}`}>
              {/* Clause List Strip */}
              <div className="clauses-sidebar-panel">
                <div className="clauses-panel-heading mono">
                  <span>IDENTIFIED CLAUSES ({docData.clauses?.length || 0})</span>
                  {docData.audit_results?.risk_level === 'CRITICAL_VOID_TERMS' && (
                    <span className="badge-risk-critical mono">CRITICAL RISK</span>
                  )}
                </div>

                <div className="clauses-pills-list">
                  {docData.clauses?.map((clause, idx) => {
                    const isSelected = (activeClause?.chunk_id === clause.chunk_id);
                    const isViol = clause.is_violation;
                    return (
                      <button
                        key={clause.chunk_id || idx}
                        type="button"
                        className={`clause-nav-pill ${isSelected ? 'is-selected' : ''} ${isViol ? 'is-violation' : ''}`}
                        onClick={() => setSelectedClauseId(clause.chunk_id)}
                      >
                        <div className="pill-top-row">
                          <span className="pill-title">{clause.heading || clause.title || `Clause ${idx + 1}`}</span>
                          {isViol ? (
                            <span className="pill-status-dot red" title="Statutory Violation" />
                          ) : (
                            <span className="pill-status-dot green" title="Compliant" />
                          )}
                        </div>
                        <p className="pill-snippet">
                          {clause.text ? clause.text.slice(0, 90) + '...' : ''}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Selected Clause Detailed View */}
              {activeClause && (
                <div className="clause-detail-panel animate-fade-in">
                  <div className="clause-detail-header">
                    <div>
                      <span className="clause-kicker mono">
                        CLAUSE {activeClause.clause_index || 1} &bull; {activeClause.is_violation ? "NON-COMPLIANT" : "STATUTORILY SOUND"}
                      </span>
                      <h2 className="clause-heading font-serif">{activeClause.heading || activeClause.title}</h2>
                    </div>

                    <div className="clause-header-actions">
                      {activeClause.balanced_redline && (
                        <button
                          type="button"
                          className={`btn-diff-toggle mono ${diffMode ? 'is-active' : ''}`}
                          onClick={() => setDiffMode(!diffMode)}
                        >
                          <FileDiff size={13} />
                          <span>{diffMode ? "Standard View" : "Diff View"}</span>
                        </button>
                      )}
                      {onTriggerAgentAnalysis && (
                        <button
                          type="button"
                          className="btn-agent-audit mono"
                          onClick={() => onTriggerAgentAnalysis(activeClause.text, docData.title)}
                        >
                          <Cpu size={13} />
                          <span>Agent StateGraph</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Clause Original vs Redline (Diff Mode or Normal) */}
                  {diffMode && activeClause.balanced_redline ? (
                    <div className="clause-diff-container">
                      <div className="diff-column original">
                        <div className="diff-header mono">ORIGINAL EXTRACTED CLAUSE TEXT</div>
                        <div className="diff-body font-mono">{activeClause.text}</div>
                      </div>
                      <div className="diff-column replacement">
                        <div className="diff-header mono">SECTION 27 BALANCED REDLINE</div>
                        <div className="diff-body font-mono">{activeClause.balanced_redline}</div>
                      </div>
                    </div>
                  ) : (
                    <div className="clause-text-box">
                      <p className="clause-prose font-mono">
                        {appliedRedlines[activeClause.chunk_id] && activeClause.balanced_redline
                          ? activeClause.balanced_redline
                          : activeClause.text}
                      </p>
                    </div>
                  )}

                  {/* Statutory Analysis Card */}
                  {activeClause.is_violation ? (
                    <div className="statutory-violation-card">
                      <div className="violation-card-kicker mono">
                        <AlertTriangle size={14} className="text-copper" />
                        <span>STATUTORY ISSUE &bull; {activeClause.statute || "Indian Contract Act, 1872"}</span>
                      </div>
                      <h3 className="violation-issue-title font-serif">
                        {activeClause.statutory_issue || "Restraint of trade - Void ab initio under Section 27"}
                      </h3>
                      <p className="violation-layman font-serif">
                        {activeClause.layman_translation || "Under Indian law, post-termination covenants in restraint of trade are absolute and void ab initio without any exception of reasonableness."}
                      </p>

                      {activeClause.precedents && activeClause.precedents.length > 0 && (
                        <div className="violation-precedents-strip mono">
                          <span className="prec-label">BINDING PRECEDENTS:</span>
                          {activeClause.precedents.map((p, pIdx) => (
                            <span key={pIdx} className="prec-chip">{p}</span>
                          ))}
                        </div>
                      )}

                      {activeClause.balanced_redline && (
                        <div className="redline-action-strip">
                          <button
                            type="button"
                            className="btn-apply-redline mono"
                            onClick={() => handleApplyRedline(activeClause.chunk_id)}
                          >
                            <Check size={13} />
                            <span>
                              {appliedRedlines[activeClause.chunk_id]
                                ? "Revert to Original Text"
                                : "Apply Section 27 Redline"}
                            </span>
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="statutory-compliant-card">
                      <div className="compliant-card-kicker mono">
                        <Check size={14} className="text-verified" />
                        <span>STATUTORILY COMPLIANT</span>
                      </div>
                      <p className="compliant-desc font-serif">
                        {activeClause.layman_translation || "This provision does not impose illegal post-termination restraints and is standard under Indian contractual jurisprudence."}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* COLUMN 2: DOCUMENT CHAT */}
            <div className={`doc-col-chat ${mobileTab !== 'chat' ? 'hide-on-mobile' : ''}`}>
              <div className="doc-chat-card">
                {/* Chat Top Banner */}
                <div className="doc-chat-header">
                  <div className="chat-header-main">
                    <MessageSquare size={16} className="text-copper" />
                    <div>
                      <h2 className="chat-title font-serif">Document Chat</h2>
                      <span className="chat-sub mono">
                        Strictly grounded in &ldquo;{docData.title}&rdquo;
                      </span>
                    </div>
                  </div>

                  {chatMessages.length > 1 && (
                    <button
                      type="button"
                      className="btn-clear-chat mono"
                      onClick={() => setChatMessages([chatMessages[0]])}
                      title="Clear chat messages"
                    >
                      <Trash2 size={12} />
                      <span>Clear</span>
                    </button>
                  )}
                </div>

                {/* Suggested Generic Prompts Strip */}
                <div className="generic-prompts-dock">
                  <span className="prompts-kicker mono">SUGGESTED QUESTIONS:</span>
                  <div className="prompts-chips-scroll">
                    {GENERIC_PROMPTS.map((promptText, pIdx) => (
                      <button
                        key={pIdx}
                        type="button"
                        className="prompt-chip mono"
                        onClick={() => handleSendQuestion(promptText)}
                        disabled={isChatLoading}
                      >
                        <Sparkles size={11} />
                        <span>{promptText}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Chat Messages Stream */}
                <div className="doc-chat-messages-scroll" role="log" aria-live="polite">
                  {chatMessages.map((msg) => (
                    <div key={msg.id} className={`doc-message-row ${msg.sender}`}>
                      <div className="doc-message-bubble">
                        <div className="doc-message-text font-serif">
                          {renderWithBadges(msg.text)}
                        </div>

                        {/* Verbatim Citations List */}
                        {msg.citations && msg.citations.length > 0 && (
                          <div className="doc-citations-block">
                            <span className="citations-kicker mono">VERBATIM SOURCES IN DOCUMENT:</span>
                            <div className="citations-list">
                              {msg.citations.map((cite, cIdx) => {
                                const citeKey = `${msg.id}-${cIdx}`;
                                const isExpanded = expandedCitations[citeKey];
                                return (
                                  <div key={cIdx} className="doc-citation-item">
                                    <button
                                      type="button"
                                      className="citation-toggle-btn mono"
                                      onClick={() => setExpandedCitations(prev => ({
                                        ...prev,
                                        [citeKey]: !isExpanded
                                      }))}
                                    >
                                      <Quote size={11} className="text-copper" />
                                      <span>{cite.clause_number}: {cite.heading}</span>
                                      {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                                    </button>
                                    {isExpanded && (
                                      <blockquote className="citation-quote-box font-mono">
                                        &ldquo;{cite.quoted_text}&rdquo;
                                      </blockquote>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        <span className="doc-message-time mono">{msg.timestamp}</span>
                      </div>
                    </div>
                  ))}

                  {isChatLoading && (
                    <div className="doc-message-row assistant">
                      <div className="doc-message-bubble loading-shimmer">
                        <RefreshCw size={14} className="spin-icon text-copper" />
                        <span className="mono">Checking clauses and verifying quotes...</span>
                      </div>
                    </div>
                  )}

                  {chatError && (
                    <div className="doc-chat-error-card mono">
                      <AlertCircle size={14} />
                      <span>{chatError}</span>
                    </div>
                  )}

                  <div ref={chatMessagesEndRef} />
                </div>

                {/* Chat Input Bar */}
                <form
                  className="doc-chat-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSendQuestion(chatInput);
                  }}
                >
                  <input
                    type="text"
                    className="doc-chat-input"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder="Ask anything about this document..."
                    disabled={isChatLoading}
                  />
                  <button
                    type="submit"
                    className="doc-chat-submit-btn"
                    disabled={!chatInput.trim() || isChatLoading}
                    aria-label="Send query"
                  >
                    <Send size={15} />
                  </button>
                </form>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
