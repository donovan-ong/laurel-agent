// The widget's whole view of the backend. Everything goes through a transport (see transport.js), so the same
// code runs on the saved-page host (plain fetch) and inside the extension (messages to its service worker).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export function makeApi(transport) {
  return {
    me: () => transport.request("GET", "/api/me"),
    login: (username, password) => transport.login(username, password),
    logout: () => transport.logout(),
    chat: (message) => transport.request("POST", "/api/chat", { message }),
    history: () => transport.request("GET", "/api/chat/history"),
    profile: () => transport.request("GET", "/api/profile"),
    openWebapp: () => transport.openWebapp(),
  };
}
