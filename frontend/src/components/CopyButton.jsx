// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useCallback, useEffect, useRef, useState } from "react";

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
         strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function ClipboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

/**
 * Copy `text` to the clipboard, with a two-second confirmation.
 *
 * navigator.clipboard is unavailable on insecure origins, and this app is
 * always behind TLS — but a LAN deployment reached by raw IP can still end up
 * there, so there is a textarea fallback rather than a button that silently
 * does nothing.
 */
function CopyButton({ text, label = "Copy", className = "", compact = false }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const copy = useCallback(async () => {
    const value = typeof text === "function" ? text() : text;
    if (!value) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const el = document.createElement("textarea");
        el.value = value;
        el.setAttribute("readonly", "");
        el.style.position = "fixed";
        el.style.opacity = "0";
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
      }
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // A denied clipboard permission is not worth an error dialog.
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      className={
        "inline-flex items-center gap-1.5 rounded-md text-xs text-neutral-500 transition " +
        "hover:bg-neutral-100 hover:text-neutral-700 dark:text-neutral-400 " +
        "dark:hover:bg-neutral-700/60 dark:hover:text-neutral-200 " +
        (compact ? "px-1.5 py-1 " : "px-2 py-1.5 ") +
        className
      }
    >
      {copied ? <CheckIcon /> : <ClipboardIcon />}
      {!compact && <span>{copied ? "Copied" : label}</span>}
    </button>
  );
}

export default CopyButton;
