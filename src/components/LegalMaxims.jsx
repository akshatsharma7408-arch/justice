import React, { useState, useEffect, useMemo } from 'react';
import { 
  Search, Sparkles, BookOpen, Layers, CheckCircle2, 
  RotateCw, HelpCircle, ChevronDown, ChevronUp, ArrowRight,
  ExternalLink, Bookmark, Check, X, Shuffle, Award
} from 'lucide-react';
import { LEGAL_MAXIMS } from '../data/legalMaxims';
import { 
  fetchMaximsWithBackend, 
  fetchMaximOfTheDayWithBackend, 
  explainMaximWithBackend 
} from '../config/gemini';

export default function LegalMaxims() {
  const [activeView, setActiveView] = useState('browse'); // 'browse', 'flashcards', 'quiz'
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [selectedLetter, setSelectedLetter] = useState('ALL');
  const [expandedCardId, setExpandedCardId] = useState('audi-alteram-partem');
  
  // Backend data + Fallback
  const [maximsList, setMaximsList] = useState(LEGAL_MAXIMS);
  const [maximOfTheDay, setMaximOfTheDay] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // AI Explain State per maxim
  const [explainingId, setExplainingId] = useState(null);
  const [aiExplanations, setAiExplanations] = useState({});
  const [factScenarios, setFactScenarios] = useState({});

  // Flashcards state
  const [flashcardIndex, setFlashcardIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [masteredMaxims, setMasteredMaxims] = useState(() => {
    try {
      const saved = localStorage.getItem('justice_maxims_mastered');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Quiz state
  const [quizQuestionIndex, setQuizQuestionIndex] = useState(0);
  const [quizScore, setQuizScore] = useState(0);
  const [selectedOption, setSelectedOption] = useState(null);
  const [quizAnswered, setQuizAnswered] = useState(false);

  // Alphabet list for A-Z index
  const alphabet = ['ALL', ...'ABCDEFGHIJKLMNOPQRSTUVWYZ'.split('')];

  // Distinct categories
  const categories = useMemo(() => {
    const cats = new Set(LEGAL_MAXIMS.map(m => m.category || 'General'));
    return ['ALL', ...Array.from(cats).sort()];
  }, []);

  // Fetch Maxim of the Day & List from backend on mount
  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    // 1. Fetch Maxim of the day
    fetchMaximOfTheDayWithBackend()
      .then(res => {
        if (!isMounted) return;
        if (res && res.maxim) setMaximOfTheDay(res.maxim);
      })
      .catch(err => {
        console.warn("[LegalMaxims] Backend random maxim failed, using local stable fallback:", err.message);
        // Fallback: stable daily hash
        const todayStr = new Date().toISOString().split('T')[0];
        let hash = 0;
        for (let i = 0; i < todayStr.length; i++) {
          hash = (hash << 5) - hash + todayStr.charCodeAt(i);
          hash |= 0;
        }
        const idx = Math.abs(hash) % LEGAL_MAXIMS.length;
        if (isMounted) setMaximOfTheDay(LEGAL_MAXIMS[idx]);
      });

    // 2. Fetch all maxims
    fetchMaximsWithBackend(searchQuery, selectedCategory, selectedLetter, 1, 300)
      .then(res => {
        if (!isMounted) return;
        if (res && res.results && res.results.length > 0) {
          setMaximsList(res.results);
        }
      })
      .catch(err => {
        console.warn("[LegalMaxims] Backend maxims fetch failed, using local corpus fallback:", err.message);
        if (isMounted) setMaximsList(LEGAL_MAXIMS);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [searchQuery, selectedCategory, selectedLetter]);

  // Client-side filtering as fallback/refinement
  const filteredMaxims = useMemo(() => {
    return maximsList.filter(item => {
      if (selectedCategory !== 'ALL' && item.category !== selectedCategory) return false;
      if (selectedLetter !== 'ALL' && !item.maxim.toLowerCase().startsWith(selectedLetter.toLowerCase())) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const inMaxim = item.maxim.toLowerCase().includes(q);
        const inMeaning = item.meaning.toLowerCase().includes(q);
        const inExpl = (item.explanation || '').toLowerCase().includes(q);
        return inMaxim || inMeaning || inExpl;
      }
      return true;
    });
  }, [maximsList, selectedCategory, selectedLetter, searchQuery]);

  // Flashcards navigation
  const currentFlashcard = filteredMaxims[flashcardIndex] || filteredMaxims[0] || LEGAL_MAXIMS[0];

  const handleNextFlashcard = () => {
    setIsFlipped(false);
    setFlashcardIndex((prev) => (prev + 1) % (filteredMaxims.length || 1));
  };

  const handlePrevFlashcard = () => {
    setIsFlipped(false);
    setFlashcardIndex((prev) => (prev - 1 + (filteredMaxims.length || 1)) % (filteredMaxims.length || 1));
  };

  const handleShuffleFlashcards = () => {
    setIsFlipped(false);
    const rand = Math.floor(Math.random() * (filteredMaxims.length || 1));
    setFlashcardIndex(rand);
  };

  const toggleMasteredStatus = (id) => {
    setMasteredMaxims((prev) => {
      const next = prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id];
      try {
        localStorage.setItem('justice_maxims_mastered', JSON.stringify(next));
      } catch (err) {
        console.warn("Failed to persist mastered status:", err);
      }
      return next;
    });
  };

  // Quiz state generation
  const currentQuizItem = useMemo(() => {
    const list = filteredMaxims.length >= 4 ? filteredMaxims : LEGAL_MAXIMS;
    const target = list[quizQuestionIndex % list.length];
    
    // Pick 3 random distractor meanings from other maxims
    const otherItems = LEGAL_MAXIMS.filter(m => m.id !== target.id);
    const shuffledOthers = [...otherItems].sort(() => 0.5 - Math.random()).slice(0, 3);
    const options = [
      { id: 'correct', text: target.meaning, isCorrect: true },
      ...shuffledOthers.map((m, i) => ({ id: `distractor-${i}`, text: m.meaning, isCorrect: false }))
    ].sort(() => 0.5 - Math.random());

    return { target, options };
  }, [quizQuestionIndex, filteredMaxims]);

  const handleSelectQuizOption = (option) => {
    if (quizAnswered) return;
    setSelectedOption(option.id);
    setQuizAnswered(true);
    if (option.isCorrect) {
      setQuizScore(s => s + 1);
    }
  };

  const handleNextQuizQuestion = () => {
    setSelectedOption(null);
    setQuizAnswered(false);
    setQuizQuestionIndex(i => i + 1);
  };

  // AI Explanation handler
  const handleRequestAiExplanation = async (maximItem) => {
    setExplainingId(maximItem.id);
    const userFact = factScenarios[maximItem.id] || null;

    try {
      const res = await explainMaximWithBackend(maximItem.maxim, userFact);
      if (res && res.explanation) {
        setAiExplanations(prev => ({
          ...prev,
          [maximItem.id]: {
            explanation: res.explanation,
            model_used: res.model_used || 'openai/gpt-oss-120b'
          }
        }));
      }
    } catch (err) {
      console.warn("[LegalMaxims] AI explanation failed:", err.message);
      setAiExplanations(prev => ({
        ...prev,
        [maximItem.id]: {
          explanation: `${maximItem.explanation} (Principle applied grounded in verified legal authorities.)`,
          model_used: 'stored_corpus_baseline'
        }
      }));
    } finally {
      setExplainingId(null);
    }
  };

  const activeDaily = maximOfTheDay || LEGAL_MAXIMS[0];

  return (
    <div className="workspace-module-pane">
      {/* Module Workspace Header */}
      <div className="workspace-module-header">
        <div className="module-breadcrumbs">
          <span className="crumb-root">WORKSPACE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">LEGAL MAXIMS</span>
        </div>
        <h1 className="module-heading font-judicial">Latin Legal Maxims & Jurisprudence</h1>
        <p className="module-description">
          Authoritative compendium of over 240 classical Latin legal maxims, foundational common law canons, 
          and constitutional principles. Designed for rigorous judicial study, contract drafting, and bar advocacy.
        </p>

        {/* View Mode Switcher */}
        <div className="maxims-view-tabs">
          <button
            type="button"
            className={`maxims-view-btn ${activeView === 'browse' ? 'active' : ''}`}
            onClick={() => setActiveView('browse')}
          >
            <BookOpen size={14} />
            <span>Directory & Search</span>
          </button>

          <button
            type="button"
            className={`maxims-view-btn ${activeView === 'flashcards' ? 'active' : ''}`}
            onClick={() => setActiveView('flashcards')}
          >
            <Layers size={14} />
            <span>Interactive Flashcards</span>
          </button>

          <button
            type="button"
            className={`maxims-view-btn ${activeView === 'quiz' ? 'active' : ''}`}
            onClick={() => setActiveView('quiz')}
          >
            <HelpCircle size={14} />
            <span>Knowledge Quiz</span>
          </button>
        </div>
      </div>

      {/* =========================================================================
          MAXIM OF THE DAY CARD (Pinned at top of workspace)
          ========================================================================= */}
      {activeDaily && (
        <div className="daily-maxim-card">
          <div className="daily-card-header">
            <div className="daily-badge-group">
              <Sparkles size={14} className="daily-sparkle-icon" />
              <span className="daily-title-badge">MAXIM OF THE DAY</span>
              <span className="daily-date-stamp mono">{new Date().toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
            </div>
            <span className="maxim-category-chip">{activeDaily.category}</span>
          </div>

          <div className="daily-body">
            <h2 className="daily-latin font-judicial">{activeDaily.maxim}</h2>
            <div className="daily-meaning font-judicial">"{activeDaily.meaning}"</div>
            <p className="daily-explanation">{activeDaily.explanation}</p>
            {activeDaily.example && (
              <div className="daily-example-box">
                <span className="example-label">PRACTICAL SCENARIO:</span>{' '}
                <span className="example-text">{activeDaily.example}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          VIEW 1: DIRECTORY & SEARCH
          ========================================================================= */}
      {activeView === 'browse' && (
        <>
          {/* Search Box */}
          <div className="maxims-search-row">
            <div className="search-input-wrapper">
              <Search className="search-input-icon" size={17} />
              <input
                type="text"
                className="search-input-field"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search Latin maxim or English meaning (e.g. 'audi', 'mens rea', 'buyer beware')..."
              />
            </div>
          </div>

          {/* A-Z Alphabet Filter Strip */}
          <div className="alphabet-strip-container">
            <span className="alphabet-label mono">INDEX:</span>
            <div className="alphabet-scroll-row">
              {alphabet.map((letter) => (
                <button
                  key={letter}
                  type="button"
                  className={`alphabet-btn mono ${selectedLetter === letter ? 'active' : ''}`}
                  onClick={() => setSelectedLetter(letter)}
                >
                  {letter}
                </button>
              ))}
            </div>
          </div>

          {/* Category Chips Bar */}
          <div className="category-chips-strip">
            <span className="category-strip-label">SUBJECT:</span>
            <div className="category-chips-list">
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  className={`category-pill-btn ${selectedCategory === cat ? 'active' : ''}`}
                  onClick={() => setSelectedCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Results Summary Bar */}
          <div className="maxims-results-meta-bar">
            <span className="results-count-text">
              Showing <strong>{filteredMaxims.length}</strong> verified legal maxims
            </span>
            {masteredMaxims.length > 0 && (
              <span className="mastered-stats-pill mono">
                <Check size={12} /> {masteredMaxims.length} mastered in flashcards
              </span>
            )}
          </div>

          {/* Maxims Cards Grid */}
          <div className="maxims-cards-stream">
            {filteredMaxims.length === 0 ? (
              <div className="workspace-empty-card">
                <BookOpen size={32} className="empty-icon" />
                <h3 className="empty-heading font-judicial">No matching legal maxims found</h3>
                <p className="empty-text">
                  Try clearing your search query or selecting 'ALL' in the A-Z alphabet index.
                </p>
              </div>
            ) : (
              filteredMaxims.map((item) => {
                const isExpanded = expandedCardId === item.id;
                const isMastered = masteredMaxims.includes(item.id);
                const aiExplanation = aiExplanations[item.id];
                const isExplaining = explainingId === item.id;

                return (
                  <article key={item.id} className={`maxim-card ${isExpanded ? 'expanded' : ''}`}>
                    <div 
                      className="maxim-card-header" 
                      onClick={() => setExpandedCardId(isExpanded ? null : item.id)}
                    >
                      <div className="maxim-title-group">
                        <div className="maxim-latin-row">
                          <h3 className="maxim-latin-text font-judicial">{item.maxim}</h3>
                          <span className="maxim-category-chip">{item.category}</span>
                          {isMastered && (
                            <span className="mastered-check-chip" title="Mastered in flashcard practice">
                              <Check size={11} /> Mastered
                            </span>
                          )}
                        </div>
                        <div className="maxim-meaning-text font-judicial">"{item.meaning}"</div>
                      </div>

                      <button 
                        type="button" 
                        className="btn-toggle-expand"
                        aria-label={isExpanded ? "Collapse" : "Expand"}
                      >
                        {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </button>
                    </div>

                    {/* Expandable Details Canvas */}
                    {isExpanded && (
                      <div className="maxim-expanded-content">
                        {/* 2-3 sentence simple explanation */}
                        <div className="maxim-section-block">
                          <div className="section-label-kicker mono">LEGAL DOCTRINE & EXPLANATION</div>
                          <p className="section-prose">{item.explanation}</p>
                        </div>

                        {/* Real-world Practical Scenario */}
                        {item.example && (
                          <div className="maxim-section-block example-block">
                            <div className="section-label-kicker mono">PRACTICAL SCENARIO</div>
                            <p className="section-prose font-judicial">"{item.example}"</p>
                          </div>
                        )}

                        {/* Origin Note */}
                        {item.origin_note && (
                          <div className="maxim-section-block origin-block">
                            <span className="origin-title mono">HISTORICAL ORIGIN:</span>{' '}
                            <span className="origin-text">{item.origin_note}</span>
                          </div>
                        )}

                        {/* Related Maxims Chips */}
                        {item.related_maxims && item.related_maxims.length > 0 && (
                          <div className="maxim-section-block">
                            <div className="section-label-kicker mono">RELATED MAXIMS</div>
                            <div className="related-chips-row">
                              {item.related_maxims.map((relId) => {
                                const relItem = LEGAL_MAXIMS.find(m => m.id === relId);
                                return (
                                  <button
                                    key={relId}
                                    type="button"
                                    className="related-maxim-chip"
                                    onClick={() => {
                                      setSearchQuery(relItem ? relItem.maxim : relId);
                                      setExpandedCardId(relId);
                                    }}
                                  >
                                    <span>{relItem ? relItem.maxim : relId}</span>
                                    <ArrowRight size={11} />
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Indian Case References or Needs Citation Badge */}
                        <div className="maxim-section-block">
                          <div className="section-label-kicker mono">INDIAN JUDICIAL PRECEDENTS</div>
                          {item.indian_case_refs && item.indian_case_refs.length > 0 ? (
                            <div className="case-refs-list">
                              {item.indian_case_refs.map((cRef, idx) => (
                                <div key={idx} className="case-ref-row">
                                  <div className="case-name font-judicial">{cRef.case_name}</div>
                                  <div className="case-citation mono">{cRef.citation}</div>
                                  {cRef.source_url && (
                                    <a
                                      href={cRef.source_url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="case-source-link"
                                    >
                                      <span>View Judgment</span>
                                      <ExternalLink size={11} />
                                    </a>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="needs-citation-badge mono">
                              <span>Needs citation</span> &bull; 
                              <span className="needs-sub">Strict accuracy: no synthetic case citations permitted</span>
                            </div>
                          )}
                        </div>

                        {/* Grounded Legal AI Explanation Bar */}
                        <div className="maxim-ai-interactive-panel">
                          <div className="ai-panel-header">
                            <div className="ai-title-group">
                              <Sparkles size={14} className="sparkle-icon" />
                              <span className="ai-title">AI-GROUNDED LEGAL SYNTHESIS</span>
                            </div>
                            <button
                              type="button"
                              className="btn-ai-explain"
                              onClick={() => handleRequestAiExplanation(item)}
                              disabled={isExplaining}
                            >
                              <span>{isExplaining ? 'Synthesizing...' : 'Explain with Legal AI'}</span>
                            </button>
                          </div>

                          <div className="fact-input-row">
                            <input
                              type="text"
                              className="fact-scenario-input"
                              placeholder="Optional: Enter a brief fact scenario to apply this maxim to..."
                              value={factScenarios[item.id] || ''}
                              onChange={(e) => setFactScenarios({ ...factScenarios, [item.id]: e.target.value })}
                            />
                          </div>

                          {aiExplanation && (
                            <div className="ai-explanation-box">
                              <div className="ai-box-badge mono" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                                <span>GROUNDED EXPLANATION</span>
                                {aiExplanation?.model_used && (
                                  <span className={`ai-model-tag mono ${aiExplanation.model_used.includes('baseline') || aiExplanation.model_used.includes('fallback') ? 'is-fallback' : 'is-neural'}`} title={`Model: ${aiExplanation.model_used}`}>
                                    [{aiExplanation.model_used.includes('baseline') ? 'CORPUS BASELINE' : aiExplanation.model_used}]
                                  </span>
                                )}
                              </div>
                              <p className="ai-box-text">
                                {typeof aiExplanation === 'string' ? aiExplanation : aiExplanation.explanation}
                              </p>
                            </div>
                          )}
                        </div>

                        {/* Footer Card Actions */}
                        <div className="maxim-card-footer">
                          <button
                            type="button"
                            className={`btn-mastered-toggle ${isMastered ? 'mastered' : ''}`}
                            onClick={() => toggleMasteredStatus(item.id)}
                          >
                            {isMastered ? (
                              <>
                                <Check size={13} />
                                <span>Mastered in Flashcards</span>
                              </>
                            ) : (
                              <>
                                <Bookmark size={13} />
                                <span>Mark as Known</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })
            )}
          </div>
        </>
      )}

      {/* =========================================================================
          VIEW 2: FLASHCARDS MODE
          ========================================================================= */}
      {activeView === 'flashcards' && (
        <div className="flashcards-stage">
          <div className="flashcards-top-meta">
            <span className="flashcard-counter mono">
              CARD {flashcardIndex + 1} OF {filteredMaxims.length || 1}
            </span>
            <div className="flashcard-progress-tags">
              <span className="progress-pill mastered mono">
                {masteredMaxims.length} MASTERED
              </span>
              <span className="progress-pill remaining mono">
                {(filteredMaxims.length || LEGAL_MAXIMS.length) - masteredMaxims.length} REVIEWING
              </span>
            </div>
          </div>

          {/* Interactive Flip Card */}
          <div className="flashcard-interactive-container" onClick={() => setIsFlipped(!isFlipped)}>
            <div className={`flashcard-surface ${isFlipped ? 'flipped' : ''}`}>
              {/* FRONT: Latin Maxim */}
              <div className="flashcard-face flashcard-front">
                <span className="flashcard-badge mono">LATIN LEGAL MAXIM &bull; CLICK TO FLIP</span>
                <span className="flashcard-cat">{currentFlashcard.category}</span>
                <h2 className="flashcard-latin-title font-judicial">{currentFlashcard.maxim}</h2>
                <div className="flip-instruction">
                  <RotateCw size={14} />
                  <span>Click to reveal English meaning</span>
                </div>
              </div>

              {/* BACK: English Meaning & Doctrine */}
              <div className="flashcard-face flashcard-back">
                <span className="flashcard-badge mono">ENGLISH MEANING & DOCTRINE</span>
                <h3 className="flashcard-meaning-title font-judicial">"{currentFlashcard.meaning}"</h3>
                <p className="flashcard-back-expl">{currentFlashcard.explanation}</p>
                {currentFlashcard.example && (
                  <div className="flashcard-back-eg">
                    <strong>Scenario:</strong> {currentFlashcard.example}
                  </div>
                )}
                <div className="flip-instruction">
                  <RotateCw size={14} />
                  <span>Click to flip back</span>
                </div>
              </div>
            </div>
          </div>

          {/* Flashcard Action Buttons */}
          <div className="flashcard-controls-bar">
            <button
              type="button"
              className="btn-secondary"
              onClick={handlePrevFlashcard}
            >
              Previous Card
            </button>

            <button
              type="button"
              className={`btn-knowledge-toggle ${masteredMaxims.includes(currentFlashcard.id) ? 'known' : 'review'}`}
              onClick={(e) => {
                e.stopPropagation();
                toggleMasteredStatus(currentFlashcard.id);
              }}
            >
              {masteredMaxims.includes(currentFlashcard.id) ? (
                <>
                  <CheckCircle2 size={16} />
                  <span>Mastered (Click to review again)</span>
                </>
              ) : (
                <>
                  <Bookmark size={16} />
                  <span>Know It (Mark as Mastered)</span>
                </>
              )}
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={handleShuffleFlashcards}
              title="Pick a random card"
            >
              <Shuffle size={14} />
              <span>Shuffle</span>
            </button>

            <button
              type="button"
              className="btn-primary"
              onClick={handleNextFlashcard}
            >
              <span>Next Card</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* =========================================================================
          VIEW 3: KNOWLEDGE QUIZ MODE
          ========================================================================= */}
      {activeView === 'quiz' && (
        <div className="quiz-stage-container">
          <div className="quiz-score-header">
            <div className="quiz-question-ord mono">
              QUESTION {quizQuestionIndex + 1}
            </div>
            <div className="quiz-score-badge mono">
              <Award size={14} />
              <span>SCORE: {quizScore} / {quizQuestionIndex + (quizAnswered ? 1 : 0)}</span>
            </div>
          </div>

          <div className="quiz-card-surface">
            <span className="quiz-kicker mono">WHAT IS THE MEANING OF THIS LEGAL MAXIM?</span>
            <h2 className="quiz-maxim-question font-judicial">{currentQuizItem.target.maxim}</h2>
            <div className="quiz-category-tag">{currentQuizItem.target.category}</div>

            {/* 4 Multiple Choice Options */}
            <div className="quiz-options-grid">
              {currentQuizItem.options.map((opt) => {
                let statusClass = '';
                if (quizAnswered) {
                  if (opt.isCorrect) statusClass = 'correct';
                  else if (selectedOption === opt.id) statusClass = 'incorrect';
                }

                return (
                  <button
                    key={opt.id}
                    type="button"
                    className={`quiz-option-btn ${selectedOption === opt.id ? 'selected' : ''} ${statusClass}`}
                    onClick={() => handleSelectQuizOption(opt)}
                    disabled={quizAnswered}
                  >
                    <span className="quiz-option-letter mono">
                      {opt.id === 'distractor-0' ? 'B' : opt.id === 'distractor-1' ? 'C' : opt.id === 'distractor-2' ? 'D' : 'A'}
                    </span>
                    <span className="quiz-option-text font-judicial">"{opt.text}"</span>
                    {quizAnswered && opt.isCorrect && <Check size={16} className="option-feedback-icon correct" />}
                    {quizAnswered && !opt.isCorrect && selectedOption === opt.id && <X size={16} className="option-feedback-icon incorrect" />}
                  </button>
                );
              })}
            </div>

            {/* Quiz Post-Answer Feedback */}
            {quizAnswered && (
              <div className="quiz-feedback-banner">
                <div className="feedback-result-line">
                  {currentQuizItem.options.find(o => o.id === selectedOption)?.isCorrect ? (
                    <span className="feedback-text correct">Correct! Outstanding retention.</span>
                  ) : (
                    <span className="feedback-text incorrect">
                      Incorrect. The correct meaning is: "{currentQuizItem.target.meaning}"
                    </span>
                  )}
                </div>
                <p className="feedback-expl">{currentQuizItem.target.explanation}</p>

                <div className="quiz-next-bar">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={handleNextQuizQuestion}
                  >
                    <span>Next Question</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
