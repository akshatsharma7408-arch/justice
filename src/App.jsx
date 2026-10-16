import React, { useState } from 'react';
import Header from './components/Header';
import Footer from './components/Footer';
import UniversalSearch from './components/UniversalSearch';
import SmartCitator from './components/SmartCitator';
import DocumentAnalyzer from './components/DocumentAnalyzer';
import ManupatraComparison from './components/ManupatraComparison';
import AgentVisualizerModal from './components/AgentVisualizerModal';
import CommandPalette from './components/CommandPalette';
import { AgentExecutionSession } from './services/agentEngine';

export default function App() {
  const [activeTab, setActiveTab] = useState('analyzer'); // default to analyzer to showcase document review & redlines
  const [selectedCitatorCaseId, setSelectedCitatorCaseId] = useState('sc-2006-percept');
  const [isAgentModalOpen, setIsAgentModalOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [agentSessionState, setAgentSessionState] = useState(null);
  const [isAgentRunning, setIsAgentRunning] = useState(false);

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
    <div className="app-shell">
      {/* Primary Clean Navigation */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
      />

      {/* Main Workspace Stage */}
      <main className="workspace-main">
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
      </main>

      {/* Subtle Editorial Footer */}
      <Footer
        onOpenComparison={() => setActiveTab('comparison')}
        onOpenAgentModal={() => setIsAgentModalOpen(true)}
      />

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
