import React, { useState, useEffect } from 'react';
import { Command, Search, Cpu, Menu, X, ShieldCheck } from 'lucide-react';

export default function Header({ 
  activeTab, 
  setActiveTab, 
  onOpenCommandPalette, 
  onOpenAgentModal,
  isMobileSidebarOpen,
  onToggleMobileSidebar 
}) {
  const [backendHealth, setBackendHealth] = useState({
    status: 'checking', // 'healthy', 'offline', 'checking'
    model: 'gemini-3.8-flash',
    systemMode: null
  });

  // Poll GET http://localhost:8000/health
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    const checkHealth = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/health', {
          method: 'GET',
          signal: controller.signal,
          headers: { 'Accept': 'application/json' }
        });
        if (!isMounted) return;
        if (res.ok) {
          const data = await res.json();
          setBackendHealth({
            status: 'healthy',
            model: data.enforced_model || 'gemini-3.8-flash',
            systemMode: data.system_mode || 'ONLINE'
          });
        } else {
          setBackendHealth(prev => ({ ...prev, status: 'offline' }));
        }
      } catch (err) {
        if (!isMounted) return;
        setBackendHealth(prev => ({ ...prev, status: 'offline' }));
      }
    };

    // Initial check
    checkHealth();

    // Poll every 12 seconds
    const interval = setInterval(checkHealth, 12000);

    return () => {
      isMounted = false;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="workspace-topbar">
      <div className="topbar-inner">
        {/* Left: Mobile Toggle & Brand */}
        <div className="topbar-left">
          {onToggleMobileSidebar && (
            <button 
              type="button" 
              className="topbar-mobile-toggle"
              onClick={onToggleMobileSidebar}
              aria-label="Toggle Navigation Menu"
            >
              {isMobileSidebarOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          )}

          <div className="topbar-brand" onClick={() => setActiveTab && setActiveTab('search')}>
            <span className="brand-title-serif">JUSTICE</span>
            <span className="brand-chip">LEGAL WORKSPACE</span>
          </div>
        </div>

        {/* Center: Omni-Search Trigger Button */}
        <div className="topbar-center">
          <button 
            type="button" 
            className="topbar-omni-trigger" 
            onClick={onOpenCommandPalette}
            title="Press Ctrl+K or ⌘K to open command palette"
          >
            <Search size={14} className="omni-search-icon" />
            <span className="omni-search-text">Search precedents, statutes, citations...</span>
            <kbd className="omni-kbd">⌘K</kbd>
          </button>
        </div>

        {/* Right: Backend Health Dot & Quick Traces */}
        <div className="topbar-right">
          {/* Backend Health Dot */}
          <div 
            className={`backend-health-pill status-${backendHealth.status}`}
            title={`Backend: http://localhost:8000/health (${backendHealth.status})`}
          >
            <span className="health-dot" />
            <span className="health-label">
              {backendHealth.status === 'healthy' && 'FastAPI Active'}
              {backendHealth.status === 'offline' && 'Backend Offline'}
              {backendHealth.status === 'checking' && 'Connecting...'}
            </span>
            {backendHealth.status === 'healthy' && (
              <span className="health-model-badge mono">{backendHealth.model}</span>
            )}
          </div>

          {/* Quick Agent Visualizer Trigger */}
          {onOpenAgentModal && (
            <button 
              type="button" 
              className="topbar-agent-btn"
              onClick={onOpenAgentModal}
              title="Inspect LangGraph Agent DAG Execution"
            >
              <Cpu size={14} />
              <span className="agent-btn-text">Agent DAG</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
