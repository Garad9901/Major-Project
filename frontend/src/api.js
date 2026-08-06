// Copyright (c) 2026 Yash Garad. All rights reserved.

// Session-cookie auth: the browser holds an httpOnly session cookie (not
// readable by JS), and we send Django's CSRF token from the csrftoken cookie
// as the X-CSRFToken header on every unsafe (POST) request. Nothing sensitive
// is kept in localStorage.

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

// Ask the server to set the csrftoken cookie. Call once before the first POST.
export async function ensureCsrf() {
  await fetch("/api/auth/csrf/", { credentials: "include" }).catch(() => {});
}

function csrfHeaders() {
  const token = getCookie("csrftoken");
  return token ? { "X-CSRFToken": token } : {};
}

export async function login(username, password) {
  await ensureCsrf();
  const res = await fetch("/api/auth/login/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Login failed (${res.status})`);
  }
  return data; // { username, role, is_staff, must_change_password }
}

export async function logout() {
  await fetch("/api/auth/logout/", {
    method: "POST",
    credentials: "include",
    headers: { ...csrfHeaders() },
  }).catch(() => {});
}

// Returns the full user object if a valid session exists, or null otherwise.
// { username, role, is_staff, must_change_password }
export async function getMe() {
  const res = await fetch("/api/auth/me/", { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}

// Change the signed-in user's password. Also clears the server-side
// must_change_password flag, which is what unlocks /api/ask/ for a newly
// provisioned account.
export async function changePassword(currentPassword, newPassword) {
  await ensureCsrf();
  const res = await fetch("/api/auth/change-password/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // The server returns the full validator message (length, common-password,
    // similarity, numeric) — surface it verbatim so the user knows what to fix.
    throw new Error(data.error || `Could not change password (${res.status})`);
  }
  return data;
}

// Persist the UI theme on the user's PROFILE, server-side.
//
// Not localStorage: that is per-browser and per-device, so the same person on a
// lab machine, a laptop and a phone would get three different themes, and
// clearing site data would silently reset it. On the profile it follows the
// account.
export async function saveTheme(theme) {
  const res = await fetch("/api/auth/preferences/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: JSON.stringify({ theme }),
  });
  if (!res.ok) throw new Error(`Could not save theme (${res.status})`);
  return res.json();
}

// The signed-in user's conversations, most recently active first.
export async function listConversations() {
  const res = await fetch("/api/conversations/", { credentials: "include" });
  if (!res.ok) return [];
  return res.json();
}

// One conversation with its full message history.
export async function getConversation(id) {
  const res = await fetch(`/api/conversations/${id}/`, { credentials: "include" });
  if (!res.ok) throw new Error(`Could not open that conversation (${res.status})`);
  return res.json();
}

export async function deleteConversation(id) {
  const res = await fetch(`/api/conversations/${id}/`, {
    method: "DELETE",
    credentials: "include",
    headers: { ...csrfHeaders() },
  });
  if (!res.ok && res.status !== 204) throw new Error(`Could not delete (${res.status})`);
}

/**
 * POST a question to /api/ask/ and stream the SSE response. Callbacks:
 *   onConversation({id,title}), onStage({stage,route}), onMeta(meta), onToken(text),
 *   onDone(final), onError(msg).
 *
 * onStage fires as soon as each pipeline step completes, well before the first
 * answer token exists. On CPU inference that gap is tens of seconds, so it is
 * the difference between a visibly working assistant and an apparently frozen one.
 *
 * `conversationId` continues an existing thread; omit it to start a new one, in
 * which case onConversation fires with the id the server just created.
 * Returns a promise that resolves when the stream ends.
 */
export async function askStream(question, { conversationId, onConversation, onStage, onMeta, onToken, onDone, onError }) {
  const res = await fetch("/api/ask/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: JSON.stringify(
      conversationId ? { question, conversation_id: conversationId } : { question }
    ),
  });

  if (res.status === 401 || res.status === 403) {
    onError?.("Your session is not authorized. Please log in again.");
    return { unauthorized: true };
  }
  if (res.status === 429) {
    onError?.("You're sending questions too quickly. Please wait a moment and try again.");
    return { throttled: true };
  }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    onError?.(data.error || `Request failed (${res.status})`);
    return {};
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // SSE frames are separated by a blank line; parse them as they complete.
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      handleFrame(frame, { onConversation, onStage, onMeta, onToken, onDone, onError });
    }
  }
  return {};
}

function handleFrame(frame, { onConversation, onStage, onMeta, onToken, onDone, onError }) {
  let event = "message";
  let dataLine = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
  }
  if (!dataLine) return;

  let payload;
  try {
    payload = JSON.parse(dataLine);
  } catch {
    return;
  }

  if (event === "conversation") onConversation?.(payload);
  else if (event === "stage") onStage?.(payload);
  else if (event === "meta") onMeta?.(payload);
  else if (event === "token") onToken?.(payload.text || "");
  else if (event === "done") onDone?.(payload.answer || "");
  else if (event === "error") onError?.(payload.error || "Unknown error");
}
