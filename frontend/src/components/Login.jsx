// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useEffect, useRef, useState } from "react";

import { login } from "../api";
import { INSTITUTE } from "../institute";
import IdentityPattern from "./IdentityPattern";
import InstituteMark from "./InstituteMark";

// THE SIGN-IN SCREEN.
//
// Structure is a 5/7 split, not 6/6. An exact half-and-half reads as a layout
// grid rather than a composition; the uneven ratio makes the form the subject
// and the identity panel the context.
//
// Deliberately absent, because each is a tell that a page was generated rather
// than designed: a centred card floating on empty background, a purple or blue
// background gradient, a drop shadow doing the work of a border, and rocket /
// spark / brain iconography.

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" className="h-4 w-4">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

/**
 * Turn a failed sign-in into calm, specific guidance.
 *
 * CALM IS A REQUIREMENT HERE, NOT A PREFERENCE. Most sign-in failures are a
 * mistyped password by somebody who belongs here. A red alert box treats every
 * one of them as an incident, and by the third time it has trained the user to
 * ignore the message — including on the one occasion it says something they
 * actually need to act on.
 *
 * So: no red fill, no warning triangle, no exclamation mark. A quiet panel with
 * a rule down one side, and wording that says what to do next.
 */
export function describeFailure(err) {
  const status = err?.status;

  if (status === 423) {
    // The per-account lockout from the brute-force protection. This is not the
    // user's mistake to fix and the wording must not imply it is — it needs to
    // convey "wait, or ask for help", with the real time the server gave.
    const minutes = /(\d+)\s*minute/.exec(err.message || "")?.[1];
    return {
      tone: "hold",
      title: "This account is temporarily locked",
      detail: minutes
        ? `Too many sign-in attempts were made. It unlocks on its own in about ${minutes} minute${minutes === "1" ? "" : "s"}, or an administrator can clear it sooner.`
        : "Too many sign-in attempts were made. It unlocks on its own shortly, or an administrator can clear it sooner.",
    };
  }

  if (status === 429) {
    return {
      tone: "hold",
      title: "Too many attempts from this network",
      detail:
        "Please wait about a minute before trying again. This limit is shared by everyone signing in from the same connection.",
    };
  }

  if (status === 401) {
    return {
      tone: "retry",
      title: "That username and password did not match",
      detail:
        "Check for typos and that Caps Lock is off. If you have forgotten your password, an administrator can reset it — there is no self-service reset.",
    };
  }

  // Network failure, server error, anything unforeseen. Says plainly that it is
  // probably not the user's fault, because it probably is not.
  return {
    tone: "retry",
    title: "Could not reach the sign-in service",
    detail: err?.message || "Please try again in a moment.",
  };
}

