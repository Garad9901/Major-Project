// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  askStream,
  deleteConversation,
  getConversation,
  listConversations,
  saveTheme,
} from "../api";
import Markdown from "./Markdown";
import Sidebar from "./Sidebar";

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

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" className="h-5 w-5">
      <path d="M3 6h18M3 12h18M3 18h18" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

const ROUTE_LABEL = { SQL: "database", RAG: "documents", BOTH: "database + documents" };

function Chat({ username, initialTheme, onLogout, onSessionExpired }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [theme, setTheme] = useState(initialTheme === "light" ? "light" : "dark");
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const scrollRef = useRef(null);
  const textareaRef = useRef(null);

  // Apply the theme by toggling one class on <html>, which is what Tailwind's
  // darkMode:"class" keys off. Done as an effect so it stays correct no matter
  // how `theme` changed (toggle, or loaded from the profile at sign-in).
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    listConversations().then(setConversations).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Grow the input with its content, up to a cap, like ChatGPT's composer.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  async function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next); // optimistic: the UI must not wait on a round trip
    try {
      await saveTheme(next);
    } catch {
      // Kept locally for this session even if the save failed. Reverting would
      // undo a change the user just made and watched happen.
    }
  }

  const refreshConversations = useCallback(() => {
    listConversations().then(setConversations).catch(() => {});
  }, []);

  function newChat() {
    setActiveId(null);
    setMessages([]);
    setInput("");
    setSidebarOpen(false);
  }

  async function openConversation(id) {
    setSidebarOpen(false);
    if (busy) return; // don't swap the transcript out from under a live stream
    try {
      const convo = await getConversation(id);
      setActiveId(convo.id);
      setMessages(convo.messages.map((m) => ({ ...m, pending: false })));
    } catch {
      /* a deleted conversation simply does not open */
    }
  }

  async function removeConversation(id) {
    try {
      await deleteConversation(id);
    } catch {
      return;
    }
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (id === activeId) newChat();
  }

  async function handleSubmit(e) {
    e?.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "", route: "", pending: true },
    ]);

    // Index of the assistant placeholder just appended. Captured with the
    // functional form below so it stays correct regardless of batching.
    let assistantIndex = -1;
    setMessages((prev) => {
      assistantIndex = prev.length - 1;
      return prev;
    });

    const update = (patch) =>
      setMessages((prev) => {
        const next = [...prev];
        const i = next.length - 1;
        next[i] = { ...next[i], ...patch(next[i]) };
        return next;
      });

    let expired = false;
    let createdId = null;

    const result = await askStream(question, {
      conversationId: activeId,
      onConversation: (c) => {
        createdId = c.id;
        if (!activeId) setActiveId(c.id);
      },
      onMeta: (meta) =>
        update(() => ({
          route: meta.route || "",
          // Stage text from the route the router actually chose, so the label
          // reflects real work rather than a guess.
          stage: meta.cached
            ? "Found an earlier answer to this…"
            : meta.route === "SQL"
              ? "Querying the database…"
              : meta.route === "RAG"
                ? "Searching documents…"
                : meta.route === "BOTH"
                  ? "Querying the database and searching documents…"
                  : "Writing the answer…",
        })),
      onToken: (text) => update((m) => ({ text: m.text + text, pending: false })),
      onDone: (final) => update((m) => ({ text: final || m.text, pending: false })),
      onError: (msg) => {
        if (msg.toLowerCase().includes("authorized")) expired = true;
        update((m) => ({ text: m.text || msg, error: true, pending: false }));
      },
    }).catch((err) => {
      update((m) => ({ text: m.text || err.message, error: true, pending: false }));
      return {};
    });

    setBusy(false);
    // Refresh after the stream so a new conversation appears in the sidebar
    // with the title the server generated from this first message.
    if (createdId) refreshConversations();
    if (expired || result?.unauthorized) onSessionExpired();
  }

  function onKeyDown(e) {
    // Enter sends, Shift+Enter makes a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white text-neutral-900 dark:bg-[#0f0f10] dark:text-neutral-100">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={openConversation}
        onNew={newChat}
        onDelete={removeConversation}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-neutral-200 px-4 py-2.5 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="Toggle sidebar"
              className="rounded-lg p-1.5 text-neutral-500 transition hover:bg-neutral-100 md:hidden dark:hover:bg-neutral-800"
            >
              <MenuIcon />
            </button>
            <span className="text-sm font-medium">College Assistant</span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
              className="rounded-lg p-2 text-neutral-500 transition hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
            <span className="hidden text-xs text-neutral-500 sm:inline dark:text-neutral-400">
              {username}
            </span>
            <button
              onClick={onLogout}
              className="rounded-lg px-2.5 py-1.5 text-xs text-neutral-500 transition hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              Sign out
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {messages.length === 0 ? (
              <div className="mt-28 text-center">
                <h1 className="text-2xl font-semibold">What would you like to know?</h1>
                <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
                  Ask about courses, departments, faculty, fees or schedules.
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {messages.map((msg, i) =>
                  msg.role === "user" ? (
                    // User: right-aligned, subtle bubble.
                    <div key={i} className="flex justify-end">
                      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-neutral-100 px-4 py-2.5 text-[15px] leading-7 dark:bg-neutral-800">
                        {msg.text}
                      </div>
                    </div>
                  ) : (
                    // Assistant: left-aligned, NO bubble — just text on the page.
                    <div key={i} className="text-[15px]">
                      {msg.route && (
                        <div className="mb-1.5 text-xs text-neutral-400 dark:text-neutral-500">
                          answered from {ROUTE_LABEL[msg.route] || msg.route.toLowerCase()}
                        </div>
                      )}
                      <div className={msg.error ? "text-red-600 dark:text-red-400" : ""}>
                        {msg.text ? (
                          <Markdown>{msg.text}</Markdown>
                        ) : msg.pending ? (
                          <Skeleton stage={msg.stage || "Thinking…"} />
                        ) : null}
                      </div>
                    </div>
                  )
                )}
              </div>
            )}
          </div>
        </div>

        <div className="px-4 pb-4">
          <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl">
            <div className="flex items-end gap-2 rounded-2xl border border-neutral-300 bg-white p-2 shadow-sm focus-within:border-neutral-400 dark:border-neutral-700 dark:bg-neutral-900 dark:focus-within:border-neutral-600">
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={busy ? "Waiting for the answer…" : "Ask a question…"}
                disabled={busy}
                className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-neutral-400 disabled:opacity-60 dark:placeholder:text-neutral-500"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                aria-label="Send"
                className="rounded-lg bg-accent p-2 text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
              >
                <SendIcon />
              </button>
            </div>
            <p className="mt-2 text-center text-[11px] text-neutral-400 dark:text-neutral-500">
              Answers run on a local model and can take a minute or more. Please ask one question at a time.
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

function Dot({ delay = "0ms" }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400 dark:bg-neutral-500"
      style={{ animationDelay: delay }}
    />
  );
}

// Shown while waiting for the FIRST token, which on CPU is the long part —
// measured at ~7s warm and far worse under load. Three shimmering bars plus a
// stage label.
//
// The stage text is driven by real events, not a timer: "Thinking" until the
// router reports a route, then the actual work being done. An honest progress
// signal is the difference between "it's working" and "it's frozen"; a fake
// progress bar would be worse than nothing because it would be wrong.
function Skeleton({ stage }) {
  return (
    <div aria-live="polite" aria-busy="true">
      <div className="mb-2 flex items-center gap-2 text-xs text-neutral-400 dark:text-neutral-500">
        <span className="inline-flex gap-1">
          <Dot /> <Dot delay="150ms" /> <Dot delay="300ms" />
        </span>
        <span>{stage}</span>
      </div>
      <div className="space-y-2">
        <div className="h-3.5 w-[92%] animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
        <div className="h-3.5 w-[78%] animate-pulse rounded bg-neutral-200 dark:bg-neutral-800"
             style={{ animationDelay: "120ms" }} />
        <div className="h-3.5 w-[55%] animate-pulse rounded bg-neutral-200 dark:bg-neutral-800"
             style={{ animationDelay: "240ms" }} />
      </div>
    </div>
  );
}

export default Chat;
