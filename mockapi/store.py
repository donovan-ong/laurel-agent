"""What the service remembers while it runs: enrolments made and classes dropped. Lost on restart or reset."""
import threading
from collections import Counter

from tools import enrolment as enr


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.made: dict[str, list[dict]] = {}
        self.dropped: dict[str, dict[tuple, list]] = {}

    def reset(self):
        with self.lock:
            self.made, self.dropped = {}, {}

    def enrolments(self, student: dict) -> list[dict]:
        """The student's record, less what they dropped, plus what they enrolled in here."""
        n = student["student_number"]
        return enr.effective_enrolments(student, self.extra(n), list(self.dropped.get(n, {})))

    def extra(self, number: str) -> list[dict]:
        return [{k: e[k] for k in ("course_id", "term", "class_ids")} for e in self.made.get(number, [])]

    def taken(self) -> dict[str, int]:
        """Seats taken (positive) or freed (negative) by class number, across every student."""
        seats = Counter()
        for made in self.made.values():
            for e in made:
                seats.update(e["class_ids"])
        for dropped in self.dropped.values():
            for class_ids in dropped.values():
                seats.subtract(class_ids)
        return {c: n for c, n in seats.items() if n}

    def state(self, student: dict) -> dict:
        """Keyword arguments that make the enrolment logic use this state."""
        n = student["student_number"]
        return {"extra_enrolments": self.extra(n), "dropped": list(self.dropped.get(n, {})), "taken": self.taken()}

    def add(self, student: dict, summary: dict, reference: str, at: str) -> None:
        class_ids = [summary["lecture"]["class_id"], summary["workshop"]["class_id"]]
        self.made.setdefault(student["student_number"], []).append(
            {"course_id": summary["course_id"], "term": summary["term"], "class_ids": class_ids,
             "reference": reference, "at": at})

    def remove(self, student: dict, course_id: str, term: str) -> None:
        n = student["student_number"]
        made = self.made.get(n, [])
        left = [e for e in made if (e["course_id"], e["term"]) != (course_id, term)]
        if len(left) != len(made):
            self.made[n] = left
            return
        record = next(e for e in student["current_enrolments"] if (e["course_id"], e["term"]) == (course_id, term))
        self.dropped.setdefault(n, {})[(course_id, term)] = record["class_ids"]
