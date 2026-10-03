#!/usr/bin/env bash
# Save a self-contained copy of an RMIT page as the offline fallback host for the Laurel widget:
#
#   scripts/capture_rmit_page.sh [url]          # default https://www.rmit.edu.au/
#
# Writes demo/rmit/index.html (git-ignored: it is third-party content, not ours to commit), served by the
# backend at http://127.0.0.1:8100/demo/rmit/ with the widget added by one <script> tag. Needs Node and network
# access once, and Chrome (CHROME_PATH to override the macOS default). Uses SingleFile (fetched on demand by npx).
#
# Three things are done on top of SingleFile's output:
#   - Node 22 lacks the global CloseEvent that SingleFile's CLI expects, so a tiny polyfill is preloaded.
#   - SingleFile adds a Content-Security-Policy <meta> that keeps the page inert (default-src 'none'); it would
#     also block the widget's script and its calls to the backend, so it is removed. The saved page has no
#     scripts of RMIT's own left in it.
#   - The widget's one-line embed is appended.
set -euo pipefail

URL="${1:-https://www.rmit.edu.au/}"
CHROME="${CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/polyfill.cjs" <<'EOF'
globalThis.CloseEvent = globalThis.CloseEvent || class CloseEvent extends Event {
  constructor(type, init = {}) { super(type, init); this.code = init.code || 0; this.reason = init.reason || ""; this.wasClean = !!init.wasClean; }
};
EOF

NODE_OPTIONS="--require $TMP/polyfill.cjs" npx --yes single-file-cli "$URL" "$TMP/page.html" \
  --browser-executable-path="$CHROME" --browser-headless=true

mkdir -p "$ROOT/demo/rmit"
python3 - "$TMP/page.html" "$ROOT/demo/rmit/index.html" <<'PY'
import re, sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8")
html = re.sub(r"<meta[^>]+http-equiv=[\"']?content-security-policy[\"']?[^>]*>", "", html, flags=re.I)
embed = '\n<script src="/widget/laurel-widget.js" data-laurel data-api-base="" defer></script>\n'
match = re.search(r"</body>", html, re.I)
# SingleFile's output can end without closing tags; browsers cope, so just append the embed in that case.
html = html[: match.start()] + embed + html[match.start():] if match else html + embed
Path(sys.argv[2]).write_text(html, encoding="utf-8")
print(f"wrote {sys.argv[2]} ({len(html) / 1e6:.1f} MB)")
PY
