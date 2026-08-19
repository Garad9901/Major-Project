// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  askStream,
  deleteConversation,
  getConversation,
  listConversations,
  saveTheme,
  truncateConversation,
} from "../api";
import useSmoothText from "../hooks/useSmoothText";
import CopyButton from "./CopyButton";
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

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function RegenerateIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
      <path d="M3 12a9 9 0 0 1 15.5-6.2L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-15.5 6.2L3 16" />
      <path d="M3 21v-5h5" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
    </svg>
  );
}

const ROUTE_LABEL = { SQL: "database", RAG: "documents", BOTH: "database + documents" };

function Chat({ username, initialTheme, onOpenAdmin, onLogout, onSessionExpired }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [theme, setTheme] = useState(initialTheme === "light" ? "light" : "dark");
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editDraft, setEditDraft] = useState("");
  const [stickToBottom, setStickToBottom] = useState(true);

  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const abortRef = useRef(null);

  // Mirrors of state that runQuestion needs to read WITHOUT being re-created
  // every render. It is a useCallback used by keyboard handlers and buttons; if
  // it closed over `messages` and `busy` directly it would be a new function on
  // every token, and every consumer would re-render with it.
  const messagesRef = useRef(messages);
  const activeIdRef = useRef(activeId);
  const busyRef = useRef(false);
  const smoothRef = useRef("");

  // The smoothing buffer. `smoothText` is what actually gets rendered while a
  // message is streaming — see hooks/useSmoothText.js.
  const [smoothText, pushSmooth, resetSmooth, finishSmooth] = useSmoothText();

  useEffect(() => { messagesRef.current = messages; }, [messages]);
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);
  useEffect(() => { smoothRef.current = smoothText; }, [smoothText]);

  // Apply the theme by toggling one class on <html>, which is what Tailwind's
  // darkMode:"class" keys off. Done as an effect so it stays correct no matter
  // how `theme` changed (toggle, or loaded from the profile at sign-in).
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    listConversations().then(setConversations).catch(() => {});
  }, []);

  // AUTO-SCROLL THAT YIELDS TO THE USER.
  //
  // Following the stream is only wanted while the user is at the bottom. The
  // moment they scroll up — to re-read something, or to copy from an earlier
  // answer — yanking them back down on the next token makes the transcript
  // unusable. So scrolling up disengages, and returning to the bottom
  // re-engages, which is what ChatGPT does.
  //
  // The 80px threshold absorbs the fractional scrollTop browsers report at
  // zoom levels other than 100%, where an exact comparison never matches and
  // auto-scroll would silently never re-engage.
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setStickToBottom(distanceFromBottom < 80);
  }, []);

  useEffect(() => {
    if (!stickToBottom) return;
    const el = scrollRef.current;
    if (!el) return;
    // 'auto', not 'smooth': a smooth animation retriggered on every frame of
    // streamed text fights itself and visibly judders.
    el.scrollTop = el.scrollHeight;
  }, [messages, smoothText, stickToBottom]);

  const jumpToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    setStickToBottom(true);
  }, []);

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

  // ---------------------------------------------------------------------
  // ONE runner for every way a question can be asked.
  //
  // Send, Regenerate and Edit differ only in what the transcript looks like
  // BEFORE the question runs. Keeping three copies of the streaming, abort,
  // error and persistence logic in sync was not going to happen, so they all
  // funnel through here with a prepared `history`.
  // ---------------------------------------------------------------------
  const runQuestion = useCallback(
    async (question, history, { regenerate = false } = {}) => {
      if (!question || busyRef.current) return;

      busyRef.current = true;
      setBusy(true);
      resetSmooth();

      // The transcript is rebuilt from `history`, not appended to whatever is
      // on screen — that is what lets Edit rewrite the middle of a thread.
      setMessages([
        ...history,
        { role: "user", text: question },
        { role: "assistant", text: "", route: "", pending: true, streaming: true },
      ]);

      // If this is an existing conversation, discard the tail the user has
      // just abandoned so the stored thread matches the visible one. Only
      // meaningful for regenerate/edit, where history is shorter than what
      // the server holds.
      if (activeIdRef.current) {
        try {
          await truncateConversation(activeIdRef.current, history.length);
        } catch {
          // Best effort — see api.truncateConversation. Never costs the answer.
        }
      }

      const update = (patch) =>
        setMessages((prev) => {
          const next = [...prev];
          const i = next.length - 1;
          if (i < 0) return prev;
          next[i] = { ...next[i], ...patch(next[i]) };
          return next;
        });

      const controller = new AbortController();
      abortRef.current = controller;

      let expired = false;
      let createdId = null;

      const result = await askStream(question, {
        conversationId: activeIdRef.current,
        signal: controller.signal,
        // Regenerate skips the response cache. Without this it would return
        // the exact answer the user just rejected — and a wrong answer that
        // got cached would be unfixable from the UI.
        regenerate,
        onConversation: (c) => {
          createdId = c.id;
          if (!activeIdRef.current) {
            activeIdRef.current = c.id;
            setActiveId(c.id);
          }
        },
        onStage: (s) =>
          update(() => ({
            stage:
              s.stage === "routing_done"
                ? s.route === "SQL"
                  ? "Querying the database…"
                  : s.route === "RAG"
                    ? "Searching documents…"
                    : s.route === "BOTH"
                      ? "Querying the database and searching documents…"
                      : s.route === "WEB"
                        ? "Reading the college page…"
                        : "Working…"
                : s.stage === "sources_ready"
                  ? "Writing the answer…"
                  : s.stage === "verifying"
                    ? "Checking the answer against the records…"
                    : "Working…",
            verifying: s.stage === "verifying",
          })),
        onMeta: (meta) =>
          update(() => ({
            route: meta.route || "",
            stage: meta.cached ? "Found an earlier answer to this…" : undefined,
          })),
        // Text goes to the smoothing buffer, NOT straight into state. The
        // buffer drips it out a few characters per animation frame; see
        // hooks/useSmoothText.js for why (the transport is not the problem).
        onToken: (text) => {
          pushSmooth(text);
          update((m) => (m.pending ? { pending: false } : {}));
        },
        onDone: (final) => {
          finishSmooth(final);
          update(() => ({ text: final, pending: false, streaming: false, verifying: false }));
        },
        onError: (msg) => {
          if (msg.toLowerCase().includes("authorized")) expired = true;
          finishSmooth();
          update((m) => ({
            text: m.text || msg, error: true, pending: false,
            streaming: false, verifying: false,
          }));
        },
      }).catch((err) => {
        finishSmooth();
        update((m) => ({
          text: m.text || err.message, error: true, pending: false,
          streaming: false, verifying: false,
        }));
        return {};
      });

      // A stopped answer keeps whatever had already streamed. Discarding it
      // would throw away work the user watched being produced and may want.
      if (result?.aborted) {
        finishSmooth();
        update((m) => ({
          text: m.text || smoothRef.current || "",
          pending: false, streaming: false, verifying: false, stopped: true,
        }));
      }

      abortRef.current = null;
      busyRef.current = false;
      setBusy(false);
      if (createdId) refreshConversations();
      if (expired || result?.unauthorized) onSessionExpired();
    },
    [finishSmooth, onSessionExpired, pushSmooth, refreshConversations, resetSmooth]
  );

  async function handleSubmit(e) {
    e?.preventDefault();
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    await runQuestion(question, messagesRef.current);
  }

  // --- Stop generating ---------------------------------------------------
  // Aborts the fetch, which drops the connection. Django closes the response
  // generator, releasing the LLM slot, and common/ollama.chat_stream closes
  // the socket to Ollama so it stops generating. Without that chain this would
  // hide the answer while the model kept running — and on a machine that
  // serves one request at a time, that would block the next person.
  const stopGenerating = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // --- Regenerate --------------------------------------------------------
  // Re-runs the last user question against a transcript truncated to just
  // before it, so the model starts from the same place rather than seeing its
  // own previous attempt.
  const regenerate = useCallback(() => {
    if (busyRef.current) return;
    const msgs = messagesRef.current;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "user") {
        runQuestion(msgs[i].text, msgs.slice(0, i), { regenerate: true });
        return;
      }
    }
  }, [runQuestion]);

  // --- Edit a past question ----------------------------------------------
  // Everything after the edited message is dropped, exactly as ChatGPT does:
  // the answers that followed were responses to the old wording and would be
  // incoherent underneath the new one.
  const submitEdit = useCallback(
    (index, newText) => {
      const text = (newText || "").trim();
      setEditingIndex(null);
      if (!text || busyRef.current) return;
      runQuestion(text, messagesRef.current.slice(0, index));
    },
    [runQuestion]
  );


  function onKeyDown(e) {
    // Enter sends, Shift+Enter makes a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  // Ctrl/Cmd+K starts a new chat from anywhere, including while the composer
  // has focus. Bound on the document rather than the textarea so it works when
  // the user is scrolled up reading, and preventDefault stops Firefox and
  // Safari hijacking it for their address bars.
  useEffect(() => {
    function onGlobalKey(e) {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        newChat();
        textareaRef.current?.focus();
        return;
      }
      // Escape stops a running answer, then closes an open editor. Ordered so
      // the more urgent action wins when both apply.
      if (e.key === "Escape") {
        if (busyRef.current) {
          stopGenerating();
        } else if (editingIndex !== null) {
          setEditingIndex(null);
        }
      }
    }
    document.addEventListener("keydown", onGlobalKey);
    return () => document.removeEventListener("keydown", onGlobalKey);
  }, [editingIndex, stopGenerating]);

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
            {/* Staff only, and undefined for everyone else — App decides. The
                server refuses these routes to a non-staff account regardless. */}
            {onOpenAdmin && (
              <button
                onClick={onOpenAdmin}
                className="rounded-lg px-2.5 py-1.5 text-xs text-neutral-500 transition hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
              >
                Admin
              </button>
            )}
            <button
              onClick={onLogout}
              className="rounded-lg px-2.5 py-1.5 text-xs text-neutral-500 transition hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              Sign out
            </button>
          </div>
        </header>

        <div ref={scrollRef} onScroll={handleScroll} className="relative flex-1 overflow-y-auto">
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
                {messages.map((msg, i) => {
                  const isLast = i === messages.length - 1;
                  // While streaming, the LAST assistant message renders from the
                  // smoothing buffer instead of its own state, so text appears a
                  // few characters per frame rather than in ~4-char jumps nine
                  // times a second. Every other message renders its stored text.
                  const body = msg.streaming && isLast ? smoothText : msg.text;

                  return msg.role === "user" ? (
                    <div key={i} className="group flex flex-col items-end gap-1">
                      {editingIndex === i ? (
                        // Editing rewrites the thread from this point: every
                        // answer below was a response to the old wording.
                        <div className="w-full max-w-[85%] rounded-2xl border border-neutral-300 bg-white p-2 dark:border-neutral-600 dark:bg-neutral-900">
                          <textarea
                            autoFocus
                            rows={Math.min(8, editDraft.split(String.fromCharCode(10)).length + 1)}
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                submitEdit(i, editDraft);
                              }
                            }}
                            className="w-full resize-none bg-transparent px-2 py-1 text-[15px] outline-none"
                          />
                          <div className="mt-1 flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setEditingIndex(null)}
                              className="rounded-lg px-3 py-1.5 text-xs text-neutral-500 transition hover:bg-neutral-100 dark:hover:bg-neutral-800"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={() => submitEdit(i, editDraft)}
                              disabled={!editDraft.trim() || busy}
                              className="rounded-lg bg-accent px-3 py-1.5 text-xs text-white transition hover:opacity-90 disabled:opacity-40"
                            >
                              Send
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-neutral-100 px-4 py-2.5 text-[15px] leading-7 dark:bg-neutral-800">
                            {msg.text}
                          </div>
                          {/* Revealed on hover/focus so the transcript stays
                              clean, but never hidden from keyboard users. */}
                          <div className="flex gap-0.5 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => { setEditingIndex(i); setEditDraft(msg.text); }}
                              title="Edit and re-run from here"
                              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-neutral-500 transition hover:bg-neutral-100 disabled:opacity-40 dark:text-neutral-400 dark:hover:bg-neutral-800"
                            >
                              <EditIcon /> Edit
                            </button>
                            <CopyButton text={msg.text} />
                          </div>
                        </>
                      )}
                    </div>
                  ) : (
                    <div key={i} className="group text-[15px]">
                      {msg.route && (
                        <div className="mb-1.5 text-xs text-neutral-400 dark:text-neutral-500">
                          answered from {ROUTE_LABEL[msg.route] || msg.route.toLowerCase()}
                        </div>
                      )}
                      <div className={msg.error ? "text-red-600 dark:text-red-400" : ""}>
                        {body ? (
                          <Markdown>{body}</Markdown>
                        ) : msg.pending ? (
                          <Skeleton stage={msg.stage || "Thinking…"} />
                        ) : null}

                        {msg.stopped && (
                          <p className="mt-2 text-xs italic text-neutral-400 dark:text-neutral-500">
                            Stopped. This answer is incomplete and was not fact-checked.
                          </p>
                        )}

                        {/* The answer has streamed but the fact-check is still
                            running. That wait is real — up to a minute on a
                            retrieval answer — and without this the UI looks
                            finished while a correction may still arrive. */}
                        {body && msg.verifying && (
                          <div className="mt-2 flex items-center gap-2 text-xs text-neutral-400 dark:text-neutral-500">
                            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
                            Checking this answer against the records…
                          </div>
                        )}
                      </div>

                      {/* Action row. Hidden while this message is still being
                          produced — copying half an answer, or regenerating on
                          top of a running one, are both mistakes. */}
                      {!msg.streaming && !msg.pending && body && (
                        <div className="mt-2 flex gap-0.5 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">
                          <CopyButton text={body} />
                          {isLast && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={regenerate}
                              title="Run this question again"
                              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-neutral-500 transition hover:bg-neutral-100 disabled:opacity-40 dark:text-neutral-400 dark:hover:bg-neutral-800"
                            >
                              <RegenerateIcon /> Regenerate
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="px-4 pb-4">
          {/* Shown only when the user has scrolled away from the bottom, which
              is exactly when auto-scroll has disengaged. Without it there is no
              way back to a streaming answer except scrolling by hand. */}
          {!stickToBottom && (
            <div className="pointer-events-none mx-auto mb-2 flex w-full max-w-3xl justify-center">
              <button
                type="button"
                onClick={jumpToBottom}
                className="pointer-events-auto rounded-full border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-600 shadow-sm transition hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700"
              >
                Jump to latest ↓
              </button>
            </div>
          )}

          {busy && (
            <div className="mx-auto mb-2 flex w-full max-w-3xl justify-center">
              <button
                type="button"
                onClick={stopGenerating}
                className="inline-flex items-center gap-2 rounded-full border border-neutral-300 bg-white px-3.5 py-1.5 text-xs font-medium text-neutral-700 shadow-sm transition hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:bg-neutral-700"
              >
                <StopIcon /> Stop generating
              </button>
            </div>
          )}

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
              Answers run on a local model and can take a minute or more.{" "}
              <span className="hidden sm:inline">
                Enter to send, Shift+Enter for a new line, Ctrl/Cmd+K for a new chat.
              </span>
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
