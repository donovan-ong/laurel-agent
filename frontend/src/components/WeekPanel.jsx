import { splitWeek } from "../week";
import WeekList from "./WeekList";
import styles from "./WeekPanel.module.css";

const MAX_ROWS = 5;

// The home screen's "Your week": what needs attention before the student has asked anything. Each row is a
// ready-made question, so one click starts the conversation about it.
export default function WeekPanel({ week, onAsk, disabled }) {
  const { items, plan } = splitWeek(week);
  if (!items.length && !plan) return null;

  return (
    <section className={styles.panel} aria-label="Your week">
      <header className={styles.header}>
        <h2 className={styles.title}>Your week</h2>
        {week.week_label && <span className={styles.label}>{week.week_label}</span>}
      </header>
      <WeekList items={items.slice(0, MAX_ROWS)} plan={plan} onAsk={onAsk} disabled={disabled} />
    </section>
  );
}
