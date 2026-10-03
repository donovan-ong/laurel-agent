"""Assemble build/package with only the tools and data, for `orchestrate tools import -p`.

The ADK uploads every file under the package root, so the repo root cannot be used.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "package"
NOT_PACKAGED = {"accounts.json"}  # login credentials stay out of the cloud package
sys.path.insert(0, str(ROOT / "seed"))
import validate  # noqa: E402


def main() -> int:
    errors = validate.validate(validate.load_data(ROOT / "data"))
    if errors:
        print("Data failed validation, not packaging:\n  " + "\n  ".join(errors))
        return 1
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "tools").mkdir(parents=True)
    (OUT / "data").mkdir()
    for f in (ROOT / "tools").glob("*.py"):
        shutil.copy(f, OUT / "tools" / f.name)
    for f in (ROOT / "data").glob("*.json"):
        if f.name not in NOT_PACKAGED:
            shutil.copy(f, OUT / "data" / f.name)
    (OUT / "requirements.txt").write_text("", encoding="utf-8")
    print(f"Packaged to {OUT.relative_to(ROOT)}")
    print("Import a tool, for example:")
    print("  orchestrate tools import -k python -f build/package/tools/student_tools.py "
          "-p build/package -r build/package/requirements.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
