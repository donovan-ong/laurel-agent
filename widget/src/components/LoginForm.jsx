import { useState } from "react";
import { ApiError } from "../api";
import { ChatIcon } from "../icons";

// The demo login. In a real deployment this is the seam where the site's single sign-on session would be
// picked up instead, and the form only shown when nobody is signed in (see docs/widget-integration.md).
export default function LoginForm({ onLogin, showDemoHint }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="lw-login" onSubmit={submit}>
      <span className="lw-login-mark">
        <ChatIcon size={26} />
      </span>
      <h2>Sign in to Laurel</h2>
      <p className="lw-dim">Your study assistant. Sign in to see your own record, enrolments and more.</p>
      <label>
        Username
        <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
      </label>
      <button className="lw-primary" type="submit" disabled={submitting}>
        {submitting ? "Signing in…" : "Sign in"}
      </button>
      {error && (
        <p className="lw-form-error" role="alert">
          {error}
        </p>
      )}
      {showDemoHint && <p className="lw-dim lw-hint">Prototype: use a demo account, for example demo4 with password demo4.</p>}
    </form>
  );
}
