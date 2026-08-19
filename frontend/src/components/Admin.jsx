// Copyright (c) 2026 Yash Garad. All rights reserved.

// The settings an operator changes while the system is running.
//
// SCOPE IS NARROW ON PURPOSE. This is not a general admin panel; four things
// are here because they are the four an operator touches during normal running
// and each previously required either editing JSON on the server and
// restarting, or an SSH session and a management command.
//
// The server is the authority on access — every endpoint is staff-only and
// returns 403 otherwise. This component only decides whether to offer the link,
// which is a usability choice, not a security one.

import { useEffect, useState } from "react";

import {
  getAdminUsers,
  getAllowlist,
  getIdentity,
  getRuntimeSettings,
  saveAllowlist,
  saveIdentity,
  setUserActive,
} from "../api";

const TABS = [
  ["identity", "Identity"],
  ["sources", "Web sources"],
  ["users", "Users"],
  ["settings", "Settings"],
];

function Banner({ tone, children }) {
  if (!children) return null;
  const styles =
    tone === "error"
      ? "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
      : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200";
  return (
    <div className={`mb-4 whitespace-pre-wrap rounded-md border px-3 py-2 text-sm ${styles}`}>
      {children}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="mb-4 block">
      <span className="mb-1 block text-sm font-medium text-neutral-800 dark:text-neutral-200">
        {label}
      </span>
      {children}
      {hint && (
        <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">{hint}</span>
      )}
    </label>
  );
}

const inputClass =
  "w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm " +
  "text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100";

