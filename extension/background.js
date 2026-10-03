// The extension's service worker: the only thing that talks to the backend.
//
// The RMIT page's content script sends messages here. This file adds the session token (kept in
// chrome.storage.session, which the page cannot read and which is cleared when the browser session ends, so
// every new session asks for a login again), calls the backend, and sends the answer back. Going through the
// worker means the page's CORS, mixed-content and private-network rules never apply to these calls.

const DEFAULT_API_BASE = "http://127.0.0.1:8100";
const TOKEN_KEY = "token";

async function apiBase() {
  // Override from the service worker console if the backend runs elsewhere:
  //   chrome.storage.local.set({ apiBase: "http://127.0.0.1:9000" })
  const { apiBase: base } = await chrome.storage.local.get("apiBase");
  return (base || DEFAULT_API_BASE).replace(/\/$/, "");
}

async function getToken() {
  const stored = await chrome.storage.session.get(TOKEN_KEY);
  return stored[TOKEN_KEY] || null;
}

async function call(method, path, body, withToken = true) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  const token = withToken ? await getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch((await apiBase()) + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  let data = null;
  try {
    data = await res.json();
  } catch {
    // no body, or not JSON
  }
  return { ok: res.ok, status: res.status, data, error: res.ok ? undefined : (data && data.detail) || "Something went wrong." };
}

// A chat reply takes 10 to 70 seconds, and Chrome ends an extension worker whose fetch takes more than 30 s.
// Calling any extension API resets that idle timer, so ping one while a request is in flight.
function keepAlive() {
  const id = setInterval(() => chrome.runtime.getPlatformInfo(), 20_000);
  return () => clearInterval(id);
}

async function handle(message) {
  switch (message && message.type) {
    case "laurel:request": {
      const { method, path, body } = message;
      // Only the backend's own API, only reads and posts: the page's script can never turn this into a general proxy.
      if (!["GET", "POST"].includes(method) || typeof path !== "string" || !path.startsWith("/api/")) {
        return { ok: false, status: 400, error: "Request not allowed." };
      }
      return call(method, path, body);
    }
    case "laurel:login": {
      const result = await call("POST", "/api/widget/login", { username: message.username, password: message.password }, false);
      if (!result.ok) return result;
      await chrome.storage.session.set({ [TOKEN_KEY]: result.data.token });
      // The token stays here; the page only learns who signed in.
      return { ok: true, status: 200, data: { username: result.data.username, student_number: result.data.student_number } };
    }
    case "laurel:logout": {
      try {
        await call("POST", "/api/widget/logout");
      } finally {
        await chrome.storage.session.remove(TOKEN_KEY);
      }
      return { ok: true, status: 200, data: { status: "logged_out" } };
    }
    case "laurel:openWebapp": {
      // Built and opened entirely here, so the token never reaches the content script or the RMIT page —
      // same invariant as login/logout above.
      const token = await getToken();
      const url = token ? `${await apiBase()}/api/session/adopt?token=${encodeURIComponent(token)}` : `${await apiBase()}/`;
      await chrome.tabs.create({ url });
      return { ok: true, status: 200, data: {} };
    }
    default:
      return { ok: false, status: 400, error: "Unknown message." };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false; // only this extension's own content script
  const stopKeepAlive = keepAlive();
  handle(message)
    .catch(() => ({ ok: false, status: null, error: "Could not reach the server." }))
    .then(sendResponse)
    .finally(stopKeepAlive);
  return true; // the response is sent asynchronously
});
