import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Search, Scale, FileText, MessageSquare, SlidersHorizontal, BookOpen, Cpu, X, Menu } from 'lucide-react';
import { BACKEND_URL } from '../config/gemini';

const MODULES = [
  { id: 'search', label: 'Search Precedents, Statutes and Citations' },
  { id: 'citator', label: 'Smart Citator' },
  { id: 'documents', label: 'Documents' },
  { id: 'comparison', label: 'Comparison' },
  { id: 'maxims', label: 'Legal Maxims' },
];

export default function Navbar({
  activeView,
  onNavigate,
  onSearchSubmit,
  searchQuery = '',
  onOpenCommandPalette,
  onOpenAgentModal,
  isSticky = true
}) {
  const [localQuery, setLocalQuery] = useState(searchQuery);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [backendHealth, setBackendHealth] = useState({
    status: 'checking',
    model: 'openai/gpt-oss-120b'
  });

  useEffect(() => {
    setLocalQuery(searchQuery);
  }, [searchQuery]);

  // Check backend health
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    const check = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`, {
          method: 'GET',
          signal: controller.signal,
          headers: { Accept: 'application/json' }
        });
        if (!isMounted) return;
        if (res.ok) {
          const data = await res.json();
          setBackendHealth({
            status: 'healthy',
            model: data.enforced_model || 'openai/gpt-oss-120b'
          });
        } else {
          setBackendHealth(prev => ({ ...prev, status: 'offline' }));
        }
      } catch {
        if (!isMounted) return;
        setBackendHealth(prev => ({ ...prev, status: 'offline' }));
      }
    };

    check();
    const interval = setInterval(check, 12000);
    return () => {
      isMounted = false;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    const q = localQuery.trim();
    if (!q) return;
    if (onSearchSubmit) {
      onSearchSubmit(q);
    } else if (onNavigate) {
      onNavigate('search', q);
    }
  };

  return (
    <header className={`top-navbar ${isSticky ? 'is-sticky' : ''}`} role="banner">
      <div className="navbar-container">
        {/* Brand Wordmark: Cormorant Garamond 600 weight with copper dot */}
        <div className="navbar-brand-col">
          <button
            type="button"
            className="navbar-brand-btn"
            onClick={() => onNavigate('landing')}
            aria-label="Justice Home"
          >
            <span className="justice-wordmark">
              Justice<span className="copper-dot">.</span>
            </span>
          </button>
        </div>

        {/* Center: Compact Search Bar */}
        <div className="navbar-search-col">
          <form className="navbar-compact-search-form" onSubmit={handleSearch}>
            <Search size={14} className="navbar-search-icon" aria-hidden="true" />
            <input
              type="text"
              className="navbar-search-input"
              placeholder="Search precedents, statutes, citations..."
              value={localQuery}
              onChange={(e) => setLocalQuery(e.target.value)}
              aria-label="Search precedents, statutes and citations"
            />
            <button
              type="button"
              className="navbar-kbd-hint"
              onClick={onOpenCommandPalette}
              title="Open command palette (Ctrl+K or ⌘K)"
            >
              <kbd className="mono">⌘K</kbd>
            </button>
          </form>
        </div>

        {/* Right: Module Links (desktop row / mobile swipeable chip row) */}
        <nav className="navbar-modules-nav" aria-label="Workspace Modules">
          <div className="modules-row">
            {MODULES.map((m) => {
              const isActive = activeView === m.id || (m.id === 'documents' && (activeView === 'analyzer' || activeView === 'docchat'));
              return (
                <motion.button
                  key={m.id}
                  type="button"
                  className={`module-link-btn ${isActive ? 'is-active' : ''}`}
                  onClick={() => onNavigate(m.id)}
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.97 }}
                >
                  <span className="module-link-text">{m.label}</span>
                  {isActive && (
                    <motion.span
                      layoutId="activeNavUnderline"
                      className="module-active-bar"
                      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                    />
                  )}
                </motion.button>
              );
            })}
          </div>
        </nav>

        {/* Utility Actions (Status dot & Agent DAG trigger) */}
        <div className="navbar-actions-col">
          <div
            className={`navbar-health-pill status-${backendHealth.status}`}
            title={`FastAPI backend: ${backendHealth.status}`}
          >
            <span className="health-dot" />
            <span className="health-label mono">
              {backendHealth.status === 'healthy' ? 'Active' : 'Connecting'}
            </span>
          </div>

          {onOpenAgentModal && (
            <button
              type="button"
              className="navbar-dag-btn"
              onClick={onOpenAgentModal}
              title="Inspect LangGraph Agent DAG Execution"
              aria-label="Inspect LangGraph Agent DAG"
            >
              <Cpu size={14} />
              <span className="dag-btn-text">Agent DAG</span>
            </button>
          )}

          {/* Mobile Menu Toggle */}
          <button
            type="button"
            className="navbar-mobile-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? 'Close Menu' : 'Open Menu'}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="navbar-mobile-drawer animate-fade-in">
          <div className="mobile-drawer-inner">
            <div className="mobile-drawer-label mono">WORKSPACE MODULES</div>
            <div className="mobile-drawer-list">
              {MODULES.map((m) => {
                const isActive = activeView === m.id || (m.id === 'documents' && (activeView === 'analyzer' || activeView === 'docchat'));
                return (
                  <button
                    key={m.id}
                    type="button"
                    className={`mobile-drawer-item ${isActive ? 'is-active' : ''}`}
                    onClick={() => {
                      onNavigate(m.id);
                      setMobileMenuOpen(false);
                    }}
                  >
                    <span>{m.label}</span>
                    {isActive && <span className="mobile-active-dot" />}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
