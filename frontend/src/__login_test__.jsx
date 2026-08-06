// Copyright (c) 2026 Yash Garad. All rights reserved.

// Renders the sign-in screen to static HTML and asserts the things that break
// silently: the institute identity actually appearing, the error states staying
// calm and distinct, and the generated pattern being stable.
//
// It also asserts the ABSENCE of the visual clichés the redesign was asked to
// avoid. Those are the parts most likely to creep back in during a later edit
// — someone adds a shadow, someone reaches for indigo — and they are cheap to
// catch mechanically.
//
// Run: see RUNBOOK.md → Running the automated tests.

import { renderToStaticMarkup } from "react-dom/server";

import IdentityPattern from "./components/IdentityPattern";
import InstituteMark from "./components/InstituteMark";
import Login, { describeFailure } from "./components/Login";
import { INSTITUTE, initialsOf, seedFrom } from "./institute";

// Browser globals the component reads during render (its useState initialiser
// checks a saved theme, and the theme effect writes one back). Assigned in the
// module body rather than an import: ES imports hoist, but this runs before the
// first renderToStaticMarkup call below, which is when they are actually read.
globalThis.localStorage = {
  _v: {},
  getItem(k) { return this._v[k] ?? null; },
  setItem(k, v) { this._v[k] = String(v); },
};
globalThis.window = globalThis.window || {};
globalThis.window.matchMedia = () => ({ matches: false });
globalThis.document = globalThis.document || {
  documentElement: { classList: { toggle() {} } },
};

let pass = 0;
let fail = 0;
const check = (label, ok, detail = "") => {
  if (ok) { pass++; console.log(`  [PASS] ${label}`); }
  else { fail++; console.log(`  [FAIL] ${label}${detail ? " — " + detail : ""}`); }
};

const html = renderToStaticMarkup(<Login onLoggedIn={() => {}} />);
const visible = html.replace(/<[^>]+>/g, " ").replace(/&[a-z]+;|&#x?\d+;/gi, " ");

console.log("\n--- institute identity is actually present ---");
check("wordmark shows the institute name", visible.includes(INSTITUTE.name));
check("descriptor is shown", visible.includes(INSTITUTE.descriptor));
check("monogram uses the derived initials", html.includes(`>${initialsOf()}<`));
check("wordmark uses the display face", /font-display/.test(html));

console.log("\n--- layout is a split, not a centred card ---");
check("uses a 12-column grid", /lg:grid-cols-12/.test(html));
check("identity panel is 5 of 12 (asymmetric)", /lg:col-span-5/.test(html));
check("form panel is 7 of 12", /lg:col-span-7/.test(html));
check("identity panel is a real <aside>", /<aside/.test(html));
check("form is NOT centred in an empty page",
      !/min-h-screen[^"]*items-center[^"]*justify-center/.test(html));

console.log("\n--- none of the 'AI template' tells ---");
check("no purple/violet/indigo/fuchsia", !/(purple|violet|indigo|fuchsia)-\d/.test(html));
check("no decorative background gradient",
      !/bg-gradient-to-\w+ from-(purple|blue|indigo|violet|pink)/.test(html));
check("no floating card shadow", !/shadow-(lg|xl|2xl)/.test(html));
check("no rocket/spark/brain/robot glyphs",
      !/[\u{1F680}\u{2728}\u{1F9E0}\u{1F916}]/u.test(html));
check("no 'Welcome back' boilerplate", !/welcome back/i.test(visible));
check("no gradient text treatment", !/bg-clip-text/.test(html));

console.log("\n--- accessibility basics ---");
check("both inputs have a real <label for>",
      (html.match(/<label[^>]*for="/g) || []).length >= 2);
// Case-insensitive: renderToStaticMarkup preserves the camelCase
// `autoComplete` rather than lowercasing it. HTML attribute names are
// case-insensitive so browsers honour it either way — matching case-
// sensitively here tested React's serialiser, not the page.
check("username has autocomplete", /autocomplete="username"/i.test(html));
check("password has autocomplete", /autocomplete="current-password"/i.test(html));
check("error region is live", /aria-live="polite"/.test(html));
check("theme toggle has an accessible name",
      /aria-label="Switch to (light|dark) mode"/.test(html));
check("decorative pattern hidden from assistive tech", /aria-hidden="true"/.test(html));

console.log("\n--- error states are distinct, specific and calm ---");
const mk = (status, message) => Object.assign(new Error(message), { status });

const wrong = describeFailure(mk(401, "Invalid username or password."));
const locked = describeFailure(mk(423,
  "This account is temporarily locked after repeated failed sign-in attempts. " +
  "Try again in 12 minute(s), or ask an administrator to reset it."));
const throttled = describeFailure(mk(429,
  "Request was throttled. Expected available in 53 seconds."));
const broken = describeFailure(new Error("Failed to fetch"));

check("401 tells the user to check what they typed", /did not match/i.test(wrong.title));
check("401 mentions Caps Lock", /caps lock/i.test(wrong.detail));
check("423 names the lockout", /locked/i.test(locked.title));
check("423 quotes the real wait time from the server", /12 minutes/.test(locked.detail),
      locked.detail);
check("423 does not blame the user", !/you (entered|typed|got)/i.test(locked.detail));
check("429 explains the shared limit", /network|connection/i.test(throttled.title + throttled.detail));
check("network failure is not presented as a credential problem",
      /could not reach/i.test(broken.title));

const titles = [wrong.title, locked.title, throttled.title, broken.title];
check("all four failure modes have distinct wording", new Set(titles).size === 4);

// "Calm" made concrete: the lock and throttle are marked as something to wait
// out, the other two as something to retry — and nothing is styled as an alarm.
check("lock and throttle are 'hold', not 'retry'",
      locked.tone === "hold" && throttled.tone === "hold");
check("wrong password is a 'retry'", wrong.tone === "retry");
const allCopy = titles.join(" ") + [wrong, locked, throttled, broken].map((f) => f.detail).join(" ");
check("no alarm punctuation in any message", !/[!⚠]/.test(allCopy), allCopy.slice(0, 80));
check("no red styling on any error path", !/(text|bg|border)-red-\d/.test(html));

console.log("\n--- generated pattern is deterministic ---");
const a = renderToStaticMarkup(<IdentityPattern />);
const b = renderToStaticMarkup(<IdentityPattern />);
check("same name renders an identical lattice", a === b);
check("pattern is inline SVG, needs no asset", a.startsWith("<svg") && !/<img/.test(a));
check("seed is stable for a name", seedFrom("Example Institute") === seedFrom("Example Institute"));
check("different names give different seeds", seedFrom("Alpha College") !== seedFrom("Beta College"));

console.log("\n--- monogram ---");
const mark = renderToStaticMarkup(<InstituteMark />);
check("renders as SVG when no logo file is set", mark.startsWith("<svg"));
check("is labelled for screen readers", /aria-label=/.test(mark));
check("initials skip filler words",
      initialsOf({ name: "Institute of Science and Technology" }) === "IST",
      initialsOf({ name: "Institute of Science and Technology" }));

console.log(`\n==== ${pass} passed, ${fail} failed ====`);
if (fail > 0) process.exitCode = 1;
