// Copyright (c) 2026 Yash Garad. All rights reserved.

// A minimal hook harness for Node, with a MANUALLY DRIVEN animation clock.
//
// WHY NOT @testing-library/react-hooks
// It would pull in a test runner, jsdom and a DOM implementation to exercise
// about eighty lines of buffer arithmetic. The rest of this project's frontend
// tests are esbuild + node with no runner (see __markdown_test__.jsx), and
// keeping one mechanism means one command to remember.
//
// WHY THE CLOCK IS MANUAL
// requestAnimationFrame does not exist in Node, and even where it does, a real
// clock makes the test timing-dependent and flaky. Driving frames explicitly
// with flushFrame() makes "how many frames did this take" an assertable fact
// rather than a race.

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

/**
 * Renders a hook and returns a handle:
 *   handle.current     the hook's latest return value
 *   handle.flushFrame() run exactly one queued animation frame
 *
 * Implemented with a tiny hand-rolled dispatcher rather than a real renderer:
 * useState / useRef / useEffect / useCallback are all that useSmoothText needs,
 * and re-invoking the hook function after each state change reproduces React's
 * behaviour closely enough for pure buffer logic.
 */
export function renderHook(hookFn) {
  const frameQueue = [];
  let nextFrameId = 1;

  // Installed for the duration of the test so the hook's rAF calls land in our
  // queue instead of failing on an undefined global.
  globalThis.requestAnimationFrame = (cb) => {
    const id = nextFrameId++;
    frameQueue.push({ id, cb });
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => {
    const i = frameQueue.findIndex((f) => f.id === id);
    if (i !== -1) frameQueue.splice(i, 1);
  };

  const states = [];
  const refs = [];
  let stateIndex = 0;
  let refIndex = 0;

  const handle = { current: null };

  function render() {
    stateIndex = 0;
    refIndex = 0;
    handle.current = hookFn();
  }

  // React's real hooks, reduced to what this buffer uses.
  const dispatcher = {
    useState(initial) {
      const i = stateIndex++;
      if (!(i in states)) states[i] = typeof initial === "function" ? initial() : initial;
      const setter = (value) => {
        const next = typeof value === "function" ? value(states[i]) : value;
        if (!Object.is(next, states[i])) {
          states[i] = next;
          render(); // synchronous re-render, which is all this test needs
        }
      };
      return [states[i], setter];
    },
    useRef(initial) {
      const i = refIndex++;
      if (!(i in refs)) refs[i] = { current: initial };
      return refs[i];
    },
    // The hook's callbacks are recreated every render here rather than being
    // memoised. That is safe for these tests — they call through the handle,
    // which always holds the latest — and avoids reimplementing dependency
    // comparison just to test buffer arithmetic.
    useCallback: (fn) => fn,
    useEffect: () => {},
  };

  // Swap React's internals for the dispatcher above while the hook runs.
  const ReactInternals =
    require("react").__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
  const previous = ReactInternals.ReactCurrentDispatcher.current;
  ReactInternals.ReactCurrentDispatcher.current = dispatcher;

  render();

  handle.flushFrame = () => {
    const frame = frameQueue.shift();
    if (frame) frame.cb();
  };
  handle.pendingFrames = () => frameQueue.length;
  handle.restore = () => {
    ReactInternals.ReactCurrentDispatcher.current = previous;
  };

  return handle;
}

// Referenced so the react-dom/server import is not tree-shaken away; keeping it
// makes this harness usable for component tests later without another rewrite.
export { createElement, renderToStaticMarkup };
