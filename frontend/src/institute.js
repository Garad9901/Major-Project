// Copyright (c) 2026 Yash Garad. All rights reserved.

// THE INSTITUTE'S IDENTITY, IN ONE PLACE.
//
// Everything on the sign-in screen — the wordmark, the monogram, the generated
// pattern, the page title — reads from here. Rebranding for a different
// institute is editing this file, not hunting through JSX.
//
// ─────────────────────────────────────────────────────────────────────────────
// ACTION REQUIRED: `name` below is a PLACEHOLDER.
//
// Replace it with the institute's real registered name and the page picks it up
// everywhere, including the lattice pattern (which is generated from the
// initials, so a different name produces a genuinely different pattern).
// ─────────────────────────────────────────────────────────────────────────────

export const INSTITUTE = {
  // The full name, as it should appear on the wordmark.
  name: "College Assistant",

  // Shown under the wordmark. Keep it factual — what this system IS, not a
  // slogan. Marketing copy on an internal login screen reads as filler.
  descriptor: "Academic Information Service",

  // A short line at the foot of the identity panel. Optional; set to "" to hide.
  footnote: "Authorised users only",

  // Initials for the monogram and the pattern seed. Derived from `name` when
  // left null, which is right for most names; override for something like
  // "Indian Institute of Technology" where the conventional initials (IIT)
  // are not simply the capitals.
  initials: null,

  // Set to a logo module once one exists, e.g.
  //     import logoUrl from "./assets/logo.svg";
  //     logo: logoUrl,
  // Left null, the wordmark and monogram stand in — which is deliberately
  // better than stretching a low-resolution crest.
  logo: null,
};

/** Two or three initials, derived unless explicitly set. */
export function initialsOf(institute = INSTITUTE) {
  if (institute.initials) return institute.initials.toUpperCase();
  const words = institute.name
    .split(/\s+/)
    // Words that carry no identity and would dilute a monogram.
    .filter((w) => !/^(of|the|and|for|at|in|&)$/i.test(w))
    .filter(Boolean);
  return words.slice(0, 3).map((w) => w[0].toUpperCase()).join("");
}

/**
 * A stable 32-bit hash of a string.
 *
 * Used to seed the identity pattern so it is DETERMINISTIC: the same institute
 * name always produces the same lattice, on every machine and every build. A
 * random pattern would change on each render, which is the kind of motion that
 * makes a page feel generated rather than designed.
 */
export function seedFrom(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
