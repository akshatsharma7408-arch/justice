import React, { useState } from 'react';
import { ArrowRight, Scale, BookOpen, ShieldCheck, AlertTriangle, CheckCircle2, ChevronRight, Shuffle } from 'lucide-react';
import { LANDMARK_PRECEDENTS } from '../data/legalCorpus';

export default function PrecedentComparison({ onSwitchToWorkspace }) {
  const [case1Id, setCase1Id] = useState('sc-2006-percept');
  const [case2Id, setCase2Id] = useState('sc-1967-niranjan-golikari');

  const case1 = LANDMARK_PRECEDENTS.find(c => c.id === case1Id) || LANDMARK_PRECEDENTS[0];
  const case2 = LANDMARK_PRECEDENTS.find(c => c.id === case2Id) || LANDMARK_PRECEDENTS[1];

  const presetPairs = [
    {
      label: "Section 27 Non-Compete: Post-Service vs During-Service",
      c1: 'sc-2006-percept',
      c2: 'sc-1967-niranjan-golikari'
    },
    {
      label: "Article 21 Privacy: Privacy Recognized vs Emergency Suspension",
      c1: 'sc-2017-puttaswamy',
      c2: 'sc-1976-adm-jabalpur'
    },
    {
      label: "Section 27: Division Bench (2006) vs 3-Judge Full Bench (1981)",
      c1: 'sc-2006-percept',
      c2: 'sc-1981-super-superintendence'
    }
  ];

  return (
    <div className="workspace-module-pane animate-fade-in">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">PRECEDENT COMPARISON</span>
        </div>
        <h1 className="module-heading font-serif">Precedent Comparison & Doctrine Matrix</h1>
        <p className="module-description">
          Side-by-side comparative analysis of authoritative Supreme Court decisions. Evaluate bench hierarchy, ratio decidendi differences, statutory interpretations, and subsequent judicial treatment.
        </p>

        {/* Quick Comparison Presets Strip */}
        <div className="comparison-presets-bar">
          <span className="presets-label mono">FEATURED COMPARISONS:</span>
          <div className="presets-chips-row">
            {presetPairs.map((p, idx) => (
              <button
                key={idx}
                type="button"
                className={`preset-pair-chip ${case1Id === p.c1 && case2Id === p.c2 ? 'is-active' : ''}`}
                onClick={() => {
                  setCase1Id(p.c1);
                  setCase2Id(p.c2);
                }}
              >
                <span>{p.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Selectors Bar */}
      <div className="precedent-selector-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '20px',
        marginBottom: '28px'
      }}>
        {/* Selector 1 */}
        <div className="precedent-pick-card" style={{
          backgroundColor: '#12261F',
          border: '1px solid rgba(212, 163, 89, 0.25)',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <label className="picker-field-label mono text-xs text-muted" style={{ display: 'block', marginBottom: '8px' }}>
            PRECEDENT A (PRIMARY / APPLIED)
          </label>
          <select
            className="precedent-dropdown-select"
            value={case1Id}
            onChange={(e) => setCase1Id(e.target.value)}
            style={{
              width: '100%',
              backgroundColor: '#0D1B16',
              color: '#F4EEDA',
              border: '1px solid rgba(212, 163, 89, 0.3)',
              borderRadius: '8px',
              padding: '10px 12px',
              fontSize: '14px',
              fontFamily: 'serif'
            }}
          >
            {LANDMARK_PRECEDENTS.map(c => (
              <option key={c.id} value={c.id}>
                {c.title} ({c.decisionYear}) — {c.citation}
              </option>
            ))}
          </select>
        </div>

        {/* Selector 2 */}
        <div className="precedent-pick-card" style={{
          backgroundColor: '#12261F',
          border: '1px solid rgba(212, 163, 89, 0.25)',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <label className="picker-field-label mono text-xs text-muted" style={{ display: 'block', marginBottom: '8px' }}>
            PRECEDENT B (COMPARATOR / DISTINGUISHED)
          </label>
          <select
            className="precedent-dropdown-select"
            value={case2Id}
            onChange={(e) => setCase2Id(e.target.value)}
            style={{
              width: '100%',
              backgroundColor: '#0D1B16',
              color: '#F4EEDA',
              border: '1px solid rgba(212, 163, 89, 0.3)',
              borderRadius: '8px',
              padding: '10px 12px',
              fontSize: '14px',
              fontFamily: 'serif'
            }}
          >
            {LANDMARK_PRECEDENTS.map(c => (
              <option key={c.id} value={c.id}>
                {c.title} ({c.decisionYear}) — {c.citation}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Side-by-Side Comparison Matrix */}
      <div className="precedent-comparison-cards-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '24px',
        marginBottom: '40px'
      }}>
        {/* Case 1 Card */}
        <div className="comparison-case-card" style={{
          backgroundColor: '#12261F',
          border: '1px solid rgba(212, 163, 89, 0.2)',
          borderRadius: '16px',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px'
        }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span className="mono text-xs" style={{ color: '#D4A359', letterSpacing: '0.05em' }}>
                CASE A &bull; {case1.court?.toUpperCase()}
              </span>
              <span className="citation-badge mono text-xs" style={{
                backgroundColor: 'rgba(212, 163, 89, 0.12)',
                color: '#D4A359',
                padding: '4px 8px',
                borderRadius: '4px'
              }}>
                {case1.citation}
              </span>
            </div>
            <h2 className="font-serif text-xl" style={{ color: '#F4EEDA', lineHeight: 1.3, marginBottom: '6px' }}>
              {case1.title}
            </h2>
            <div className="mono text-xs text-muted">
              Decided in {case1.decisionYear} &bull; {case1.benchSize || 2}-Judge {case1.benchType || 'Bench'}
            </div>
          </div>

          {/* Status & Standing */}
          <div style={{
            backgroundColor: 'rgba(0,0,0,0.2)',
            padding: '12px 14px',
            borderRadius: '8px',
            borderLeft: case1.status === 'GREEN' ? '3px solid #2ECC71' : case1.status === 'RED' ? '3px solid #E74C3C' : '3px solid #F39C12'
          }}>
            <div className="mono text-xs" style={{
              color: case1.status === 'GREEN' ? '#2ECC71' : case1.status === 'RED' ? '#E74C3C' : '#F39C12',
              fontWeight: 600,
              marginBottom: '4px'
            }}>
              {case1.statusLabel || 'Authoritative Ruling'}
            </div>
            <p className="font-serif text-xs text-muted" style={{ margin: 0 }}>
              {case1.statusDescription}
            </p>
          </div>

          {/* Ratio Decidendi */}
          <div>
            <span className="mono text-xs text-muted" style={{ display: 'block', marginBottom: '6px' }}>
              CORE RATIO DECIDENDI
            </span>
            <blockquote className="font-serif" style={{
              margin: 0,
              padding: '14px',
              backgroundColor: 'rgba(255,255,255,0.03)',
              borderRadius: '8px',
              color: '#F4EEDA',
              fontSize: '14px',
              lineHeight: 1.5,
              borderLeft: '2px solid rgba(212, 163, 89, 0.4)'
            }}>
              "{case1.ratioSummary}"
            </blockquote>
          </div>

          {/* Statutes */}
          <div>
            <span className="mono text-xs text-muted" style={{ display: 'block', marginBottom: '6px' }}>
              STATUTORY PROVISIONS
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {(case1.statutes || []).map((s, i) => (
                <span key={i} className="mono text-xs" style={{
                  backgroundColor: 'rgba(212, 163, 89, 0.08)',
                  color: '#D4A359',
                  padding: '3px 8px',
                  borderRadius: '4px'
                }}>
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* Treatment History */}
          {case1.treatmentHistory && case1.treatmentHistory.length > 0 && (
            <div>
              <span className="mono text-xs text-muted" style={{ display: 'block', marginBottom: '6px' }}>
                DOWNSTREAM JUDICIAL TREATMENT
              </span>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {case1.treatmentHistory.slice(0, 3).map((th, i) => (
                  <li key={i} className="text-xs font-serif" style={{ color: '#C8C2B3', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{th.case} ({th.court})</span>
                    <span className="mono" style={{ color: th.treatment === 'AFFIRMED' ? '#2ECC71' : '#E0955A' }}>
                      {th.treatment}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Case 2 Card */}
        <div className="comparison-case-card" style={{
          backgroundColor: '#12261F',
          border: '1px solid rgba(212, 163, 89, 0.2)',
          borderRadius: '16px',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px'
        }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span className="mono text-xs" style={{ color: '#D4A359', letterSpacing: '0.05em' }}>
                CASE B &bull; {case2.court?.toUpperCase()}
              </span>
              <span className="citation-badge mono text-xs" style={{
                backgroundColor: 'rgba(212, 163, 89, 0.12)',
                color: '#D4A359',
                padding: '4px 8px',
                borderRadius: '4px'
              }}>
                {case2.citation}
              </span>
            </div>
            <h2 className="font-serif text-xl" style={{ color: '#F4EEDA', lineHeight: 1.3, marginBottom: '6px' }}>
              {case2.title}
            </h2>
            <div className="mono text-xs text-muted">
              Decided in {case2.decisionYear} &bull; {case2.benchSize || 2}-Judge {case2.benchType || 'Bench'}
            </div>
          </div>

          {/* Status & Standing */}
          <div style={{
            backgroundColor: 'rgba(0,0,0,0.2)',
            padding: '12px 14px',
            borderRadius: '8px',
            borderLeft: case2.status === 'GREEN' ? '3px solid #2ECC71' : case2.status === 'RED' ? '3px solid #E74C3C' : '3px solid #F39C12'
          }}>
            <div className="mono text-xs" style={{
              color: case2.status === 'GREEN' ? '#2ECC71' : case2.status === 'RED' ? '#E74C3C' : '#F39C12',
              fontWeight: 600,
              marginBottom: '4px'
            }}>
              {case2.statusLabel || 'Authoritative Ruling'}
            </div>
            <p className="font-serif text-xs text-muted" style={{ margin: 0 }}>
              {case2.statusDescription}
            </p>
          </div>

          {/* Ratio Decidendi */}
          <div>
            <span className="mono text-xs text-muted" style={{ display: 'block', marginBottom: '6px' }}>
              CORE RATIO DECIDENDI
            </span>
            <blockquote className="font-serif" style={{
              margin: 0,
              padding: '14px',
              backgroundColor: 'rgba(255,255,255,0.03)',
              borderRadius: '8px',
              color: '#F4EEDA',
              fontSize: '14px',
              lineHeight: 1.5,
              borderLeft: '2px solid rgba(212, 163, 89, 0.4)'
            }}>
              "{case2.ratioSummary}"
            </blockquote>
          </div>

          {/* Statutes */}
          <div>
            <span className="mono text-xs text-muted" style={{ display: 'block', marginBottom: '6px' }}>
              STATUTORY PROVISIONS
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {(case2.statutes || []).map((s, i) => (
                <span key={i} className="mono text-xs" style={{
                  backgroundColor: 'rgba(212, 163, 89, 0.08)',
                  color: '#D4A359',
                  padding: '3px 8px',
                  borderRadius: '4px'
                }}>
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* Treatment History */}
          {case2.treatmentHistory && case2.treatmentHistory.length > 0 && (
            <div>
              <span className="mono text-xs text-muted" style={{ display: 'block', marginBottom: '6px' }}>
                DOWNSTREAM JUDICIAL TREATMENT
              </span>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {case2.treatmentHistory.slice(0, 3).map((th, i) => (
                  <li key={i} className="text-xs font-serif" style={{ color: '#C8C2B3', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{th.case} ({th.court})</span>
                    <span className="mono" style={{ color: th.treatment === 'AFFIRMED' ? '#2ECC71' : '#E0955A' }}>
                      {th.treatment}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Cross-Bench Comparison Summary Table */}
      <div className="comparison-summary-table-wrap" style={{
        backgroundColor: '#12261F',
        border: '1px solid rgba(212, 163, 89, 0.2)',
        borderRadius: '16px',
        padding: '24px'
      }}>
        <h3 className="font-serif text-lg" style={{ color: '#F4EEDA', marginBottom: '16px' }}>
          Comparative Precedent Summary
        </h3>
        <table className="comparison-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(212, 163, 89, 0.2)' }}>
              <th className="mono text-xs text-muted" style={{ padding: '10px 12px' }}>METRIC / DOCTRINE</th>
              <th className="mono text-xs text-muted" style={{ padding: '10px 12px', width: '42%' }}>{case1.title}</th>
              <th className="mono text-xs text-muted" style={{ padding: '10px 12px', width: '42%' }}>{case2.title}</th>
            </tr>
          </thead>
          <tbody className="font-serif text-sm">
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <td className="mono text-xs text-muted" style={{ padding: '12px' }}>Bench Strength</td>
              <td style={{ padding: '12px', color: '#F4EEDA' }}>{case1.benchSize || 2} Judges ({case1.benchType || 'Bench'})</td>
              <td style={{ padding: '12px', color: '#F4EEDA' }}>{case2.benchSize || 2} Judges ({case2.benchType || 'Bench'})</td>
            </tr>
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <td className="mono text-xs text-muted" style={{ padding: '12px' }}>Decision Year</td>
              <td style={{ padding: '12px', color: '#F4EEDA' }}>{case1.decisionYear}</td>
              <td style={{ padding: '12px', color: '#F4EEDA' }}>{case2.decisionYear}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <td className="mono text-xs text-muted" style={{ padding: '12px' }}>Primary Statute</td>
              <td style={{ padding: '12px', color: '#F4EEDA' }}>{(case1.statutes || []).join(', ') || 'N/A'}</td>
              <td style={{ padding: '12px', color: '#F4EEDA' }}>{(case2.statutes || []).join(', ') || 'N/A'}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <td className="mono text-xs text-muted" style={{ padding: '12px' }}>Precedent Status</td>
              <td style={{ padding: '12px', color: case1.status === 'GREEN' ? '#2ECC71' : case1.status === 'RED' ? '#E74C3C' : '#F39C12' }}>
                {case1.statusLabel}
              </td>
              <td style={{ padding: '12px', color: case2.status === 'GREEN' ? '#2ECC71' : case2.status === 'RED' ? '#E74C3C' : '#F39C12' }}>
                {case2.statusLabel}
              </td>
            </tr>
            <tr>
              <td className="mono text-xs text-muted" style={{ padding: '12px' }}>Article 141 Hierarchy</td>
              <td style={{ padding: '12px', color: '#C8C2B3' }}>
                {case1.benchSize >= case2.benchSize ? "Larger or equal bench strength" : "Smaller bench strength"}
              </td>
              <td style={{ padding: '12px', color: '#C8C2B3' }}>
                {case2.benchSize >= case1.benchSize ? "Larger or equal bench strength" : "Smaller bench strength"}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
