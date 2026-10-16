import React, { useState, useEffect } from 'react';
import { Search, CornerDownLeft, X } from 'lucide-react';

export default function CommandPalette({ isOpen, onClose, onNavigate }) {
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else onNavigate(null, true); // trigger open
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, onNavigate]);

  if (!isOpen) return null;

  const quickActions = [
    {
      id: 'search-noncompete',
      title: "Query Section 27 non-compete enforceability",
      category: "Universal Search",
      action: () => {
        onNavigate('search');
        onClose();
      }
    },
    {
      id: 'citator-percept',
      title: "Verify Shepard status: Percept D'Mark v. Zaheer Khan",
      category: "Smart Citator",
      action: () => {
        onNavigate('citator', false, 'sc-2006-percept');
        onClose();
      }
    },
    {
      id: 'citator-puttaswamy',
      title: "Inspect 9-Judge Bench overruling ADM Jabalpur (Puttaswamy)",
      category: "Smart Citator",
      action: () => {
        onNavigate('citator', false, 'sc-2017-puttaswamy');
        onClose();
      }
    },
    {
      id: 'analyzer-contract',
      title: "Audit Technology Consultant Agreement & Auto-Redline Clause 9.3",
      category: "Document Analyzer",
      action: () => {
        onNavigate('analyzer');
        onClose();
      }
    },
    {
      id: 'compare-manupatra',
      title: "Inspect Legacy Manupatra vs. Justice Editorial UI Critique",
      category: "Architectural Comparison",
      action: () => {
        onNavigate('comparison');
        onClose();
      }
    }
  ];

  const filtered = quickActions.filter(item =>
    item.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="command-palette-box" onClick={(e) => e.stopPropagation()}>
        <div className="command-input-row">
          <Search size={18} className="command-icon-stark" />
          <input
            type="text"
            className="command-input"
            autoFocus
            placeholder="TYPE COMMAND OR SEARCH QUERY (E.G. 'SECTION 27' OR 'CITATOR')..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <button className="btn-close-palette" onClick={onClose} aria-label="Close Command Palette">
            <X size={18} />
          </button>
        </div>

        <div className="command-results-list">
          <div className="command-group-heading">SUGGESTED DISCOVERY & NAVIGATION</div>
          {filtered.length === 0 ? (
            <div className="command-no-results">
              No matching actions found. Press <kbd>ENTER</kbd> to search legal corpus.
            </div>
          ) : (
            filtered.map((item) => (
              <div
                key={item.id}
                className="command-item"
                onClick={item.action}
              >
                <div className="command-item-left">
                  <span className="command-item-category">{item.category}</span>
                  <div className="command-item-title">{item.title}</div>
                </div>
                <CornerDownLeft size={13} className="command-item-arrow" />
              </div>
            ))
          )}
        </div>

        <div className="command-palette-footer">
          <span>NAVIGATE <kbd>&uarr;</kbd> <kbd>&darr;</kbd></span>
          <span>SELECT <kbd>ENTER</kbd></span>
          <span>CLOSE <kbd>ESC</kbd></span>
        </div>
      </div>
    </div>
  );
}
