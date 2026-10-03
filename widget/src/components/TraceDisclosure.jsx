// One reply's tool calls, in the shape the backend's build_trace() returns: {tool, args, result_preview}[].
export default function TraceDisclosure({ trace }) {
  if (!trace || !trace.length) return null;
  return (
    <details className="lw-trace">
      <summary>
        Show trace ({trace.length} tool call{trace.length === 1 ? "" : "s"})
      </summary>
      <ol>
        {trace.map((t, i) => (
          <li key={i}>
            <span className="lw-tool">{t.tool}</span>
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
