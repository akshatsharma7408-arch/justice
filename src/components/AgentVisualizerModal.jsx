import React from 'react';
import { X } from 'lucide-react';

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
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog-large" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-header-left">
            <span className="editorial-meta-label">AUTONOMOUS WORKFLOW</span>
            <h2 className="modal-title font-judicial">Agent Execution Trace</h2>
            <div className="modal-subtitle">LangGraph StateGraph DAG Lifecycle & Execution Telemetry</div>
          </div>

          <div className="modal-header-right">
            <div className="telemetry-badge-mono">
              <span>TOKENS: <strong>{tokensUsed.toLocaleString()}</strong></span>
            </div>
            <button className="btn-modal-close" onClick={onClose} aria-label="Close Inspector">
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Agent Pipeline Track - Clean Minimalist Horizontal Sequence */}
        <div className="editorial-pipeline-track">
          {agentNodes.map((node, idx) => {
            const isCompleted = idx < currentStepIndex;
            const isCurrent = idx === currentStepIndex;

            return (
              <div 
                key={idx} 
                className={`pipeline-step-unit ${isCompleted ? 'completed' : ''} ${isCurrent ? 'active' : ''}`}
              >
                <div className="step-number-box">
                  {isCompleted ? '✓' : `0${idx + 1}`}
                </div>
                <div className="step-info-block">
                  <div className="step-name-text">{node.name}</div>
                  <div className="step-role-text">{node.role}</div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Current Active Step Banner */}
        {isRunning && currentStep && (
          <div className="active-agent-editorial-banner">
            <div className="active-agent-label-row">
              <span className="status-running-mark">● ACTIVE NODE:</span>
              <strong className="active-agent-name">{currentStep.agent}</strong>
              <span className="tool-pill-mono mono">[{currentStep.tool}]</span>
            </div>
            <blockquote className="agent-thought-quote">
              "{currentStep.thought}"
            </blockquote>
          </div>
        )}

        {/* Execution Log Stream */}
        <div className="editorial-trace-terminal">
          <div className="terminal-header-strip">
            <span className="terminal-title-text">EXECUTION TRACE & STATE TRANSITIONS</span>
            <span className="mono terminal-step-indicator">STEP {currentStepIndex + 1} OF {totalSteps}</span>
          </div>

          <div className="terminal-stream-body">
            {trace.length === 0 ? (
              <div className="terminal-empty-text">
                Workflow ready. Launch "RUN TRACE" on any clause in the Document Analyzer to begin telemetry streaming.
              </div>
            ) : (
              trace.map((item, index) => (
                <div key={index} className="trace-entry-row animate-fade-in">
                  <div className="trace-meta-line">
                    <span className="trace-ordinal">#{item.stepNumber}</span>
                    <span className="trace-agent-label">{item.agent}</span>
                    <span className="trace-tool-tag mono">[{item.tool}]</span>
                    <span className="trace-tokens-stat">+{item.tokens} tokens</span>
                    <span className="trace-time-stamp mono">{item.timestamp}</span>
                  </div>
                  <div className="trace-thought-content">
                    &rarr; {item.thought}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <div className="framework-credits-text">
            <span>MODEL: <strong>GEMINI-3.8-FLASH</strong></span>
            <span className="meta-sep">&bull;</span>
            <span>ORCHESTRATION: <strong>LANGGRAPH DAG (PERSISTENT CHECKPOINTS)</strong></span>
            <span className="meta-sep">&bull;</span>
            <span>VECTOR STORE: <strong>QDRANT HYBRID (INLEGALBERT)</strong></span>
          </div>
          <button className="btn-secondary" onClick={onClose}>CLOSE INSPECTOR</button>
        </div>
      </div>
    </div>
  );
}
