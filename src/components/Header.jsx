import React from 'react';
import { Command } from 'lucide-react';

export default function Header({ activeTab, setActiveTab, onOpenCommandPalette }) {
  return (
    <header className="header-master">
      <div className="header-inner">
        {/* Brand - Zara Editorial Typography */}
        <div className="brand-group" onClick={() => setActiveTab('search')}>
          <div className="brand-text">
            <div className="brand-title">
              <span className="title-bold">JUSTICE</span>
            </div>
            <div className="brand-tagline">AUTONOMOUS LEGAL INTELLIGENCE &bull; ARCHITECTURE</div>
          </div>
        </div>

        {/* Core Workspace Navigation Tabs */}
        <nav className="nav-tabs" aria-label="Main Navigation">
          <button
            className={`nav-tab-btn ${activeTab === 'search' ? 'active' : ''}`}
            onClick={() => setActiveTab('search')}
          >
            <span>Universal Search</span>
          </button>

          <button
            className={`nav-tab-btn ${activeTab === 'citator' ? 'active' : ''}`}
            onClick={() => setActiveTab('citator')}
          >
            <span>Smart Citator</span>
            <span className="nav-bracket-flag">[Art. 141]</span>
          </button>

          <button
            className={`nav-tab-btn ${activeTab === 'analyzer' ? 'active' : ''}`}
            onClick={() => setActiveTab('analyzer')}
          >
            <span>Document Analyzer</span>
            <span className="nav-bracket-flag">[Redline]</span>
          </button>
        </nav>

        {/* Global Keyboard Action - Minimalist Omni-Command */}
        <div className="header-actions">
          <button 
            className="omni-search-trigger" 
            onClick={onOpenCommandPalette}
            title="Press Ctrl+K or ⌘K to open Omni-Search"
          >
            <Command size={13} />
            <span>Search</span>
            <kbd>⌘K</kbd>
          </button>
        </div>
      </div>
    </header>
  );
}
