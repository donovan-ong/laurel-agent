import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

// Mirrors the old requireLogin()'s behaviour: redirect to /login when not logged in. Renders nothing while
// the app's one GET /api/me is still in flight, to avoid a flash-redirect before that resolves.
export function ProtectedRoute({ children }) {
  const { loading, loggedIn } = useAuth();
  if (loading) return null;
  if (!loggedIn) return <Navigate to="/login" replace />;
  return children;
}
