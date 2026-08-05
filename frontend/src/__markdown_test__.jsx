// Copyright (c) 2026 Yash Garad. All rights reserved.

// Renders <Markdown> to static HTML and asserts the result contains real
// elements and NO leftover markdown punctuation. Bundled with esbuild and run
// in Node — see the command in RUNBOOK / the Phase notes. Not shipped: the
// filename is excluded from the production build context.

import { renderToStaticMarkup } from "react-dom/server";

import Markdown from "./components/Markdown";

// A realistic assistant answer: bold, a bulleted list, a numbered list, inline
// code, a fenced code block, and a GFM table.
const SAMPLE = `The **Computer Science** department has the following profile:

- Overall development index: **67.2**
- Data literacy: 60.8
- Uses \`nomic-embed-text\` for search

Steps to reproduce:

1. Open the assistant
2. Ask a question
3. Read the answer

\`\`\`sql
SELECT COUNT(*) FROM faculty_development
WHERE department = 'Engineering' AND competency_level = 'Expert';
\`\`\`

| Department | Faculty |
| --- | --- |
| Engineering | 2073 |
| Medicine | 1046 |
`;

const html = renderToStaticMarkup(<Markdown>{SAMPLE}</Markdown>);

let pass = 0;
let fail = 0;
const check = (label, ok, detail = "") => {
  if (ok) { pass++; console.log(`  [PASS] ${label}`); }
  else { fail++; console.log(`  [FAIL] ${label}${detail ? " — " + detail : ""}`); }
};

console.log("\n--- elements actually produced ---");
check("bold renders as <strong>", /<strong[^>]*>Computer Science<\/strong>/.test(html));
check("bulleted list renders as <ul><li>", /<ul[^>]*>[\s\S]*?<li[^>]*>/.test(html));
check("numbered list renders as <ol><li>", /<ol[^>]*>[\s\S]*?<li[^>]*>/.test(html));
check("fenced block renders as <pre><code>", /<pre[^>]*>[\s\S]*?<code[^>]*>/.test(html));
check("inline code renders as <code>", /<code[^>]*>nomic-embed-text<\/code>/.test(html));
check("GFM table renders as <table>", /<table[^>]*>[\s\S]*?<th[^>]*>/.test(html));
check("paragraphs render as <p>", /<p[^>]*>/.test(html));

console.log("\n--- no RAW markdown symbols left visible ---");
// Strip tags and entities, then look for markdown punctuation in what a human
// would actually see on screen.
const visible = html
  .replace(/<[^>]+>/g, "")
  .replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, "&")
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">");

check("no ** bold markers", !visible.includes("**"), JSON.stringify(visible.match(/.{0,20}\*\*.{0,20}/)?.[0] || ""));
check("no ``` fences", !visible.includes("```"));
check("no backticks at all", !visible.includes("`"), JSON.stringify(visible.match(/.{0,20}`.{0,20}/)?.[0] || ""));
check("no '- ' bullet markers", !/(^|\n)\s*-\s/.test(visible), JSON.stringify(visible.match(/(^|\n)\s*-\s.{0,25}/)?.[0] || ""));
check("no '| ' table pipes", !visible.includes("|"), JSON.stringify(visible.match(/.{0,20}\|.{0,20}/)?.[0] || ""));
check("no '1. ' ordered markers", !/(^|\n)\s*\d+\.\s/.test(visible), JSON.stringify(visible.match(/(^|\n)\s*\d+\.\s.{0,25}/)?.[0] || ""));

console.log("\n--- content survived (text is still there) ---");
check("keeps the bold word", visible.includes("Computer Science"));
check("keeps list item text", visible.includes("Data literacy"));
check("keeps the SQL body", visible.includes("SELECT COUNT(*) FROM faculty_development"));
check("keeps table cells", visible.includes("Engineering") && visible.includes("2073"));

console.log("\n--- no raw HTML injection path ---");
const evil = renderToStaticMarkup(
  <Markdown>{'Normal text <img src=x onerror="alert(1)"> and <script>alert(2)</script>'}</Markdown>
);
check("embedded <script> is NOT rendered as a tag", !/<script/i.test(evil));
check("embedded <img onerror> is NOT rendered as a tag", !/<img/i.test(evil));

console.log(`\n==== ${pass} passed, ${fail} failed ====`);
if (fail > 0) process.exitCode = 1;
