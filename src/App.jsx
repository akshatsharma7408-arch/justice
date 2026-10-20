import React, { useState, useEffect, lazy, Suspense } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Navbar from './components/Navbar';
import LandingPage from './components/LandingPage';
import TextSelectionToolbar from './components/TextSelectionToolbar';
import { ScrollProgressBar, SoftCursorFollower } from './components/InteractiveEffects';
import { AgentExecutionSession } from './services/agentEngine';

// Lazy-load heavy module views and modals to optimize Landing Page performance (Lighthouse > 85)
const SearchResults = lazy(() => import('./components/SearchResults'));
const SmartCitator = lazy(() => import('./components/SmartCitator'));
const DocumentAnalyzer = lazy(() => import('./components/DocumentAnalyzer'));
const DocumentChat = lazy(() => import('./components/DocumentChat'));
const Documents = lazy(() => import('./components/Documents'));
const PrecedentComparison = lazy(() => import('./components/PrecedentComparison'));
const LegalMaxims = lazy(() => import('./components/LegalMaxims'));
const CaseChatPanel = lazy(() => import('./components/CaseChatPanel'));
const AgentVisualizerModal = lazy(() => import('./components/AgentVisualizerModal'));
const CommandPalette = lazy(() => import('./components/CommandPalette'));
const ExplainSelectionModal = lazy(() => import('./components/ExplainSelectionModal'));

