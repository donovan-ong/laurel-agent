"""Demo accounts, password hashing and the local session file. A placeholder for a real login."""
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

ACCOUNTS_FILE = Path(__file__).resolve().parent.parent / "data" / "accounts.json"
SESSION_TTL_SECONDS = 8 * 3600


class SessionError(Exception):
    pass


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), expected_hash)


def load_accounts(path: Path = ACCOUNTS_FILE) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def authenticate(username: str, password: str, accounts: list[dict] | None = None) -> dict | None:
    """Return the matching account, or None. An unknown user still costs one hash."""
    accounts = load_accounts() if accounts is None else accounts
    account = next((a for a in accounts if a["username"] == username), None)
    if account is None:
        hash_password(password, b"\x00" * 16)
        return None
    return account if verify_password(password, account["salt"], account["password_hash"]) else None


def session_path() -> Path:
    override = os.environ.get("PLANNER_SESSION_FILE")
    return Path(override) if override else Path.home() / ".cache" / "study-planner" / "session.json"


def write_session(account: dict, now: float | None = None) -> dict:
    """Store only the username, student number and expiry, never the password."""
    now = time.time() if now is None else now
    session = {"username": account["username"], "student_number": account["student_number"],
               "logged_in_at": now, "expires_at": now + SESSION_TTL_SECONDS}
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session), encoding="utf-8")
    path.chmod(0o600)
    return session


def read_session(now: float | None = None) -> dict | None:
    """The current session, or None if there is none, it is unreadable or it has expired."""
    now = time.time() if now is None else now
    try:
        session = json.loads(session_path().read_text(encoding="utf-8"))
        if session["expires_at"] <= now or not session["student_number"]:
            return None
        return session
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return None


def clear_session() -> bool:
    try:
        session_path().unlink()
        return True
    except FileNotFoundError:
        return False


def require_session() -> dict:
    session = read_session()
    if session is None:
        raise SessionError("Not logged in. Run: python -m planner login")
    return session
