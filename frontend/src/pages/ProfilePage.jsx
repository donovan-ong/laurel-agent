import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../hooks/useAuth";
import NavBar from "../components/NavBar";
import styles from "./ProfilePage.module.css";

// A near-mechanical port of the old plain-JS profile.js: same fields, same order, same found:false
// fallback. prior_qualification was never rendered there either — carrying that omission forward rather
// than silently adding a new field mid-migration. No agent call — GET /api/profile calls
// get_student_profile.fn(...) directly.
export default function ProfilePage() {
  const { logout } = useAuth();
  const [state, setState] = useState({ loading: true, data: null, error: null });

  // A 401 here means the session died server-side (a restart, or expiry) - self-heal to the login page the
  // same way ChatPage does, rather than showing "Profile unavailable" for a session that isn't coming back.
  useEffect(() => {
    let cancelled = false;
    api
      .profile()
      .then((data) => {
        if (!cancelled) setState({ loading: false, data, error: null });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setState({ loading: false, data: null, error: err.message || "Could not reach the server." });
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  return (
    <div>
      <NavBar />
      <div className={styles.content}>
        {state.loading ? (
          <p>Loading…</p>
        ) : state.error ? (
          <p>Profile unavailable: {state.error}</p>
        ) : !state.data.found ? (
          <p>Profile unavailable: {state.data.reason || "unknown reason"}</p>
        ) : (
          <ProfileContent data={state.data} />
        )}
      </div>
    </div>
  );
}

function ProfileContent({ data }) {
  const s = data.student;
  return (
    <>
      <h1 className={styles.name}>{s.name}</h1>
      <dl className={styles.fields}>
        <dt>Student number</dt>
        <dd>{s.student_number}</dd>
        <dt>Email</dt>
        <dd>{s.email}</dd>
        <dt>Program</dt>
        <dd>{s.program_code}</dd>
        <dt>Status</dt>
        <dd>{s.enrolment_status}</dd>
        <dt>Study load</dt>
        <dd>{s.study_load}</dd>
        <dt>Start term</dt>
        <dd>{s.start_term}</dd>
        <dt>Residency</dt>
        <dd>{s.residency}</dd>
        <dt>Fee type</dt>
        <dd>{s.fee_type}</dd>
        <dt>Account hold</dt>
        <dd>{s.account_hold ? <span className={styles.holdWarning}>{s.account_hold.message}</span> : "None"}</dd>
      </dl>
      <h2>Current enrolments</h2>
      {s.current_enrolments.length ? (
        <ul className={styles.enrolments}>
          {s.current_enrolments.map((e) => (
            <li key={`${e.course_id}-${e.term}`}>
              {e.title} ({e.course_id}), {e.term}
            </li>
          ))}
        </ul>
      ) : (
        <p>None</p>
      )}
      <p className={styles.sourceNote}>
        Source: {data.source.file}, {data.source.provenance}, snapshot {data.source.snapshot_date}
      </p>
    </>
  );
}
