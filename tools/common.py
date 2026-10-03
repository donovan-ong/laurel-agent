"""Data loading, provenance and grade helpers shared by the tools, generator and validator."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
META_FIELDS = ("provenance", "field_provenance", "snapshot_date")

# Grade bands: (grade, lowest mark, grade points). GPA is on a 0 to 4 scale.
GRADE_BANDS = [("HD", 80, 4), ("DI", 70, 3), ("CR", 60, 2), ("PA", 50, 1), ("NN", 0, 0)]


_cache: dict = {}


def load(name: str):
    """A data file, parsed once and reused until the file changes. Callers must not modify what they get."""
    path = DATA_DIR / name
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _cache:
        _cache.clear() if len(_cache) > 64 else None
        _cache[key] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[key]


def strip_meta(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in META_FIELDS}


def source(record: dict, file: str) -> dict:
    """The source block every successful response carries (requirements section 6)."""
    provenance = record["provenance"]
    if provenance == "synthetic" and "from_public_page" in record.get("field_provenance", {}).values():
        provenance = "mixed"
    return {"provenance": provenance, "snapshot_date": record["snapshot_date"], "file": file}


def not_found(reason: str) -> dict:
    return {"found": False, "reason": reason}


def grade_for(mark: int) -> str:
    return next(grade for grade, low, _ in GRADE_BANDS if mark >= low)


def grade_points(mark: int) -> int:
    return next(points for _, low, points in GRADE_BANDS if mark >= low)


def round_one_decimal(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _weighted(results: list[dict], credit_points: dict, value) -> float | None:
    total_cp = sum(credit_points[r["course_id"]] for r in results)
    if not total_cp:
        return None
    return round_one_decimal(sum(value(r["mark"]) * credit_points[r["course_id"]] for r in results) / total_cp)


def gpa(results: list[dict], credit_points: dict) -> float | None:
    """Credit-point-weighted grade points on a 0 to 4 scale, one decimal. Fails count."""
    return _weighted(results, credit_points, grade_points)


def wam(results: list[dict], credit_points: dict) -> float | None:
    """Credit-point-weighted mean mark, one decimal. Fails count."""
    return _weighted(results, credit_points, lambda mark: mark)


def today() -> date:
    """Today's date in Melbourne, where the university calendar applies."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Melbourne")).date()
    except (ImportError, KeyError, OSError):
        return datetime.now(timezone(timedelta(hours=10))).date()


STOPWORDS = {"the", "and", "of", "to", "in", "a", "an"}


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def find_courses(query: str, courses: list[dict]):
    """The courses a query means, and how it matched: an exact code or title, the query as a phrase in the title, else every word in it."""
    q = normalise(query)
    for c in courses:
        if q in (c["course_id"].lower(), c["handbook_code"].lower()):
            return [c], "course code" if q == c["course_id"].lower() else "Handbook code"
    exact = [c for c in courses if normalise(c["title"]) == q]
    if exact:
        return exact, "title"
    phrase = re.compile(r"(?<![a-z0-9])" + re.escape(q) + r"(?![a-z0-9])")
    in_title = [c for c in courses if q and phrase.search(normalise(c["title"]))]
    if in_title:
        return in_title, "phrase in the title"
    words = [w for w in re.split(r"[^a-z0-9]+", q) if len(w) >= 2 and w not in STOPWORDS]
    if not words:
        return [], None
    return [c for c in courses if all(w in c["title"].lower() for w in words)], "words in the title"


NOT_LOGGED_IN = "Nobody is logged in. Ask the student to log in with the command line tool, then try again."


def current_student(context: object):
    """The logged-in student's record from the run context, or a not-found response."""
    number = context.request_context.get("student_number") if context and context.request_context else None
    if not number:
        return None, not_found(NOT_LOGGED_IN)
    try:
        student = next((s for s in load("students.json") if s["student_number"] == number), None)
    except (FileNotFoundError, ValueError):
        return None, not_found("Student data is not available.")
    if student is None:
        return None, not_found("No student record was found for this login.")
    return student, None
