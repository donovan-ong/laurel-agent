// The rows of "Your week": every item, then the plan suggestion. Each row sends its ready-made question.
// Shared by the start screen's WeekBox and the header's dropdown.
export default function WeekItems({ week, onAsk }) {
  const items = week.items.filter((i) => i.kind !== "plan");
  const plan = week.items.find((i) => i.kind === "plan");
  return (
    <>
      {items.map((item) => (
        <button key={`${item.kind}-${item.title}`} type="button" className="lw-week-item" onClick={() => onAsk(item.prompt)}>
          <span className={`lw-week-dot lw-week-${item.urgency}`} aria-hidden="true" />
          <span>
            <strong>{item.title}</strong>
            <span className="lw-dim">{item.detail}</span>
          </span>
        </button>
      ))}
      {plan && (
        <button type="button" className="lw-week-item lw-week-plan" onClick={() => onAsk(plan.prompt)}>
          <span>
            <strong>{plan.title}</strong>
            <span className="lw-dim">{plan.detail}</span>
          </span>
        </button>
      )}
    </>
  );
}

/** The number of items, not counting the plan suggestion: the count shown on the bar and the header button. */
export function weekCount(week) {
  return week && week.found ? week.items.filter((i) => i.kind !== "plan").length : 0;
}
