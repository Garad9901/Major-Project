// Copyright (c) 2026 Yash Garad. All rights reserved.

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  // "class", not "media": the theme follows the user's SAVED PREFERENCE (stored
  // on their profile in the database), not the operating system setting. With
  // "media" the toggle would have nothing to switch.
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Deliberately tiny palette. Two neutral surfaces per mode, one border,
        // two text weights, and a single accent — anything more becomes visual
        // clutter on a page that is mostly prose.
        accent: "#10a37f",

        // --- institutional identity ------------------------------------------
        // Oxford navy and ochre. Used ONLY on the sign-in screen, deliberately:
        // the chat itself stays neutral so nothing competes with the answers,
        // which is where attention belongs once the user is inside.
        //
        // Navy runs dark enough at 900/950 to carry white text well past AA,
        // and the ochre is desaturated a long way below a "warning yellow" so
        // it never reads as an alert when used for a focus ring or a button.
        ink: {
          50: "#F4F6F9",
          100: "#E4E9F0",
          200: "#C4CFDE",
          300: "#94A7C0",
          400: "#5E779B",
          500: "#3C577C",
          600: "#2A4166",
          700: "#1E3352",
          800: "#182740",
          900: "#132A45",
          950: "#0B1728",
        },
        ochre: {
          50: "#FBF6EC",
          100: "#F5E9CF",
          200: "#EBD3A1",
          300: "#DDB56A",
          400: "#C98A2E",
          500: "#B0741F",
          600: "#8D5B18",
          700: "#6B4514",
          800: "#4A3010",
        },
      },
      fontFamily: {
        // ONE distinctive typographic choice, used for the wordmark and
        // headings only. Fraunces is a variable serif with real optical-size,
        // softness and "wonk" axes, so it has a voice that Inter, Roboto and
        // the system stack do not — which is exactly the point: those are the
        // faces a starter template ships with.
        //
        // SELF-HOSTED, NOT OPTIONAL. The production CSP sets `font-src 'self'`,
        // so a Google Fonts <link> would be blocked outright and the page would
        // silently fall back to Georgia. @fontsource-variable bundles the woff2
        // through Vite so it is served from our own origin.
        display: ['"Fraunces Variable"', "Fraunces", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
