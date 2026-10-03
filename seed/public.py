"""The public facts (requirements 5.1): public_values.json plus the programs and courses in public_programs.json."""
import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
PUBLIC_VALUES_FILE = SEED_DIR / "public_values.json"
PUBLIC_PROGRAMS_FILE = SEED_DIR / "public_programs.json"


def load_public() -> dict:
    """Both files merged. Where a course is in both, the first file wins and the two must agree on title, credit points and campus."""
    base = json.loads(PUBLIC_VALUES_FILE.read_text(encoding="utf-8"))
    extra = json.loads(PUBLIC_PROGRAMS_FILE.read_text(encoding="utf-8"))
    for cid, value in extra["courses"].items():
        if cid in base["courses"]:
            for key in ("title", "credit_points", "campus"):
                assert base["courses"][cid][key] == value[key], f"{cid}: {key} differs between the public files"
    courses = {**base["courses"], **{c: v for c, v in extra["courses"].items() if c not in base["courses"]}}
    return {**base, "programs": {**base["programs"], **extra["programs"]}, "courses": courses}
