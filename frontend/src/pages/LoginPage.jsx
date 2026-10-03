import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../hooks/useAuth";
import LaurelLogo from "../components/LaurelLogo";
import styles from "./LoginPage.module.css";

export default function LoginPage() {
  const { loading, loggedIn, refresh } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // The app's one GET /api/me already covers "already logged in? skip the form."
  if (loading) return null;
  if (loggedIn) return <Navigate to="/" replace />;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.login(username, password);
      await refresh();
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.welcome}>
        <LaurelLogo size={32} />
        Laurel
        <span className={styles.badge}>Prototype</span>
      </h1>
      <div className={styles.card}>
        <h2 className={styles.title}>Welcome back</h2>
        <form onSubmit={handleSubmit}>
          <label className={styles.field}>
            Username
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className={styles.field}>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button className={styles.submit} type="submit" disabled={submitting}>
            Log in
          </button>
        </form>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
