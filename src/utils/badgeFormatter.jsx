import React from 'react';

/**
 * Parses and decorates '[Not Verified]' mentions in text as rich visual badges.
 */
export function renderWithBadges(text) {
  if (!text || typeof text !== 'string') return text;
  if (!text.includes('[Not Verified]')) return text;

  const parts = text.split(/(\[Not Verified\])/g);
  return parts.map((part, index) => {
    if (part === '[Not Verified]') {
      return (
        <span
          key={index}
          className="badge-not-verified"
          title="Citation could not be verified in our corpus or database"
        >
          [Not Verified]
        </span>
      );
    }
    return part;
  });
}
