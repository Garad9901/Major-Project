// Copyright (c) 2026 Yash Garad. All rights reserved.

// THE INSTITUTE'S IDENTITY — now loaded at RUNTIME, not compiled in.
//
// WHAT CHANGED AND WHY
// This file used to hold the institution's name as a literal, which meant
// rebranding for a different college was an edit to JavaScript followed by a
// React rebuild. That is a fine thing to ask of the person who wrote it and an
// unreasonable thing to ask of a college IT department that has been handed a
// product — it puts a Node toolchain on the critical path for changing a name
// on a sign-in page.
//
// The values now come from config/institution.json, served by the backend at
// /api/institution/ and applied by applyInstitution() before the app renders.
// Changing the name is a file edit and a backend restart. No rebuild.
//
// WHY INSTITUTE IS A MUTABLE SINGLETON RATHER THAN A CONTEXT
// Three components and a test import { INSTITUTE } directly. Threading a React
// context through them would touch every call site to solve a problem none of
// them have: this value is fetched once at boot, before first render, and never
// changes for the life of the page. A context would add re-render machinery for
// a value that cannot re-render. The mutation happens exactly once, in
// applyInstitution(), before ReactDOM.createRoot() is called.
//
// THE DEFAULTS NAME NOBODY.
// `name` is empty on purpose and stays empty until a real config is loaded.
// There is no placeholder institution to accidentally ship — the sign-in screen
// showing no name is a visible, fixable problem, whereas one showing a
// plausible wrong name is not.

export const INSTITUTE = {
  // The full name, as it should appear on the wordmark. Empty until configured.
  name: "",

  // Shown under the wordmark. Factual — what this system IS, not a slogan.
  descriptor: "Academic Information Service",

  // A short line at the foot of the identity panel. "" hides it.
  footnote: "Authorised users only",

  // Initials for the monogram and the pattern seed. Derived from `name` when
  // null, which is right for most names; override for something like "Indian
  // Institute of Technology", where the conventional initials (IIT) are not
  // simply the capitals.
  initials: null,

  // Absolute URL or a path under the static root. Left null, the wordmark and
  // monogram stand in — deliberately better than stretching a low-resolution
  // crest.
  logo: null,

  // Where a user is sent when something breaks and they need a human.
  contactEmail: "",
  contactUrl: "",

  // False until the backend reports a configured institution. The sign-in
  // screen uses this to say so plainly rather than rendering a blank space.
  configured: false,
};

/**
 * Apply a payload from GET /api/institution/ to the module singleton.
 *
 * Tolerant of a partial or absent payload: every field falls back to what is
 * already there. A backend that is up but unconfigured, or a response missing a
 * field added in a later version, must not blank out the sign-in screen.
 *
 * Returns INSTITUTE so callers can use the result directly.
 */
export function applyInstitution(payload) {
  const source = (payload && payload.institution) || {};
  const theme = (payload && payload.theme) || {};

  if (source.name) INSTITUTE.name = source.name;
  if (source.descriptor) INSTITUTE.descriptor = source.descriptor;
  // Compared against undefined, not truthiness: "" is a MEANINGFUL value here
  // (it hides the footnote) and must not be treated as "unset, keep default".
  if (source.footnote !== undefined) INSTITUTE.footnote = source.footnote;
  if (source.initials !== undefined) INSTITUTE.initials = source.initials;
  if (source.logo_url !== undefined) INSTITUTE.logo = source.logo_url;
  if (source.contact_email !== undefined) INSTITUTE.contactEmail = source.contact_email;
  if (source.contact_url !== undefined) INSTITUTE.contactUrl = source.contact_url;
  if (payload && payload.configured !== undefined) INSTITUTE.configured = Boolean(payload.configured);

  applyTheme(theme);
  return INSTITUTE;
}

/**
 * Write the configurable colours onto :root as CSS custom properties.
 *
 * SCOPE, STATED PLAINLY: these three cover the sign-in identity panel and the
 * accent used through the app. The rest of the palette in tailwind.config.js
 * stays a BUILD-time concern, because Tailwind generates its utility classes
 * ahead of time and cannot read a value that only exists at runtime. Making
 * every shade runtime-settable would mean giving up static extraction, which is
 * what keeps the CSS bundle at 29 KB. That is a real limitation and it is
 * documented in config/institution.example.json rather than hidden.
 */
export function applyTheme(theme = {}) {
  if (typeof document === "undefined" || !document.documentElement) return;
  const root = document.documentElement.style;
  if (theme.accent) root.setProperty("--brand-accent", theme.accent);
  if (theme.identity_ink) root.setProperty("--brand-ink", theme.identity_ink);
  if (theme.identity_highlight) root.setProperty("--brand-highlight", theme.identity_highlight);
}

/**
 * Fetch the institution config and apply it. Never throws.
 *
 * A FAILURE HERE MUST NOT BLOCK SIGN-IN. If the endpoint is unreachable the app
 * still renders, with the neutral defaults above — an unbranded but working
 * sign-in page beats a blank screen, and the operator sees the problem on the
 * health dashboard rather than through a user who cannot log in.
 */
export async function loadInstitution(fetchImpl) {
  const doFetch = fetchImpl || (typeof fetch !== "undefined" ? fetch : null);
  if (!doFetch) return INSTITUTE;
  try {
    const response = await doFetch("/api/institution/", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return applyInstitution(await response.json());
  } catch (error) {
    // console.warn, not an error boundary: this is a degraded-but-usable state,
    // and the operator-facing report of it lives on the health dashboard.
    console.warn("institution config unavailable; using defaults:", error.message);
    return INSTITUTE;
  }
}

/** Two or three initials, derived unless explicitly set. */
export function initialsOf(institute = INSTITUTE) {
  if (institute.initials) return institute.initials.toUpperCase();
  const words = (institute.name || "")
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
  for (let i = 0; i < (text || "").length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
