import React, { useState, useEffect, useRef } from 'react';
import { motion, useScroll, useSpring, useInView, animate } from 'framer-motion';

/**
 * 1. Top Window Scroll Progress Bar
 * Sits at the very top of the window, glowing with polished copper & emerald gradient.
 */
export function ScrollProgressBar() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 280,
    damping: 30,
    restDelta: 0.001
  });

  return (
    <motion.div
      className="window-scroll-progress-bar"
      style={{ scaleX, transformOrigin: '0%' }}
      aria-hidden="true"
    />
  );
}

/**
 * 2. Soft Copper Cursor Follower
 * Tracks mouse position across hero and cards with a smooth, diffused ambient glow.
 * Skips strictly on touch/mobile devices or when prefers-reduced-motion is active.
 */
export function SoftCursorFollower() {
  const [pos, setPos] = useState({ x: -1000, y: -1000 });
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Disable on touch devices or small screens
    if (typeof window === 'undefined' || window.innerWidth < 1024) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let rafId = null;
    const handleMove = (e) => {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        setPos({ x: e.clientX, y: e.clientY });
        if (!visible) setVisible(true);
      });
    };

    const handleLeave = () => setVisible(false);

    window.addEventListener('mousemove', handleMove, { passive: true });
    document.addEventListener('mouseleave', handleLeave);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseleave', handleLeave);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className="soft-copper-cursor-light"
      style={{
        transform: `translate3d(${pos.x}px, ${pos.y}px, 0)`
      }}
      aria-hidden="true"
    />
  );
}

/**
 * 3. 3D Card Tilt with Moving Glossy Sheen
 * Gently tilts toward cursor (up to ~6deg) with a dynamic radial highlight.
 * Falls back gracefully to flat layout on touch or reduced motion.
 */
export function TiltCard({
  children,
  className = '',
  maxTilt = 6,
  style = {},
  onClick,
  as: Component = 'div',
  ...rest
}) {
  const cardRef = useRef(null);
  const [tilt, setTilt] = useState({ rotateX: 0, rotateY: 0 });
  const [glare, setGlare] = useState({ x: 50, y: 50, opacity: 0 });
  const [isHovered, setIsHovered] = useState(false);

  const handleMouseMove = (e) => {
    if (typeof window === 'undefined' || window.innerWidth < 1024) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const el = cardRef.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const px = (mouseX / width - 0.5) * 2; // -1 to 1
    const py = (mouseY / height - 0.5) * 2; // -1 to 1

    const rotX = -py * maxTilt;
    const rotY = px * maxTilt;

    setTilt({ rotateX: rotX, rotateY: rotY });
    setGlare({
      x: (mouseX / width) * 100,
      y: (mouseY / height) * 100,
      opacity: 0.18
    });
  };

  const handleMouseEnter = () => setIsHovered(true);

  const handleMouseLeave = () => {
    setIsHovered(false);
    setTilt({ rotateX: 0, rotateY: 0 });
    setGlare(prev => ({ ...prev, opacity: 0 }));
  };

  return (
    <Component
      ref={cardRef}
      className={`tilt-card-wrapper ${className} ${isHovered ? 'is-tilting' : ''}`}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        ...style,
        transform: `perspective(1000px) rotateX(${tilt.rotateX}deg) rotateY(${tilt.rotateY}deg)`,
        transition: isHovered
          ? 'transform 0.12s ease-out, box-shadow 0.25s ease'
          : 'transform 0.45s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.35s ease'
      }}
      {...rest}
    >
      {children}
      {/* Dynamic glossy specular reflection */}
      <div
        className="tilt-card-glare"
        style={{
          background: `radial-gradient(circle 380px at ${glare.x}% ${glare.y}%, rgba(255, 255, 255, ${glare.opacity}) 0%, transparent 70%)`
        }}
        aria-hidden="true"
      />
    </Component>
  );
}

/**
 * 4. Magnetic Button
 * Slightly pulls toward cursor on hover and tactilely compresses on click.
 */
