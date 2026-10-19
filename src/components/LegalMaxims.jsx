import React, { useState, useEffect, useMemo } from 'react';
import { 
  Search, Sparkles, BookOpen, Layers, CheckCircle2, 
  RotateCw, HelpCircle, ChevronDown, ChevronUp, ArrowRight,
  ExternalLink, Bookmark, Check, X, Shuffle, Award, AlertTriangle 
} from 'lucide-react';
import { LEGAL_MAXIMS } from '../data/legalMaxims';
import { 
  fetchMaximsWithBackend, 
  fetchMaximOfTheDayWithBackend, 
  explainMaximWithBackend 
} from '../config/gemini';
import { renderWithBadges } from '../utils/badgeFormatter';

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

  // Fetch Maxim of the Day & List from backend
  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    fetchMaximOfTheDayWithBackend()
      .then(res => {
        if (!isMounted) return;
        if (res && res.maxim) setMaximOfTheDay(res.maxim);
      })
      .catch(() => {
        const todayStr = new Date().toISOString().split('T')[0];
        let hash = 0;
        for (let i = 0; i < todayStr.length; i++) {
          hash = (hash << 5) - hash + todayStr.charCodeAt(i);
          hash |= 0;
        }
        const idx = Math.abs(hash) % LEGAL_MAXIMS.length;
        if (isMounted) setMaximOfTheDay(LEGAL_MAXIMS[idx]);
      });

    fetchMaximsWithBackend(searchQuery, selectedCategory, selectedLetter, 1, 300)
      .then(res => {
        if (!isMounted) return;
        if (res && res.results && res.results.length > 0) {
          setMaximsList(res.results);
        }
      })
      .catch(() => {
        if (isMounted) setMaximsList(LEGAL_MAXIMS);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [searchQuery, selectedCategory, selectedLetter]);

  // Client-side filter
  const filteredMaxims = useMemo(() => {
    return maximsList.filter(item => {
      if (selectedCategory !== 'ALL' && item.category !== selectedCategory) return false;
      if (selectedLetter !== 'ALL' && !item.maxim.toUpperCase().startsWith(selectedLetter)) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const text = `${item.maxim} ${item.meaning} ${item.explanation || ''} ${item.category || ''}`.toLowerCase();
        return text.includes(q);
      }
      return true;
    });
  }, [maximsList, selectedCategory, selectedLetter, searchQuery]);

  const toggleMasteredStatus = (id) => {
    setMasteredMaxims(prev => {
      const next = prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id];
      try {
        localStorage.setItem('justice_maxims_mastered', JSON.stringify(next));
      } catch (e) {}
      return next;
    });
  };

  // Flashcards rotation
  const currentFlashcard = filteredMaxims[flashcardIndex] || LEGAL_MAXIMS[0];

  const handleNextFlashcard = () => {
    setIsFlipped(false);
    setFlashcardIndex(prev => (prev + 1) % (filteredMaxims.length || 1));
  };

  const handlePrevFlashcard = () => {
    setIsFlipped(false);
    setFlashcardIndex(prev => (prev - 1 + (filteredMaxims.length || 1)) % (filteredMaxims.length || 1));
  };

  const handleShuffleFlashcards = () => {
    setIsFlipped(false);
    const rand = Math.floor(Math.random() * (filteredMaxims.length || 1));
    setFlashcardIndex(rand);
  };

  // Quiz Question Generator
  const currentQuizItem = useMemo(() => {
    const pool = filteredMaxims.length >= 4 ? filteredMaxims : LEGAL_MAXIMS;
    const target = pool[quizQuestionIndex % pool.length];
    
    // Pick 3 distractors
    const otherCandidates = pool.filter(m => m.id !== target.id);
    const shuffled = [...otherCandidates].sort(() => 0.5 - Math.random());
    const distractors = shuffled.slice(0, 3).map((d, i) => ({
      id: `distractor-${i}`,
      text: d.meaning,
      isCorrect: false
    }));

    const options = [
      { id: 'correct-opt', text: target.meaning, isCorrect: true },
      ...distractors
    ].sort(() => 0.5 - Math.random());

    return { target, options };
  }, [quizQuestionIndex, filteredMaxims]);

  const handleSelectQuizOption = (opt) => {
    if (quizAnswered) return;
    setSelectedOption(opt.id);
    setQuizAnswered(true);
    if (opt.isCorrect) {
      setQuizScore(prev => prev + 1);
    }
  };

  const handleNextQuizQuestion = () => {
    setQuizAnswered(false);
    setSelectedOption(null);
    setQuizQuestionIndex(prev => prev + 1);
  };

  return (
    <div className="module-view-container animate-fade-in">
      {/* Module Header */}
      <div className="module-header-block">
        <div className="module-breadcrumbs mono">
          <span className="crumb-root">JUSTICE</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-leaf">LEGAL MAXIMS & CANONS</span>
        </div>
        <h1 className="module-title font-serif">Legal Maxims & Latin Canons</h1>
        <p className="module-subtitle">
          Over 240 classical Latin legal maxims mapped to Indian Supreme Court jurisprudence, interactive 3D flashcards, and knowledge assessment quizzes.
        </p>

        {/* View Mode Switcher */}
        <div className="module-tabs-strip">
          {[
            { id: 'browse', label: 'Browse & Doctrine Search' },
            { id: 'flashcards', label: '3D Flip Flashcards' },
            { id: 'quiz', label: 'Interactive Knowledge Quiz' }
          ].map((v) => (
            <button
              key={v.id}
              type="button"
              className={`module-tab-btn ${activeView === v.id ? 'is-active' : ''}`}
              onClick={() => setActiveView(v.id)}
            >
              <span>{v.label}</span>
              {activeView === v.id && <span className="tab-copper-line" />}
            </button>
          ))}
        </div>
      </div>

      {/* =========================================================================
          VIEW 1: BROWSE & SEARCH
          ========================================================================= */}
      {activeView === 'browse' && (
        <div className="maxims-browse-stage animate-fade-in">
          {/* Maxim of the Day Card */}
          {maximOfTheDay && (
            <div className="maxim-daily-hero-card">
              <div className="daily-kicker-strip">
                <span className="kicker-badge mono">MAXIM OF THE DAY</span>
                <span className="daily-category mono">{maximOfTheDay.category}</span>
              </div>
              <h2 className="daily-latin-heading font-serif">{maximOfTheDay.maxim}</h2>
              <div className="daily-meaning-quote font-serif">"{maximOfTheDay.meaning}"</div>
              <p className="daily-explanation">{maximOfTheDay.explanation}</p>
              {maximOfTheDay.example && (
                <div className="daily-scenario-box font-serif">
                  <span className="scenario-label mono">PRACTICAL SCENARIO:</span> {maximOfTheDay.example}
                </div>
              )}
            </div>
          )}

          {/* Search & Filter Bar */}
          <div className="maxims-filter-toolbar">
            <div className="maxims-search-box">
              <Search size={16} className="search-icon" />
              <input
                type="text"
                className="maxims-search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search Latin maxims, English meanings, or doctrine keywords..."
                aria-label="Search Legal Maxims"
              />
            </div>

            {/* A-Z Alphabet Filter */}
            <div className="alphabet-bar mono">
              {alphabet.map((letter) => (
                <button
                  key={letter}
                  type="button"
                  className={`alpha-btn ${selectedLetter === letter ? 'is-active' : ''}`}
                  onClick={() => setSelectedLetter(letter)}
                >
                  {letter}
                </button>
              ))}
            </div>
          </div>

          {/* Maxims List */}
          <div className="maxims-cards-stack">
            {filteredMaxims.length === 0 ? (
              <div className="results-empty-state">
                <BookOpen size={32} className="empty-state-icon" />
                <h3 className="empty-title font-serif">No Maxims Found</h3>
                <p className="empty-desc">Try clearing the letter filter or search term.</p>
              </div>
            ) : (
              filteredMaxims.map((item) => {
                const isExpanded = expandedCardId === item.id;
                const isMastered = masteredMaxims.includes(item.id);

                return (
                  <article key={item.id} className="maxim-item-card">
                    <div
                      className="maxim-card-summary-row"
                      onClick={() => setExpandedCardId(isExpanded ? null : item.id)}
                    >
                      <div className="maxim-main-content">
                        <div className="maxim-meta-line mono">
                          <span className="maxim-cat-tag">{item.category}</span>
                          {isMastered && (
                            <span className="mastered-pill">
                              <Check size={11} /> Mastered
                            </span>
                          )}
                        </div>
                        <h3 className="maxim-latin-title font-serif">{item.maxim}</h3>
                        <div className="maxim-meaning-line font-serif">"{item.meaning}"</div>
                      </div>

                      <button
                        type="button"
                        className="btn-expand-maxim"
                        aria-label={isExpanded ? 'Collapse' : 'Expand'}
                      >
                        {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </button>
                    </div>

                    {isExpanded && (
                      <div className="maxim-expanded-drawer animate-fade-in">
                        <div className="maxim-section">
                          <div className="section-kicker mono">LEGAL DOCTRINE & EXPLANATION</div>
                          <p className="section-prose">{item.explanation}</p>
                        </div>

                        {item.example && (
                          <div className="maxim-section">
                            <div className="section-kicker mono">PRACTICAL SCENARIO</div>
                            <p className="section-prose font-serif">"{item.example}"</p>
                          </div>
                        )}

                        {item.indian_case_refs && item.indian_case_refs.length > 0 && (
                          <div className="maxim-section">
                            <div className="section-kicker mono">INDIAN JUDICIAL PRECEDENTS</div>
                            <div className="precedents-list">
                              {item.indian_case_refs.map((ref, idx) => (
                                <div key={idx} className="precedent-pill mono">
                                  <strong>{ref.case_name}</strong> &bull; {ref.citation}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="maxim-footer-bar">
                          <button
                            type="button"
                            className={`btn-mastered-toggle ${isMastered ? 'is-mastered' : ''} mono`}
                            onClick={() => toggleMasteredStatus(item.id)}
                          >
                            <Check size={13} />
                            <span>{isMastered ? 'Mastered in Flashcards' : 'Mark as Mastered'}</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          VIEW 2: 3D FLIP FLASHCARDS
          ========================================================================= */}
      {activeView === 'flashcards' && (
        <div className="flashcards-stage animate-fade-in">
          <div className="flashcards-meta-row mono">
            <span>CARD {flashcardIndex + 1} OF {filteredMaxims.length || 1}</span>
            <div className="flashcards-score-pills">
              <span className="score-pill green">{masteredMaxims.length} MASTERED</span>
              <span className="score-pill grey">
                {(filteredMaxims.length || LEGAL_MAXIMS.length) - masteredMaxims.length} REMAINING
              </span>
            </div>
          </div>

          {/* 3D Flip Card Container */}
          <div
            className="flashcard-3d-scene"
            onClick={() => setIsFlipped(!isFlipped)}
            title="Click card to flip"
          >
            <div className={`flashcard-3d-flipper ${isFlipped ? 'is-flipped' : ''}`}>
              {/* FRONT: Latin Maxim */}
              <div className="flashcard-face flashcard-front">
                <span className="card-kicker mono">LATIN LEGAL CANON &bull; CLICK TO FLIP</span>
                <span className="card-category-tag mono">{currentFlashcard.category}</span>
                <h2 className="card-latin-title font-serif">{currentFlashcard.maxim}</h2>
                <div className="card-flip-prompt mono">
                  <RotateCw size={13} />
                  <span>Click to reveal English meaning</span>
                </div>
              </div>

              {/* BACK: English Meaning & Doctrine */}
              <div className="flashcard-face flashcard-back">
                <span className="card-kicker mono">ENGLISH MEANING & JURISPRUDENCE</span>
                <h3 className="card-meaning-title font-serif">"{currentFlashcard.meaning}"</h3>
                <p className="card-explanation-prose">{currentFlashcard.explanation}</p>
                {currentFlashcard.example && (
                  <div className="card-scenario-note font-serif">
                    <strong>Scenario:</strong> {currentFlashcard.example}
                  </div>
                )}
                <div className="card-flip-prompt mono">
                  <RotateCw size={13} />
                  <span>Click to flip back</span>
                </div>
              </div>
            </div>
          </div>

          {/* Flashcard Navigation Controls */}
          <div className="flashcard-controls-strip">
            <button
              type="button"
              className="btn-control-prev mono"
              onClick={handlePrevFlashcard}
            >
              Previous Card
            </button>

            <button
              type="button"
              className={`btn-control-mastered mono ${masteredMaxims.includes(currentFlashcard.id) ? 'is-mastered' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                toggleMasteredStatus(currentFlashcard.id);
              }}
            >
              <CheckCircle2 size={15} />
              <span>
                {masteredMaxims.includes(currentFlashcard.id) ? 'Mastered' : 'Mark as Known'}
              </span>
            </button>

            <button
              type="button"
              className="btn-control-shuffle mono"
              onClick={handleShuffleFlashcards}
              title="Pick random card"
            >
              <Shuffle size={14} />
              <span>Shuffle</span>
            </button>

            <button
              type="button"
              className="btn-control-next mono"
              onClick={handleNextFlashcard}
            >
              <span>Next Card</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* =========================================================================
          VIEW 3: INTERACTIVE KNOWLEDGE QUIZ (Green/Red Animated Feedback)
          ========================================================================= */}
      {activeView === 'quiz' && (
        <div className="quiz-stage animate-fade-in">
          <div className="quiz-header-bar mono">
            <span>QUESTION {quizQuestionIndex + 1}</span>
            <div className="quiz-score-pill">
              <Award size={14} />
              <span>SCORE: {quizScore} / {quizQuestionIndex + (quizAnswered ? 1 : 0)}</span>
            </div>
          </div>

          <div className="quiz-question-card">
            <span className="quiz-question-kicker mono">SELECT THE CORRECT LEGAL MEANING</span>
            <h2 className="quiz-target-maxim font-serif">{currentQuizItem.target.maxim}</h2>
            <div className="quiz-category-badge mono">{currentQuizItem.target.category}</div>

            {/* 4 Options Grid */}
            <div className="quiz-options-matrix">
              {currentQuizItem.options.map((opt, idx) => {
                let statusClass = '';
                if (quizAnswered) {
                  if (opt.isCorrect) statusClass = 'is-correct';
                  else if (selectedOption === opt.id) statusClass = 'is-incorrect';
                }

                return (
                  <button
                    key={opt.id}
                    type="button"
                    className={`quiz-option-card ${selectedOption === opt.id ? 'is-selected' : ''} ${statusClass}`}
                    onClick={() => handleSelectQuizOption(opt)}
                    disabled={quizAnswered}
                  >
                    <span className="opt-letter mono">
                      {String.fromCharCode(65 + idx)}
                    </span>
                    <span className="opt-text font-serif">"{opt.text}"</span>
                    {quizAnswered && opt.isCorrect && (
                      <Check size={16} className="opt-feedback-icon green" />
                    )}
                    {quizAnswered && !opt.isCorrect && selectedOption === opt.id && (
                      <X size={16} className="opt-feedback-icon red" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Post-Answer Animated Feedback Banner */}
            {quizAnswered && (
              <div className="quiz-feedback-banner animate-fade-in">
                <div className="feedback-headline">
                  {currentQuizItem.options.find(o => o.id === selectedOption)?.isCorrect ? (
                    <span className="feedback-result correct font-serif">Correct! Outstanding retention.</span>
                  ) : (
                    <span className="feedback-result incorrect font-serif">
                      Incorrect. The correct meaning is: "{currentQuizItem.target.meaning}"
                    </span>
                  )}
                </div>
                <p className="feedback-explanation">{currentQuizItem.target.explanation}</p>

                <div className="feedback-actions">
                  <button
                    type="button"
                    className="btn-quiz-next mono"
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
