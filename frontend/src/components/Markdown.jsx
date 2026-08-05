// Copyright (c) 2026 Yash Garad. All rights reserved.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders the assistant's answer as real HTML.
//
// The model emits markdown whether or not we ask it to — **bold**, `- ` lists,
// numbered lists and fenced code blocks all appear in normal answers. Printing
// that string raw (which is what the previous UI did) showed the asterisks and
// backticks to the user.
//
// remark-gfm adds the GitHub extensions on top of CommonMark: tables,
// strikethrough, task lists and bare autolinks. The assistant produces tables
// often enough — comparing departments, listing fees — that CommonMark alone
// would leave pipe characters on screen.
//
// SAFETY: react-markdown does NOT render raw HTML by default. There is no
// rehype-raw here and no dangerouslySetInnerHTML anywhere, so markup embedded in
// a retrieved document — which is untrusted content stored by staff — is shown
// as text and cannot inject anything into the page.

const components = {
  // Tight vertical rhythm: the default browser margins are far too large inside
  // a chat bubble and make short answers look broken up.
  p: ({ children }) => <p className="mb-3 last:mb-0 leading-7">{children}</p>,

  h1: ({ children }) => <h1 className="mb-3 mt-5 text-xl font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-5 text-lg font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold first:mt-0">{children}</h3>,

  // list-outside + padding keeps wrapped lines aligned under the text rather
  // than under the bullet.
  ul: ({ children }) => <ul className="mb-3 list-outside list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-outside list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-7">{children}</li>,

  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,

  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),

  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-neutral-300 pl-4 italic text-neutral-600 dark:border-neutral-600 dark:text-neutral-400">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="my-4 border-neutral-200 dark:border-neutral-700" />,

  // react-markdown v10 no longer passes `inline`; an inline code span is a
  // <code> whose parent is not <pre>. Detecting it by the language class is the
  // supported approach — fenced blocks carry `language-*`, inline spans do not.
  code: ({ className, children, ...props }) => {
    const isBlock = /language-\w+/.test(className || "");
    if (!isBlock) {
      return (
        <code
          className="rounded bg-neutral-200/70 px-1.5 py-0.5 font-mono text-[0.875em] text-neutral-800 dark:bg-neutral-700/60 dark:text-neutral-100"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className="font-mono text-[13px] leading-6" {...props}>
        {children}
      </code>
    );
  },

  // overflow-x-auto so a long line scrolls inside the block instead of widening
  // the whole chat column.
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg bg-neutral-100 p-3.5 last:mb-0 dark:bg-neutral-800/80">
      {children}
    </pre>
  ),

  // Tables come from remark-gfm. Wrapped so a wide table scrolls on its own.
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-neutral-300 bg-neutral-100 px-3 py-1.5 text-left font-semibold dark:border-neutral-600 dark:bg-neutral-800">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-neutral-300 px-3 py-1.5 dark:border-neutral-600">{children}</td>
  ),
};

function Markdown({ children }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children || ""}
    </ReactMarkdown>
  );
}

export default Markdown;
