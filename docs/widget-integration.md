# Laurel chat widget for RMIT pages

A floating chat button for RMIT web pages: a red circle fixed to the bottom-right (it holds its position while the
page scrolls) that opens a small RMIT-styled chat window on the same page. Sign-in happens inside the window,
and is asked for again in every new browser session. It behaves like the Laurel webapp (`frontend/`, restyled to
match this same RMIT theme — see below): rotating "Calculating…" status text with a spinner while the agent
works, copy / thumbs up-down / retry under each reply, a trace ("source") toggle, an expand button in the header
(a larger window on the same page, remembered), a phone button that shows RMIT's general-enquiries number
(`ENQUIRIES_PHONE` in `widget/src/Widget.jsx`), markdown replies, and the conversation restored from the server
when the page changes. Clicking "Laurel" in the header opens the full webapp in a new tab, staying signed in if
the widget already was (see "Opening the full webapp" below).

This is a **student-project prototype on synthetic data**, not an official RMIT product. The window carries a
"Prototype" badge for that reason.

## How it fits together

```
 www.rmit.edu.au page ──┐                                          ┌── Orchestrate agent
                        │  laurel-widget.js (Shadow DOM)           │   (tools, synthetic data)
   extension host       │        │                                 │
   content script ──────┴─ extensionTransport ─► service worker ─┐ │
                                                  (holds token)   │ │
   saved-page host                                                ├─► FastAPI backend (webapp/server.py)
   <script data-laurel> ── fetchTransport ────────────────────────┘     Bearer-token sessions, CORS allow-list
```

- **One widget, built once** (`widget/`, Vite library build → `laurel-widget.js`, React inside a Shadow DOM so
  RMIT's CSS cannot reach the widget and the widget's CSS cannot reach the page).
- **Two hosts** for it:
  - **Chrome extension** (`extension/`, MV3) puts it on the real `https://www.rmit.edu.au/*`. The demo.
  - **Saved page** (`demo/rmit/`, captured by `scripts/capture_rmit_page.sh`) served by the backend at
    `/demo/rmit/`, with the widget added by one `<script>` tag. The offline fallback, and the literal "how a site
    would embed it" story.
- **A transport is the one place the hosts differ** (`widget/src/transport.js`): plain `fetch` with the token in
  `sessionStorage` on the saved page; messages to the extension's service worker in the extension.
- **The backend** gained Bearer-token auth (`Authorization: Bearer …` accepted alongside the webapp's cookie),
  `POST /api/widget/login` and `/api/widget/logout`, `GET /api/session/adopt` (below), a CORS allow-list, and
  `/widget` + `/demo` static mounts. `/api/login`'s response contract is untouched.
- **The webapp is now restyled to match**: same navy/red/white RMIT palette, sans-serif throughout, the same
  Laurel mark (white laurel leaves on a red disc, from `assets/brand/`) — one shared look across the full app and the widget. Only the visual
  layer changed; its routes, session handling and tests are otherwise as before.

### Design choices worth knowing

- **Bearer tokens, not cookies**: a widget on another origin cannot rely on third-party cookies.
- **The extension keeps the token away from the page.** The service worker stores it in `chrome.storage.session`
  (cleared when the browser session ends, which is what makes every new session ask for a login) and adds the
  header itself. The RMIT page never sees it, and CORS, mixed-content and private-network rules never apply.
- **Least privilege**: the extension matches only `https://www.rmit.edu.au/*` (never SSO or student-portal
  pages), not in iframes, and its worker forwards only GET/POST to `/api/…` paths from its own content script.
- **Long replies**: chat replies take 10 to 70 seconds and Chrome ends an extension worker whose fetch takes over 30
  seconds, so the worker pings an extension API every 20 seconds while a request is in flight (tested with a 45
  second reply). If that ever proves flaky, the fallback is to make chat a start-then-poll job.
- **Style isolation**: a shadow root is not enough on its own. Inherited properties still cross from the host
  element, and for the host itself the page's rules beat the shadow tree's, so `:host { all: initial }` does not
  stop a page with `* { text-transform: uppercase }`. The reset (`all: initial`) is on a container *inside* the
  shadow root, where page selectors cannot match. `demo/index.html` has deliberately hostile global CSS to prove it.
- **Crowded corners**: RMIT's own Library page already has an "Ask the Library" chat button fixed bottom-right. The
  widget samples its corner and sits above any other fixed element (another chat button, a cookie banner),
  re-checking after load and on resize (`widget/src/avoidCollisions.js`).
- **Page-aware suggestions**: the empty state's chips come from the section of the site (`location.pathname`):
  library page → loans and renewals, international → the visa question, study/courses → enrolment, students →
  print, room booking, IT ticket.
- **Copied, not shared, from the webapp**: the widget has its own small API/hook/component code ported from
  `frontend/src`. A shared core could be extracted later.
- **Opening the full webapp, staying signed in**: the webapp's cookie and the widget's bearer token are the
  same secret string — both `/api/login` and `/api/widget/login` mint it through one shared `open_session()`
  helper in `webapp/server.py`, they just carry it out differently (`Set-Cookie` vs the JSON body). Clicking
  "Laurel" asks the transport for a token-carrying URL and opens it in a new tab: the fetch transport reads its
  own `sessionStorage` token directly; the extension keeps that lookup inside the service worker
  (`chrome.runtime.sendMessage({type: "laurel:openWebapp"})` → `chrome.tabs.create`), so the token still never
  reaches the page, the same invariant as login. That URL, `GET /api/session/adopt?token=…`, is a **top-level
  navigation, not a fetch** — the browser talking to the backend's own origin directly — so it sits outside
  CORS/`allow_credentials` entirely: it just sets the webapp's cookie for that same token and redirects to `/`
  (or to `/login` if the token is missing or unknown). Signed out, "Laurel" just opens the webapp's own root.
- **Sans-serif replies**, to suit RMIT's look (the webapp was later restyled to match, so both are sans-serif
  now). System font stack here specifically, because web fonts declared inside a shadow root do not register.

