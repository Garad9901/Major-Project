// Copyright (c) 2026 Yash Garad. All rights reserved.

// Runs the assertions in ../__markdown_test__.jsx under vitest.
//
// The legacy file is imported for its SIDE EFFECTS: its module body executes
// the assertions, each of which calls the shared `check` collector. A static
// import is evaluated before this module's own body runs, so by the time
// registerCollected() is reached the results are already there.
//
// Keeping the assertions in the original file and the runner wiring here means
// the valuable part stayed byte-identical when the runner was introduced. See
// __testutils__/check.js for the full reasoning.

import { describe, expect, test } from "vitest";

import { registerCollected } from "../__testutils__/check";
import "../__markdown_test__.jsx";

describe("answer markdown rendering", () => {
  registerCollected(test, expect);
});