export default function App() {
  // Navigation: 'landing' (default first page), 'search', 'citator', 'analyzer', 'docchat', 'comparison', 'maxims'
  const [activeView, setActiveView] = useState('landing');
  const [activeSearchQuery, setActiveSearchQuery] = useState('');
  const [selectedCitatorCaseId, setSelectedCitatorCaseId] = useState('sc-2006-percept');

  // Modals & Panels
  const [isAgentModalOpen, setIsAgentModalOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [agentSessionState, setAgentSessionState] = useState(null);
  const [isAgentRunning, setIsAgentRunning] = useState(false);

  // Active case for Case Chat scoping (null by default; opened only when user selects a case)
  const [activeCase, setActiveCase] = useState(null);

  // Persist Case Chat panel collapsed state in localStorage
  const [isCaseChatOpen, setIsCaseChatOpen] = useState(() => {
    try {
      return localStorage.getItem('justice_case_chat_open') !== 'false';
    } catch {
      return true;
    }
  });

  const [caseChatExternalPrompt, setCaseChatExternalPrompt] = useState(null);

  // Global Explain Selection state
  const [isExplainModalOpen, setIsExplainModalOpen] = useState(false);
  const [standaloneExplainText, setStandaloneExplainText] = useState('');
  const [standaloneExplainContext, setStandaloneExplainContext] = useState(null);
  const [standaloneExplainCaseId, setStandaloneExplainCaseId] = useState(null);

  const handleToggleCaseChat = () => {
    setIsCaseChatOpen(prev => {
      const next = !prev;
      try {
        localStorage.setItem('justice_case_chat_open', String(next));
      } catch (e) {}
      return next;
    });
  };

  // Global Keyboard Shortcuts: Ctrl+K focuses universal search; Esc dismisses modals/palette
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const heroInput = document.querySelector('.hero-search-input');
        const searchInput = document.querySelector('.module-search-input');
        const navbarInput = document.querySelector('.navbar-search-input');
        if (heroInput && document.activeElement !== heroInput) {
          heroInput.focus();
        } else if (searchInput && document.activeElement !== searchInput) {
          searchInput.focus();
        } else if (navbarInput && document.activeElement !== navbarInput) {
          navbarInput.focus();
        } else {
          setIsCommandPaletteOpen(prev => !prev);
        }
      }
      if (e.key === 'Escape') {
        setIsCommandPaletteOpen(false);
        setIsAgentModalOpen(false);
        setIsExplainModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  const handleNavigate = (view, query = '') => {
    setActiveView(view);
    if (query) {
      setActiveSearchQuery(query);
    }
    if (view !== 'citator') {
      setActiveCase(null);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSearchSubmit = (query) => {
    setActiveSearchQuery(query);
    setActiveCase(null);
    setActiveView('search');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleTriggerGlobalExplain = (selectedText) => {
    setStandaloneExplainText(selectedText);

    if (activeView === 'citator' || (activeView === 'search' && activeCase)) {
      const cId = activeCase?.id || selectedCitatorCaseId || null;
      const cTitle = activeCase?.title || 'Supreme Court Judgment';
      setStandaloneExplainCaseId(cId);
      setStandaloneExplainContext(`Case: ${cTitle}`);
      setIsExplainModalOpen(true);
      return;
    }

    if (activeView === 'documents' || activeView === 'analyzer' || activeView === 'docchat') {
      setStandaloneExplainCaseId(null);
      setStandaloneExplainContext("Document & Clause Audit Context");
      setIsExplainModalOpen(true);
      return;
    }

    if (activeView === 'maxims') {
      setStandaloneExplainCaseId(null);
      setStandaloneExplainContext("Legal Maxim Doctrine");
      setIsExplainModalOpen(true);
      return;
    }

    setStandaloneExplainCaseId(null);
    setStandaloneExplainContext(null);
    setIsExplainModalOpen(true);
  };

  const handleOpenCaseChatFromSearch = (precedent) => {
    if (!precedent) {
      setActiveCase(null);
      return;
    }
    setActiveCase({
      id: precedent.id,
      title: precedent.title,
      citation: precedent.citation
    });
    setIsCaseChatOpen(true);
    try {
      localStorage.setItem('justice_case_chat_open', 'true');
    } catch (e) {}
  };

  const handleSelectCaseForCitator = (precedent) => {
    setSelectedCitatorCaseId(precedent.id);
    setActiveView('citator');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleTriggerAgentAnalysis = (clause, contractTitle) => {
    setIsAgentModalOpen(true);
    setIsAgentRunning(true);

    const session = new AgentExecutionSession(
      (update) => setAgentSessionState(update),
      () => setIsAgentRunning(false)
    );

    session.runAnalysis(clause, contractTitle);
  };

  const handleCommandNavigate = (target, openOnly = false, caseId = null) => {
    if (openOnly) {
      setIsCommandPaletteOpen(true);
      return;
    }
    if (target) {
      setActiveView(target);
    }
    if (caseId) {
      setSelectedCitatorCaseId(caseId);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Case Chat should show alongside only when a specific case is opened
  const showCaseChatBeside = (activeView === 'citator' || activeView === 'search') && Boolean(activeCase);

  return (
    <div className="justice-app-root">
      {/* Persistent Top Navbar on all non-landing module pages */}
      {activeView !== 'landing' && (
        <Navbar
          activeView={activeView}
          onNavigate={handleNavigate}
          onSearchSubmit={handleSearchSubmit}
          searchQuery={activeSearchQuery}
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
          onOpenAgentModal={() => setIsAgentModalOpen(true)}
        />
      )}

      {/* Main View Area */}
      <div className={`justice-view-layout ${showCaseChatBeside && isCaseChatOpen ? 'has-case-chat' : ''}`}>
        <main className="justice-main-view">
          <Suspense fallback={
            <div className="module-view-container animate-fade-in">
              <div className="skeleton-cards-stack">
                <div className="skeleton-card">
                  <div className="skeleton-line skeleton-shimmer" style={{ width: '30%' }} />
                  <div className="skeleton-title skeleton-shimmer" />
                  <div className="skeleton-block skeleton-shimmer" />
                </div>
              </div>
            </div>
          }>
            <AnimatePresence mode="wait">
              <motion.div
                key={activeView}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                style={{ display: 'flex', flexDirection: 'column', flex: 1, width: '100%' }}
              >
                {/* 1. LANDING PAGE VIEW */}
                {activeView === 'landing' && (
                  <LandingPage
                    onNavigate={handleNavigate}
                    onSearchSubmit={handleSearchSubmit}
                    onOpenCaseChat={handleOpenCaseChatFromSearch}
                    onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
                  />
                )}

                {/* 2. SEARCH RESULTS MODULE */}
                {activeView === 'search' && (
                  <SearchResults
                    initialQuery={activeSearchQuery}
                    onSelectCaseForCitator={handleSelectCaseForCitator}
                    onOpenCaseChat={handleOpenCaseChatFromSearch}
                    onSearchAgain={(q) => {
                      setActiveSearchQuery(q);
                      setActiveCase(null);
                    }}
                  />
                )}

                {/* 3. SMART CITATOR MODULE */}
                {activeView === 'citator' && (
                  <SmartCitator
                    key={selectedCitatorCaseId}
                    initialCaseId={selectedCitatorCaseId}
                    onActiveCaseChange={setActiveCase}
                  />
                )}

                {/* 4. DOCUMENTS UNIFIED WORKSPACE (Analysis, Multi-image OCR, & Document Chat) */}
                {(activeView === 'documents' || activeView === 'analyzer' || activeView === 'docchat') && (
                  <Documents
                    onTriggerAgentAnalysis={handleTriggerAgentAnalysis}
                  />
                )}

                {/* 5. COMPARISON MODULE */}
                {activeView === 'comparison' && (
                  <PrecedentComparison
                    onSwitchToWorkspace={() => handleNavigate('documents')}
                  />
                )}

                {/* 7. LEGAL MAXIMS MODULE */}
                {activeView === 'maxims' && (
                  <LegalMaxims />
                )}
              </motion.div>
            </AnimatePresence>
          </Suspense>
        </main>

        {/* Case Chat Panel alongside open case on search or citator view */}
        {showCaseChatBeside && (
          <Suspense fallback={null}>
            <CaseChatPanel
              caseId={activeCase?.id || selectedCitatorCaseId}
              caseTitle={activeCase?.title}
              caseCitation={activeCase?.citation}
              isOpen={isCaseChatOpen}
              onToggle={handleToggleCaseChat}
              externalPrompt={caseChatExternalPrompt}
              onClearExternalPrompt={() => setCaseChatExternalPrompt(null)}
            />
          </Suspense>
        )}
      </div>

      {/* Real-time Agent StateGraph Visualizer Modal */}
      <Suspense fallback={null}>
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

        {/* Standalone Explain Selection Modal / Bottom Sheet */}
        <ExplainSelectionModal
          isOpen={isExplainModalOpen}
          onClose={() => {
            setIsExplainModalOpen(false);
            setStandaloneExplainText('');
            setStandaloneExplainCaseId(null);
            setStandaloneExplainContext(null);
          }}
          selectedText={standaloneExplainText}
          context={standaloneExplainContext}
          caseId={standaloneExplainCaseId}
        />
      </Suspense>

      {/* Global Text Selection Toolbar (Floats near selection 3-1500 chars) */}
      <TextSelectionToolbar
        onTriggerExplain={handleTriggerGlobalExplain}
      />
    </div>
  );
}
