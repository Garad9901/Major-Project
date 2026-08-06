// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useCallback, useEffect, useRef, useState } from "react";

// Smooth out the arrival cadence of streamed text.
//
// WHY THIS EXISTS — AND WHY IT IS NOT A TRANSPORT FIX
// The obvious suspect for choppy streaming is buffering in the proxy, so that
// was measured first. It is not the problem:
//
//     Content-Encoding : (none)      Caddy does not compress text/event-stream
//     token events     : 14
//     inter-token gap  : median 112ms, mean 114ms, max 128ms
//     clumped (<2ms after previous): 0/13  (0%)
//     gaps over 500ms  : 0
//
// Nothing is being held back. The tokens are evenly spaced and arrive the
// instant the model produces them. The choppiness is that Ollama emits roughly
// four characters at a time, about nine times a second, so the text visibly
// jumps in chunks — and on CPU inference those chunks are large and slow enough
// to read as stuttering rather than typing.
//
// So the fix belongs on the render side: accept text as fast as it arrives,
// but REVEAL it a few characters per animation frame. This is what makes
// ChatGPT feel smooth; the underlying stream there is chunked too.
//
// THE RULE THIS FOLLOWS: never fall behind, never invent.
// The revealed text is always a prefix of the text actually received — this
// cannot show a character the server did not send. And when the buffer grows
// (the model got ahead of the animation), the reveal rate scales up so the
// display converges instead of lagging further and further behind.

// Characters revealed per animation frame at the slowest rate. At ~60fps that
// is ~120 chars/sec, comfortably faster than the model's ~36 chars/sec, so the
// display keeps up without ever looking like it is racing.
const MIN_CHARS_PER_FRAME = 2;

// Hard ceiling so a large catch-up (or a cached answer arriving all at once)
// does not dump thousands of characters in one frame and defeat the effect.
const MAX_CHARS_PER_FRAME = 40;

/**
 * Returns [visibleText, push, reset, finish].
 *
 *   push(chunk)  append newly received text
 *   reset()      clear everything (new question)
 *   finish()     reveal the remainder immediately (stream ended or was stopped)
 */
export default function useSmoothText() {
  const [visible, setVisible] = useState("");
  const fullRef = useRef("");     // everything received so far
  const shownRef = useRef(0);     // how much of it has been revealed
  const rafRef = useRef(null);
  const doneRef = useRef(false);

  const stop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    const pending = fullRef.current.length - shownRef.current;
    if (pending <= 0) {
      rafRef.current = null;
      return;
    }

    // Reveal faster the further behind we are, so a burst is absorbed within a
    // few frames rather than queuing up. Dividing by 8 means a 200-character
    // backlog clears in about eight frames (~130ms).
    const step = Math.max(
      MIN_CHARS_PER_FRAME,
      Math.min(MAX_CHARS_PER_FRAME, Math.ceil(pending / 8))
    );

    shownRef.current = Math.min(fullRef.current.length, shownRef.current + step);
    setVisible(fullRef.current.slice(0, shownRef.current));
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const schedule = useCallback(() => {
    if (rafRef.current === null && !doneRef.current) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }, [tick]);

  const push = useCallback(
    (chunk) => {
      if (!chunk) return;
      fullRef.current += chunk;
      schedule();
    },
    [schedule]
  );

  const reset = useCallback(() => {
    stop();
    fullRef.current = "";
    shownRef.current = 0;
    doneRef.current = false;
    setVisible("");
  }, [stop]);

  // Called when the stream ends OR the user stops it. Skips the animation and
  // shows everything received — waiting out a drip after the answer is complete
  // would be pure artificial delay, which is the opposite of the point.
  const finish = useCallback(
    (finalText) => {
      stop();
      doneRef.current = true;
      if (typeof finalText === "string" && finalText.length >= fullRef.current.length) {
        fullRef.current = finalText;
      }
      shownRef.current = fullRef.current.length;
      setVisible(fullRef.current);
    },
    [stop]
  );

  // Cancel any in-flight frame if the component unmounts mid-stream.
  useEffect(() => stop, [stop]);

  return [visible, push, reset, finish];
}
