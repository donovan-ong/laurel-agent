import styles from "./WeekPanel.module.css";

const URGENCY_LABEL = {
  action: "Needs action",
  overdue: "Overdue",
  today: "Due today",
  soon: "Due soon",
  upcoming: "Later",
};

// The rows of "Coming up" and the plan button after them. Each row is a ready-made question, so one click
// asks about it. Shared by the home screen's panel and the nav bar's menu.
export default function WeekList({ items, plan, onAsk, disabled }) {
  return (
    <>
      {items.length > 0 && (
        <ul className={styles.list}>
          {items.map((item) => (
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
    </>
  );
}
