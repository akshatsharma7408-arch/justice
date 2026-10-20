import React, { useState, useEffect } from 'react';
import { Sparkles, X, Copy, Check, Scale, AlertCircle } from 'lucide-react';
import { explainSelectedText } from '../config/gemini';

export default function ExplainSelectionModal({
  isOpen,
  onClose,
  selectedText,
  context = null,
  caseId = null
}) {
  const [loading, setLoading] = useState(false);
  const [explanationData, setExplanationData] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  // Close on Escape key press
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Fetch explanation when opened
  useEffect(() => {
    if (!isOpen || !selectedText) {
      setExplanationData(null);
      setError(null);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    explainSelectedText({
      selectedText: selectedText,
      context: context,
      caseId: caseId
    })
      .then(res => {
        if (!isMounted) return;
        setExplanationData(res);
      })
      .catch(err => {
        if (!isMounted) return;
        console.error("[ExplainSelection] Failed:", err);
        setError(err.message || "Failed to generate explanation. Please try again.");
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, selectedText, context, caseId]);

  if (!isOpen) return null;

  const handleCopy = () => {
    const textToCopy = explanationData?.explanation || '';
    if (textToCopy) {
      // Clean raw asterisks when copying plain text
      const cleanText = textToCopy.replace(/\*\*(.*?)\*\*/g, '$1');
      navigator.clipboard?.writeText(cleanText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Helper to format inline markdown (**bold** to <strong>, *italic* to <em>)
  const formatInline = (text) => {
    if (!text) return '';
    const parts = text.split(/(\*\*.*?\*\*|\*.*?\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-semibold text-ivory">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*')) {
        return <em key={i} className="italic text-ivory">{part.slice(1, -1)}</em>;
      }
      return part;
    });
  };

  // Helper to render structured explanation text with real bold and real lists (no raw asterisks)
  const renderFormattedExplanation = (rawText) => {
    if (!rawText) return null;

    // Split on section headers: "In simple words:", "Legal terms explained:", "Why it matters:"
    const sections = rawText.split(/\n\s*\n/);

    return sections.map((sec, idx) => {
      const trimmed = sec.trim();
      if (!trimmed) return null;

      // Section 1: In simple words
      if (trimmed.toLowerCase().startsWith('in simple words:')) {
        const bodyLines = trimmed.replace(/^in simple words:\s*/i, '').split('\n').filter(Boolean);
        return (
          <div key={idx} className="explain-section-block">
            <h4 className="explain-section-title">In simple words</h4>
            <div className="explain-section-paragraphs">
              {bodyLines.map((line, lIdx) => (
                <p key={lIdx} className="explain-section-body font-judicial">
                  {formatInline(line.replace(/^[-*]\s*/, ''))}
                </p>
              ))}
            </div>
          </div>
        );
      }

      // Section 2: Legal terms explained
      if (trimmed.toLowerCase().startsWith('legal terms explained:')) {
        const lines = trimmed.split('\n').slice(1).filter(l => l.trim().length > 0);
        return (
          <div key={idx} className="explain-section-block">
            <h4 className="explain-section-title">Legal terms explained</h4>
            <ul className="explain-terms-list">
              {lines.map((l, lIdx) => {
                // Strip bullet marker and any wrapping raw asterisks on terms
                let cleanLine = l.replace(/^[-*•]\s*/, '').trim();
                const colonIdx = cleanLine.indexOf(':');
                if (colonIdx !== -1) {
                  let rawTerm = cleanLine.substring(0, colonIdx).trim().replace(/^\*\*|\*\*$/g, '');
                  let rawMeaning = cleanLine.substring(colonIdx + 1).trim();
                  return (
                    <li key={lIdx} className="explain-term-item">
                      <strong className="term-name font-mono">{rawTerm}:</strong>
                      <span className="term-meaning">{formatInline(rawMeaning)}</span>
                    </li>
                  );
                }
                return (
                  <li key={lIdx} className="explain-term-item">
                    <span className="term-meaning">{formatInline(cleanLine)}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      }

      // Section 3: Why it matters
      if (trimmed.toLowerCase().startsWith('why it matters:')) {
        const body = trimmed.replace(/^why it matters:\s*/i, '');
        return (
          <div key={idx} className="explain-section-block">
            <h4 className="explain-section-title">Why it matters</h4>
            <p className="explain-section-body font-judicial">
              {formatInline(body)}
            </p>
          </div>
        );
      }

      // Default paragraph block (convert **bold** to real bold)
      return (
        <div key={idx} className="explain-section-block">
          <p className="explain-section-body font-judicial">
            {formatInline(trimmed)}
          </p>
        </div>
      );
    });
  };

  return (
    <div 
      className="explain-modal-backdrop" 
      onClick={onClose} 
      role="dialog" 
      aria-modal="true"
      aria-labelledby="explain-modal-heading"
    >
      <div 
        className="explain-modal-dialog" 
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: '#12261F',
          maxWidth: '640px',
          borderRadius: '20px',
          overflow: 'hidden'
        }}
      >
        {/* Header */}
        <div className="explain-modal-header">
          <div className="explain-header-left">
            <div className="explain-header-badge">
              <Sparkles size={14} className="explain-sparkle-icon" />
              <span>{explanationData?.source || (caseId ? 'Case Judgment' : 'Source: Not from a case')}</span>
            </div>
            <h3 id="explain-modal-heading" className="explain-modal-title font-judicial">
              Explain Selected Text
            </h3>
          </div>

          <button 
            type="button" 
            className="explain-close-btn" 
            onClick={onClose}
            aria-label="Close explanation popup"
          >
            <X size={18} />
          </button>
        </div>

        {/* Selected Quote Banner */}
        <div className="explain-selected-quote">
          <span className="quote-label">SELECTED EXCERPT:</span>
          <blockquote className="quote-text font-judicial">
            "{selectedText}"
          </blockquote>
        </div>

        {/* Body Content */}
        <div className="explain-modal-body">
          {loading ? (
            <div className="explain-loading-state">
              <div className="skeleton-line skeleton-shimmer" style={{ width: '40%', height: '18px' }} />
              <div className="skeleton-block skeleton-shimmer" style={{ height: '70px', marginTop: '10px' }} />
              <div className="skeleton-line skeleton-shimmer" style={{ width: '50%', height: '18px', marginTop: '20px' }} />
              <div className="skeleton-block skeleton-shimmer" style={{ height: '80px', marginTop: '10px' }} />
              <div className="skeleton-line skeleton-shimmer" style={{ width: '35%', height: '18px', marginTop: '20px' }} />
              <div className="skeleton-block skeleton-shimmer" style={{ height: '50px', marginTop: '10px' }} />
            </div>
          ) : error ? (
            <div className="explain-error-box">
              <AlertCircle size={20} className="error-icon" />
              <p className="error-text">{error}</p>
            </div>
          ) : explanationData ? (
            <div className="explain-content-stream">
              {renderFormattedExplanation(explanationData.explanation)}
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="explain-modal-footer">
          <div className="footer-disclaimer-tag">
            <Scale size={12} />
            <span>AI explanation, not verified, not legal advice</span>
          </div>

          <div className="footer-actions">
            {explanationData && (
              <button 
                type="button" 
                className="btn-explain-copy" 
                onClick={handleCopy}
              >
                {copied ? (
                  <>
                    <Check size={14} className="text-emerald" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={14} />
                    <span>Copy explanation</span>
                  </>
                )}
              </button>
            )}

            <button 
              type="button" 
              className="btn-primary-explain-close" 
              onClick={onClose}
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
