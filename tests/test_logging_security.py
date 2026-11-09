"""בדיקות ללוגים, למזהה בקשה, לבדיקת חיות ולנעילה אחרי ניסיונות התחברות כושלים."""
import os
from pathlib import Path

from conftest import NEW_PASSWORD

ADMIN = "שירה"


def read_log():
    return (Path(os.environ["BUILDAPP_LOG_DIR"]) / "buildapp.log").read_text(encoding="utf-8")


def test_health_checks_database(client):
    res = client.get("/health")
    assert res.status_code == 200 and res.json() == {"status": "ok", "database": "ok"}


def test_request_id_header_and_log_line(client, auth):
    res = client.get("/projects/", headers={**auth(ADMIN), "X-Request-ID": "test-rid-123"})
    assert res.headers["X-Request-ID"] == "test-rid-123"
    assert client.get("/health").headers["X-Request-ID"]  # נוצר אוטומטית כשלא נשלח
    line = next(line for line in read_log().splitlines() if "rid=test-rid-123" in line)
    assert "GET /projects/ -> 200" in line and f"user={ADMIN}" in line


def test_log_never_contains_secrets(client, auth):
    """חתימות של קישורי קבצים (query string), טוקנים וסיסמאות לא נכתבים ללוג."""
    pid = client.post("/projects/", headers=auth(ADMIN), json={"name": "לוג", "initial_budget": 1}).json()["id"]
    client.post(f"/projects/{pid}/files/", headers=auth(ADMIN), files={"file": ("a.txt", b"a")})
    view_url = client.get(f"/projects/{pid}", headers=auth(ADMIN)).json()["file_list"][0]["view_url"]
    assert client.get(view_url).status_code == 200
    log = read_log()
    assert "sig=" not in log
    assert auth(ADMIN)["Authorization"].split()[1] not in log
    assert NEW_PASSWORD not in log


def test_audit_log_records_sensitive_actions(client, auth):
    client.post("/auth/login", json={"username": ADMIN, "password": "wrong-password"})
    pid = client.post("/projects/", headers=auth(ADMIN), json={"name": "למחיקה", "initial_budget": 1}).json()["id"]
    client.delete(f"/projects/{pid}", headers=auth(ADMIN))
    log = read_log()
    assert f"Login failed user={ADMIN}" in log
    assert f"Project deleted id={pid}" in log


def test_login_lockout_after_repeated_failures(client, auth):
    client.post("/users/", headers=auth(ADMIN),
                json={"username": "נעילה", "password": "Temp-Pass-2026", "role": "viewer"})
    for _ in range(5):
        assert client.post("/auth/login", json={"username": "נעילה", "password": "wrong"}).status_code == 401
    locked = client.post("/auth/login", json={"username": "נעילה", "password": "Temp-Pass-2026"})
    assert locked.status_code == 429  # נעול גם עם הסיסמה הנכונה
    assert int(locked.headers["Retry-After"]) > 0
    # משתמש אחר לא מושפע
    assert client.post("/auth/login", json={"username": ADMIN, "password": NEW_PASSWORD}).status_code == 200


def test_limiter_unlocks_after_window():
    from server.ratelimit import LoginLimiter
    limiter = LoginLimiter(max_failures=2, window_seconds=0.2)
    limiter.record_failure("x")
    limiter.record_failure("x")
    assert limiter.retry_after("x") > 0
    import time
    time.sleep(0.3)
    assert limiter.retry_after("x") == 0
    limiter.record_failure("y")
    limiter.reset("y")
    assert limiter.retry_after("y") == 0
