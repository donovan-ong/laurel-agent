import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MessageActions from "./MessageActions";
import TraceDisclosure from "./TraceDisclosure";

// The panel is narrow, so wide tables scroll sideways inside their own wrapper, and links always open in a new
// tab so they never navigate the RMIT page the student is on.
const MARKDOWN_COMPONENTS = {
  table: ({ node, ...props }) => (
    <div className="lw-table-wrap">
      <table {...props} />
    </div>
  ),
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
};

export default function Message({ message, traceVisible, onRetry, retryDisabled }) {
  const { role, text, trace } = message;
  if (role === "assistant") {
    return (
      <div className="lw-msg lw-assistant">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
          {text}
        </ReactMarkdown>
        {traceVisible && <TraceDisclosure trace={trace} />}
        <MessageActions text={text} onRetry={onRetry} retryDisabled={retryDisabled} />
      </div>
    );
  }
  return <div className={`lw-msg ${role === "error" ? "lw-error" : "lw-user"}`}>{text}</div>;
}
