// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useState } from "react";

import { changePassword } from "../api";

/**
 * Forced password change for a newly provisioned account.
 *
 * The server refuses /api/ask/ while must_change_password is set, so without
 * this screen an operator-created user could log in and then be unable to do
 * anything, with no way to fix it themselves. There is deliberately no "skip"
 * — the flag is the whole point, and the only escape is logging out.
 *
 * Password RULES ARE NOT DUPLICATED HERE. The hint text below describes them,
 * but validation is the server's: Django's AUTH_PASSWORD_VALIDATORS are the
 * single source of truth, and re-implementing them in JavaScript would let the
 * two drift and give users a client-side "OK" the server then rejects.
 */
function ChangePassword({ user, onChanged, onLogout }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    // The only check done client-side: comparing two fields the server never
    // sees as a pair. Everything about password STRENGTH is the server's call.
    if (next !== confirm) {
      setError("The two new passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const updated = await changePassword(current, next);
      onChanged(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const inputClass =
    "mb-4 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 " +
    "text-slate-100 outline-none focus:border-emerald-500";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 px-4 text-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-800 p-8 shadow-lg"
      >
        <h1 className="mb-1 text-2xl font-bold">Choose a new password</h1>
        <p className="mb-6 text-sm text-slate-400">
          Signed in as <span className="font-medium text-slate-300">{user.username}</span>. You
          must replace the password you were given before you can use the assistant.
        </p>

        <label className="mb-1 block text-sm font-medium text-slate-300">
          Current password
        </label>
        <input
          type="password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoFocus
          required
          autoComplete="current-password"
          className={inputClass}
        />

        <label className="mb-1 block text-sm font-medium text-slate-300">New password</label>
        <input
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          required
          autoComplete="new-password"
          className={inputClass}
        />

        <label className="mb-1 block text-sm font-medium text-slate-300">
          Confirm new password
        </label>
        <input
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
          autoComplete="new-password"
          className={inputClass}
        />

        <ul className="mb-4 space-y-1 text-xs text-slate-500">
          <li>• At least 12 characters</li>
          <li>• Not a commonly used password</li>
          <li>• Not similar to your username</li>
          <li>• Not entirely numbers</li>
        </ul>

        {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-emerald-600 py-2 font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Saving…" : "Set new password"}
        </button>

        <button
          type="button"
          onClick={onLogout}
          className="mt-3 w-full rounded-lg border border-slate-600 py-2 text-sm text-slate-400 transition hover:bg-slate-700"
        >
          Sign out instead
        </button>
      </form>
    </div>
  );
}

export default ChangePassword;
