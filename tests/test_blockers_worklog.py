"""בדיקות לסטטוס 'חסום' וליומן העבודה."""
import datetime as dt

from conftest import SEED_PASSWORDS
from test_api import ADMIN, CONTRACTOR, CONTRACTOR2, MANAGER, MANAGER2, make_project

TODAY = dt.date.today().isoformat()


def add_task(client, auth, pid, assignee=CONTRACTOR, title="משימה"):
    res = client.post(f"/projects/{pid}/tasks/", headers=auth(ADMIN),
                      json={"title": title, "assigned_to": assignee, "priority": 3})
    return res.json()["id"]


def get_task(client, auth, pid, tid):
    return next(t for t in client.get(f"/projects/{pid}", headers=auth(ADMIN)).json()["task_list"] if t["id"] == tid)


# =========================================================
# סטטוס "חסום"
# =========================================================
def test_blocking_requires_reason_and_records_date(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    tid = add_task(client, auth, pid)
    h = auth(CONTRACTOR)  # קבלן יכול לחסום משימה שלו
    assert client.patch(f"/projects/{pid}/tasks/{tid}", headers=h, json={"status": "חסום"}).status_code == 422
    assert client.patch(f"/projects/{pid}/tasks/{tid}", headers=h,
                        json={"status": "חסום", "blocked_reason": "   "}).status_code == 422
    res = client.patch(f"/projects/{pid}/tasks/{tid}", headers=h,
                       json={"status": "חסום", "blocked_reason": " ממתינים לאישור חשמל "})
    assert res.status_code == 200
    task = get_task(client, auth, pid, tid)
    assert task["status"] == "חסום" and task["blocked_reason"] == "ממתינים לאישור חשמל"
    assert task["blocked_since"] == TODAY

    summary = next(p for p in client.get("/projects/", headers=auth(ADMIN)).json() if p["id"] == pid)
    assert summary["blocked"] == 1
    open_task = next(t for t in client.get("/tasks/open", headers=h).json() if t["id"] == tid)
    assert open_task["blocked_reason"] == "ממתינים לאישור חשמל"


def test_updating_reason_keeps_date_and_unblocking_clears(client, auth, monkeypatch):
    pid = make_project(client, auth, members=[CONTRACTOR])
    tid = add_task(client, auth, pid)
    h = auth(ADMIN)
    client.patch(f"/projects/{pid}/tasks/{tid}", headers=h, json={"status": "חסום", "blocked_reason": "א"})
    # מזייפים שהחסימה התחילה לפני 5 ימים - עדכון הסיבה לא אמור לאפס את התאריך
    from server.db import SessionLocal
    from server.models import Task
    with SessionLocal() as db:
        db.get(Task, tid).blocked_since = dt.date.today() - dt.timedelta(days=5)
        db.commit()
    client.patch(f"/projects/{pid}/tasks/{tid}", headers=h, json={"status": "חסום", "blocked_reason": "ב"})
    task = get_task(client, auth, pid, tid)
    assert task["blocked_reason"] == "ב" and task["blocked_since"] == (dt.date.today() - dt.timedelta(days=5)).isoformat()

    client.patch(f"/projects/{pid}/tasks/{tid}", headers=h, json={"status": "בתהליך"})
    task = get_task(client, auth, pid, tid)
    assert task["status"] == "בתהליך" and task["blocked_reason"] is None and task["blocked_since"] is None


def test_contractor_cannot_block_others_task(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR, CONTRACTOR2])
    tid = add_task(client, auth, pid, assignee=CONTRACTOR2)
    res = client.patch(f"/projects/{pid}/tasks/{tid}", headers=auth(CONTRACTOR),
                       json={"status": "חסום", "blocked_reason": "x"})
    assert res.status_code == 403


def test_personal_tasks_have_no_blocked_status(client, auth):
    tid = client.post("/personal_tasks/", headers=auth(CONTRACTOR),
                      json={"title": "פגישה", "priority": 3, "date": TODAY}).json()["id"]
    assert client.patch(f"/personal_tasks/{tid}", headers=auth(CONTRACTOR),
                        json={"status": "חסום"}).status_code == 422


# =========================================================
# יומן עבודה
# =========================================================
def log_payload(**overrides):
    payload = {"log_date": TODAY, "weather": "☀️ בהיר", "work_done": "יציקת רצפה בקומה 2",
               "issues": "עיכוב באספקת ברזל",
               "crew": [{"name": CONTRACTOR, "workers": 3}, {"name": "צוות חיצוני", "workers": 0}]}
    payload.update(overrides)
    return payload


