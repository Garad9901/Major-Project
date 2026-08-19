// Copyright (c) 2026 Yash Garad. All rights reserved.

// Tests the streaming smoothing buffer (hooks/useSmoothText.js).
//
// This is the one piece of Prompt 27 with real logic rather than markup, and it
// has a safety property worth pinning down: the text it reveals must ALWAYS be
// a prefix of the text actually received. A bug here would show the user
// characters the server never sent, in an application whose whole purpose is
// answering factual questions.
//
// Run with:
//   docker compose exec -T frontend sh -c "cd /app && npx --yes esbuild \
//     src/__smoothtext_test__.jsx --bundle --platform=node --format=cjs \
//     --outfile=/tmp/smoothtest.cjs --loader:.jsx=jsx --jsx=automatic \
//     --log-level=error && node /tmp/smoothtest.cjs"

import { renderHook } from "./__testutils__/renderHook";
import useSmoothText from "./hooks/useSmoothText";

// `check` now comes from the shared collector so a real runner can see these
// assertions; every call site below is unchanged. See __testutils__/check.js.
import { check } from "./__testutils__/check";

console.log("\n--- reveals text gradually, never all at once ---");
{
  const h = renderHook(() => useSmoothText());
  const [, push] = h.current;
  const FULL = "There are 3,053 faculty members holding the Lecturer rank.";
  push(FULL);

  const frames = [];
  for (let i = 0; i < 60; i++) {
    h.flushFrame();
    frames.push(h.current[0]);
    if (h.current[0] === FULL) break;
  }

  check("did not reveal everything in one frame", frames[0].length < FULL.length,
        `first frame showed ${frames[0].length}/${FULL.length}`);
  check("took several frames", frames.length > 3, `${frames.length} frames`);
  check("eventually reveals the whole string", h.current[0] === FULL);
  check("length increases monotonically",
        frames.every((f, i) => i === 0 || f.length >= frames[i - 1].length));
}

console.log("\n--- NEVER shows text that was not received ---");
{
  const h = renderHook(() => useSmoothText());
  const [, push] = h.current;
  const FULL = "The average is 67.2 out of 100.";
  push(FULL);
  let violations = 0;
  for (let i = 0; i < 60; i++) {
    h.flushFrame();
    if (!FULL.startsWith(h.current[0])) violations++;
    if (h.current[0] === FULL) break;
  }
  check("every intermediate value is a prefix of the source", violations === 0,
        `${violations} violation(s)`);
}

console.log("\n--- catches up rather than falling behind ---");
{
  const h = renderHook(() => useSmoothText());
  const [, push] = h.current;
  // A big burst, as happens when a cached answer arrives in one chunk.
  const BIG = "x".repeat(2000);
  push(BIG);
  let frames = 0;
  while (h.current[0].length < BIG.length && frames < 500) {
    h.flushFrame();
    frames++;
  }
  check("absorbs a 2000-char burst quickly", frames < 120, `${frames} frames`);
  check("still reveals the whole burst", h.current[0].length === BIG.length);
}

console.log("\n--- finish() skips the animation ---");
{
  const h = renderHook(() => useSmoothText());
  const [, push, , finish] = h.current;
  push("partial text here");
  h.flushFrame();
  const midway = h.current[0].length;
  finish("partial text here and the rest of it");
  check("revealed everything immediately",
        h.current[0] === "partial text here and the rest of it");
  check("had genuinely been mid-animation", midway > 0 && midway < 17,
        `showed ${midway} chars before finish()`);
}

console.log("\n--- finish() without an argument keeps what was received ---");
{
  const h = renderHook(() => useSmoothText());
  const [, push, , finish] = h.current;
  push("stopped halfway");
  finish();
  check("keeps the received text", h.current[0] === "stopped halfway");
}

console.log("\n--- reset() clears everything for the next question ---");
{
  const h = renderHook(() => useSmoothText());
  const [, push, reset] = h.current;
  push("first answer");
  h.flushFrame();
  reset();
  check("visible text is empty after reset", h.current[0] === "");
  // And a new push must not resurrect the old text.
  h.current[1]("second");
  for (let i = 0; i < 20; i++) h.flushFrame();
  check("new text does not include the old", h.current[0] === "second",
        JSON.stringify(h.current[0]));
}

console.log("\n--- incremental pushes behave like a real stream ---");
{
  const h = renderHook(() => useSmoothText());
  const chunks = ["There ", "are ", "1,046 ", "faculty ", "in ", "Medicine."];
  const expected = chunks.join("");
  let violations = 0;
  for (const chunk of chunks) {
    h.current[1](chunk);
    for (let i = 0; i < 4; i++) {
      h.flushFrame();
      if (!expected.startsWith(h.current[0])) violations++;
    }
  }
  for (let i = 0; i < 60 && h.current[0] !== expected; i++) h.flushFrame();
  check("assembles the full answer", h.current[0] === expected, JSON.stringify(h.current[0]));
  check("never showed a non-prefix mid-stream", violations === 0);
}
