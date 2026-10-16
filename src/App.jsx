import React, { useState } from 'react';
import { Search, Scale, FileText, SlidersHorizontal, Cpu, BookOpen } from 'lucide-react';
import Header from './components/Header';
import Footer from './components/Footer';
import UniversalSearch from './components/UniversalSearch';
import SmartCitator from './components/SmartCitator';
import DocumentAnalyzer from './components/DocumentAnalyzer';
import ManupatraComparison from './components/ManupatraComparison';
import LegalMaxims from './components/LegalMaxims';
import AgentVisualizerModal from './components/AgentVisualizerModal';
import CommandPalette from './components/CommandPalette';
import { AgentExecutionSession } from './services/agentEngine';

export default function App() {
  const [activeTab, setActiveTab] = useState('analyzer'); // default to analyzer
  const [selectedCitatorCaseId, setSelectedCitatorCaseId] = useState('sc-2006-percept');
  const [isAgentModalOpen, setIsAgentModalOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [agentSessionState, setAgentSessionState] = useState(null);
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // Jump from search to citator
  const handleSelectCaseForCitator = (precedent) => {
    setSelectedCitatorCaseId(precedent.id);
    setActiveTab('citator');
  };

  // Launch agent analysis workflow
  const handleTriggerAgentAnalysis = (clause, contractTitle) => {
    setIsAgentModalOpen(true);
    setIsAgentRunning(true);

    const session = new AgentExecutionSession(
      (update) => {
        setAgentSessionState(update);
      },
      (completion) => {
        setIsAgentRunning(false);
      }
    );

    session.runAnalysis(clause, contractTitle);
  };

  // Command palette navigation
  const handleCommandNavigate = (tab, openOnly = false, caseId = null) => {
    if (openOnly) {
      setIsCommandPaletteOpen(true);
      return;
    }
    if (tab) setActiveTab(tab);
    if (caseId) setSelectedCitatorCaseId(caseId);
  };

  return (
    <div className="workspace-app-shell">
      {/* Slim Top Bar Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        onOpenAgentModal={() => setIsAgentModalOpen(true)}
        isMobileSidebarOpen={isMobileSidebarOpen}
        onToggleMobileSidebar={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
      />

      {/* Main Workspace Frame with Fixed Left Sidebar */}
      <div className="workspace-body-layout">
        {/* Mobile Backdrop */}
        {isMobileSidebarOpen && (
          <div 
            className="sidebar-backdrop" 
            onClick={() => setIsMobileSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Fixed Left Navigation Sidebar */}
        <aside className={`workspace-sidebar ${isMobileSidebarOpen ? 'mobile-open' : ''}`}>
          <div className="sidebar-content-wrap">
            <div className="sidebar-group-label">WORKSPACE MODULES</div>

            <nav className="sidebar-nav-list" aria-label="Workspace Modules">
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === 'search' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('search');
                  setIsMobileSidebarOpen(false);
                }}
              >
                <div className="sidebar-nav-icon">
                  <Search size={16} />
                </div>
                <div className="sidebar-nav-text">
                  <span className="sidebar-nav-title">Universal Search</span>
                  <span className="sidebar-nav-desc">Neural Precedents & HyDE</span>
                </div>
              </button>

              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === 'citator' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('citator');
                  setIsMobileSidebarOpen(false);
                }}
              >
                <div className="sidebar-nav-icon">
                  <Scale size={16} />
                </div>
                <div className="sidebar-nav-text">
                  <span className="sidebar-nav-title">Smart Citator</span>
                  <span className="sidebar-nav-desc">Article 141 Lineage DAG</span>
                </div>
                <span className="sidebar-module-tag">Art. 141</span>
              </button>

              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === 'analyzer' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('analyzer');
                  setIsMobileSidebarOpen(false);
                }}
              >
                <div className="sidebar-nav-icon">
                  <FileText size={16} />
                </div>
                <div className="sidebar-nav-text">
                  <span className="sidebar-nav-title">Document Analyzer</span>
                  <span className="sidebar-nav-desc">Section 27 Redline Audit</span>
                </div>
                <span className="sidebar-module-tag redline">Redline</span>
              </button>

              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === 'comparison' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('comparison');
                  setIsMobileSidebarOpen(false);
                }}
              >
                <div className="sidebar-nav-icon">
                  <SlidersHorizontal size={16} />
                </div>
                <div className="sidebar-nav-text">
                  <span className="sidebar-nav-title">Comparison</span>
                  <span className="sidebar-nav-desc">Legacy System Critique</span>
                </div>
              </button>

              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === 'maxims' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('maxims');
                  setIsMobileSidebarOpen(false);
                }}
              >
                <div className="sidebar-nav-icon">
                  <BookOpen size={16} />
                </div>
                <div className="sidebar-nav-text">
                  <span className="sidebar-nav-title">Legal Maxims</span>
                  <span className="sidebar-nav-desc">Latin Canons & Flashcards</span>
                </div>
                <span className="sidebar-module-tag">240+</span>
              </button>
            </nav>
          </div>

          {/* Sidebar Status Footer Card */}
          <div className="sidebar-bottom-panel">
            <div className="sidebar-card">
              <div className="sidebar-card-header">
                <span className="sidebar-card-indicator" />
                <span className="sidebar-card-badge">CONSTITUTIONAL ENGINE</span>
              </div>
              <p className="sidebar-card-text">
                Enforcing Article 141 judicial hierarchy across Supreme Court & High Court benches.
              </p>
              <button 
                type="button" 
                className="sidebar-card-action"
                onClick={() => setIsAgentModalOpen(true)}
              >
                <Cpu size={13} />
                <span>Inspect Agent DAG</span>
              </button>
            </div>
          </div>
        </aside>

        {/* Center Workspace Scroll Pane */}
        <div className="workspace-main-area">
          <main className="workspace-main-scroll">
            {activeTab === 'search' && (
              <UniversalSearch onSelectCaseForCitator={handleSelectCaseForCitator} />
            )}

            {activeTab === 'citator' && (
              <SmartCitator
                key={selectedCitatorCaseId}
                initialCaseId={selectedCitatorCaseId}
              />
            )}

            {activeTab === 'analyzer' && (
              <DocumentAnalyzer
                onTriggerAgentAnalysis={handleTriggerAgentAnalysis}
              />
            )}

            {activeTab === 'comparison' && (
              <ManupatraComparison
                onSwitchToWorkspace={() => setActiveTab('analyzer')}
              />
            )}

            {activeTab === 'maxims' && (
              <LegalMaxims />
            )}

            {/* Bottom Status Footer */}
            <Footer
              onOpenComparison={() => setActiveTab('comparison')}
              onOpenAgentModal={() => setIsAgentModalOpen(true)}
            />
          </main>
        </div>
      </div>

      {/* Real-time Agent StateGraph Visualizer Modal */}
      <AgentVisualizerModal
        isOpen={isAgentModalOpen}
        onClose={() => setIsAgentModalOpen(false)}
        sessionState={agentSessionState}
        isRunning={isAgentRunning}
      />

      {/* Global Omni-Command Palette (Ctrl+K / ⌘K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={handleCommandNavigate}
      />
    </div>
  );
}
