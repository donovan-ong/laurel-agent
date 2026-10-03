import { useState } from "react";
import { EnterIcon } from "../icons";

export default function ChatInput({ onSend, disabled, placeholder }) {
  const [value, setValue] = useState("");

  function submit(e) {
    e.preventDefault();
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  return (
    <form className="lw-input" onSubmit={submit}>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        aria-label="Message Laurel"
        autoComplete="off"
        disabled={disabled}
      />
      <button type="submit" className="lw-send" disabled={disabled || !value.trim()} aria-label="Send">
        <EnterIcon size={18} />
      </button>
    </form>
  );
}
