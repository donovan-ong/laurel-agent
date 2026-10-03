import { useState } from "react";
import styles from "./ChatInput.module.css";

export default function ChatInput({ onSend, disabled, placeholder }) {
  const [value, setValue] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <input
        className={styles.input}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        disabled={disabled}
        required
      />
      <button className={styles.sendBtn} type="submit" disabled={disabled} aria-label="Send">
        {/* The "Enter" keyboard glyph (a corner-down-left arrow) rather than a plain up-arrow — reads as
            "submit" the way a keyboard's own Enter key does. */}
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="9 10 4 15 9 20" />
          <path d="M20 4v7a4 4 0 0 1-4 4H4" />
        </svg>
      </button>
    </form>
  );
}
