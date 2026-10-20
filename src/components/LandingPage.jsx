import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Search, ArrowRight, ArrowUpRight, Scale, ShieldCheck, Check, MessageSquare, BookOpen, FileText, SlidersHorizontal, Sparkles, ChevronRight, AlertTriangle, ExternalLink } from 'lucide-react';
import { 
  ScrollProgressBar, 
  SoftCursorFollower, 
  TiltCard, 
  MagneticButton, 
  CountUpNumber, 
  TypewriterPlaceholder, 
  DraggableQuestionsRow 
} from './InteractiveEffects';

const ROTATING_PLACEHOLDERS = [
  "What are my rights if an officer arrests me without a warrant?",
  "Can my landlord evict me without notice?",
  "Section 27 Contract Act post termination non compete enforceability",
  "What are my rights when stopped on my bike?",
  "What should I do if a police officer asks for a bribe?",
  "Are non-compete clauses valid after I quit my job?"
];

const EVERYDAY_CHIPS = [
  { label: "Arrest without warrant", query: "What to do if police arrest me without a warrant" },
  { label: "Landlord eviction notice", query: "Can my landlord evict me without notice" },
  { label: "Traffic police bike stop", query: "What are my rights when stopped by traffic police on the road" },
  { label: "Police asking for bribe", query: "What should I do if a police officer asks for a bribe" },
  { label: "Non-compete validity (Sec 27)", query: "Section 27 Contract Act post termination non compete enforceability" },
  { label: "Right to Privacy & Art. 21", query: "Right to privacy under Article 21 proportionality test and state surveillance" }
];

const MODULE_LINKS = [
  { id: 'search', label: 'Search Precedents, Statutes and Citations' },
  { id: 'citator', label: 'Smart Citator' },
  { id: 'analyzer', label: 'Document Analyser' },
  { id: 'docchat', label: 'Document Chat' },
  { id: 'comparison', label: 'Comparison' },
  { id: 'maxims', label: 'Legal Maxims' },
];

