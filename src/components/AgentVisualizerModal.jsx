import React from 'react';
import { X, Check, Cpu, Terminal, Sparkles } from 'lucide-react';

export default function AgentVisualizerModal({ isOpen, onClose, sessionState, isRunning }) {
  if (!isOpen) return null;

  const currentStep = sessionState?.currentStep;
  const currentStepIndex = sessionState?.currentStepIndex ?? -1;
  const totalSteps = sessionState?.totalSteps || 7;
  const trace = sessionState?.state?.executionTrace || [];
  const tokensUsed = sessionState?.state?.tokensUsed || 0;

  const agentNodes = [
    { name: "DocParserAgent", role: "AST & Hierarchy" },
    { name: "SupervisorAgent", role: "DAG Orchestrator" },
    { name: "LegalRetrieverAgent", role: "InLegalBERT Vector" },
    { name: "CitatorAgent", role: "Neo4j Art 141" },
    { name: "RiskComplianceAgent", role: "Statutory Rules" },
    { name: "SimplifierAgent", role: "Plain English" },
    { name: "SynthesisAgent", role: "Card Emitter" }
  ];

  return (
    <div className="agent-modal-overlay" onClick={onClose}>
      <div className="agent-modal-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="agent-modal-header">
          <div className="modal-header-text">
            <span className="modal-kicker-tag mono">AUTONOMOUS WORKFLOW</span>
            <h2 className="modal-title font-judicial">Agent Execution Trace</h2>
            <div className="modal-subtitle">
              LangGraph StateGraph DAG Lifecycle & Real-Time Telemetry
            </div>
          </div>

          <div className="modal-header-actions">
            <div className="telemetry-chip mono">
              <span>TOKENS: <strong>{tokensUsed.toLocaleString()}</strong></span>
            </div>
            <button 
              type="button" 
              className="modal-close-icon-btn" 
              onClick={onClose} 
              aria-label="Close Inspector"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Agent Pipeline Track */}
        <div className="agent-pipeline-track">
          {agentNodes.map((node, idx) => {
            const isCompleted = idx < currentStepIndex;
            const isCurrent = idx === currentStepIndex;

            return (
              <div 
                key={idx} 
                className={`pipeline-node-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'active' : ''}`}
              >
                <div className="node-number-bubble">
                  {isCompleted ? <Check size={11} /> : `0${idx + 1}`}
                </div>
                <div className="node-details">
                  <div className="node-name-text">{node.name}</div>
                  <div className="node-role-text">{node.role}</div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Current Active Step Banner */}
        {isRunning && currentStep && (
          <div className="active-agent-banner">
            <div className="active-agent-header">
              <span className="active-pulse-dot" />
              <strong className="active-agent-name">{currentStep.agent}</strong>
              <span className="active-tool-badge mono">[{currentStep.tool}]</span>
            </div>
            <blockquote className="active-agent-quote font-judicial">
              "{currentStep.thought}"
            </blockquote>
          </div>
        )}

        {/* Execution Log Stream (Terminal Surface) */}
        <div className="agent-terminal-card">
          <div className="terminal-header-bar">
            <div className="terminal-title-group">
              <Terminal size={14} />
              <span className="terminal-title">STATE TRANSITIONS & EXECUTION LOG</span>
            </div>
            <span className="terminal-step-badge mono">
              STEP {currentStepIndex + 1} OF {totalSteps}
            </span>
          </div>

          <div className="terminal-scroll-viewport">
            {trace.length === 0 ? (
              <div className="terminal-empty-prompt">
                Workflow ready. Launch "RUN TRACE" on any clause in the Document Analyzer to begin telemetry streaming.
              </div>
            ) : (
              trace.map((item, index) => (
                <div key={index} className="trace-row-entry">
                  <div className="trace-row-meta">
                    <span className="trace-ord mono">#{item.stepNumber}</span>
                    <span className="trace-agent">{item.agent}</span>
                    <span className="trace-tool mono">[{item.tool}]</span>
                    <span className="trace-tokens mono">+{item.tokens} tokens</span>
                    <span className="trace-time mono">{item.timestamp}</span>
                  </div>
                  <div className="trace-thought-text font-judicial">
                    &rarr; {item.thought}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="agent-modal-footer">
          <div className="modal-credits-meta">
            <span>MODEL: <strong>GEMINI-3.8-FLASH</strong></span>
            <span className="meta-sep">&bull;</span>
            <span>ORCHESTRATION: <strong>LANGGRAPH DAG</strong></span>
            <span className="meta-sep">&bull;</span>
            <span>VECTOR: <strong>QDRANT (INLEGALBERT)</strong></span>
          </div>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
}