export function MagneticButton({
  children,
  className = '',
  strength = 0.2,
  onClick,
  type = 'button',
  ...rest
}) {
  const btnRef = useRef(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [ripples, setRipples] = useState([]);

  const handleMouseMove = (e) => {
    if (typeof window === 'undefined' || window.innerWidth < 1024) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const el = btnRef.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    const dx = (e.clientX - centerX) * strength;
    const dy = (e.clientY - centerY) * strength;

    // Constrain offset to +/- 8px
    const clampedX = Math.max(-8, Math.min(8, dx));
    const clampedY = Math.max(-8, Math.min(8, dy));

    setOffset({ x: clampedX, y: clampedY });
  };

  const handleMouseLeave = () => setOffset({ x: 0, y: 0 });

  const handleClick = (e) => {
    const el = btnRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      const rippleX = e.clientX - rect.left;
      const rippleY = e.clientY - rect.top;
      const id = Date.now();

      setRipples(prev => [...prev.slice(-3), { id, x: rippleX, y: rippleY }]);
      setTimeout(() => {
        setRipples(prev => prev.filter(r => r.id !== id));
      }, 600);
    }

    if (onClick) onClick(e);
  };

  return (
    <motion.button
      ref={btnRef}
      type={type}
      className={`magnetic-button ${className}`}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      animate={{ x: offset.x, y: offset.y }}
      transition={{ type: 'spring', stiffness: 350, damping: 20 }}
      whileTap={{ scale: 0.96, y: 1 }}
      {...rest}
    >
      <span className="magnetic-btn-content">{children}</span>
      <span className="magnetic-btn-shimmer" aria-hidden="true" />
      {/* Ripple effects */}
      {ripples.map(r => (
        <span
          key={r.id}
          className="magnetic-ripple"
          style={{ left: r.x, top: r.y }}
          aria-hidden="true"
        />
      ))}
    </motion.button>
  );
}

/**
 * 5. CountUp Number (Smooth spring count animation when scrolled into view)
 */
export function CountUpNumber({ target = 100, suffix = '', prefix = '', duration = 1.6 }) {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.1 });

  useEffect(() => {
    if (!isInView) return;
    const controls = animate(0, target, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => setVal(Math.floor(latest))
    });
    return () => controls.stop();
  }, [isInView, target, duration]);

  return (
    <span ref={ref} className="countup-number mono">
      {prefix}{val.toLocaleString('en-IN')}{suffix}
    </span>
  );
}

/**
 * 6. Typewriter Search Placeholder Hook & Component
 */
export function TypewriterPlaceholder({ placeholders = [], speed = 40, delay = 2200 }) {
  const [text, setText] = useState('');
  const [pIndex, setPIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!placeholders || placeholders.length === 0) return;

    const currentPhrase = placeholders[pIndex] || '';
    let timer = null;

    if (!isDeleting) {
      if (text.length < currentPhrase.length) {
        timer = setTimeout(() => {
          setText(currentPhrase.slice(0, text.length + 1));
        }, speed);
      } else {
        timer = setTimeout(() => setIsDeleting(true), delay);
      }
    } else {
      if (text.length > 0) {
        timer = setTimeout(() => {
          setText(currentPhrase.slice(0, text.length - 1));
        }, speed * 0.6);
      } else {
        setIsDeleting(false);
        setPIndex((prev) => (prev + 1) % placeholders.length);
      }
    }

    return () => clearTimeout(timer);
  }, [text, isDeleting, pIndex, placeholders, speed, delay]);

  return (
    <span className="typewriter-text">
      {text}
      <span className="typewriter-cursor" aria-hidden="true">|</span>
    </span>
  );
}

/**
 * 7. Draggable Questions Strip (Momentum drag horizontally with grab cursor)
 */
export function DraggableQuestionsRow({ chips = [], onChipClick }) {
  const containerRef = useRef(null);

  return (
    <div className="draggable-chips-container" ref={containerRef}>
      <motion.div
        className="draggable-chips-track"
        drag="x"
        dragConstraints={containerRef}
        dragElastic={0.12}
        whileTap={{ cursor: 'grabbing' }}
      >
        {chips.map((chip, idx) => (
          <motion.button
            key={idx}
            type="button"
            className="everyday-chip draggable-chip"
            onClick={() => onChipClick && onChipClick(chip.query)}
            whileHover={{ scale: 1.03, y: -2 }}
            whileTap={{ scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
          >
            <span>{chip.label}</span>
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
