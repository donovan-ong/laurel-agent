import { useCallback, useState } from "react";
import { ApiError } from "./api";

// The conversation state machine, the same as the webapp's ChatPage: append the student's message, ask the
// agent, append the reply or an error. Retry drops the reply it is retrying and re-asks the message before it
// (the agent's own thread still has both turns, since a past turn cannot be erased there).
export function useChat(api, { onUnauthorised } = {}) {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);

  const sendToAgent = useCallback(
    async (text) => {
      setSending(true);
      try {
        const data = await api.chat(text);
        setMessages((prev) => [...prev, { role: "assistant", text: data.reply, trace: data.trace }]);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          onUnauthorised?.();
          setMessages((prev) => [...prev, { role: "error", text: "Your session has ended. Please sign in again." }]);
        } else {
          setMessages((prev) => [...prev, { role: "error", text: err instanceof ApiError ? err.message : "Something went wrong." }]);
        }
      } finally {
        setSending(false);
      }
    },
    [api, onUnauthorised],
  );

  const send = useCallback(
    async (text) => {
      setMessages((prev) => [...prev, { role: "user", text }]);
      await sendToAgent(text);
    },
    [sendToAgent],
  );

  const retry = useCallback(
    async (index) => {
      if (sending) return;
      const userMessage = messages[index - 1];
      if (!userMessage || userMessage.role !== "user") return;
      setMessages(messages.slice(0, index));
      await sendToAgent(userMessage.text);
    },
    [messages, sending, sendToAgent],
  );

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.history();
      if (data.messages && data.messages.length) setMessages(data.messages);
    } catch {
      // best-effort: an empty transcript is a fine starting point
    }
  }, [api]);

  const reset = useCallback(() => setMessages([]), []);

  return { messages, sending, send, retry, loadHistory, reset };
}
