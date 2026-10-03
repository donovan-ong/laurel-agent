"""The web app's backend: session cookies over the same authenticate()/ChatClient the CLI uses."""
import os
import secrets
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ibm_watsonx_orchestrate.run.context import AgentRun

from planner import auth
from planner.client import ChatError, connect, message_text
from tools.student_tools import get_student_profile
from tools.week_tools import get_my_week

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "frontend" / "dist"  # built by `cd frontend && npm run build`
WIDGET_DIR = ROOT / "widget" / "dist"  # built by `cd widget && npm run build`: laurel-widget.js
DEMO_DIR = ROOT / "demo"  # the widget's dev harness and the saved RMIT page it can be shown on
# Origins allowed to call the API from another site: the RMIT page itself, localhost on any port (the demo
# pages and dev servers) and Chrome extensions. Override with WIDGET_ORIGIN_REGEX.
WIDGET_ORIGIN_REGEX = os.environ.get(
    "WIDGET_ORIGIN_REGEX", r"^(https://www\.rmit\.edu\.au|http://(localhost|127\.0\.0\.1)(:\d+)?|chrome-extension://[a-p]{32})$")
SESSION_COOKIE = "session"
SESSION_TTL_SECONDS = 8 * 3600  # same policy as planner.auth.SESSION_TTL_SECONDS; a separate, in-memory mechanism
TRACE_CHARS = 600  # matches planner.client.format_steps's truncation


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:].strip() or None if header.lower().startswith("bearer ") else None


def session_for(request: Request) -> dict | None:
    # The cookie is the webapp's; the Authorization header is the embeddable widget's, which runs on another
    # origin where third-party cookies cannot be relied on. Both name the same in-memory session.
    token = request.cookies.get(SESSION_COOKIE) or bearer_token(request)
    return request.app.state.sessions.get(token) if token else None


def require_session(request: Request) -> dict:
    """A FastAPI dependency: the logged-in session, or a 401 if there is none."""
    session = session_for(request)
    if session is None:
        raise HTTPException(401, "Not logged in.")
    return session


def build_trace(steps: list) -> list[dict]:
    """One entry per tool call, with its arguments and a truncated result preview.

    Walks a reply's step_history the same way planner.client.format_steps does (tool_calls, then a matching
    tool_response), but merges each call with its response into one JSON-friendly dict instead of two lines
    of text.
    """
    trace: list[dict] = []
    for step in steps or []:
        for detail in step.get("step_details", []):
            if detail.get("type") == "tool_calls":
                for call in detail.get("tool_calls", []):
                    trace.append({"tool": call.get("name"), "args": call.get("args") or {}, "result_preview": None})
            elif detail.get("type") == "tool_response":
                name, content = detail.get("name", "tool"), str(detail.get("content", ""))
                if len(content) > TRACE_CHARS:
                    content = content[:TRACE_CHARS] + " ..."
                target = next((t for t in reversed(trace) if t["tool"] == name and t["result_preview"] is None), None)
                if target:
                    target["result_preview"] = content
                else:
                    trace.append({"tool": name, "args": {}, "result_preview": content})
    return trace


def recover_history(chat_client, thread_id: str) -> list[dict]:
    """The chat page's transcript recovered from the platform, for a reload mid-conversation.

    Calls ThreadsClient.get_thread_messages directly (not through ChatClient.ask, so this triggers no new
    run). Best-effort: the chat page works fine without this, so any failure here — an unexpected response
    shape, a transient network error — just means no history is recovered, never a broken page.
    """
    try:
        raw = chat_client.threads_client.get_thread_messages(thread_id)
        messages = raw.get("data", []) if isinstance(raw, dict) else (raw or [])
        recovered = []
        for m in messages:
            if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
                continue
            entry = {"role": m["role"], "text": message_text(m.get("content", ""))}
            if m["role"] == "assistant":
                entry["trace"] = build_trace(m.get("step_history") or [])
            recovered.append(entry)
        return recovered
    except Exception:
        return []


