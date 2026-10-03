import styles from "./WeekPanel.module.css";

const MAX_ROWS = 5;
const URGENCY_LABEL = {
  action: "Needs action",
  overdue: "Overdue",
  today: "Due today",
  soon: "Due soon",
  upcoming: "Coming up",
};

// The home screen's "Your week": what needs attention before the student has asked anything. Each row is a
// ready-made question, so one click starts the conversation about it.
export default function WeekPanel({ week, onAsk, disabled }) {
  if (!week || !week.found) return null;
  const rows = week.items.filter((i) => i.kind !== "plan").slice(0, MAX_ROWS);
  const plan = week.items.find((i) => i.kind === "plan");
  if (!rows.length && !plan) return null;

  return (
    <section className={styles.panel} aria-label="Your week">
      <header className={styles.header}>
        <h2 className={styles.title}>Your week</h2>
        {week.week_label && <span className={styles.label}>{week.week_label}</span>}
      </header>
      {rows.length > 0 && (
        <ul className={styles.list}>
          {rows.map((item) => (
            <li key={`${item.kind}-${item.title}`}>
              <button
                type="button"
                className={styles.row}
                onClick={() => onAsk(item.prompt)}
                disabled={disabled}
                title={item.prompt}
              >
                <span className={`${styles.dot} ${styles[item.urgency]}`} aria-label={URGENCY_LABEL[item.urgency]} />
                <span className={styles.text}>
                  <span className={styles.itemTitle}>{item.title}</span>
                  <span className={styles.detail}>{item.detail}</span>
                </span>
                <span className={styles.ask} aria-hidden="true">
                  Ask
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {plan && (
        <button type="button" className={styles.plan} onClick={() => onAsk(plan.prompt)} disabled={disabled}>
          {plan.title}
          <span className={styles.planDetail}>{plan.detail}</span>
        </button>
      )}
    </section>
  );
}
