import React, { useState, useEffect } from 'react';
import { Sparkles, X, Copy, Check, Scale, BookOpen, AlertCircle } from 'lucide-react';
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
      navigator.clipboard?.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Helper to format structured explanation text
  const renderFormattedExplanation = (rawText) => {
    if (!rawText) return null;
    const sections = rawText.split(/\n\s*\n/);
    return sections.map((sec, idx) => {
      const trimmed = sec.trim();
      if (!trimmed) return null;

      // Check section headers
      if (trimmed.toLowerCase().startsWith('in simple words:')) {
        const body = trimmed.replace(/^in simple words:\s*/i, '');
        return (
          <div key={idx} className="explain-section-block">
            <h4 className="explain-section-title">In simple words</h4>
            <p className="explain-section-body font-judicial">{body}</p>
          </div>
        );
      }

      if (trimmed.toLowerCase().startsWith('legal terms explained:')) {
        const lines = trimmed.split('\n').slice(1);
        return (
          <div key={idx} className="explain-section-block">
            <h4 className="explain-section-title">Legal terms explained</h4>
            <ul className="explain-terms-list">
              {lines.map((l, lIdx) => {
                const item = l.replace(/^[-*]\s*/, '').trim();
                if (!item) return null;
                const [term, ...meaningParts] = item.split(':');
                const meaning = meaningParts.join(':');
                return (
                  <li key={lIdx} className="explain-term-item">
                    <strong className="term-name mono">{term?.trim()}:</strong>
                    <span className="term-meaning">{meaning?.trim()}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      }

      if (trimmed.toLowerCase().startsWith('why it matters:')) {
        const body = trimmed.replace(/^why it matters:\s*/i, '');
        return (
          <div key={idx} className="explain-section-block">
            <h4 className="explain-section-title">Why it matters</h4>
            <p className="explain-section-body font-judicial">{body}</p>
          </div>
        );
      }

      return <p key={idx} className="explain-section-body font-judicial">{trimmed}</p>;
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
      >
        {/* Header */}
        <div className="explain-modal-header">
          <div className="explain-header-left">
            <div className="explain-header-badge">
              <Sparkles size={14} className="explain-sparkle-icon" />
              <span>AI Legal Explanation</span>
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