// ---------------------------------------------------------------------------
function Identity({ notify }) {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getIdentity().then(setData).catch((e) => notify("error", e.message));
  }, [notify]);

  if (!data) return <p className="text-sm text-neutral-500">Loading…</p>;

  const inst = data.institution || {};
  const set = (key) => (event) =>
    setData({ ...data, institution: { ...inst, [key]: event.target.value } });

  async function save() {
    setSaving(true);
    try {
      await saveIdentity(data.institution, data.theme);
      notify("ok", "Saved. Reload the page to see the new identity on screen.");
    } catch (error) {
      notify("error", error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl">
      <Field label="Institution name" hint="Appears on the sign-in screen and in the browser tab.">
        <input className={inputClass} value={inst.name || ""} onChange={set("name")} />
      </Field>
      <Field label="Descriptor" hint="One factual line under the name. Not a slogan.">
        <input className={inputClass} value={inst.descriptor || ""} onChange={set("descriptor")} />
      </Field>
      <Field label="Support email" hint="Shown to users when something fails and they need a human. An unreachable address here is worse than none.">
        <input className={inputClass} value={inst.contact_email || ""} onChange={set("contact_email")} />
      </Field>
      <Field label="Monogram initials" hint="Leave blank to derive them from the name — right for most names.">
        <input className={inputClass} value={inst.initials || ""} onChange={set("initials")} />
      </Field>
      <button
        onClick={save}
        disabled={saving}
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save identity"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
function WebSources({ notify }) {
  const [urls, setUrls] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getAllowlist()
      .then((d) => setUrls(d.urls || []))
      .catch((e) => notify("error", e.message));
  }, [notify]);

  if (!urls) return <p className="text-sm text-neutral-500">Loading…</p>;

  const patch = (index, key, value) =>
    setUrls(urls.map((u, i) => (i === index ? { ...u, [key]: value } : u)));

  async function save(next) {
    setSaving(true);
    try {
      const saved = await saveAllowlist(next ?? urls);
      setUrls(saved.urls);
      notify("ok", "Saved. This takes effect immediately — no restart needed.");
    } catch (error) {
      // The server reports every problem at once, so show it verbatim rather
      // than collapsing it to "invalid".
      notify("error", error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <p className="mb-4 max-w-2xl text-sm text-neutral-600 dark:text-neutral-400">
        The complete list of pages this system may fetch. Nothing else is reachable.
        The assistant never chooses a web address — a page is selected by matching a
        question against the keywords below. Adding an entry here is the only way this
        system can reach it.
      </p>

      {urls.length === 0 && (
        <p className="mb-4 rounded-md border border-neutral-200 px-3 py-2 text-sm text-neutral-500 dark:border-neutral-800">
          No sources configured. Questions about term dates and notices will be
          answered from the database only.
        </p>
      )}

      {urls.map((entry, index) => (
        <div
          key={index}
          className="mb-3 rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
        >
          <div className="mb-2 flex items-center gap-3">
            <input
              className={inputClass + " flex-1"}
              value={entry.label || ""}
              placeholder="Label shown to users, e.g. Academic Calendar"
              onChange={(e) => patch(index, "label", e.target.value)}
            />
            <label className="flex shrink-0 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(entry.enabled)}
                onChange={(e) => patch(index, "enabled", e.target.checked)}
              />
              Enabled
            </label>
          </div>
          <input
            className={inputClass + " mb-2 font-mono text-xs"}
            value={entry.url || ""}
            placeholder="https://www.your-college.edu/academic-calendar"
            onChange={(e) => patch(index, "url", e.target.value)}
          />
          <input
            className={inputClass + " text-xs"}
            value={(entry.topics || []).join(", ")}
            placeholder="term dates, holidays, semester dates"
            onChange={(e) =>
              patch(index, "topics", e.target.value.split(",").map((t) => t.trim()).filter(Boolean))
            }
          />
          <div className="mt-2 flex items-center justify-between">
            <span className="font-mono text-xs text-neutral-400">{entry.id}</span>
            <button
              className="text-xs text-red-600 hover:underline dark:text-red-400"
              onClick={() => save(urls.filter((_, i) => i !== index))}
            >
              Remove
            </button>
          </div>
        </div>
      ))}

      <div className="mt-4 flex gap-3">
        <button
          onClick={() =>
            setUrls([
              ...urls,
              { id: `source-${Date.now()}`, url: "", label: "", topics: [], enabled: false },
            ])
          }
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm dark:border-neutral-700"
        >
          Add a page
        </button>
        <button
          onClick={() => save()}
          disabled={saving}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save sources"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
function Users({ notify }) {
  const [users, setUsers] = useState(null);

  const reload = () =>
    getAdminUsers()
      .then((d) => setUsers(d.users || []))
      .catch((e) => notify("error", e.message));

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!users) return <p className="text-sm text-neutral-500">Loading…</p>;

  async function toggle(user) {
    try {
      await setUserActive(user.username, !user.is_active);
      notify(
        "ok",
        user.is_active
          ? `${user.username} is disabled and their sessions have been ended.`
          : `${user.username} can sign in again.`,
      );
      reload();
    } catch (error) {
      notify("error", error.message);
    }
  }

  return (
    <div>
      <p className="mb-4 max-w-2xl text-sm text-neutral-600 dark:text-neutral-400">
        Disabling an account ends its sessions immediately. Accounts are never
        deleted here — deletion would break the audit log's record of who asked what.
        To create an account:{" "}
        <code className="font-mono text-xs">
          docker compose exec backend python manage.py create_user
        </code>{" "}
        — it generates the password into a private file rather than showing it on
        screen.
      </p>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-neutral-200 text-xs uppercase text-neutral-500 dark:border-neutral-800">
          <tr>
            <th className="py-2">Username</th>
            <th>Name</th>
            <th>Role</th>
            <th>Last signed in</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.username} className="border-b border-neutral-100 dark:border-neutral-900">
              <td className="py-2 font-mono text-xs">{user.username}</td>
              <td>{user.full_name || "—"}</td>
              <td>{user.is_staff ? "Staff" : "Student"}</td>
              <td className="text-xs text-neutral-500">
                {user.last_login ? new Date(user.last_login).toLocaleDateString() : "never"}
              </td>
              <td className="py-2 text-right">
                <button
                  onClick={() => toggle(user)}
                  className={
                    "text-xs hover:underline " +
                    (user.is_active
                      ? "text-red-600 dark:text-red-400"
                      : "text-emerald-600 dark:text-emerald-400")
                  }
                >
                  {user.is_active ? "Disable" : "Enable"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
function RuntimeSettings({ notify }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    getRuntimeSettings().then(setData).catch((e) => notify("error", e.message));
  }, [notify]);

  if (!data) return <p className="text-sm text-neutral-500">Loading…</p>;

  return (
    <div>
      <div className="mb-5 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <strong>Read only.</strong> {data.why_read_only}
        <div className="mt-2 font-mono text-xs">{data.change_by}</div>
      </div>

      {data.groups.map((group) => (
        <div key={group.title} className="mb-6">
          <h3 className="mb-1 text-sm font-semibold text-neutral-800 dark:text-neutral-200">
            {group.title}
          </h3>
          {group.note && (
            <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">{group.note}</p>
          )}
          <table className="w-full text-left text-sm">
            <tbody>
              {group.settings.map((setting) => (
                <tr
                  key={setting.key}
                  className="border-b border-neutral-100 align-top dark:border-neutral-900"
                >
                  <td className="w-64 py-2 font-mono text-xs">{setting.key}</td>
                  <td className="w-48 py-2 font-mono text-xs text-accent">{setting.value}</td>
                  <td className="py-2 text-xs text-neutral-500 dark:text-neutral-400">
                    {setting.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
export default function Admin({ onClose }) {
  const [tab, setTab] = useState("identity");
  const [banner, setBanner] = useState(null);

  // Cleared on tab change so a success message from one screen is not still
  // sitting above another.
  const notify = (tone, message) => setBanner({ tone, message });

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          Administration
        </h1>
        <button
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700"
        >
          Back to the assistant
        </button>
      </div>

      <div className="mb-6 flex gap-1 border-b border-neutral-200 dark:border-neutral-800">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => {
              setTab(key);
              setBanner(null);
            }}
            className={
              "-mb-px border-b-2 px-4 py-2 text-sm " +
              (tab === key
                ? "border-accent font-medium text-accent"
                : "border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200")
            }
          >
            {label}
          </button>
        ))}
      </div>

      <Banner tone={banner?.tone}>{banner?.message}</Banner>

      {tab === "identity" && <Identity notify={notify} />}
      {tab === "sources" && <WebSources notify={notify} />}
      {tab === "users" && <Users notify={notify} />}
      {tab === "settings" && <RuntimeSettings notify={notify} />}
    </div>
  );
}
