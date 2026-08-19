// Copyright (c) 2026 Yash Garad. All rights reserved.

// The assertion collector that lets the pre-existing test files run under a
// real test runner WITHOUT rewriting their assertions.
//
// HISTORY, BECAUSE IT EXPLAINS THE SHAPE
// These tests were written before the project had a frontend runner at all.
// Each file defined its own `check(label, ok, detail)`, counted passes and
// failures itself, printed a summary and set process.exitCode — and was run by
// hand through esbuild + node, one command per file, as documented in RUNBOOK.
// Nothing in CI ran them, and package.json had no test script, so ~22 KB of
// genuine assertions were sitting in the repository unexecuted.
//
// WHY NOT JUST REWRITE THEM AS vitest test() CALLS
// The assertions are the valuable part and they are correct. Rewriting three
// files of them by hand is a large diff in which a silently dropped or inverted
// assertion is easy to miss and hard to review. Swapping only the four lines of
// bookkeeping at the top of each file, and deleting the two-line footer, leaves
// every assertion byte-identical and the diff trivially checkable.
//
// HOW IT WORKS
// Each legacy file imports `check` from here instead of defining it. Calls
// accumulate in a module-level array. A thin spec file in __tests__/ imports
// the legacy file for its side effects — a static import, so it is evaluated
// during collection, before the describe() body runs — then turns each recorded
// result into a real vitest test.
//
// The array is module-level, which is safe because vitest gives every test FILE
// its own module registry: two specs importing this module get two independent
// arrays rather than one shared, order-dependent one.

const results = [];

/**
 * Record one assertion.
 *
 * Signature is unchanged from the hand-rolled version the test files already
 * call, which is the whole point — the call sites did not have to move.
 *
 * @param {string} label   what is being asserted, used as the vitest test name
 * @param {unknown} ok     truthy to pass
 * @param {unknown} detail optional context shown only on failure
 */
export function check(label, ok, detail = "") {
  results.push({
    label,
    ok: Boolean(ok),
    // Stringified at record time. The legacy call sites pass all sorts of
    // things here (a rendered HTML string, a JSON blob, a computed value), and
    // holding a live reference would let a later mutation change what the
    // failure message says happened.
    detail: detail === "" || detail === undefined ? "" : String(detail),
  });
}

/** Every assertion recorded so far, in call order. */
export function collected() {
  return results;
}

/**
 * Register the collected assertions as vitest tests.
 *
 * Takes `test` as a parameter rather than importing vitest here, so this module
 * stays a plain collector that the legacy files can import without dragging the
 * runner into their dependency graph.
 *
 * Fails loudly on an empty set: a legacy file that throws partway through its
 * module body would otherwise register zero tests and report a serene green
 * pass, which is the one outcome worse than a failure.
 */
export function registerCollected(test, expect, { min = 1 } = {}) {
  const found = collected();

  test("the legacy file ran to completion and recorded its assertions", () => {
    expect(
      found.length,
      `expected at least ${min} assertion(s); got ${found.length}. A module-body ` +
        "throw in the imported test file will produce this.",
    ).toBeGreaterThanOrEqual(min);
  });

  found.forEach((result, index) => {
    // Index-prefixed because several legacy labels legitimately repeat across
    // sections ("renders as SVG", etc.) and vitest needs distinguishable names.
    test(`${String(index + 1).padStart(2, "0")}. ${result.label}`, () => {
      expect(result.ok, result.detail || result.label).toBe(true);
    });
  });
}
