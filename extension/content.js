// Runs on rmit.edu.au after laurel-widget.js (same isolated world, so LaurelWidget is in scope).
// The widget goes through the extension's service worker for every network call.
LaurelWidget.mount({ transport: "extension" });
