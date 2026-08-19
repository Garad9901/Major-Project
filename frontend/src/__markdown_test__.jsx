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

// `check` now comes from the shared collector so a real runner can see these
// assertions; every call site below is unchanged. See __testutils__/check.js.
import { check } from "./__testutils__/check";

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

// ---------------------------------------------------------------------------
// EVERYTHING AT ONCE, WITH NESTING
// ---------------------------------------------------------------------------
// The sample above exercises each construct in isolation and side by side, but
// every list in it is FLAT. Nesting is where markdown renderers actually break:
// an indented sub-list, a fenced block indented INSIDE a list item, and a table
// following a list are all cases where a mis-set `tightness` or a missing
// remark-gfm plugin silently emits the raw source instead of elements.
//
// Real answers from this assistant do produce this shape — "how many faculty by
// department, broken down by rank" comes back as a nested list next to a table.
const NESTED = `Here is the **combined breakdown**:

- Engineering
  - Professors: 331
  - Lecturers: 402
    - Of whom \`Expert\` competency: 27
- Medicine
  - Professors: 118

1. First step
   1. Nested step one
   2. Nested step two
2. Second step

| Rank | Count |
| --- | --- |
| Professor | 1552 |
| Lecturer | 3053 |

\`\`\`python
def total(rows):
    return sum(r["count"] for r in rows)
\`\`\`

> A blockquote closing the answer.
`;

const nested = renderToStaticMarkup(<Markdown>{NESTED}</Markdown>);
const nestedVisible = nested
  .replace(/<[^>]+>/g, "")
  .replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, "&")
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">");

console.log("\n--- nested lists + table + code block in ONE response ---");
// A <ul> appearing inside an <li> is the actual structural assertion; matching
// on indentation in the source would prove nothing about the output.
check("nested <ul> inside an <li>", /<li[^>]*>[\s\S]*?<ul[^>]*>[\s\S]*?<li[^>]*>/.test(nested));
check("nested <ol> inside an <li>", /<li[^>]*>[\s\S]*?<ol[^>]*>[\s\S]*?<li[^>]*>/.test(nested));
check("three-deep nesting survives", /Of whom/.test(nested) && (nested.match(/<ul/g) || []).length >= 3);
check("table still renders alongside lists", /<table[^>]*>[\s\S]*?<th[^>]*>Rank<\/th>/.test(nested));
// Structural only. Since syntax highlighting was added, the code body is no
// longer contiguous text inside <code> — `def` becomes
// <span class="hljs-keyword">def</span> — so asserting on "def total" here
// tested the absence of highlighting rather than the presence of a code block.
// The body itself is still checked below, against the tag-stripped text.
check("code block still renders alongside lists", /<pre[^>]*>[\s\S]*?<code[^>]*>/.test(nested));
check("inline code inside a nested item", /<code[^>]*>Expert<\/code>/.test(nested));
check("blockquote renders as <blockquote>", /<blockquote[^>]*>/.test(nested));

console.log("\n--- nested response leaves NO raw markdown visible ---");
check("no ** markers", !nestedVisible.includes("**"), JSON.stringify(nestedVisible.match(/.{0,20}\*\*.{0,20}/)?.[0] || ""));
check("no ``` fences", !nestedVisible.includes("```"));
check("no backticks", !nestedVisible.includes("`"), JSON.stringify(nestedVisible.match(/.{0,20}`.{0,20}/)?.[0] || ""));
check("no '- ' bullets", !/(^|\n)\s*-\s/.test(nestedVisible), JSON.stringify(nestedVisible.match(/(^|\n)\s*-\s.{0,25}/)?.[0] || ""));
check("no '|' table pipes", !nestedVisible.includes("|"), JSON.stringify(nestedVisible.match(/.{0,20}\|.{0,20}/)?.[0] || ""));
check("no '>' quote markers", !/(^|\n)\s*>\s/.test(nestedVisible));
check("no ordered-list source markers", !/(^|\n)\s*\d+\.\s/.test(nestedVisible), JSON.stringify(nestedVisible.match(/(^|\n)\s*\d+\.\s.{0,25}/)?.[0] || ""));

console.log("\n--- nested response keeps its content ---");
check("keeps deepest item text", nestedVisible.includes("Of whom"));
check("keeps table cell", nestedVisible.includes("3053"));
check("keeps code body", nestedVisible.includes("def total"));

// ---------------------------------------------------------------------------
// SYNTAX HIGHLIGHTING (Prompt 27, item 8)
// ---------------------------------------------------------------------------
console.log("\n--- syntax highlighting by language ---");

const PY = renderToStaticMarkup(
  <Markdown>{"```python\ndef total(rows):\n    return sum(r for r in rows)\n```"}</Markdown>
);
check("python keywords are tokenised", /class="hljs-keyword"[^>]*>def</.test(PY));
check("language label is shown in the header", />python</i.test(PY));
check("a copy button is rendered for the block", /Copy code/i.test(PY));

const SQL = renderToStaticMarkup(
  <Markdown>{"```sql\nSELECT COUNT(*) FROM faculty_development WHERE age > 40;\n```"}</Markdown>
);
check("sql keywords are tokenised", /hljs-keyword/.test(SQL));
check("sql body survives highlighting", />SELECT</.test(SQL.replace(/<span[^>]*>/g, ">")));

// detect:false means an undeclared block must stay plain rather than being
// guessed at — a mis-highlighted block reads worse than an unhighlighted one.
const PLAIN = renderToStaticMarkup(<Markdown>{"```\njust some text\n```"}</Markdown>);
check("undeclared block is NOT auto-highlighted", !/hljs-keyword/.test(PLAIN));
check("undeclared block still renders as a code block", /<pre[^>]*>[\s\S]*?<code/.test(PLAIN));

// An unknown language must not throw (ignoreMissing) and must still render.
const WEIRD = renderToStaticMarkup(
  <Markdown>{"```notalanguage\nhello world\n```"}</Markdown>
);
check("unknown language degrades to a plain block", /<pre[^>]*>[\s\S]*?hello world/.test(
  WEIRD.replace(/<span[^>]*>/g, "").replace(/<\/span>/g, "")
));

// Highlighting must not have introduced an HTML injection path: the source is
// escaped before tokenising, so a <script> inside a fence stays inert.
const EVIL_CODE = renderToStaticMarkup(
  <Markdown>{"```javascript\nconst x = \"<script>alert(1)</script>\";\n```"}</Markdown>
);
check("script inside a highlighted fence is escaped", !/<script/i.test(EVIL_CODE));
