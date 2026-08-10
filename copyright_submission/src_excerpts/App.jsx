// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useEffect, useState } from "react";

import ChangePassword from "./components/ChangePassword";
import Chat from "./components/Chat";
import Login from "./components/Login";
import { ensureCsrf, getMe, logout } from "./api";

function App() {
  // The whole user object, not just the name: routing now depends on
  // must_change_password as well as on being signed in.
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On load: make sure we have a CSRF cookie, then ask the server whether we
  // already have a valid session (rather than trusting any client-side state).
  useEffect(() => {
    (async () => {
      await ensureCsrf();
      const me = await getMe();
      setUser(me ?? null);
      setLoading(false);
    })();
  }, []);

  // Paint the saved theme as soon as we know who the user is, so the login and
  // change-password screens are already in the right mode rather than flashing
  // the wrong one.
  //
  // SIGNED OUT, the profile does not exist yet, so the sign-in screen's own
  // preference is honoured instead (Login.jsx keeps it in localStorage — the
  // only store available before there is an account). This used to force dark
  // for every signed-out visitor, which meant choosing light on the sign-in
  // screen was undone on the next page load.
  //
  // SIGNED IN, the profile wins unconditionally. That ordering is the point:
  // the account's preference follows the person between machines, and the local
  // value is only ever a first-paint fallback.
  useEffect(() => {
    let dark;
    if (user) {
      dark = user.theme !== "light";
    } else {
      let saved = null;
      try {
        saved = localStorage.getItem("theme");
      } catch { /* private browsing can throw */ }
      dark = saved ? saved === "dark" : true;
    }
    document.documentElement.classList.toggle("dark", dark);
  }, [user]);

  async function handleLogout() {
    await logout();
    setUser(null);
  }

  function handleSessionExpired() {
    // Session was rejected mid-use — bounce back to login.
    setUser(null);
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white text-neutral-400 dark:bg-[#0f0f10] dark:text-neutral-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Login onLoggedIn={setUser} />;
  }

  // Checked BEFORE rendering Chat. The server enforces this too — /api/ask/
  // returns 403 while the flag is set — but showing a chat box that rejects
  // every question would be a confusing way to communicate that.
  if (user.must_change_password) {
    return (
      <ChangePassword user={user} onChanged={setUser} onLogout={handleLogout} />
    );
  }

  return (
    <Chat
      username={user.username}
      initialTheme={user.theme}
      onLogout={handleLogout}
      onSessionExpired={handleSessionExpired}
    />
  );
}

export default App;
