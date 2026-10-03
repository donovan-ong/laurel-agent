import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TraceDisclosure from "./TraceDisclosure";
import MessageActions from "./MessageActions";
import styles from "./Message.module.css";

const ROLE_CLASS = { user: styles.user, error: styles.error };

export default function Message({ message, traceVisible, onRetry, retryDisabled }) {
  const { role, text, trace } = message;
  if (role === "assistant") {
    return (
      <div className={styles.assistant}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        {traceVisible && <TraceDisclosure trace={trace} />}
        <MessageActions text={text} onRetry={onRetry} retryDisabled={retryDisabled} />
      </div>
    );
  }
  return <div className={ROLE_CLASS[role] || styles.user}>{text}</div>;
}
