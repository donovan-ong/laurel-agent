import { useEffect, useState } from "react";
import Spinner from "./Spinner";
import styles from "./LoadingIndicator.module.css";

// Deliberately generic — which tools get called isn't known until the reply lands, so nothing here should
// overclaim what the agent is doing. At the real 10-45s latency, cycling every 2.5s is 4-18 changes per
// request: reads as active work, not stuck.
const STATUSES = [
  "Thinking…",
  "Working on it…",
  "Checking the details…",
  "Parsing your request…",
  "Calculating…",
  "Cross-referencing…",
  "Putting it together…",
  "Almost there…",
];

export default function LoadingIndicator() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setIndex((i) => (i + 1) % STATUSES.length), 2500);
    return () => clearInterval(id);
  }, []);

  return (
    <div className={styles.wrap} role="status" aria-live="polite">
      <Spinner size={18} />
      <span>{STATUSES[index]}</span>
    </div>
  );
}
