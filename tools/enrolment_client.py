"""Calls the enrolment service when one is configured. Without a configuration the tools use their own logic.

The address and key are in service_config.json next to this file, written by scripts/deploy.py at deploy time
(see service_config.example.json for the shape expected). The
student number always comes from the run context, never from the model. If the service is configured and cannot be
reached, the tool says so and changes nothing: it never falls back to the local logic, because that could report a
result the service does not know about.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "service_config.json"
TIMEOUT = 10
UNAVAILABLE = "The enrolment service is unavailable. Nothing was changed."
SERVED_BY = "mock enrolment service"
# Course codes and terms go into the request path, so anything else is refused before it is sent
COURSE = re.compile(r"[A-Za-z0-9]{1,20}")
TERM = re.compile(r"\d{4}-[A-Za-z0-9]{1,4}")


class ServiceError(Exception):
    """The service could not be reached, or did not give a usable answer."""


def config() -> dict | None:
    try:
        found = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return found if found.get("url") and found.get("key") else None


def configured() -> bool:
    return config() is not None


def unavailable(error: ServiceError) -> dict:
    """What a tool returns when the service cannot answer. There is no reference number and nothing changed."""
    return {"found": False, "reason": UNAVAILABLE, "service_error": str(error)}


def segment(value: str, pattern: re.Pattern, what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"Give the {what} as text, for example COSC2148 or 2027-S1.")
    return urllib.parse.quote(value, safe="")


def send(method: str, path: str, body: dict | None = None, expect: str = "") -> tuple[int, dict]:
    """One request to the service. Returns the status and the JSON body of any answer the service itself gave.

    expect is a key the answer must contain, so a proxy's error page or a reply of the wrong shape is a ServiceError.
    """
    settings = config()
    if settings is None:
        raise ServiceError("no service is configured")
    request = urllib.request.Request(
        settings["url"].rstrip("/") + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"X-API-Key": settings["key"], "Content-Type": "application/json", "Accept": "application/json",
                 "X-Request-Id": uuid.uuid4().hex[:8]})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except TimeoutError:
        raise ServiceError("timed out") from None
    except (urllib.error.URLError, OSError) as error:
        raise ServiceError(f"could not connect ({type(getattr(error, 'reason', error)).__name__})") from None
    try:
        answer = json.loads(raw)
    except ValueError:
        raise ServiceError(f"reply was not JSON (HTTP {status})") from None
    if status == 401 or status >= 500:
        raise ServiceError(f"HTTP {status}")
    if not isinstance(answer, dict) or (expect and expect not in answer):
        raise ServiceError(f"unexpected reply (HTTP {status})")
    return status, answer


def check_enrolment(student_number: str, class_ids, availability) -> dict:
    return send("POST", "/v1/enrolments/check", {"student_number": student_number, "class_ids": class_ids,
                                                 "availability": availability}, "eligible")[1]


def submit_enrolment(student_number: str, class_ids, check_id: str, confirmed, availability) -> dict:
    return send("POST", "/v1/enrolments", {"student_number": student_number, "class_ids": class_ids, "check_id": check_id,
                                           "student_confirmed": confirmed, "availability": availability}, "status")[1]


def list_enrolments(student_number: str) -> dict:
    return send("GET", f"/v1/students/{urllib.parse.quote(student_number, safe='')}/enrolments", None, "enrolments")[1]


def check_drop(student_number: str, course_id: str, term: str) -> dict:
    path = f"/v1/students/{urllib.parse.quote(student_number, safe='')}/enrolments/{segment(course_id, COURSE, 'course code')}/{segment(term, TERM, 'term')}"
    return send("GET", path + "/drop-check", None, "can_drop")[1]


def drop_enrolment(student_number: str, course_id: str, term: str, check_id: str, confirmed) -> dict:
    path = f"/v1/students/{urllib.parse.quote(student_number, safe='')}/enrolments/{segment(course_id, COURSE, 'course code')}/{segment(term, TERM, 'term')}"
    return send("DELETE", path, {"check_id": check_id, "student_confirmed": confirmed}, "status")[1]