## Run it

### Develop and test without the Orchestrate trial

```
cd widget && npm install && npm run build            # widget/dist/laurel-widget.js
python scripts/widget_stub.py --port 8111 --delay 4  # the real backend with a canned agent; replies start "(stub)"
# then open http://127.0.0.1:8111/demo/index.html
cd widget && npm run smoke -- http://127.0.0.1:8111/demo/index.html      # headless-Chrome checks + screenshots in widget/.smoke/
cd widget && npm run build:extension && npm run smoke:extension -- http://127.0.0.1:8111
```

`npm run smoke` checks: launcher holds position while scrolling; sign-in (bad then good password); suggestion
chips; loading indicator; a reply with a table; trace toggle; history restored after reload; sign out; phone-width
layout; and that the launcher sits clear of another fixed chat button. It also runs against the saved page:
`npm run smoke -- http://127.0.0.1:8111/demo/rmit/`.

One automation quirk, so nobody chases it: typing into a password field leaves headless Chrome's *mouse* input
dead for that browser session (keyboard still works). The smoke test therefore checks the sign-in form with the
keyboard and runs everything else in fresh sessions with a seeded token.

### Demo on the real RMIT site (the plan for Thursday 1 October)

1. `orchestrate env activate <environment>` (the trial login token expires; without it sign-in returns a 502 that
   says so), and make sure the agent is deployed: `python scripts/deploy.py`.
2. `cd widget && npm install && npm run build:extension` (copies the bundle into `extension/`).
3. Back in the repo root (`cd ..`; `python -m webapp` only finds the package from there):
   `python -m webapp --no-open` (backend on `http://127.0.0.1:8100`).
4. In Chrome: `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose the `extension/`
   folder. (Chrome may show a "disable developer mode extensions" prompt at start-up; dismiss it.)
5. Open <https://www.rmit.edu.au/>, click the red button, sign in (`demo4` / `demo4` has the richest data), and try
   the chips. Browse to Library or International: the chips change, the widget stays, the conversation continues.
6. Restart Chrome to show the login being asked for again in a new session.

If the extension is a problem on the day, or the venue Wi-Fi is: run
`scripts/capture_rmit_page.sh` **beforehand** (needs network once) and present
`http://127.0.0.1:8100/demo/rmit/`, which works with all external network blocked.

To point the extension at a backend on another port: in `chrome://extensions` open the extension's *service worker*
console and run `chrome.storage.local.set({ apiBase: "http://127.0.0.1:9000" })`.

## How a real deployment would differ (not built)

- **Embedding**: one line, `<script src="https://…/laurel-widget.js" data-laurel data-api-base="https://…">`, added
  through the site's tag manager or page template. No extension.
- **Sign-in**: the widget talks to the transport's `login`/`logout` only. Behind RMIT's single sign-on, a transport
  would exchange the site's existing session for a chat token (for example, a backend endpoint that verifies the
  site's identity token and maps it to a student number) and the form would only appear when nobody is signed in.
  Today it is a demo username and password.
- **Hosting**: the backend on an RMIT domain with a proper CORS allow-list (`WIDGET_ORIGIN_REGEX`), HTTPS, and
  shared session storage instead of in-memory sessions.
- **Token storage**: on the saved page the token sits in `sessionStorage`, readable by any script on that page. Fine
  for a demo page we control; on a real site a first-party HttpOnly cookie, or isolating the chat in an iframe,
  would be the better choice.
- Rate limiting, audit logging, accessibility review and RMIT brand sign-off, none of which a prototype has.

## Files

| Path | What |
| --- | --- |
| `widget/` | The widget (Vite library build), its smoke tests |
| `extension/` | The Chrome extension (manifest, service worker, content script, icons). `laurel-widget.js` in here is a build output, git-ignored |
| `demo/index.html`, `demo/plain.html`, `demo/crowded.html` | Dev harness with hostile CSS; a page with no widget script (extension test); a page with its own chat button |
| `demo/rmit/` | The saved RMIT page (git-ignored: third-party content) |
| `scripts/widget_stub.py` | The real backend with a canned agent |
| `scripts/capture_rmit_page.sh` | Captures the saved page |
| `webapp/server.py` | Bearer auth, widget login/logout, CORS, static mounts |
| `tests/test_widget_api.py` | The backend's side, 18 tests |
