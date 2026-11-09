"""הגדרות לבדיקות: כל ריצה מקבלת מסד ותיקיית קבצים זמניים - המסד האמיתי לא נוגע.

הרצה (מתיקיית הפרויקט):  python -m pytest -q
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="buildapp-tests-"))
os.environ["BUILDAPP_DB_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["BUILDAPP_UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["BUILDAPP_SECRET"] = "test-secret-key-that-is-long-enough-for-hs256"
os.environ["BUILDAPP_MAX_UPLOAD_MB"] = "1"
os.environ["BUILDAPP_LOG_DIR"] = str(_tmp / "logs")
TMP_DIR = _tmp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

NEW_PASSWORD = "Strong-Pass-2026"
SEED_PASSWORDS = {"שירה": "admin"}  # לשאר המשתמשים מהמיגרציה הסיסמה ההתחלתית היא 1234


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as c:  # with = מריץ את ה-lifespan, כלומר את המיגרציות על המסד הזמני
        yield c


@pytest.fixture(scope="session")
def upload_dir():
    return Path(os.environ["BUILDAPP_UPLOAD_DIR"])


@pytest.fixture(scope="session")
def auth(client):
    """auth("שירה") -> כותרות Authorization למשתמש (כולל החלפת סיסמה ראשונה, פעם אחת)."""
    tokens = {}

    def get(username):
        if username not in tokens:
            res = client.post("/auth/login", json={"username": username, "password": NEW_PASSWORD})
            if res.status_code == 401:
                first = SEED_PASSWORDS.get(username, "1234")
                res = client.post("/auth/login", json={"username": username, "password": first})
                assert res.status_code == 200, res.text
                headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
                changed = client.post("/auth/change-password", headers=headers,
                                      json={"current_password": first, "new_password": NEW_PASSWORD})
                assert changed.status_code == 200, changed.text
            else:
                headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
            tokens[username] = headers
        return tokens[username]

    return get
