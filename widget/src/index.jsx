import { mount } from "./mount";

// One script tag is the whole integration: <script src=".../laurel-widget.js" data-laurel data-api-base="..." defer>.
// The extension and the demo harness instead call LaurelWidget.mount({...}) themselves.
const script = document.currentScript;
if (script && script.dataset.laurel !== undefined) {
  const start = () => mount({ apiBase: script.dataset.apiBase || "" });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
}

export { mount };
