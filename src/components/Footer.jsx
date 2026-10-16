import React from 'react';
import { ArrowUpRight } from 'lucide-react';

export default function Footer({ onOpenComparison, onOpenAgentModal }) {
  return (
    <footer className="footer-editorial">
      <div className="footer-inner">
        {/* Three Editorial Columns */}
        <div className="footer-columns-grid">
          {/* Left Column: System Identity */}
          <div className="footer-column">
            <span className="footer-label">SYSTEM ARCHITECTURE</span>
            <div className="footer-identity-title">
              JUSTICE // AUTONOMOUS LEGAL INTELLIGENCE
            </div>
            <div className="footer-identity-sub">
              ARTICLE 141 CONSTITUTIONAL CO-PILOT
            </div>
          </div>

          {/* Center Column: Academic & Architectural Benchmarks */}
          <div className="footer-column">
            <span className="footer-label">ACADEMIC & ARCHITECTURAL BENCHMARKS</span>
            <div>
              <button 
                type="button" 
                className="footer-text-link"
                onClick={onOpenComparison}
              >
                <span>SYSTEM BENCHMARK // LEGACY CRITIQUE</span>
                <ArrowUpRight size={12} className="footer-link-arrow" />
              </button>
            </div>
            <div className="footer-secondary-note">
              EVALUATION MATRIX: TAXONOMY VS. UNIFIED INTENT
            </div>
          </div>

          {/* Right Column: Developer Telemetry & Agent Trace */}
          <div className="footer-column">
            <span className="footer-label">DEVELOPER TELEMETRY & AGENT TRACE</span>
            <div>
              <button 
                type="button" 
                className="footer-action-btn"
                onClick={onOpenAgentModal}
              >
                [ INSPECT AGENT DAG TRACE ]
              </button>
            </div>
            <div className="footer-telemetry-caption mono">
              MODEL: GEMINI-3.8-FLASH &bull; LANGGRAPH DAG &bull; 7 ACTIVE NODES
            </div>
          </div>
        </div>

        {/* Bottom Baseline Disclaimer */}
        <div className="footer-baseline">
          <div className="footer-disclaimer-text">
            ACADEMIC RESEARCH WORKSPACE &bull; MEDI-CAPS UNIVERSITY &bull; ALL PRECEDENTS GOVERNED UNDER ART. 141
          </div>
        </div>
      </div>
    </footer>
  );
}
