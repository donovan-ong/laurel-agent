import { createContext, useCallback, useEffect, useState } from "react";
import { api } from "../api";

export const AuthContext = createContext(null);

const initial = { loading: true, loggedIn: false, username: null, studentNumber: null };

// One GET /api/me for the whole app's lifetime (plus whenever refresh() is called, e.g. after login) —
// NavBar and ProtectedRoute both read from this instead of each page checking for itself.
export function AuthProvider({ children }) {
  const [state, setState] = useState(initial);

  const refresh = useCallback(async () => {
    const data = await api.me();
    setState({
      loading: false,
      loggedIn: data.logged_in,
      username: data.username ?? null,
      studentNumber: data.student_number ?? null,
    });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Sessions are in-memory only and never survive a backend restart (see webapp/__main__.py's own docstring).
  // Killing the backend without clicking Log out first, then starting it again, leaves an already-open tab
  // showing a conversation that looks live but no longer is - the 401-on-send handling in ChatPage/ProfilePage
  // catches that once you try to use it, but switching back to a tab you'd left on the chat page, after the
  // backend was down and back up while you weren't looking at it, should notice right away rather than
  // waiting for the next failed request. Re-checking on focus/visibility covers exactly that moment.
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") refresh();
    }
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.logout();
    setState({ ...initial, loading: false });
  }, []);

  return <AuthContext.Provider value={{ ...state, refresh, logout }}>{children}</AuthContext.Provider>;
}
