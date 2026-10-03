import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { splitWeek } from "../week";
import WeekList from "./WeekList";
import styles from "./WeekMenu.module.css";

// "Your week" in the nav bar once a conversation has started: the full list, one click from anywhere in the
// chat. Refreshed each time it opens (no model call); closes on a choice, an outside click or Escape.
export default function WeekMenu({ week, onAsk, disabled }) {
  const [open, setOpen] = useState(false);
  const [latest, setLatest] = useState(week);
  const rootRef = useRef(null);
  const shown = latest || week;
  const { items, plan } = splitWeek(shown);

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (e) => rootRef.current && !rootRef.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!items.length && !plan) return null;

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      api
        .week()
        .then((d) => d.found && setLatest(d))
        .catch(() => {});
    }
  }

  function ask(prompt) {
    setOpen(false);
    onAsk(prompt);
  }

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        type="button"
        className={`${styles.button} ${open ? styles.on : ""}`}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={`Your week, ${items.length} items`}
        onClick={toggle}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <line x1="3" y1="10" x2="21" y2="10" />
          <line x1="8" y1="3" x2="8" y2="7" />
          <line x1="16" y1="3" x2="16" y2="7" />
        </svg>
        <span className={styles.text}>Your week</span>
        <span className={styles.count} aria-hidden="true">
          {items.length}
        </span>
      </button>
      {open && (
        <div className={styles.menu} role="region" aria-label="Your week">
          <header className={styles.header}>
            <strong>Your week</strong>
            {shown.week_label && <span>{shown.week_label}</span>}
          </header>
          <WeekList items={items} plan={plan} onAsk={ask} disabled={disabled} />
        </div>
      )}
    </div>
  );
}
