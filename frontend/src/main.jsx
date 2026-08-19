// Copyright (c) 2026 Yash Garad. All rights reserved.

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App.jsx";
import "./index.css";
import { INSTITUTE, loadInstitution } from "./institute";

// THE IDENTITY IS FETCHED BEFORE THE FIRST RENDER, ON PURPOSE.
//
// The alternative — render immediately, then update when the config arrives —
// shows every user an unbranded sign-in screen that visibly rewrites itself a
// moment later. On a page whose entire job is to look like it belongs to the
// institution, that flash is worse than the ~20ms the fetch costs from the same
// origin.
//
// loadInstitution() never throws: if the backend is unreachable the app renders
// with neutral defaults rather than not at all. A user who cannot sign in
// because a branding endpoint was down would be an absurd failure mode.
loadInstitution().then(() => {
  if (INSTITUTE.short_name || INSTITUTE.name) {
    document.title = INSTITUTE.name;
  }
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
