// Every fetch("/api/...") call, in one place. Mirrors webapp/server.py's contract exactly — see the
// route table in that file's docstring-equivalent (the plan doc) for the shape of each response.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Could not reach the server.", null);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    // no body, or not JSON — leave data null
  }
  if (!res.ok) {
    throw new ApiError((data && data.detail) || "Something went wrong.", res.status);
  }
  return data;
}

export const api = {
  me: () => request("GET", "/api/me"),
  login: (username, password) => request("POST", "/api/login", { username, password }),
  logout: () => request("POST", "/api/logout"),
  chat: (message) => request("POST", "/api/chat", { message }),
  chatHistory: () => request("GET", "/api/chat/history"),
  profile: () => request("GET", "/api/profile"),
  week: () => request("GET", "/api/week"),
};