def create_app() -> FastAPI:
    app = FastAPI(title="Laurel web", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions = {}
    # Bearer auth, so no cookies cross sites and credentials stay off.
    app.add_middleware(CORSMiddleware, allow_origin_regex=WIDGET_ORIGIN_REGEX, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"], allow_credentials=False)
    if (DIST_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
    # Mounted before the SPA catch-all for the same reason /assets is.
    if WIDGET_DIR.is_dir():
        app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")
    if DEMO_DIR.is_dir():
        app.mount("/demo", StaticFiles(directory=DEMO_DIR, html=True), name="demo")

    def open_session(body: dict) -> tuple[str, dict]:
        """Check the credentials, connect to the agent and store a new session. Shared by both login routes."""
        account = auth.authenticate(body.get("username") or "", body.get("password") or "")
        if account is None:
            raise HTTPException(401, "Invalid username or password.")
        try:
            chat_client = connect(account["student_number"])
        except ChatError as e:
            raise HTTPException(502, str(e)) from None
        except SystemExit:
            # The Orchestrate SDK calls sys.exit(1) itself when the trial login token is missing or expired,
            # instead of raising something catchable — fail visibly rather than letting that reach uvicorn
            # as an unhandled 500.
            raise HTTPException(502, "The Orchestrate trial login has expired. Run `orchestrate env activate "
                                     "<environment>`, then try logging in again.") from None
        token = secrets.token_urlsafe(32)
        app.state.sessions[token] = {"username": account["username"], "student_number": account["student_number"],
                                     "client": chat_client, "thread_id": None}
        return token, account

    @app.post("/api/login")
    def login(body: dict = Body(...)):
        token, account = open_session(body)
        response = JSONResponse({"username": account["username"], "student_number": account["student_number"]})
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS)
        return response

    @app.post("/api/logout")
    def logout(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        app.state.sessions.pop(token, None)
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie(SESSION_COOKIE)
        return response

    # The widget's own login: same checks, but the session token comes back in the body to be sent as a Bearer
    # header, and no cookie is set. /api/login is left alone because its exact response is part of the webapp's
    # tested contract.
    @app.post("/api/widget/login")
    def widget_login(body: dict = Body(...)):
        token, account = open_session(body)
        return {"token": token, "username": account["username"], "student_number": account["student_number"]}

    @app.post("/api/widget/logout")
    def widget_logout(request: Request):
        app.state.sessions.pop(bearer_token(request), None)
        return {"status": "logged_out"}

    # The widget's "open the full webapp" link: the bearer token it already holds and the webapp's cookie
    # name the exact same session (see session_for above), so this just mints the cookie for a token that's
    # already valid. This is a top-level navigation the browser makes itself (window.open, not a fetch), so
    # it never touches CORS/allow_credentials — that only governs cross-origin fetch/XHR. A missing or
    # unknown token fails open to the ordinary login page rather than an error.
    @app.get("/api/session/adopt")
    def adopt_session(token: str = ""):
        known = token in app.state.sessions
        response = RedirectResponse("/" if known else "/login", status_code=302)
        if known:
            response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS)
        return response

    @app.get("/api/me")
    def me(request: Request):
        session = session_for(request)
        if session is None:
            return {"logged_in": False}
        return {"logged_in": True, "username": session["username"], "student_number": session["student_number"]}

    @app.post("/api/chat")
    def chat(body: dict = Body(...), session: dict = Depends(require_session)):
        message = (body.get("message") or "").strip()
        if not message:
            raise HTTPException(400, "message must not be empty.")
        try:
            reply = session["client"].ask(message, session["thread_id"])
        except ChatError as e:
            raise HTTPException(502, str(e)) from None
        session["thread_id"] = reply.thread_id
        return {"reply": reply.text, "trace": build_trace(reply.steps), "thread_id": reply.thread_id,
                "seconds": reply.seconds}

    @app.get("/api/chat/history")
    def chat_history(session: dict = Depends(require_session)):
        thread_id = session["thread_id"]
        messages = recover_history(session["client"], thread_id) if thread_id else []
        return {"messages": messages, "thread_id": thread_id}

    @app.get("/api/profile")
    def profile(session: dict = Depends(require_session)):
        # Called directly, not through the agent: no LLM latency, nothing to parse out of markdown.
        return get_student_profile.fn(context=AgentRun(request_context={"student_number": session["student_number"]}))

    @app.get("/api/week")
    def week(on: str | None = None, session: dict = Depends(require_session)):
        # The home screen's "Your week" panel: called directly like /api/profile, so it shows straight away.
        return get_my_week.fn(context=AgentRun(request_context={"student_number": session["student_number"]}), on_date=on)

    # The SPA shell. Registered last: Starlette tries routes in registration order, and this wildcard would
    # otherwise swallow every /api/* request above it. Serves index.html for any client-side route (/, /login,
    # /profile, including a hard refresh on any of them), but a real file under dist/ (e.g. favicon.svg, or
    # anything else Vite copied from frontend/public/) is served as that file first.
    @app.get("/{full_path:path}")
    def spa_shell(full_path: str):
        index = DIST_DIR / "index.html"
        if not index.exists():
            raise HTTPException(500, "frontend/dist is missing. Run `cd frontend && npm install && npm run build`.")
        requested = (DIST_DIR / full_path).resolve()
        if full_path and requested.is_file() and requested.is_relative_to(DIST_DIR.resolve()):
            return FileResponse(requested)
        return HTMLResponse(index.read_text(encoding="utf-8"))

    return app
