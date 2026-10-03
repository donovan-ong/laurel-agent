import { useState } from "react";
import styles from "./MessageActions.module.css";

function CopyIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function ThumbsUpIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 10v12" />
      <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
    </svg>
  );
}

function ThumbsDownIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 14V2" />
      <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  );
}

// The action row under each assistant reply: copy, thumbs up/down (purely visual, no API call — see the
// plan), and retry (re-sends the preceding user message; see ChatPage.handleRetry for what that actually
// does to the conversation). Bare icons, no circular border/background, matching the pattern already
// established for the send button and the trace toggle.
export default function MessageActions({ text, onRetry, retryDisabled }) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null); // "up" | "down" | null

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard API unavailable (e.g. insecure context) — nothing to usefully fall back to */
    }
  }

  function toggleFeedback(value) {
    setFeedback((prev) => (prev === value ? null : value));
  }

  return (
    <div className={styles.row}>
      <button type="button" className={styles.iconBtn} title={copied ? "Copied" : "Copy"} aria-label="Copy response" onClick={handleCopy}>
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
      <button
        type="button"
        className={`${styles.iconBtn} ${feedback === "up" ? styles.active : ""}`}
        title="Good response"
        aria-label="Good response"
        aria-pressed={feedback === "up"}
        onClick={() => toggleFeedback("up")}
      >
        <ThumbsUpIcon />
      </button>
      <button
        type="button"
        className={`${styles.iconBtn} ${feedback === "down" ? styles.active : ""}`}
        title="Bad response"
        aria-label="Bad response"
        aria-pressed={feedback === "down"}
        onClick={() => toggleFeedback("down")}
      >
        <ThumbsDownIcon />
      </button>
      {onRetry && (
        <button type="button" className={styles.iconBtn} title="Retry" aria-label="Retry" onClick={onRetry} disabled={retryDisabled}>
          <RetryIcon />
        </button>
      )}
    </div>
  );
}
