import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  MessageSquare, Send, Copy, Check, RotateCcw,
  Trash2, X, ChevronDown, ChevronRight, Sparkles,
  Scale, ExternalLink, HelpCircle
} from 'lucide-react';
import { sendCaseChatMessage } from '../config/gemini';

const QUICK_BUTTONS = [
  "Summarise this case",
  "What did the court decide?",
  "Who were the parties?",
  "Why does it matter for ordinary people?",
  "Which laws or sections were used?"
];

export default function CaseChatPanel({
  caseId,
  caseTitle = "Supreme Court Judgment",
  caseCitation = "",
  isOpen = true,
  onToggle,
  onScrollToParagraph,
  externalPrompt = null,
  onClearExternalPrompt
}) {
  // Chat history kept per case in memory while the tab is open
  const [chatHistories, setChatHistories] = useState({});
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const openerRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      if (!openerRef.current && document.activeElement) {
        openerRef.current = document.activeElement;
      }
    } else {
      if (openerRef.current && typeof openerRef.current.focus === 'function') {
        try { openerRef.current.focus(); } catch (e) { }
        openerRef.current = null;
      }
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        if (openerRef.current && typeof openerRef.current.focus === 'function') {
          try { openerRef.current.focus(); } catch (e) { }
        }
        onToggle?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onToggle]);

  const currentHistory = (caseId && chatHistories[caseId]) || [];

  // Auto-scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentHistory, isLoading]);

  // Handle external prompt passed in (e.g. from global Explain Selection)
  useEffect(() => {
    if (externalPrompt && caseId) {
      handleSendMessage(externalPrompt);
      if (onClearExternalPrompt) onClearExternalPrompt();
    }
  }, [externalPrompt, caseId]);

  // Send message
  const handleSendMessage = async (textToSend = input) => {
    const trimmed = (textToSend || '').trim();
    if (!trimmed || !caseId || isLoading) return;

    const userMessageId = `user_${Date.now()}`;
    const userMessage = {
      id: userMessageId,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    const nextHistory = [...currentHistory, userMessage];
    setChatHistories(prev => ({
      ...prev,
      [caseId]: nextHistory
    }));

    setInput('');
    setIsLoading(true);

    try {
      const resp = await sendCaseChatMessage({
        caseId: caseId,
        question: trimmed,
        messages: nextHistory.map(m => ({ role: m.role, content: m.content }))
      });

      const assistantMessage = {
        id: `asst_${Date.now()}`,
        role: 'assistant',
        content: resp.answer || 'This case does not say that.',
        basedOn: resp.based_on || null,
        paragraphId: resp.paragraph_id || null,
        disclaimer: resp.disclaimer || 'AI answer, not legal advice',
        cached: Boolean(resp.cached),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setChatHistories(prev => ({
        ...prev,
        [caseId]: [...(prev[caseId] || nextHistory), assistantMessage]
      }));
    } catch (err) {
      console.error("[CaseChat] Request failed:", err);
      const errorMessage = {
        id: `err_${Date.now()}`,
        role: 'assistant',
        isError: true,
        content: `Could not retrieve answer (${err.message || 'Network error'}). Tap Retry to try again.`,
        failedQuery: trimmed,
        disclaimer: 'AI answer, not legal advice',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setChatHistories(prev => ({
        ...prev,
        [caseId]: [...(prev[caseId] || nextHistory), errorMessage]
      }));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCopy = (msgId, text) => {
    navigator.clipboard?.writeText(text);
    setCopiedMsgId(msgId);
    setTimeout(() => {
      setCopiedMsgId(null);
    }, 2000);
  };

  const handleClearChat = () => {
    if (!caseId) return;
    setChatHistories(prev => ({
      ...prev,
      [caseId]: []
    }));
  };

  const handleRetry = (failedQuery) => {
    handleSendMessage(failedQuery);
  };

  // Render message content with bold/paragraph formatting
  const formatAnswerContent = (text) => {
    if (!text) return null;
    return text.split('\n\n').map((paragraph, pIdx) => {
      const trimmed = paragraph.trim();
      if (!trimmed) return null;
      // Check for bullet list
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const bullets = trimmed.split('\n').filter(b => b.trim());
        return (
          <ul key={pIdx} className="chat-bullet-list">
            {bullets.map((b, bIdx) => (
              <li key={bIdx}>{b.replace(/^[-*]\s*/, '')}</li>
            ))}
          </ul>
        );
      }
      return <p key={pIdx} className="chat-paragraph">{paragraph}</p>;
    });
  };

  // Floating collapsed bar for desktop / mobile trigger
  if (!isOpen) {
    return (
      <motion.button
        type="button"
        className="case-chat-collapsed-trigger"
        onClick={onToggle}
        title="Open Case Chat (Ask about this case)"
        aria-label="Open Case Chat"
        initial={{ opacity: 0, scale: 0.9, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 10 }}
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.96 }}
        transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
      >
        <MessageSquare size={16} />
        <span className="collapsed-trigger-label">Ask about this case</span>
        <span className="collapsed-case-pill mono">{caseCitation || caseTitle.slice(0, 18)}</span>
      </motion.button>
    );
  }



  return (
    <>
      <div
        className="case-chat-backdrop"
        onClick={onToggle}
        aria-hidden="true"
      />
      <motion.aside
        className="case-chat-panel-container"
        aria-label="Ask about this case chat panel"
        id="case-chat-panel"
        initial={{ opacity: 0, x: 28, scale: 0.98 }}
        animate={{ opacity: 1, x: 0, scale: 1 }}
        exit={{ opacity: 0, x: 28, scale: 0.98 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="case-chat-drag-handle" aria-hidden="true" />
        {/* Panel Top Header */}
        <div className="case-chat-header">
          <div className="chat-header-main">
            <div className="chat-header-icon-wrap">
              <MessageSquare size={16} className="chat-header-icon" />
            </div>
            <div className="chat-header-text">
              <h2 className="chat-header-title">Ask about this case</h2>
              <div className="chat-header-sub">
                <span className="chat-scope-label">Case Scoped:</span>
                <span className="chat-scope-name font-judicial" title={caseTitle}>
                  {caseTitle}
                </span>
                {caseCitation && (
                  <span className="chat-scope-citation mono">{caseCitation}</span>
                )}
              </div>
            </div>
          </div>

          <div className="chat-header-actions">
            {currentHistory.length > 0 && (
              <button
                type="button"
                className="chat-action-btn"
                onClick={handleClearChat}
                title="Clear chat history for this case"
                aria-label="Clear chat"
              >
                <Trash2 size={13} />
                <span className="action-btn-text">Clear</span>
              </button>
            )}

            <button
              type="button"
              className="chat-toggle-collapse-btn"
              onClick={onToggle}
              title="Close / Collapse chat panel"
              aria-label="Close panel"
            >
              <X className="mobile-close-icon" size={18} />
              <ChevronRight className="desktop-collapse-icon" size={18} />
            </button>
          </div>
        </div>

        {/* Messages Scroll Area */}
        <div className="case-chat-messages-area" role="log" aria-live="polite">
          {currentHistory.length === 0 ? (
            <div className="case-chat-empty-state">
              <div className="empty-state-badge">
                <Sparkles size={14} />
                <span>Grounded Legal Synthesis</span>
              </div>
              <h3 className="empty-state-heading font-judicial">Have questions on this judgment?</h3>
              <p className="empty-state-desc">
                Answers are grounded in the recorded text available for this judgment. Coverage can be partial, so verify against the official report before citing. Pick a suggested prompt below or type your question.
              </p>
            </div>
          ) : (
            <div className="chat-messages-stream">
              {currentHistory.map((msg) => (
                <div
                  key={msg.id}
                  className={`chat-message-row role-${msg.role} ${msg.isError ? 'is-error' : ''}`}
                >
                  <div className="chat-message-bubble">
                    {msg.role === 'assistant' && (
                      <div className="chat-bubble-top-meta">
                        <span className="disclaimer-chip">
                          {msg.disclaimer || 'AI answer, not legal advice'}
                        </span>
                        {msg.cached && (
                          <span className="cached-badge mono">Cached</span>
                        )}
                      </div>
                    )}

                    <div className="chat-bubble-content font-judicial">
                      {formatAnswerContent(msg.content)}
                    </div>

                    {msg.role === 'assistant' && !msg.isError && (
                      <div className="chat-bubble-bottom-bar">
                        {/* Clickable Based on link */}
                        {msg.basedOn && (
                          <button
                            type="button"
                            className="based-on-anchor-btn mono"
                            onClick={() => {
                              if (onScrollToParagraph) {
                                onScrollToParagraph(msg.paragraphId || 'chunk-0');
                              } else {
                                const el = document.getElementById(msg.paragraphId || 'chunk-0');
                                el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                el?.classList.add('paragraph-highlight-pulse');
                                setTimeout(() => el?.classList.remove('paragraph-highlight-pulse'), 2500);
                              }
                            }}
                            title="Scroll to supporting paragraph in judgment"
                          >
                            <Scale size={11} />
                            <span>Based on: {msg.basedOn}</span>
                            <ExternalLink size={10} />
                          </button>
                        )}

                        <div className="chat-bubble-actions">
                          <button
                            type="button"
                            className="msg-icon-action-btn"
                            onClick={() => handleCopy(msg.id, msg.content)}
                            title="Copy answer to clipboard"
                            aria-label="Copy answer"
                          >
                            {copiedMsgId === msg.id ? (
                              <>
                                <Check size={12} className="text-emerald" />
                                <span className="copied-text">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy size={12} />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    )}

                    {msg.isError && (
                      <div className="chat-error-actions">
                        <button
                          type="button"
                          className="btn-retry-action"
                          onClick={() => handleRetry(msg.failedQuery)}
                        >
                          <RotateCcw size={13} />
                          <span>Retry</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Typing Indicator */}
              {isLoading && (
                <div className="chat-message-row role-assistant is-loading">
                  <div className="chat-message-bubble">
                    <div className="typing-indicator">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-label">Analyzing case text...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Quick Action Buttons Bar */}
        <div className="case-chat-quick-buttons-strip">
          <div className="quick-buttons-scroll" role="toolbar" aria-label="Suggested quick questions">
            {QUICK_BUTTONS.map((qText, idx) => (
              <motion.button
                key={idx}
                type="button"
                className={`quick-button-chip ${qText.startsWith('Summarise') ? 'is-summary' : ''}`}
                onClick={() => handleSendMessage(qText)}
                disabled={isLoading}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.96 }}
                transition={{ type: 'spring', stiffness: 400, damping: 25 }}
              >
                {qText.startsWith('Summarise') && <Sparkles size={12} />}
                <span>{qText}</span>
              </motion.button>
            ))}
          </div>
        </div>

        {/* Input Area */}
        <div className="case-chat-input-area">
          <form
            className="chat-input-form"
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
          >
            <textarea
              ref={inputRef}
              className="chat-input-field"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about this case..."
              aria-label="Ask anything about this case"
              disabled={isLoading}
            />

            <motion.button
              type="submit"
              className="chat-send-btn"
              disabled={isLoading || !input.trim()}
              title="Send question"
              aria-label="Send question"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.94 }}
            >
              <Send size={15} />
            </motion.button>
          </form>

          <div className="chat-footer-disclaimer">
            <span>AI answer, not legal advice &bull; Strictly grounded in case records</span>
          </div>
        </div>
      </motion.aside>
    </>
  );
}
