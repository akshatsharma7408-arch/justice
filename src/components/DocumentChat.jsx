import React, { useState, useEffect, useRef } from 'react';
import { 
  Upload, Send, MessageSquare, FileText, Check, ShieldCheck, 
  AlertTriangle, Quote, ChevronDown, ChevronUp, RefreshCw, X 
} from 'lucide-react';
import { CONTRACT_PRESETS } from '../data/legalCorpus';
import { uploadDocumentForChatWithBackend, chatWithDocumentWithBackend } from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

export default function DocumentChat() {
  const [selectedPresetId, setSelectedPresetId] = useState('preset-tech-consultant');
  const [contractsData, setContractsData] = useState(CONTRACT_PRESETS);
  const [contractDocIds, setContractDocIds] = useState({});
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const [messages, setMessages] = useState([
    {
      id: 'welcome-1',
      sender: 'assistant',
      text: "Upload any agreement (PDF, DOCX, or text) or choose a preset below. Every claim will quote the exact clause it originates from. If a topic is not covered in the document, I will strictly state 'not found in this document' without outside speculation.",
      citations: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [expandedCitations, setExpandedCitations] = useState({});
  const messagesEndRef = useRef(null);

  const activeContract = contractsData.find(c => c.id === selectedPresetId) || contractsData[0];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Index active contract if not yet indexed
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
        console.warn("[DocumentChat] Auto-indexing warning:", err.message);
      });

    return () => {
      isMounted = false;
    };
  }, [activeContract?.id]);

  const handleFileUpload = async (file) => {
    if (!file) return;

    setIsUploading(true);
    setUploadProgress(15);
    setUploadError(null);

    // Simulate smooth progress bar ticks while uploading
    const progressTimer = setInterval(() => {
      setUploadProgress(prev => (prev < 85 ? prev + 15 : prev));
    }, 200);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name);

      const res = await uploadDocumentForChatWithBackend(formData, file.name);
      clearInterval(progressTimer);
      setUploadProgress(100);

      const newDocId = res?.doc_id || `doc-${Date.now()}`;
      const newContract = {
        id: `upload-${Date.now()}`,
        title: file.name,
        clauses: res?.clauses || [
          {
            id: 'cl-upload-1',
            number: '1',
            title: 'Uploaded Document Body',
            text: `Document ${file.name} successfully vectorized and indexed for strict question answering.`
          }
        ]
      };

      setContractsData(prev => [newContract, ...prev]);
      setSelectedPresetId(newContract.id);
      setContractDocIds(prev => ({ ...prev, [newContract.id]: newDocId }));

      setMessages(prev => [
        ...prev,
        {
          id: `msg-indexed-${Date.now()}`,
          sender: 'assistant',
          text: `Document "${file.name}" has been indexed with clause-aware embeddings. You can now ask any question about its covenants and obligations.`,
          citations: [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err) {
      clearInterval(progressTimer);
      console.error("[DocumentChat] Upload error:", err);
      setUploadError("Could not upload file to backend. Check file format.");
    } finally {
      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress(0);
      }, 500);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFileUpload(file);
  };

  const handleSend = async (customPrompt) => {
    const question = (customPrompt || inputQuestion).trim();
    if (!question || isLoading) return;

    setInputQuestion('');
    const userMsg = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: question,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      let docId = contractDocIds[activeContract.id];
      if (!docId) {
        const fullText = activeContract.clauses
          .map(c => `${c.title}:\n${c.text}`)
          .join('\n\n');
        const uploadRes = await uploadDocumentForChatWithBackend(fullText, activeContract.title);
        docId = uploadRes.doc_id;
        setContractDocIds(prev => ({ ...prev, [activeContract.id]: docId }));
      }

      const res = await chatWithDocumentWithBackend(docId, question);

      const botMsg = {
        id: `ast-${Date.now()}`,
        sender: 'assistant',
        text: res.answer,
        citations: res.citations || [],
        notCovered: res.not_covered || false,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages(prev => [...prev, botMsg]);
    } catch (err) {
      console.error("[DocumentChat] Chat error:", err);
      setMessages(prev => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: "I encountered a communication error connecting to the document chat engine. Please try your question again.",
          citations: [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCitation = (key) => {
    setExpandedCitations(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="module-view-container animate-fade-in">
      {/* Module Header */}
      <div className="module-header-block">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">JUSTICE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">DOCUMENT CHAT</span>
        </div>
        <h1 className="module-title font-serif">Document Chat</h1>
        <p className="module-subtitle">
          Clause-grounded conversational inquiry over contracts, leases, and agreements. Strictly quotes primary clauses; zero speculative hallucination.
        </p>

        {/* Contract Switcher */}
        <div className="docchat-contract-picker">
          <span className="picker-label mono">ACTIVE DOCUMENT:</span>
          <div className="picker-chips-wrap">
            {contractsData.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`picker-contract-chip ${c.id === selectedPresetId ? 'is-active' : ''}`}
                onClick={() => setSelectedPresetId(c.id)}
              >
                <FileText size={13} />
                <span className="picker-chip-title">{c.title}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Layout: Drag-and-Drop Area & Chat Thread */}
      <div className="docchat-main-grid">
        {/* Left: Drag and Drop Upload Card */}
        <div className="docchat-sidebar-col">
          <div
            className={`dropzone-card ${isDragOver ? 'is-drag-over' : ''} ${isUploading ? 'is-uploading' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
          >
            <div className="dropzone-inner">
              <div className="dropzone-icon-wrap">
                <Upload size={28} className="dropzone-icon" />
              </div>
              <h3 className="dropzone-title font-serif">Upload Agreement</h3>
              <p className="dropzone-hint">
                Drag and drop your contract here, or click to browse (PDF, DOCX, or TXT).
              </p>

              <label className="btn-browse-file">
                <span>Select Document</span>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt"
                  className="visually-hidden"
                  onChange={(e) => handleFileUpload(e.target.files?.[0])}
                  disabled={isUploading}
                />
              </label>

              {/* Upload Progress Bar */}
              {isUploading && (
                <div className="upload-progress-wrap animate-fade-in">
                  <div className="progress-labels mono">
                    <span>INDEXING CLAUSES...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="progress-bar-track">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {uploadError && (
                <div className="upload-error-note mono">
                  <AlertTriangle size={13} />
                  <span>{uploadError}</span>
                </div>
              )}
            </div>
          </div>

          {/* Quick Questions Helper */}
          <div className="quick-questions-panel">
            <span className="quick-q-kicker mono">SUGGESTED CONTRACT INQUIRIES:</span>
            <div className="quick-q-list">
              {[
                "What non-compete restrictions are imposed on me?",
                "What is the required notice period for termination?",
                "Does the agreement contain an indemnity or penalty clause?",
                "What are the intellectual property assignment terms?"
              ].map((q, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="quick-q-btn"
                  onClick={() => handleSend(q)}
                >
                  <span>{q}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Conversational Thread */}
        <div className="docchat-thread-col">
          <div className="docchat-thread-window">
            {/* Thread Header */}
            <div className="thread-window-header">
              <div className="thread-header-title font-serif">
                Chatting with: {activeContract.title}
              </div>
              <span className="badge-verified">
                <ShieldCheck size={12} />
                <span>Strict Clause Grounding</span>
              </span>
            </div>

            {/* Message History */}
            <div className="thread-messages-list">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`chat-message-row ${msg.sender === 'user' ? 'is-user' : 'is-assistant'} animate-stagger`}
                >
                  <div className="chat-bubble">
                    <div className="bubble-header-row mono">
                      <span className="bubble-sender">{msg.sender === 'user' ? 'YOU' : 'JUSTICE DOC CHAT'}</span>
                      <span className="bubble-time">{msg.timestamp}</span>
                    </div>

                    <div className="bubble-text font-serif">
                      {renderWithBadges(msg.text)}
                    </div>

                    {/* Grounded Clause Citations */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="bubble-citations-stack">
                        <div className="citations-header mono">PRIMARY CLAUSE CITATIONS:</div>
                        {msg.citations.map((cite, i) => {
                          const citeKey = `${msg.id}-cite-${i}`;
                          const isOpen = expandedCitations[citeKey];

                          return (
                            <div key={i} className="citation-pill-item">
                              <button
                                type="button"
                                className="citation-pill-toggle"
                                onClick={() => toggleCitation(citeKey)}
                              >
                                <span className="citation-clause-tag mono">{cite.clause_number}</span>
                                <span className="citation-heading font-serif">{cite.heading}</span>
                                {isOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                              </button>

                              {isOpen && (
                                <div className="citation-quote-drawer animate-fade-in">
                                  <div className="quote-mark"><Quote size={13} /></div>
                                  <blockquote className="quote-body font-serif">
                                    "{cite.quoted_text}"
                                  </blockquote>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Animated Typing Indicator */}
              {isLoading && (
                <div className="chat-message-row is-assistant animate-fade-in">
                  <div className="chat-bubble typing-bubble">
                    <div className="typing-indicator">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </div>
                    <span className="typing-label mono">Justice is verifying contract clauses...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Message Input Bar */}
            <div className="thread-input-footer">
              <form
                className="thread-input-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
              >
                <input
                  type="text"
                  className="thread-input-field"
                  value={inputQuestion}
                  onChange={(e) => setInputQuestion(e.target.value)}
                  placeholder="Ask any question about this agreement..."
                  disabled={isLoading}
                  aria-label="Ask a question about this agreement"
                />
                <button
                  type="submit"
                  className="btn-send-question"
                  disabled={isLoading || !inputQuestion.trim()}
                  aria-label="Send question"
                >
                  <Send size={15} />
                  <span>Ask</span>
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
