import { useState } from "react";
import { CheckIcon, CopyIcon, RetryIcon, ThumbsDownIcon, ThumbsUpIcon } from "../icons";

// Copy, thumbs up/down (purely visual, mutually exclusive, click again to clear) and retry, under each reply.
export default function MessageActions({ text, onRetry, retryDisabled }) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable on this page: nothing sensible to fall back to
    }
  }

  const toggle = (value) => setFeedback((prev) => (prev === value ? null : value));

  return (
    <div className="lw-actions">
      <button type="button" className="lw-icon-btn" title={copied ? "Copied" : "Copy"} aria-label="Copy response" onClick={copy}>
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
      <button
        type="button"
        className={`lw-icon-btn${feedback === "up" ? " lw-active" : ""}`}
        title="Good response"
        aria-label="Good response"
        aria-pressed={feedback === "up"}
        onClick={() => toggle("up")}
      >
        <ThumbsUpIcon />
      </button>
      <button
        type="button"
        className={`lw-icon-btn${feedback === "down" ? " lw-active" : ""}`}
        title="Bad response"
        aria-label="Bad response"
        aria-pressed={feedback === "down"}
        onClick={() => toggle("down")}
      >
        <ThumbsDownIcon />
      </button>
      {onRetry && (
        <button type="button" className="lw-icon-btn" title="Retry" aria-label="Retry" onClick={onRetry} disabled={retryDisabled}>
          <RetryIcon />
        </button>
      )}
    </div>
  );
}
