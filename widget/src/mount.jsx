import { createRoot } from "react-dom/client";
import css from "./styles/widget.css?inline";
import Widget from "./Widget";
import { extensionTransport, fetchTransport } from "./transport";

const HOST_ID = "laurel-widget-host";

/** Put the widget on the current page. Safe to call twice: a second call does nothing.
 *
 *  options.transport: "extension" (Chrome extension), an object with request/login/logout, or omitted for
 *  plain fetch against options.apiBase (default: the page's own origin).
 */
export function mount(options = {}) {
  if (document.getElementById(HOST_ID)) return;
  // A child of <html>, not <body>: a site that transforms or clips <body> would otherwise break position: fixed.
  const host = document.createElement("div");
  host.id = HOST_ID;
  document.documentElement.appendChild(host);
  // A shadow root keeps the page's CSS out of the widget and the widget's CSS out of the page.
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = css;
  shadow.appendChild(style);
  const container = document.createElement("div");
  container.className = "lw-root";
  shadow.appendChild(container);

  let transport;
  if (options.transport === "extension") transport = extensionTransport();
  else if (options.transport && typeof options.transport === "object") transport = options.transport;
  else transport = fetchTransport({ apiBase: options.apiBase });

  createRoot(container).render(<Widget transport={transport} showDemoHint={options.showDemoHint !== false} />);
}
