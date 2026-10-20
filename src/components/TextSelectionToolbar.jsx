import React, { useState, useEffect, useRef } from 'react';
import { Sparkles } from 'lucide-react';

export default function TextSelectionToolbar({ onTriggerExplain }) {
  const [position, setPosition] = useState(null);
  const [selectedText, setSelectedText] = useState('');
  const toolbarRef = useRef(null);

  useEffect(() => {
    const handleSelectionChange = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        setPosition(null);
        setSelectedText('');
        return;
      }

      const text = selection.toString().trim();
      const words = text.split(/\s+/).filter(Boolean);

      // Minimum 1 word, maximum 800 characters
      if (words.length < 1 || text.length > 800) {
        setPosition(null);
        setSelectedText('');
        return;
      }

      // Check if selection starts or ends inside input boxes, buttons, nav bar, or chat inputs
      const anchorNode = selection.anchorNode;
      const focusNode = selection.focusNode;
      const anchorEl = anchorNode?.nodeType === Node.ELEMENT_NODE ? anchorNode : anchorNode?.parentElement;
      const focusEl = focusNode?.nodeType === Node.ELEMENT_NODE ? focusNode : focusNode?.parentElement;

      const isExcluded = (el) => {
        if (!el) return false;
        return Boolean(
          el.closest(
            'input, textarea, button, select, [contenteditable="true"], nav, header, .site-header, .navbar, .landing-top-bar, .app-nav, .docked-nav, .workspace-sidebar, .workspace-topbar, .case-chat-input-area, .case-chat-textarea, .chat-input, .docchat-input-area, .docchat-input, .case-chat-input, .explain-modal-backdrop, .explain-modal-dialog, .explain-modal-card, .case-chat-quick-buttons-strip'
          )
        );
      };

      if (isExcluded(anchorEl) || isExcluded(focusEl)) {
        setPosition(null);
        setSelectedText('');
        return;
      }

      try {
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) {
          setPosition(null);
          return;
        }

        // Calculate floating position (floating directly above the selection)
        const top = Math.max(10, rect.top - 44);
        const left = Math.max(10, Math.min(window.innerWidth - 130, rect.left + rect.width / 2 - 50));

        setSelectedText(text);
        setPosition({ top, left });
      } catch (err) {
        setPosition(null);
      }
    };

    // Global Ctrl+E / Cmd+E shortcut
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'e' || e.key === 'E')) {
        const selection = window.getSelection();
        if (selection && !selection.isCollapsed) {
          const text = selection.toString().trim();
          const words = text.split(/\s+/).filter(Boolean);
          if (words.length >= 1 && text.length <= 800) {
            e.preventDefault();
            onTriggerExplain(text);
            setPosition(null);
            selection.removeAllRanges();
          }
        }
      }
    };

    const handleScroll = () => {
      setPosition(null);
      setSelectedText('');
    };

    document.addEventListener('mouseup', handleSelectionChange);
    document.addEventListener('touchend', handleSelectionChange);
    document.addEventListener('selectionchange', handleSelectionChange);
    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mouseup', handleSelectionChange);
      document.removeEventListener('touchend', handleSelectionChange);
      document.removeEventListener('selectionchange', handleSelectionChange);
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onTriggerExplain]);

  if (!position || !selectedText) return null;

  const handleButtonClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const textToExplain = selectedText;
    setPosition(null);
    setSelectedText('');
    window.getSelection()?.removeAllRanges();
    onTriggerExplain(textToExplain);
  };

  return (
    <div
      ref={toolbarRef}
      className="floating-explain-toolbar animate-fade-in"
      style={{
        top: `${position.top}px`,
        left: `${position.left}px`
      }}
      role="toolbar"
      aria-label="Explain selection actions"
    >
      <button
        type="button"
        className="floating-explain-btn"
        onMouseDown={(e) => {
          // Prevent losing selection on click
          e.preventDefault();
        }}
        onClick={handleButtonClick}
        title="Explain this in simple words (Ctrl+E)"
        aria-label="Explain this text"
      >
        <Sparkles size={13} className="floating-explain-sparkle" />
        <span className="floating-explain-text">Explain</span>
        <span className="floating-explain-shortcut mono">Ctrl+E</span>
      </button>
    </div>
  );
}
