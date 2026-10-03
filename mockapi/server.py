"""The mock student systems API. It uses the same enrolment and drop logic as the local tools, and remembers what it did."""
import hmac
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from mockapi.events import EventBus, stream
from mockapi.store import Store
from tools import dropping as drop, enrolment as enr, scheduling as sch
from tools.common import load, today as melbourne_today

DASHBOARD = Path(__file__).parent / "dashboard.html"

# HTTP status for each refusal code
STATUS = {"NOT_CONFIRMED": 400, "INVALID_CHECK": 400, "INVALID_REQUEST": 400, "INVALID_SELECTION": 422,
          "PREREQUISITE_NOT_MET": 422, "ACCOUNT_HOLD": 403, "STUDENT_NOT_FOUND": 404, "NOT_ENROLLED": 404,
          "ENROLMENT_CLOSED": 409, "ALREADY_ENROLLED": 409, "ALREADY_PASSED": 409, "CLASS_FULL": 409,
          "TIMETABLE_CLASH": 409, "DROP_DEADLINE_PASSED": 409, "UNAUTHORISED": 401}


def refusal(code: str, message: str) -> dict:
    return {"status": "refused", "error": {"code": code, "message": message}, "simulated": True, "notice": enr.NOTICE}


def create_app(api_key: str, today=None) -> FastAPI:
    """today is a function returning the date the drop rules use. It defaults to the date in Melbourne."""
    app = FastAPI(title="Mock student systems API", docs_url=None, redoc_url=None, openapi_url=None)
    bus, store, started = EventBus(), Store(), time.time()
    app.state.bus, app.state.store, app.state.started = bus, store, started
    today = today or melbourne_today

    def record(request: Request, status: int, kind: str, student: str | None, summary: str, began: float,
               body: Any = None, response: Any = None) -> None:
        bus.publish({"time": datetime.now().strftime("%H:%M:%S"), "method": request.method, "path": request.url.path,
                     "kind": kind, "student": student, "status": status, "ms": round((time.perf_counter() - began) * 1000),
                     "summary": summary, "request": body, "response": response,
                     "request_id": request.headers.get("x-request-id")})

    def reply(request, began, kind, student, status, payload, summary, body=None) -> JSONResponse:
        record(request, status, kind, student, summary, began, body, payload)
        return JSONResponse(payload, status_code=status)

    def check_key(request: Request, header: str | None, query: str | None = None) -> None:
        given = header or query or ""
        if not hmac.compare_digest(given.encode(), api_key.encode()):
            raise HTTPException(401, "A valid API key is needed.")

    def refused(request, began, kind, student, code, message, body=None) -> JSONResponse:
        return reply(request, began, kind, student, STATUS[code], refusal(code, message), f"REFUSED {code}", body)

    def find_student(number: Any):
        return next((s for s in load("students.json") if s["student_number"] == number), None)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        payload = refusal("UNAUTHORISED" if error.status_code == 401 else "INVALID_REQUEST", str(error.detail))
        if error.status_code == 401 and request.url.path.startswith("/v1"):
            record(request, 401, "other", None, "REFUSED UNAUTHORISED", time.perf_counter(), None, payload)
        return JSONResponse(payload, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, error: RequestValidationError):
        payload = refusal("INVALID_REQUEST", "The request body must be a JSON object.")
        record(request, 400, "other", None, "REFUSED INVALID_REQUEST", time.perf_counter(), None, payload)
        return JSONResponse(payload, status_code=400)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "mock-student-systems", "simulated": True, "today": today().isoformat()}

    # Enrolment

    @app.post("/v1/enrolments/check")
    def check(request: Request, body: dict = Body(...), x_api_key: str | None = Header(None)):
        check_key(request, x_api_key)
        began = time.perf_counter()
        number = body.get("student_number")
        student = find_student(number)
        if student is None:
            return refused(request, began, "check", number, "STUDENT_NOT_FOUND", "No such student.", body)
        try:
            blocks = sch.parse_availability(body.get("availability"))
        except sch.AvailabilityError as e:
            return refused(request, began, "check", number, "INVALID_REQUEST", str(e), body)
        with store.lock:
            result = enr.check_response(student, body.get("class_ids"), blocks, **store.state(student))
        classes = " + ".join(map(str, body.get("class_ids") or []))
        summary = (f"eligible=true  classes {classes}" if result["eligible"]
                   else "not eligible: " + ", ".join(r["code"] for r in result["reasons"]))
        return reply(request, began, "check", number, 200, result, summary, body)

    @app.post("/v1/enrolments")
    def enrol(request: Request, body: dict = Body(...), x_api_key: str | None = Header(None)):
        check_key(request, x_api_key)
        began = time.perf_counter()
        number = body.get("student_number")
        student = find_student(number)
        if student is None:
            return refused(request, began, "enrol", number, "STUDENT_NOT_FOUND", "No such student.", body)
        try:
            blocks = sch.parse_availability(body.get("availability"))
        except sch.AvailabilityError as e:
            return refused(request, began, "enrol", number, "INVALID_REQUEST", str(e), body)
        with store.lock:
            result = enr.submit_response(student, body.get("class_ids"), body.get("check_id"),
                                         body.get("student_confirmed"), blocks, **store.state(student))
            if result["status"] == "enrolled":
                store.add(student, result["enrolment"], result["reference"], datetime.now().strftime("%H:%M:%S"))
        if result["status"] == "enrolled":
            return reply(request, began, "enrol", number, 201, result, f"ENROLLED {result['reference']}", body)
        code = result["error"]["code"]
        return reply(request, began, "enrol", number, STATUS.get(code, 409), result, f"REFUSED {code}", body)

    @app.get("/v1/students/{number}/enrolments")
    def enrolments(request: Request, number: str, x_api_key: str | None = Header(None)):
        check_key(request, x_api_key)
        began = time.perf_counter()
        student = find_student(number)
        if student is None:
            return refused(request, began, "list", number, "STUDENT_NOT_FOUND", "No such student.")
        with store.lock:
            current = store.enrolments(student)
            made = {(e["course_id"], e["term"]): e["reference"] for e in store.made.get(number, [])}
        described = enr.describe(current)
        for item in described:
            item["reference"] = made.get((item["course_id"], item["term"]))
            item["source"] = "made through this service" if item["reference"] else "student record"
        payload = {"student_number": number, "enrolments": described, "simulated": True, "notice": enr.NOTICE}
        return reply(request, began, "list", number, 200, payload, f"{len(described)} enrolment{'s' if len(described) != 1 else ''}")

    # Dropping

    @app.get("/v1/students/{number}/enrolments/{course_id}/{term}/drop-check")
    def drop_check(request: Request, number: str, course_id: str, term: str, x_api_key: str | None = Header(None)):
        check_key(request, x_api_key)
        began = time.perf_counter()
        student = find_student(number)
        if student is None:
            return refused(request, began, "drop_check", number, "STUDENT_NOT_FOUND", "No such student.")
        with store.lock:
            result = drop.check_response(student, course_id, term, enrolments=store.enrolments(student), today=today())
        if result["can_drop"]:
            c = result["consequences"]
            summary = f"can_drop=true  {c['phase']}, fee {c['fee_outcome'].replace('_', ' ')} ({c['currency']} {c['course_fee']:,.0f})"
        else:
            summary = "can_drop=false: " + ", ".join(r["code"] for r in result["reasons"])
        return reply(request, began, "drop_check", number, 200, result, summary)

    @app.delete("/v1/students/{number}/enrolments/{course_id}/{term}")
    def drop_class(request: Request, number: str, course_id: str, term: str, body: dict = Body(default={}),
                   x_api_key: str | None = Header(None)):
        check_key(request, x_api_key)
        began = time.perf_counter()
        student = find_student(number)
        if student is None:
            return refused(request, began, "drop", number, "STUDENT_NOT_FOUND", "No such student.", body)
        with store.lock:
            result = drop.drop_response(student, course_id, term, body.get("check_id"), body.get("student_confirmed"),
                                        enrolments=store.enrolments(student), today=today())
            if result["status"] == "dropped":
                store.remove(student, course_id, term)
        if result["status"] == "dropped":
            return reply(request, began, "drop", number, 200, result, f"DROPPED {result['reference']}", body)
        code = result["error"]["code"]
        return reply(request, began, "drop", number, STATUS.get(code, 409), result, f"REFUSED {code}", body)

    # Dashboard

    def admin(request: Request, key: str | None, header: str | None) -> None:
        check_key(request, header, key)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, key: str | None = Query(None), x_api_key: str | None = Header(None)):
        admin(request, key, x_api_key)
        return HTMLResponse(DASHBOARD.read_text(encoding="utf-8"))

    @app.get("/admin/events")
    async def events(request: Request, key: str | None = Query(None), after: int = Query(0),
                     x_api_key: str | None = Header(None), last_event_id: str | None = Header(None)):
        admin(request, key, x_api_key)
        resume = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
        if resume > bus.last_id():  # a browser reconnecting to a service that has restarted
            resume = 0
        return StreamingResponse(stream(bus, resume), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/admin/events.json")
    def events_json(request: Request, key: str | None = Query(None), after: int = Query(0),
                    x_api_key: str | None = Header(None)):
        admin(request, key, x_api_key)
        return {"events": bus.since(after)}

    @app.get("/admin/state.json")
    def state(request: Request, key: str | None = Query(None), x_api_key: str | None = Header(None)):
        admin(request, key, x_api_key)
        students = {s["student_number"]: s for s in load("students.json")}
        with store.lock:
            rows = []
            for number, student in students.items():
                made = {(e["course_id"], e["term"]): e for e in store.made.get(number, [])}
                for e in store.enrolments(student):
                    made_here = made.get((e["course_id"], e["term"]))
                    rows.append({"student": number, "name": student["name"], "course_id": e["course_id"], "term": e["term"],
                                 "class_ids": e["class_ids"], "reference": made_here["reference"] if made_here else None,
                                 "source": "service" if made_here else "record"})
            dropped = [{"student": n, "name": students[n]["name"], "course_id": c, "term": t, "class_ids": ids}
                       for n, d in store.dropped.items() for (c, t), ids in d.items()]
            seats = store.taken()
        return {"started": started, "uptime_seconds": round(time.time() - started), "today": today().isoformat(),
                "enrolments": rows, "dropped_from_record": dropped, "seats": seats}

    @app.post("/admin/reset")
    def reset(request: Request, key: str | None = Query(None), x_api_key: str | None = Header(None)):
        admin(request, key, x_api_key)
        began = time.perf_counter()
        store.reset()
        bus.clear()
        record(request, 200, "reset", None, "RESET  service memory cleared", began, None, {"status": "reset"})
        return {"status": "reset"}

    return app
