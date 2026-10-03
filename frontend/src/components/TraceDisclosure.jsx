import styles from "./TraceDisclosure.module.css";

// Renders one assistant message's trace: {tool, args, result_preview}[], exactly the shape build_trace()
// already returns — no reshaping needed. A native <details>/<summary> needs no extra state for open/closed.
export default function TraceDisclosure({ trace }) {
  if (!trace || !trace.length) return null;
  return (
    <details className={styles.trace}>
      <summary>
        Show trace ({trace.length} tool call{trace.length === 1 ? "" : "s"})
      </summary>
      <ol>
        {trace.map((t, i) => (
          <li key={i}>
            <span className={styles.toolName}>{t.tool}</span>
            {t.args && Object.keys(t.args).length ? ` ${JSON.stringify(t.args)}` : ""}
            {t.result_preview ? (
              <>
                <br />← {t.result_preview}
              </>
            ) : null}
          </li>
        ))}
      </ol>
    </details>
  );
}
