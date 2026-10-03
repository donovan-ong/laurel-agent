import { ApiError } from "./api";

// A transport is { request(method, path, body), login(username, password), logout() }. It is the one place
// the two hosts differ, and the seam a real deployment would replace: today login is a demo username and
// password; behind RMIT's single sign-on the same interface would exchange the site's existing session for a
// chat token and only show the form when the student is signed out.

const TOKEN_KEY = "laurel.token";

function store(action, key, value) {
  // Storage can throw (private mode, blocked site data), and the widget must still work without it.
  try {
    if (action === "get") return sessionStorage.getItem(key);
    if (action === "set") sessionStorage.setItem(key, value);
    if (action === "remove") sessionStorage.removeItem(key);
  } catch {
    return null;
  }
  return null;
}

/** Plain fetch, for a host page that can reach the backend itself (the saved page is served by the backend).
 *  The token lives in sessionStorage, so it is gone when the browser session ends: every new session asks for
 *  a login again. */
export function fetchTransport({ apiBase = "" } = {}) {
  const base = apiBase.replace(/\/$/, "");

  async function call(method, path, body, withToken = true) {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    const token = withToken ? store("get", TOKEN_KEY) : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    try {
      res = await fetch(base + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    } catch {
      throw new ApiError("Could not reach the server.", null);
    }
    let data = null;
    try {
      data = await res.json();
    } catch {
      // no body, or not JSON
    }
    if (!res.ok) throw new ApiError((data && data.detail) || "Something went wrong.", res.status);
    return data;
  }

  return {
    request: (method, path, body) => call(method, path, body),
    async login(username, password) {
      const data = await call("POST", "/api/widget/login", { username, password }, false);
      store("set", TOKEN_KEY, data.token);
      return { username: data.username, student_number: data.student_number };
    },
    async logout() {
      try {
        await call("POST", "/api/widget/logout");
      } finally {
        store("remove", TOKEN_KEY);
      }
    },
    // "Laurel" in the header: open the full webapp in a new tab. If signed in, hand the token to
    // /api/session/adopt — a plain top-level navigation, so CORS never comes into it — which mints the
    // webapp's own cookie for the exact same session and lands on the chat page already signed in. Signed
    // out, it just opens the webapp's root, which shows its own login page.
    openWebapp() {
      const token = store("get", TOKEN_KEY);
      const url = token ? `${base}/api/session/adopt?token=${encodeURIComponent(token)}` : `${base}/`;
      window.open(url, "_blank", "noopener");
    },
  };
}

/** For the Chrome extension. Every call is a message to the extension's service worker, which holds the token
 *  (in chrome.storage.session, so it also ends with the browser session) and talks to the backend. The RMIT
 *  page never sees the token, and CORS, mixed content and private-network rules never come into it. */
export function extensionTransport() {
  const send = (message) =>
    new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError) reject(new ApiError("The Laurel extension is not responding.", null));
          else resolve(response);
        });
      } catch {
        reject(new ApiError("The Laurel extension is not responding.", null));
      }
    });

  async function call(message) {
    const response = await send(message);
    if (!response || !response.ok) throw new ApiError((response && response.error) || "Something went wrong.", response ? response.status : null);
    return response.data;
  }

  return {
    request: (method, path, body) => call({ type: "laurel:request", method, path, body }),
    login: (username, password) => call({ type: "laurel:login", username, password }),
    logout: () => call({ type: "laurel:logout" }),
    // The token never leaves the service worker for this either: the worker itself opens the tab (see
    // background.js), so the content script/page never sees it.
    openWebapp: () => call({ type: "laurel:openWebapp" }),
  };
}

/** Small UI preferences (panel open, trace toggle), kept in the page's own storage. Not secrets. */
export const prefs = {
  get: (key) => store("get", `laurel.${key}`),
  set: (key, value) => store("set", `laurel.${key}`, String(value)),
};
