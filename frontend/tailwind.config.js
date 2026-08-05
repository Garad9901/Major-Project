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
      },
    },
  },
  plugins: [],
};
