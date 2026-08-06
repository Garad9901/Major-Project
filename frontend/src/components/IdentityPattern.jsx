// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useMemo } from "react";

import { INSTITUTE, seedFrom } from "../institute";

// A lattice generated from the institute's name.
//
// WHY GENERATED RATHER THAN A STOCK GRAPHIC
// The brief was to avoid looking template-built, and the fastest way to look
// template-built is to use the same abstract blob everybody else downloaded.
// This draws from a hash of the institute's own name, so the figure belongs to
// this institute and to no other: change the name and the lattice genuinely
// changes. It also needs no asset, so there is nothing to lose, nothing to
// serve, and nothing for the CSP's `img-src` to block.
//
// WHY A LATTICE SPECIFICALLY
// Straight lines meeting at fixed angles read as drafting, architecture and
// order — the visual register of an institution. Curves and gradient blobs read
// as consumer software. The only curve on the panel is the monogram's arc.
//
// DETERMINISTIC. Same name in, same drawing out, on every machine and every
// build. Nothing here is random at runtime.

// A tiny seeded PRNG (mulberry32). Deterministic, ~10 lines, no dependency.
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const W = 600;
const H = 900;

function buildGeometry(seed) {
  const rand = rng(seed);

  // Points on a jittered grid. The jitter is what stops it looking like graph
  // paper; the grid is what stops it looking like noise.
  const cols = 5;
  const rows = 8;
  const points = [];
  for (let r = 0; r <= rows; r++) {
    for (let c = 0; c <= cols; c++) {
      const jx = (rand() - 0.5) * (W / cols) * 0.42;
      const jy = (rand() - 0.5) * (H / rows) * 0.42;
      points.push({
        x: (c * W) / cols + jx,
        y: (r * H) / rows + jy,
        r: 1.1 + rand() * 2.2,
        // Most nodes stay quiet; a few are emphasised in ochre.
        accent: rand() > 0.87,
      });
    }
  }

  // Connect each point to its right and lower neighbours only. Connecting all
  // neighbours produces a dense mesh that turns to mush at panel size.
  const lines = [];
  const at = (r, c) => points[r * (cols + 1) + c];
  for (let r = 0; r <= rows; r++) {
    for (let c = 0; c <= cols; c++) {
      const p = at(r, c);
      if (c < cols) lines.push({ a: p, b: at(r, c + 1), w: 0.5 + rand() * 0.5 });
      if (r < rows) lines.push({ a: p, b: at(r + 1, c), w: 0.5 + rand() * 0.5 });
      // An occasional diagonal breaks the rectilinear regularity.
      if (r < rows && c < cols && rand() > 0.78) {
        lines.push({ a: p, b: at(r + 1, c + 1), w: 0.4 });
      }
    }
  }

  return { points, lines };
}

/**
 * The identity lattice. Renders as inline SVG (no asset, no network request),
 * sized by its container. Purely decorative, so it is hidden from assistive
 * technology — a screen reader announcing forty circles helps nobody.
 */
function IdentityPattern({ className = "" }) {
  const { points, lines } = useMemo(
    () => buildGeometry(seedFrom(INSTITUTE.name)),
    []
  );

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <g stroke="currentColor" strokeLinecap="round">
        {lines.map((l, i) => (
          <line
            key={`l${i}`}
            x1={l.a.x} y1={l.a.y} x2={l.b.x} y2={l.b.y}
            strokeWidth={l.w}
            // Lines recede; the nodes carry the structure.
            opacity={0.14}
          />
        ))}
      </g>
      <g>
        {points.map((p, i) => (
          <circle
            key={`p${i}`}
            cx={p.x} cy={p.y} r={p.r}
            className={p.accent ? "fill-ochre-400" : "fill-current"}
            opacity={p.accent ? 0.85 : 0.3}
          />
        ))}
      </g>
    </svg>
  );
}

export default IdentityPattern;
