import React from 'react';
import { ArrowUpRight, Cpu, ShieldCheck } from 'lucide-react';

export default function Footer({ onOpenComparison, onOpenAgentModal }) {
  return (
    <footer className="workspace-footer">
      <div className="workspace-footer-inner">
        <div className="footer-status-item">
          <span className="footer-status-dot" />
          <span className="footer-text">
            <strong>Republic of India</strong> &bull; All Precedents Governed Under Article 141
          </span>
        </div>

        <div className="footer-links-group">
          <button 
            type="button" 
            className="footer-nav-link"
            onClick={onOpenComparison}
          >
            <span>Legacy vs. Workspace Matrix</span>
            <ArrowUpRight size={12} />
          </button>

          <span className="footer-sep">&bull;</span>

          <button 
            type="button" 
            className="footer-nav-link"
            onClick={onOpenAgentModal}
          >
            <Cpu size={12} />
            <span>Agent DAG Trace</span>
          </button>

          <span className="footer-sep">&bull;</span>

          <span className="footer-research-note">
            Medi-Caps University &bull; Indian Legal AI Project
          </span>
        </div>
      </div>
    </footer>
  );
}
