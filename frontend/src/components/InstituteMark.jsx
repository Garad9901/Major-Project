// Copyright (c) 2026 Yash Garad. All rights reserved.

import { INSTITUTE, initialsOf } from "../institute";

/**
 * The institute's mark.
 *
 * Renders the real logo when `INSTITUTE.logo` is set, and otherwise draws a
 * monogram from the initials. The monogram is a genuine fallback rather than a
 * placeholder to be replaced later: a clean set of initials in the display face
 * looks considerably better than a low-resolution crest scaled to 40px, which
 * is what institutional logo files usually turn out to be.
 *
 * Deliberately NOT a rocket, a spark, a brain or a chat bubble. Those four are
 * the visual signature of a generated template, and none of them says anything
 * about a college.
 */
function InstituteMark({ size = 44, className = "" }) {
  if (INSTITUTE.logo) {
    return (
      <img
        src={INSTITUTE.logo}
        alt={`${INSTITUTE.name} logo`}
        width={size}
        height={size}
        // Contain, never cover: cropping somebody's crest is worse than
        // letterboxing it.
        className={`object-contain ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  const initials = initialsOf();
  // Shrink the type as initials are added so three still fit the same square.
  const fontSize = initials.length >= 3 ? 15 : initials.length === 2 ? 19 : 24;

  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      role="img"
      aria-label={`${INSTITUTE.name} monogram`}
      className={className}
    >
      {/* An open arc rather than a closed ring — a full circle around initials
          is the standard "app icon" shape and reads as generic. The gap at the
          top right makes it a drawn mark instead. */}
      <path
        d="M24 3 A21 21 0 1 1 9.1 9.1"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.55"
      />
      {/* The one accent: a short ochre rule under the initials, echoing the
          rule beneath the wordmark on the identity panel. */}
      <line
        x1="16" y1="34" x2="32" y2="34"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        className="text-ochre-400"
      />
      <text
        x="24"
        y="28"
        textAnchor="middle"
        fontSize={fontSize}
        // Matches the wordmark; see tailwind.config.js for why this face.
        fontFamily='"Fraunces Variable", Fraunces, Georgia, serif'
        fontWeight="600"
        letterSpacing="0.5"
        fill="currentColor"
      >
        {initials}
      </text>
    </svg>
  );
}

export default InstituteMark;
