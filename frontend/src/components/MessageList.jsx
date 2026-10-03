import Message from "./Message";
import styles from "./MessageList.module.css";

export default function MessageList({ messages, traceVisible, onRetry, retryDisabled }) {
  return (
    <div className={styles.list}>
      {messages.map((m, i) => (
        <Message
          key={i}
          message={m}
          traceVisible={traceVisible}
          onRetry={m.role === "assistant" ? () => onRetry(i) : undefined}
          retryDisabled={retryDisabled}
        />
      ))}
    </div>
  );
}
