import styles from "./OptionsRow.module.css";

function TraceIcon({ size = 14 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="8 6 3 12 8 18" />
      <polyline points="16 6 21 12 16 18" />
    </svg>
  );
}

// The actual llm: value from agents/study_planner.yaml, not a Claude model name — this agent runs on
// watsonx Orchestrate's own model routing, not Claude, so the label says that rather than borrowing a
// name from the styling reference.
const MODEL_NAME = "watsonx Orchestrate";
const MODEL_VARIANT = "Frontier";

// The row under the chat input: a trace-toggle icon on the left, a disclaimer centred on the chat box
// (matching claude.ai's own one), and the model in use on the right. title gives the icon a native hover
// tooltip — no extra tooltip library needed.
export default function OptionsRow({ traceVisible, onToggleTrace }) {
  const label = traceVisible ? "Hide the tool-call trace" : "Show the tool-call trace";
  return (
    <div className={styles.row} role="toolbar" aria-label="Chat options">
      <button
        type="button"
        className={`${styles.iconBtn} ${traceVisible ? styles.iconBtnActive : ""}`}
        aria-pressed={traceVisible}
        aria-label={label}
        title={label}
        onClick={onToggleTrace}
      >
        <TraceIcon />
      </button>
      <p className={styles.disclaimer}>Laurel is AI and can make mistakes.</p>
      <span className={styles.model}>
        <span className={styles.modelName}>{MODEL_NAME}</span> · {MODEL_VARIANT}
      </span>
    </div>
  );
}
