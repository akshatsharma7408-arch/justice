import React, { useState, useEffect } from 'react';
import { Search, CornerDownLeft, X, Sparkles, Scale, FileText, SlidersHorizontal, BookOpen } from 'lucide-react';

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
      id: 'maxims-module',
      title: "Explore Latin Legal Maxims Compendium (240+ Canons & Flashcards)",
      category: "Legal Maxims",
      icon: BookOpen,
      action: () => {
        onNavigate('maxims');
        onClose();
      }
    },
    {
      id: 'maxim-audi',
      title: "Maxim: Audi alteram partem (Listen to the other side / Natural Justice)",
      category: "Legal Maxims",
      icon: BookOpen,
      action: () => {
        onNavigate('maxims');
        onClose();
      }
    },
    {
      id: 'maxim-mens-rea',
      title: "Maxim: Actus non facit reum nisi mens sit rea (Mental intent in crime)",
      category: "Legal Maxims",
      icon: BookOpen,
      action: () => {
        onNavigate('maxims');
        onClose();
      }
    },
    {
      id: 'maxim-nemo-judex',
      title: "Maxim: Nemo judex in causa sua (Rule against bias / Natural Justice)",
      category: "Legal Maxims",
      icon: BookOpen,
      action: () => {
        onNavigate('maxims');
        onClose();
      }
    },
    {
      id: 'maxim-res-ipsa',
      title: "Maxim: Res ipsa loquitur (The thing speaks for itself / Negligence)",
      category: "Legal Maxims",
      icon: BookOpen,
      action: () => {
        onNavigate('maxims');
        onClose();
      }
    },
    {
      id: 'maxim-ubi-jus',
      title: "Maxim: Ubi jus ibi remedium (Where there is a right, there is a remedy)",
      category: "Legal Maxims",
      icon: BookOpen,
      action: () => {
        onNavigate('maxims');
        onClose();
      }
    },
    {
      id: 'search-noncompete',
      title: "Query Section 27 non-compete enforceability",
      category: "Universal Search",
      icon: Search,
      action: () => {
        onNavigate('search');
        onClose();
      }
    },
    {
      id: 'citator-percept',
      title: "Verify Shepard status: Percept D'Mark v. Zaheer Khan",
      category: "Smart Citator",
      icon: Scale,
      action: () => {
        onNavigate('citator', false, 'sc-2006-percept');
        onClose();
      }
    },
    {
      id: 'citator-puttaswamy',
      title: "Inspect 9-Judge Bench overruling ADM Jabalpur (Puttaswamy)",
      category: "Smart Citator",
      icon: Scale,
      action: () => {
        onNavigate('citator', false, 'sc-2017-puttaswamy');
        onClose();
      }
    },
    {
      id: 'analyzer-contract',
      title: "Audit Technology Consultant Agreement & Auto-Redline Clause 9.3",
      category: "Document Analyzer",
      icon: FileText,
      action: () => {
        onNavigate('analyzer');
        onClose();
      }
    },
    {
      id: 'compare-manupatra',
      title: "Inspect Legacy Manupatra vs. Justice Workspace UI Critique",
      category: "Comparison",
      icon: SlidersHorizontal,
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
    <div className="palette-overlay" onClick={onClose}>
      <div className="palette-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input-header">
          <Search size={18} className="palette-search-icon" />
          <input
            type="text"
            className="palette-search-input"
            autoFocus
            placeholder="Type a command or search query (e.g. 'Section 27' or 'Citator')..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <button 
            type="button" 
            className="palette-close-btn" 
            onClick={onClose} 
            aria-label="Close Command Palette"
          >
            <X size={16} />
          </button>
        </div>

        <div className="palette-results-container">
          <div className="palette-group-label">SUGGESTED DISCOVERY & NAVIGATION</div>
          {filtered.length === 0 ? (
            <div className="palette-empty-note">
              No matching actions found. Press <kbd>ENTER</kbd> to query the legal corpus.
            </div>
          ) : (
            filtered.map((item) => {
              const IconComp = item.icon || Search;
              return (
                <div
                  key={item.id}
                  className="palette-item-card"
                  onClick={item.action}
                >
                  <div className="palette-item-icon-box">
                    <IconComp size={15} />
                  </div>
                  <div className="palette-item-body">
                    <div className="palette-item-category mono">{item.category}</div>
                    <div className="palette-item-title">{item.title}</div>
                  </div>
                  <CornerDownLeft size={13} className="palette-item-enter-icon" />
                </div>
              );
            })
          )}
        </div>

        <div className="palette-dialog-footer">
          <div className="palette-hint-group">
            <span>NAVIGATE <kbd className="palette-kbd">&uarr;</kbd> <kbd className="palette-kbd">&darr;</kbd></span>
            <span>SELECT <kbd className="palette-kbd">ENTER</kbd></span>
            <span>DISMISS <kbd className="palette-kbd">ESC</kbd></span>
          </div>
          <span className="palette-engine-tag mono">JUSTICE OMNI-INTENT</span>
        </div>
      </div>
    </div>
  );
}