function Login({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [failure, setFailure] = useState(null);
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState(() => {
    // PRE-AUTHENTICATION ONLY.
    //
    // Everywhere else the theme lives on the user's profile in the database, on
    // purpose (see Chat.jsx). That is impossible here — there is no account yet.
    // localStorage is the only store available before sign-in, and the profile
    // takes over the moment App.jsx knows who the user is, so this is a
    // first-paint preference rather than a competing source of truth.
    try {
      const saved = localStorage.getItem("theme");
      if (saved === "light" || saved === "dark") return saved;
    } catch {
      // Private browsing can throw on access. Falling through to a default.
    }
    return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
  });

  const usernameRef = useRef(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch { /* not worth surfacing */ }
  }, [theme]);

  useEffect(() => {
    document.title = `Sign in · ${INSTITUTE.name}`;
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setFailure(null);
    setLoading(true);
    try {
      const user = await login(username, password);
      onLoggedIn(user);
    } catch (err) {
      setFailure(describeFailure(err));
      // Clear the password so a retry does not append to a half-typed one, and
      // put the cursor back at the top of the form.
      setPassword("");
      usernameRef.current?.focus();
    } finally {
      setLoading(false);
    }
  }

  const field =
    "w-full rounded-md border bg-transparent px-3 py-2.5 text-[15px] outline-none " +
    // The only micro-interaction on the inputs: the border deepens and a
    // hairline ochre ring appears. 150ms, no movement, no glow — enough to
    // confirm focus to a sighted user and nothing more.
    "transition-colors duration-150 " +
    "border-ink-200 text-ink-900 placeholder:text-ink-300 " +
    "focus:border-ochre-400 focus:ring-1 focus:ring-ochre-400 " +
    "dark:border-ink-700 dark:text-ink-50 dark:placeholder:text-ink-500 " +
    "dark:focus:border-ochre-400 dark:focus:ring-ochre-400";

  return (
    <div className="flex min-h-screen flex-col bg-ink-50 text-ink-900 lg:grid lg:grid-cols-12 dark:bg-ink-950 dark:text-ink-50">
      {/* ── identity panel ─────────────────────────────────────────────────
          Five columns of twelve. On small screens it collapses to a compact
          banner rather than disappearing: the institute's name is the one
          thing that must survive to a phone. */}
      <aside className="relative overflow-hidden bg-ink-900 text-ink-50 lg:col-span-5 dark:border-r dark:border-ink-800 dark:bg-ink-950">
        <div className="pointer-events-none absolute inset-0 text-ink-200">
          <IdentityPattern className="h-full w-full" />
        </div>
        {/* One soft vignette so the wordmark keeps contrast over the densest
            part of the lattice. Functional, not a decorative gradient. */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink-950/80 via-transparent to-ink-950/40" />

        <div className="relative flex h-full flex-col justify-between p-8 lg:min-h-screen lg:p-12">
          <div className="flex items-center gap-3">
            <InstituteMark size={40} className="text-ink-100" />
            <span className="text-xs uppercase tracking-[0.18em] text-ink-300">
              {INSTITUTE.descriptor}
            </span>
          </div>

          <div className="mt-10 lg:mt-0">
            <h1 className="font-display text-4xl font-semibold leading-[1.08] tracking-tight lg:text-5xl">
              {INSTITUTE.name}
            </h1>
            {/* The rule the monogram echoes. */}
            <div className="mt-5 h-px w-16 bg-ochre-400" />
            <p className="mt-5 max-w-sm text-sm leading-6 text-ink-200">
              Ask about courses, departments, faculty, fees and schedules.
              Answers are drawn from the institute&rsquo;s own records.
            </p>
          </div>

          {INSTITUTE.footnote ? (
            <p className="mt-10 hidden text-xs text-ink-400 lg:block">{INSTITUTE.footnote}</p>
          ) : (
            <span className="hidden lg:block" />
          )}
        </div>
      </aside>

      {/* ── form panel ────────────────────────────────────────────────────── */}
      <main className="flex flex-1 flex-col lg:col-span-7">
        <div className="flex justify-end p-4">
          <button
            type="button"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Light mode" : "Dark mode"}
            className="rounded-md p-2 text-ink-400 transition-colors duration-150 hover:bg-ink-100 hover:text-ink-700 dark:hover:bg-ink-800 dark:hover:text-ink-100"
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>

        {/* Offset left rather than centred in the panel: the form aligns to a
            column, which reads as considered rather than defaulted. */}
        <div className="flex flex-1 items-center px-6 pb-16 sm:px-12 lg:px-20">
          <form onSubmit={handleSubmit} className="w-full max-w-sm" noValidate>
            <h2 className="font-display text-2xl font-semibold tracking-tight">Sign in</h2>
            <p className="mt-1.5 text-sm text-ink-500 dark:text-ink-300">
              Use the account issued to you by the institute.
            </p>

            <div className="mt-8 space-y-5">
              <div>
                <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
                  Username
                </label>
                <input
                  id="username"
                  ref={usernameRef}
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                  className={field}
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  className={field}
                />
              </div>
            </div>

            {/* aria-live so a failure is announced, and the meaning lives in the
                words rather than the colour — this has to work for a screen
                reader and in greyscale. */}
            <div aria-live="polite">
              {failure && (
                <div
                  className={
                    "mt-6 border-l-2 py-1 pl-4 " +
                    (failure.tone === "hold"
                      ? "border-ochre-400"
                      : "border-ink-300 dark:border-ink-600")
                  }
                >
                  <p className="text-sm font-medium">{failure.title}</p>
                  <p className="mt-1 text-sm leading-6 text-ink-500 dark:text-ink-300">
                    {failure.detail}
                  </p>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !username || !password}
              className={
                "mt-8 w-full rounded-md bg-ink-900 py-2.5 text-sm font-medium text-ink-50 " +
                "transition-colors duration-150 hover:bg-ink-700 " +
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-ochre-400 focus-visible:ring-offset-2 " +
                "focus-visible:ring-offset-ink-50 dark:focus-visible:ring-offset-ink-950 " +
                "disabled:cursor-not-allowed disabled:opacity-40 " +
                "dark:bg-ochre-400 dark:text-ink-950 dark:hover:bg-ochre-300"
              }
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>

            <p className="mt-6 text-xs leading-5 text-ink-400">
              Forgotten your password? Contact the administrator — there is no
              self-service reset, and nobody from the institute will ask you for
              your password.
            </p>
          </form>
        </div>
      </main>
    </div>
  );
}

export default Login;