export default function LandingPage({
  onNavigate,
  onSearchSubmit,
  onOpenCaseChat,
  onOpenCommandPalette
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [placeholderFade, setPlaceholderFade] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [mouseParallax, setMouseParallax] = useState({ x: 0, y: 0 });
  const [toastMessage, setToastMessage] = useState(null);
  const [copiedCitationId, setCopiedCitationId] = useState(null);

  // Rotating placeholder
  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderFade(true);
      setTimeout(() => {
        setPlaceholderIndex((prev) => (prev + 1) % ROTATING_PLACEHOLDERS.length);
        setPlaceholderFade(false);
      }, 300);
    }, 4200);
    return () => clearInterval(interval);
  }, []);

  // Parallax tracking on desktop
  const handleMouseMove = (e) => {
    if (window.innerWidth < 1024) return;
    const { clientX, clientY } = e;
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    const moveX = ((clientX - centerX) / centerX) * 12;
    const moveY = ((clientY - centerY) / centerY) * 12;
    setMouseParallax({ x: moveX, y: moveY });
  };

  // Scroll tracking for hero-to-sticky transformation
  useEffect(() => {
    const onScroll = () => {
      const scrollY = window.scrollY;
      const heroHeight = window.innerHeight || 800;
      // Normalise progress between 0 and 1 across the first 350px of scroll
      const progress = Math.min(Math.max(scrollY / 340, 0), 1);
      setScrollProgress(progress);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    if (onSearchSubmit) {
      onSearchSubmit(q);
    } else {
      onNavigate('search', q);
    }
  };

  const handleChipClick = (q) => {
    setSearchQuery(q);
    if (onSearchSubmit) {
      onSearchSubmit(q);
    } else {
      onNavigate('search', q);
    }
  };

  const copyCitation = (text, id = null) => {
    navigator.clipboard?.writeText(text);
    if (id) setCopiedCitationId(id);
    setToastMessage(`Copied "${text}" to clipboard`);
    setTimeout(() => {
      setToastMessage(null);
      if (id) setCopiedCitationId(null);
    }, 2400);
  };

  // Dynamic transforms based on scrollProgress (0 = hero full, 1 = sticky top bar)
  // Transition logo, search bar, and modules row smoothly
  const isScrolledPast = scrollProgress > 0.85;

  return (
    <div className="landing-page-root" onMouseMove={handleMouseMove}>
      {/* Top Window Scroll Progress Line */}
      <ScrollProgressBar />

      {/* Ambient Soft Copper Cursor Glow across Hero and Cards */}
      <SoftCursorFollower />

      {/* Toast Notification */}
      {toastMessage && (
        <div className="landing-toast animate-fade-in" role="status">
          <Check size={14} className="toast-icon" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* =========================================================================
          HERO & SCROLL-DRIVEN STICKY TRANSFORMATION DOCK
          ========================================================================= */}
      <section className="landing-hero-viewport" id="landing-hero">
        {/* Background Depth: Drifting Copper Aurora & Scales Line Art */}
        <div className="hero-background-layer" aria-hidden="true">
          <div
            className="hero-copper-glow"
            style={{
              transform: `translate(${mouseParallax.x * -1}px, ${mouseParallax.y * -1}px)`
            }}
          />
          <div
            className="hero-line-art"
            style={{
              transform: `translate(${mouseParallax.x * 0.5}px, ${mouseParallax.y * 0.5}px)`
            }}
          >
            {/* Fine SVG line art representing constitutional pillars and scales of justice */}
            <svg viewBox="0 0 1000 600" fill="none" xmlns="http://www.w3.org/2000/svg" className="scales-svg">
              <circle cx="500" cy="300" r="280" stroke="#24403A" strokeWidth="0.75" strokeDasharray="4 6" opacity="0.6" />
              <circle cx="500" cy="300" r="190" stroke="#C77B3A" strokeWidth="0.5" opacity="0.25" />
              <line x1="500" y1="90" x2="500" y2="510" stroke="#24403A" strokeWidth="1" opacity="0.7" />
              <line x1="260" y1="210" x2="740" y2="210" stroke="#24403A" strokeWidth="1" opacity="0.7" />
              {/* Left Scale Pan */}
              <path d="M 260 210 L 210 320 L 310 320 Z" stroke="#C77B3A" strokeWidth="0.75" fill="none" opacity="0.4" />
              <path d="M 190 320 Q 260 360 330 320" stroke="#C77B3A" strokeWidth="0.75" fill="none" opacity="0.4" />
              {/* Right Scale Pan */}
              <path d="M 740 210 L 690 320 L 790 320 Z" stroke="#C77B3A" strokeWidth="0.75" fill="none" opacity="0.4" />
              <path d="M 670 320 Q 740 360 810 320" stroke="#C77B3A" strokeWidth="0.75" fill="none" opacity="0.4" />
              {/* Central Pedestal */}
              <path d="M 460 510 L 540 510 L 520 480 L 480 480 Z" stroke="#24403A" strokeWidth="1" opacity="0.7" />
            </svg>
          </div>
        </div>

        {/* HERO CENTER CONTENT (Wordmark + Headline + Big Search Bar) */}
        <div
          className="hero-stage-container"
          style={{
            transform: `translate(${mouseParallax.x * 0.4}px, ${mouseParallax.y * 0.4}px)`,
            opacity: Math.max(1 - scrollProgress * 1.4, 0),
            pointerEvents: scrollProgress > 0.7 ? 'none' : 'auto'
          }}
        >
          {/* Wordmark in Cormorant Garamond */}
          <div className="hero-brand-block">
            <h1 className="hero-wordmark font-serif">
              Justice<span className="copper-period">.</span>
            </h1>
            <p className="hero-subline">
              Indian Supreme Court judgments, in plain language
            </p>
          </div>

          {/* Big Search Bar replacing Universal Search */}
          <div className="hero-big-search-wrap">
            <form className="hero-search-form" onSubmit={handleSearch}>
              <div className="hero-search-input-box">
                <Search size={20} className="hero-search-icon" aria-hidden="true" />
                <div style={{ position: 'relative', width: '100%', display: 'flex', alignItems: 'center' }}>
                  <input
                    type="text"
                    className="hero-search-input"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    aria-label="Ask any question, case name, statute or citation"
                    autoComplete="off"
                  />
                  {!searchQuery && (
                    <div style={{ position: 'absolute', left: 0, pointerEvents: 'none', width: '100%' }}>
                      <TypewriterPlaceholder placeholders={ROTATING_PLACEHOLDERS} />
                    </div>
                  )}
                </div>
                <MagneticButton
                  type="submit"
                  className="hero-search-submit-btn"
                  aria-label="Execute Search"
                >
                  <span>Search Precedents</span>
                  <ArrowRight size={16} />
                </MagneticButton>
              </div>
            </form>

            {/* Horizontally Draggable Popular Questions Strip */}
            <div className="hero-chips-strip">
              <span className="chips-kicker mono">POPULAR CITIZEN QUESTIONS (DRAG OR SWIPE):</span>
              <DraggableQuestionsRow chips={EVERYDAY_CHIPS} onChipClick={handleChipClick} />
            </div>

            {/* Real Number Counters Strip (Scrolled into view count-up) */}
            <div className="landing-stats-strip" aria-label="Corpus Statistics">
              <div className="stat-card-box">
                <span className="stat-number-val font-serif"><CountUpNumber target={1736} suffix="+" /></span>
                <span className="stat-label-text">Supreme Court Judgments</span>
              </div>
              <div className="stat-card-box">
                <span className="stat-number-val font-serif"><CountUpNumber target={12} suffix="" /></span>
                <span className="stat-label-text">Landmark Rulings</span>
              </div>
              <div className="stat-card-box">
                <span className="stat-number-val font-serif"><CountUpNumber target={33} suffix="k+" /></span>
                <span className="stat-label-text">Indexed Chunks</span>
              </div>
              <div className="stat-card-box">
                <span className="stat-number-val font-serif" style={{ fontSize: '1.25rem', lineHeight: 1.3 }}>Supreme Court</span>
                <span className="stat-label-text">Every case shown comes from the Supreme Court dataset</span>
              </div>
            </div>
          </div>
        </div>

        {/* HERO BOTTOM: Workspace Modules Text Links (glides up to become sticky bar) */}
        <div
          className={`hero-bottom-modules-dock ${scrollProgress > 0.1 ? 'in-scroll' : ''} ${isScrolledPast ? 'is-docked-sticky' : ''}`}
          style={{
            transform: isScrolledPast
              ? 'translateY(0)'
              : `translateY(${Math.min(scrollProgress * -80, 0)}px)`
          }}
        >
          <div className="modules-dock-inner">
            {/* Scrolled Wordmark appears on top left when docked */}
            <div className={`dock-scrolled-brand ${scrollProgress > 0.4 ? 'is-visible' : ''}`}>
              <button
                type="button"
                className="dock-brand-link"
                onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
              >
                <span className="justice-wordmark">
                  Justice<span className="copper-dot">.</span>
                </span>
              </button>
            </div>

            {/* Scrolled Compact Search Bar */}
            <div className={`dock-scrolled-search ${scrollProgress > 0.4 ? 'is-visible' : ''}`}>
              <form onSubmit={handleSearch} className="dock-mini-search-form">
                <Search size={13} className="mini-search-icon" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search precedents..."
                  className="dock-mini-search-input"
                  aria-label="Search precedents from top bar"
                />
              </form>
            </div>

            {/* Module row text links */}
            <nav className="dock-modules-row" aria-label="Workspace Modules">
              {MODULE_LINKS.map((mod) => (
                <button
                  key={mod.id}
                  type="button"
                  className="dock-module-link"
                  onClick={() => onNavigate(mod.id)}
                >
                  <span className="dock-link-text">{mod.label}</span>
                  <span className="dock-copper-underline" />
                </button>
              ))}
            </nav>

            {/* Command Palette Hint */}
            <div className={`dock-palette-trigger ${scrollProgress > 0.4 ? 'is-visible' : ''}`}>
              <button
                type="button"
                className="dock-palette-btn"
                onClick={onOpenCommandPalette}
                title="Command Palette (Ctrl+K or ⌘K)"
              >
                <kbd className="mono">⌘K</kbd>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION A: ASK IN PLAIN WORDS (3 Real Questions & Real Sourced Answers)
          ========================================================================= */}
      <section className="landing-section dark-section" id="plain-words">
        <div className="section-container">
          <div className="section-header-block">
            <span className="section-eyebrow mono">EDITORIAL CLARITY &bull; GENUINE LAW</span>
            <h2 className="section-heading font-serif">Ask in plain words.</h2>
            <p className="section-lead">
              Indian citizens have fundamental constitutional rights. You don't need Latin phrases or legal jargon to discover them.
            </p>
          </div>

          <div className="three-answers-grid">
            {/* Card 1: D.K. Basu (TiltCard with glossy highlight) */}
            <TiltCard className="editorial-answer-card" maxTilt={6}>
              <div className="card-top-kicker">
                <span className="kicker-tag mono">ARREST & DETENTION</span>
                <span className="badge-verified">
                  <ShieldCheck size={12} />
                  <span>Verified Citation</span>
                </span>
              </div>
              <h3 className="card-question font-serif">
                "What are my rights if an officer arrests me without a warrant?"
              </h3>
              <p className="card-answer-prose">
                The arresting officer must carry accurate identification, prepare an <strong>Arrest Memo</strong> countersigned by at least one witness (a family member or respected citizen), and inform your relative or friend of your location within 8 to 12 hours. You have the right to a medical examination at the time of arrest and must be produced before a Magistrate within 24 hours.
              </p>
              <div className="card-source-citation">
                <span className="citation-title font-serif">D.K. Basu v. State of West Bengal</span>
                <div className="citation-code-row">
                  <span className="citation-pill mono">(1997) 1 SCC 416</span>
                  <button
                    type="button"
                    className="btn-copy-cite"
                    onClick={() => copyCitation("(1997) 1 SCC 416", "dk-basu")}
                    title="Copy citation"
                  >
                    {copiedCitationId === "dk-basu" ? (
                      <span className="copy-success-badge"><Check size={12} /> Copied</span>
                    ) : (
                      "Copy"
                    )}
                  </button>
                  <button
                    type="button"
                    className="btn-verify-cite"
                    onClick={() => onNavigate('search', 'D.K. Basu v. State of West Bengal arrest guidelines')}
                  >
                    <span>View Judgment</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            </TiltCard>

            {/* Card 2: Biswabani / Landlord eviction (TiltCard with glossy highlight) */}
            <TiltCard className="editorial-answer-card" maxTilt={6}>
              <div className="card-top-kicker">
                <span className="kicker-tag mono">TENANCY & HOUSING</span>
                <span className="badge-verified">
                  <ShieldCheck size={12} />
                  <span>Verified Citation</span>
                </span>
              </div>
              <h3 className="card-question font-serif">
                "Can my landlord evict me without notice?"
              </h3>
              <p className="card-answer-prose">
                No. In India, a landlord cannot physically throw you out, cut off electricity or water, or change the locks. Even if your lease has expired or rent is delayed, Section 106 of the Transfer of Property Act and state Rent Control statutes mandate written statutory notice. A tenant can only be dispossessed pursuant to a formal eviction decree from a competent civil court.
              </p>
              <div className="card-source-citation">
                <span className="citation-title font-serif">Biswabani (P) Ltd. v. Santosh Kumar Dutta</span>
                <div className="citation-code-row">
                  <span className="citation-pill mono">(1980) 1 SCC 185</span>
                  <button
                    type="button"
                    className="btn-copy-cite"
                    onClick={() => copyCitation("(1980) 1 SCC 185", "biswabani")}
                    title="Copy citation"
                  >
                    {copiedCitationId === "biswabani" ? (
                      <span className="copy-success-badge"><Check size={12} /> Copied</span>
                    ) : (
                      "Copy"
                    )}
                  </button>
                  <button
                    type="button"
                    className="btn-verify-cite"
                    onClick={() => onNavigate('search', 'Biswabani landlord eviction notice rent control')}
                  >
                    <span>View Judgment</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            </TiltCard>

            {/* Card 3: Percept D'Mark / Non-compete (TiltCard with glossy highlight) */}
            <TiltCard className="editorial-answer-card" maxTilt={6}>
              <div className="card-top-kicker">
                <span className="kicker-tag mono">EMPLOYMENT & CONTRACTS</span>
                <span className="badge-verified">
                  <ShieldCheck size={12} />
                  <span>Verified Citation</span>
                </span>
              </div>
              <h3 className="card-question font-serif">
                "Are non-compete clauses valid after I quit my job?"
              </h3>
              <p className="card-answer-prose">
                Post-service non-compete clauses are completely void in India. Under <strong>Section 27 of the Indian Contract Act 1872</strong>, the doctrine of restraint of trade is absolute. An employer can only restrict you from competing during the actual tenure of your employment; the moment you resign, any covenant prohibiting you from working for a competitor is null and unenforceable.
              </p>
              <div className="card-source-citation">
                <span className="citation-title font-serif">Percept D'Mark (India) v. Zaheer Khan</span>
                <div className="citation-code-row">
                  <span className="citation-pill mono">(2006) 4 SCC 227</span>
                  <button
                    type="button"
                    className="btn-copy-cite"
                    onClick={() => copyCitation("(2006) 4 SCC 227", "percept")}
                    title="Copy citation"
                  >
                    {copiedCitationId === "percept" ? (
                      <span className="copy-success-badge"><Check size={12} /> Copied</span>
                    ) : (
                      "Copy"
                    )}
                  </button>
                  <button
                    type="button"
                    className="btn-verify-cite"
                    onClick={() => onNavigate('search', 'Percept DMark Section 27 non compete')}
                  >
                    <span>View Judgment</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            </TiltCard>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION B: SEE THE SOURCES (How Citations Link to Primary Judgments)
          ========================================================================= */}
      <section className="landing-section raised-section" id="sources">
        <div className="section-container">
          <div className="source-split-layout">
            <div className="source-prose-col">
              <span className="section-eyebrow mono">TRANSPARENCY & EVIDENCE</span>
              <h2 className="section-heading font-serif">See the sources.</h2>
              <p className="section-lead">
                Every principle presented by Justice is anchored directly to verbatim Supreme Court of India judgments. We never fabricate citations or synthesize imaginary case names.
              </p>

              <div className="source-features-list">
                <div className="source-feature-item">
                  <div className="feature-marker mono">01</div>
                  <div>
                    <h4 className="feature-title font-serif">Paragraph-Level Grounding</h4>
                    <p className="feature-desc">
                      Tap any citation tag to jump directly to the exact paragraph in the recorded Supreme Court judgment.
                    </p>
                  </div>
                </div>

                <div className="source-feature-item">
                  <div className="feature-marker mono">02</div>
                  <div>
                    <h4 className="feature-title font-serif">Article 141 Bench Hierarchy</h4>
                    <p className="feature-desc">
                      Understand whether a ruling comes from a 2-judge Division Bench or a 5-judge Constitution Bench, and if coordinate benches are bound.
                    </p>
                  </div>
                </div>

                <div className="source-feature-item">
                  <div className="feature-marker mono">03</div>
                  <div>
                    <h4 className="feature-title font-serif">Official Neutral Citations</h4>
                    <p className="feature-desc">
                      Cross-referenced against SCR (Supreme Court Reports) and SCC citations for courtroom and academic authenticity.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Interactive Source Inspector Mock (TiltCard) */}
            <div className="source-interactive-col">
              <TiltCard className="judgment-excerpt-window" maxTilt={5}>
                <div className="window-header">
                  <span className="window-pill mono">RECORDED JUDGMENT EXCERPT &bull; PARAGRAPH 35</span>
                  <span className="badge-verified">
                    <Check size={12} />
                    <span>VERIFIED RECORD</span>
                  </span>
                </div>

                <div className="window-body">
                  <div className="judgment-case-title font-serif">
                    D.K. Basu v. State of West Bengal
                  </div>
                  <div className="judgment-citation-line mono">
                    [1997] 1 S.C.R. 283 &bull; (1997) 1 SCC 416 &bull; Supreme Court of India
                  </div>

                  <blockquote className="judgment-quote font-serif">
                    "The police officer carrying out the arrest shall prepare a memo of arrest at the time of arrest and such memo shall be attested by at least one witness, who may be either a member of the family of the arrestee or a respectable person of the locality from where the arrest is made. It shall also be countersigned by the arrestee and shall contain the time and date of arrest."
                  </blockquote>

                  <div className="window-annotation">
                    <span className="annotation-label mono">HOLDING RATIO:</span>
                    <span className="annotation-text">
                      Constitutional safeguard against custodial violence and unlawful detention enforceable under Article 21 and 22.
                    </span>
                  </div>
                </div>

                <div className="window-footer">
                  <button
                    type="button"
                    className="window-action-btn"
                    onClick={() => onNavigate('citator')}
                  >
                    <span>Inspect Article 141 Lineage in Citator</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </TiltCard>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION C: FULL-WIDTH IVORY SECTION (#EFE8D6 background, #07110D text)
          "Ask the case anything" — Showcasing Case Chat
          ========================================================================= */}
      <section className="landing-section ivory-contrast-section" id="case-chat-showcase">
        <div className="section-container">
          <div className="ivory-header-block">
            <span className="ivory-eyebrow mono">CONVERSATIONAL JURISPRUDENCE</span>
            <h2 className="ivory-heading font-serif">Ask the case anything.</h2>
            <p className="ivory-lead">
              A dedicated Case Chat panel sits beside every judgment. Question its ratio, inspect the parties, ask why it matters for ordinary Indians, or request a four-line plain-language summary.
            </p>
          </div>

          {/* Interactive Case Chat Visual Spread */}
          <div className="ivory-chat-showcase-grid">
            {/* Left: Precedent Card Preview (TiltCard) */}
            <TiltCard className="ivory-case-card" maxTilt={5}>
              <div className="ivory-card-meta">
                <span className="ivory-court-pill mono">Supreme Court of India</span>
                <span className="ivory-year-pill mono">1973 &bull; 13 Judges</span>
              </div>
              <h3 className="ivory-case-title font-serif">
                Kesavananda Bharati v. State of Kerala
              </h3>
              <div className="ivory-citation mono">
                [1973] Supp. 1 SCR 1 &bull; AIR 1973 SC 1461
              </div>
              <p className="ivory-case-summary">
                The landmark 13-judge constitutional bench decision establishing that Parliament's amending power under Article 368 cannot abrogate the basic structure or essential framework of the Constitution of India.
              </p>
              <div className="ivory-case-chips">
                <span className="ivory-chip mono">Basic Structure</span>
                <span className="ivory-chip mono">Article 368</span>
                <span className="ivory-chip mono">Judicial Review</span>
              </div>
            </TiltCard>

            {/* Right: Live Interactive Case Chat Mock */}
            <div className="ivory-chat-window">
              <div className="ivory-chat-topbar">
                <div className="ivory-chat-title-group">
                  <MessageSquare size={16} className="ivory-chat-icon" />
                  <div>
                    <div className="ivory-chat-title font-serif">Ask about Kesavananda Bharati</div>
                    <div className="ivory-chat-subtitle mono">Scoped strictly to this judgment</div>
                  </div>
                </div>
                <span className="ivory-chat-badge mono">Live Model</span>
              </div>

              {/* Quick Prompt Buttons */}
              <div className="ivory-quick-prompts">
                <span className="quick-prompt-chip active">Summarise this case</span>
                <span className="quick-prompt-chip">What did the court decide?</span>
                <span className="quick-prompt-chip">Why does it matter for ordinary people?</span>
              </div>

              {/* Chat Messages */}
              <div className="ivory-chat-messages">
                <div className="ivory-msg user">
                  <span>Summarise this case</span>
                </div>
                <div className="ivory-msg assistant">
                  <div className="summary-section">
                    <strong className="summary-kicker mono">WHAT IT WAS ABOUT:</strong>
                    <p>The petitioner challenged Kerala land reform legislation that expropriated property belonging to a religious mutt.</p>
                  </div>
                  <div className="summary-section">
                    <strong className="summary-kicker mono">WHAT THE COURT DECIDED:</strong>
                    <p>By a 7:6 majority, the Supreme Court held that while Parliament can amend any provision of the Constitution, it cannot alter its basic structure.</p>
                  </div>
                  <div className="summary-section">
                    <strong className="summary-kicker mono">WHY IT MATTERS FOR ORDINARY INDIANS:</strong>
                    <p>It guarantees that no government, even with a two-thirds majority in Parliament, can abolish democracy, judicial independence, or fundamental rights.</p>
                  </div>
                </div>
              </div>

              <div className="ivory-chat-footer">
                <button
                  type="button"
                  className="ivory-chat-cta-btn"
                  onClick={() => onNavigate('search', 'Kesavananda Bharati basic structure')}
                >
                  <span>Open Kesavananda Bharati in Workspace</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION D: VERIFIED VS LABELLED AI ANSWERS (Trust Architecture)
          ========================================================================= */}
      <section className="landing-section dark-section" id="verified-vs-ai">
        <div className="section-container">
          <div className="section-header-block">
            <span className="section-eyebrow mono">TWO-TIER ARCHITECTURE OF TRUTH</span>
            <h2 className="section-heading font-serif">Verified Citations vs AI Answers.</h2>
            <p className="section-lead">
              Artificial intelligence often hallucinates legal cases. Justice enforces rigorous boundaries: when an answer is certified from law books, we label it verified; when an answer is general conceptual reasoning, we tell you immediately.
            </p>
          </div>

          <div className="tier-comparison-grid">
            {/* TIER 1: VERIFIED (TiltCard) */}
            <TiltCard className="tier-card tier-verified" maxTilt={5}>
              <div className="tier-badge-line">
                <span className="badge-verified">
                  <ShieldCheck size={14} />
                  <span>TIER 1 &bull; VERIFIED CITATION</span>
                </span>
              </div>
              <h3 className="tier-title font-serif">Primary Sourced Precedent</h3>
              <p className="tier-desc">
                Derived directly from our indexed library of official Supreme Court judgments and bare acts. Includes exact paragraph numbers, neutral citations, and bench size metrics.
              </p>
              <ul className="tier-points-list">
                <li><Check size={14} className="point-icon green" /> Verbatim text extracts from official Law Reports</li>
                <li><Check size={14} className="point-icon green" /> Validated under Article 141 judicial discipline</li>
                <li><Check size={14} className="point-icon green" /> Zero synthetic case numbers or imaginary precedents</li>
              </ul>
              <div className="tier-sample-pill green mono">
                Status: Good Law (Affirmed by Coordinate Bench)
              </div>
            </TiltCard>

            {/* TIER 2: AI ANSWER NOT VERIFIED (TiltCard) */}
            <TiltCard className="tier-card tier-unverified" maxTilt={5}>
              <div className="tier-badge-line">
                <span className="badge-not-verified">
                  <AlertTriangle size={14} />
                  <span>TIER 2 &bull; AI ANSWER NOT VERIFIED</span>
                </span>
              </div>
              <h3 className="tier-title font-serif">General Conceptual Legal Explanation</h3>
              <p className="tier-desc">
                When a query cannot be grounded in our primary judgment corpus, the AI provides conceptual background with an explicit warning label.
              </p>
              <ul className="tier-points-list">
                <li><AlertTriangle size={14} className="point-icon amber" /> Explicitly prefixed with: <em>"AI answer, not verified against a legal database."</em></li>
                <li><AlertTriangle size={14} className="point-icon amber" /> Never names imaginary judgments or unverified citations</li>
                <li><AlertTriangle size={14} className="point-icon amber" /> Accompanied by advice to verify with primary sources or an advocate</li>
              </ul>
              <div className="tier-sample-pill amber mono">
                Notice: General information only. Check a primary source.
              </div>
            </TiltCard>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION E: FOOTER
          ========================================================================= */}
      <footer className="landing-footer" role="contentinfo">
        <div className="section-container">
          <div className="footer-top-row">
            <div className="footer-brand-col">
              <div className="footer-wordmark font-serif">
                Justice<span className="copper-period">.</span>
              </div>
              <p className="footer-tagline">
                Plain-language Indian Supreme Court jurisprudence and constitutional analysis.
              </p>
            </div>

            <div className="footer-nav-col">
              <span className="footer-col-title mono">WORKSPACE MODULES</span>
              <ul className="footer-links-list">
                {MODULE_LINKS.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      className="footer-link-btn"
                      onClick={() => onNavigate(m.id)}
                    >
                      {m.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div className="footer-nav-col">
              <span className="footer-col-title mono">CONSTITUTIONAL BOUNDARIES</span>
              <ul className="footer-links-list">
                <li><span className="footer-text-note">Article 141 (Binding Precedents)</span></li>
                <li><span className="footer-text-note">Article 21 (Personal Liberty)</span></li>
                <li><span className="footer-text-note">Section 27 (Indian Contract Act)</span></li>
                <li><span className="footer-text-note">Section 74 (Liquidated Damages)</span></li>
              </ul>
            </div>
          </div>

          <div className="footer-bottom-row">
            <div className="footer-disclaimer">
              Justice is an independent legal research instrument. It does not provide legal advice or create an attorney-client relationship. Consult an advocate enrolled with the Bar Council of India before acting on legal matters.
            </div>
            <div className="footer-meta-right mono">
              <span>Jurisdiction: Republic of India</span> &bull; <span>FastAPI + Qdrant</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
