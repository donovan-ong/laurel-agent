import { useEffect, useState } from "react";

// Deliberately generic: which tools get called isn't known until the reply lands, so nothing here overclaims.
// Chat replies take 10-70 seconds, so rotating the wording every 2.5s reads as work in progress, not stuck.
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
    <div className="lw-loading" role="status" aria-live="polite">
      <span className="lw-spinner" aria-hidden="true" />
      <span>{STATUSES[index]}</span>
    </div>
  );
}