def test_work_log_create_and_list(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    res = client.post(f"/projects/{pid}/work_logs", headers=auth(CONTRACTOR), json=log_payload())
    assert res.status_code == 201, res.text
    logs = client.get(f"/projects/{pid}/work_logs", headers=auth(ADMIN)).json()
    assert len(logs) == 1
    log = logs[0]
    assert log["author"] == CONTRACTOR and log["log_date"] == TODAY and log["weather"] == "☀️ בהיר"
    assert log["crew"] == [{"name": CONTRACTOR, "workers": 3}]  # שורה עם 0 עובדים לא נשמרת
    assert log["total_workers"] == 3 and log["issues"] == "עיכוב באספקת ברזל" and log["photos"] == []


def test_work_log_validation(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    h = auth(CONTRACTOR)
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    for bad in [log_payload(log_date=tomorrow), log_payload(work_done="  "), log_payload(weather="שלג"),
                log_payload(crew=[{"name": "x", "workers": -1}]), log_payload(crew=[{"name": " ", "workers": 2}])]:
        assert client.post(f"/projects/{pid}/work_logs", headers=h, json=bad).status_code == 422, bad


def test_work_log_permissions(client, auth):
    if "צופה יומן" not in SEED_PASSWORDS:
        client.post("/users/", headers=auth(ADMIN),
                    json={"username": "צופה יומן", "password": "Temp-Pass-2026", "role": "viewer"})
        SEED_PASSWORDS["צופה יומן"] = "Temp-Pass-2026"
    pid = make_project(client, auth, members=[CONTRACTOR, CONTRACTOR2, "צופה יומן"])
    # צופה רואה אבל לא מדווח; מי שלא שותף לא רואה בכלל
    assert client.post(f"/projects/{pid}/work_logs", headers=auth("צופה יומן"), json=log_payload()).status_code == 403
    assert client.get(f"/projects/{pid}/work_logs", headers=auth("צופה יומן")).status_code == 200
    assert client.get(f"/projects/{pid}/work_logs", headers=auth(MANAGER2)).status_code == 404
    assert client.post(f"/projects/{pid}/work_logs", headers=auth(MANAGER2), json=log_payload()).status_code == 404
    # מחיקה: לא קבלן אחר; כן מי שכתב
    lid = client.post(f"/projects/{pid}/work_logs", headers=auth(CONTRACTOR), json=log_payload()).json()["id"]
    assert client.delete(f"/projects/{pid}/work_logs/{lid}", headers=auth(CONTRACTOR2)).status_code == 403
    assert client.delete(f"/projects/{pid}/work_logs/{lid}", headers=auth(CONTRACTOR)).status_code == 204
    assert client.get(f"/projects/{pid}/work_logs", headers=auth(ADMIN)).json() == []


def test_work_log_photos(client, auth, upload_dir):
    pid = make_project(client, auth, members=[CONTRACTOR, CONTRACTOR2])
    other_pid = make_project(client, auth, members=[CONTRACTOR])
    lid = client.post(f"/projects/{pid}/work_logs", headers=auth(CONTRACTOR), json=log_payload()).json()["id"]
    photo = b"\x89PNG fake image"
    ok = client.post(f"/projects/{pid}/files/", headers=auth(CONTRACTOR), data={"work_log_id": str(lid)},
                     files={"file": ("אתר.png", photo, "image/png")})
    assert ok.status_code == 201, ok.text
    # לא לדיווח של מישהו אחר, ולא לדיווח מפרויקט אחר
    assert client.post(f"/projects/{pid}/files/", headers=auth(CONTRACTOR2), data={"work_log_id": str(lid)},
                       files={"file": ("x.png", photo)}).status_code == 403
    assert client.post(f"/projects/{other_pid}/files/", headers=auth(CONTRACTOR), data={"work_log_id": str(lid)},
                       files={"file": ("x.png", photo)}).status_code == 404

    log = client.get(f"/projects/{pid}/work_logs", headers=auth(CONTRACTOR)).json()[0]
    assert [p["filename"] for p in log["photos"]] == ["אתר.png"]
    assert client.get(log["photos"][0]["view_url"]).content == photo
    file_id = log["photos"][0]["id"]
    assert (upload_dir / str(pid) / file_id).exists()

    # מנהל מוחק את הדיווח - גם התמונה נמחקת מהדיסק
    assert client.delete(f"/projects/{pid}/work_logs/{lid}", headers=auth(ADMIN)).status_code == 204
    assert not (upload_dir / str(pid) / file_id).exists()
    assert file_id not in [f["id"] for f in client.get(f"/projects/{pid}", headers=auth(ADMIN)).json()["file_list"]]


def test_delete_project_with_work_logs_and_photos(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    lid = client.post(f"/projects/{pid}/work_logs", headers=auth(CONTRACTOR), json=log_payload()).json()["id"]
    client.post(f"/projects/{pid}/files/", headers=auth(CONTRACTOR), data={"work_log_id": str(lid)},
                files={"file": ("a.png", b"img")})
    assert client.delete(f"/projects/{pid}", headers=auth(ADMIN)).status_code == 204
    assert client.get(f"/projects/{pid}/work_logs", headers=auth(ADMIN)).status_code == 404


def test_manager_can_log_on_own_project(client, auth):
    pid = make_project(client, auth, user=MANAGER, members=[CONTRACTOR])
    assert client.post(f"/projects/{pid}/work_logs", headers=auth(MANAGER), json=log_payload()).status_code == 201


# =========================================================
# פונקציות ממשק
# =========================================================
def test_validate_work_log_helper():
    from worklog_ui import CREW_NAME, CREW_WORKERS, validate_work_log
    today = dt.date.today()
    rows = [{CREW_NAME: "דנה", CREW_WORKERS: 3}, {CREW_NAME: "", CREW_WORKERS: None},  # שורה ריקה - מדולגת
            {CREW_NAME: "אבי", CREW_WORKERS: 0}]                                       # 0 עובדים - לא נשמר
    assert validate_work_log(today, rows, "יציקה") == ([], [{"name": "דנה", "workers": 3}])
    errors, _ = validate_work_log(today + dt.timedelta(days=1), [{CREW_NAME: "", CREW_WORKERS: 2},
                                                                   {CREW_NAME: "x", CREW_WORKERS: 2.5}], "")
    assert len(errors) == 4  # עתידי, חסר תיאור, חסר שם, מספר לא שלם


def test_blocked_text_helper():
    import ui
    today = dt.date.today()
    assert ui.blocked_days({"blocked_since": None}) == 0
    assert "מהיום" in ui.blocked_text({"blocked_since": today.isoformat(), "blocked_reason": "x"})
    assert "מאתמול" in ui.blocked_text({"blocked_since": (today - dt.timedelta(days=1)).isoformat(),
                                        "blocked_reason": "x"})
    assert "4 ימים" in ui.blocked_text({"blocked_since": (today - dt.timedelta(days=4)).isoformat(),
                                        "blocked_reason": "x"})



# =========================================================
# עריכה מרוכזת בטבלה
# =========================================================
def bulk(client, auth, user, pid, updates):
    return client.patch(f"/projects/{pid}/tasks/", headers=auth(user), json={"updates": updates})


def test_bulk_update_by_manager(client, auth):
    pid = make_project(client, auth, user=MANAGER, members=[CONTRACTOR, CONTRACTOR2])
    t1 = add_task(client, auth, pid, title="א")
    t2 = add_task(client, auth, pid, title="ב")
    res = bulk(client, auth, MANAGER, pid, [
        {"id": t1, "title": " שם חדש ", "priority": 5, "assigned_to": CONTRACTOR2},
        {"id": t2, "status": "חסום", "blocked_reason": "אין חומר"},
    ])
    assert res.status_code == 200 and res.json() == {"updated": 2}
    a, b = get_task(client, auth, pid, t1), get_task(client, auth, pid, t2)
    assert (a["title"], a["priority"], a["assigned_to"]) == ("שם חדש", 5, CONTRACTOR2)
    assert b["status"] == "חסום" and b["blocked_reason"] == "אין חומר" and b["blocked_since"] == TODAY
    # שליחה חוזרת של אותם ערכים - שום דבר לא משתנה
    assert bulk(client, auth, MANAGER, pid, [{"id": t1, "title": "שם חדש", "priority": 5}]).json() == {"updated": 0}


def test_bulk_update_is_all_or_nothing(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    t1 = add_task(client, auth, pid, title="א")
    t2 = add_task(client, auth, pid, title="ב")
    res = bulk(client, auth, ADMIN, pid, [{"id": t1, "priority": 1},
                                          {"id": t2, "status": "חסום"}])          # חסום בלי סיבה
    assert res.status_code == 422
    assert get_task(client, auth, pid, t1)["priority"] == 3                       # גם השינוי התקין לא נשמר
    assert bulk(client, auth, ADMIN, pid, [{"id": t1, "assigned_to": MANAGER2}]).status_code == 422  # לא שותף
    assert bulk(client, auth, ADMIN, pid, [{"id": t1, "title": "   "}]).status_code == 422
    assert bulk(client, auth, ADMIN, pid, [{"id": "nope", "priority": 1}]).status_code == 404


def test_bulk_update_permissions(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR, CONTRACTOR2])
    mine = add_task(client, auth, pid, assignee=CONTRACTOR)
    other = add_task(client, auth, pid, assignee=CONTRACTOR2)
    # קבלן: סטטוס של משימה שלו - כן; כותרת/דחיפות או משימה של אחר - לא
    assert bulk(client, auth, CONTRACTOR, pid, [{"id": mine, "status": "בתהליך"}]).status_code == 200
    assert bulk(client, auth, CONTRACTOR, pid, [{"id": mine, "priority": 5}]).status_code == 403
    assert bulk(client, auth, CONTRACTOR, pid, [{"id": other, "status": "בוצע"}]).status_code == 403
    # מי שלא שותף בפרויקט לא רואה אותו בכלל
    assert bulk(client, auth, MANAGER2, pid, [{"id": mine, "status": "בוצע"}]).status_code == 404


def test_bulk_update_reason_only_keeps_blocked_date(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    tid = add_task(client, auth, pid)
    bulk(client, auth, ADMIN, pid, [{"id": tid, "status": "חסום", "blocked_reason": "א"}])
    assert bulk(client, auth, ADMIN, pid, [{"id": tid, "blocked_reason": "ב"}]).json() == {"updated": 1}
    task = get_task(client, auth, pid, tid)
    assert task["blocked_reason"] == "ב" and task["status"] == "חסום"
