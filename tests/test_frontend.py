"""בדיקות לממשק: פונקציות עזר, ובדיקת עשן לכל דף לכל תפקיד מול שרת אמיתי שרץ ברקע."""
import socket
import threading
import time

import pytest
import uvicorn
from streamlit.testing.v1 import AppTest

import api
import main
import ui
from conftest import NEW_PASSWORD

ADMIN, MANAGER, CONTRACTOR = "שירה", "יוסי הקבלן", "דנה האדריכלית"
FRONTEND = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "frontend.py")


# =========================================================
# פונקציות עזר
# =========================================================
def summary(budget, spent_pct, done_pct, name="פ"):
    return {"name": name, "initial_budget": budget, "spent_pct": spent_pct, "done_pct": done_pct}


def test_project_risk_levels():
    assert ui.project_risk(summary(1000, 85, 20))[0] == "high"   # הרבה כסף, מעט התקדמות
    assert ui.project_risk(summary(1000, 95, 80))[0] == "warn"   # קרוב לחריגה
    assert ui.project_risk(summary(1000, 50, 10)) is None
    assert ui.project_risk(summary(0, 0, 0)) is None             # בלי תקציב - אין חישוב


def test_formatting():
    assert ui.money(1234567.4) == "₪1,234,567"
    assert ui.file_size(512) == "512 B"
    assert ui.file_size(55619) == "54.3 KB"
    assert ui.file_size(3 * 1024 * 1024) == "3.0 MB"
    assert ui.file_size(None) == ""


class FakeResponse:
    def __init__(self, status_code, detail=None):
        self.status_code, self._detail = status_code, detail

    def json(self):
        return {"detail": self._detail}


def test_api_error_messages_are_translated():
    assert api._message(FakeResponse(403, "Permission denied"))[0] == api.STATUS_MESSAGES[403]
    assert api._message(FakeResponse(400, "Current password is incorrect"))[0] == "הסיסמה הנוכחית שגויה."
    assert "דני" in api._message(FakeResponse(422, "Unknown or inactive users: דני"))[0]
    assert "25MB" in api._message(FakeResponse(413, "File larger than 25MB"))[0]
    assert api._message(FakeResponse(429, "Too many failed attempts"))[0] == api.STATUS_MESSAGES[429]
    assert "599" in api._message(FakeResponse(599))[0]


# =========================================================
# בדיקות עשן לממשק מול שרת חי
# =========================================================
@pytest.fixture(scope="module")
def live_api(client):
    """מריץ את השרת האמיתי (uvicorn) ב-thread על פורט פנוי ומכוון אליו את api.py."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    original = api.API_URL
    api.API_URL = f"http://127.0.0.1:{port}"
    yield api.API_URL
    api.API_URL = original
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def sample_project(client, auth):
    res = client.post("/projects/", headers=auth(ADMIN),
                      json={"name": "פרויקט עשן", "initial_budget": 10000, "members": [MANAGER, CONTRACTOR]})
    pid = res.json()["id"]
    client.post(f"/projects/{pid}/tasks/", headers=auth(ADMIN),
                json={"title": "משימה", "assigned_to": CONTRACTOR, "priority": 4})
    client.post(f"/projects/{pid}/expenses/", headers=auth(ADMIN), json={"catalog_id": "101"})
    client.post(f"/projects/{pid}/files/", headers=auth(ADMIN), files={"file": ("שרטוט.pdf", b"%PDF")})
    return pid


def logged_in_app(client, auth, username):
    headers = auth(username)
    me = client.get("/auth/me", headers=headers).json()
    at = AppTest.from_file(FRONTEND, default_timeout=30)
    at.session_state["token"] = headers["Authorization"].split()[1]
    at.session_state["username"] = username
    at.session_state["role"] = me["role"]
    at.session_state["must_change_password"] = me["must_change_password"]
    return at


def section_options(at):
    """האפשרויות של בורר האזורים (segmented_control נקרא button_group ב-AppTest)."""
    return [o.content for o in at.get("button_group")[0].proto.options]


def assert_clean(at, where):
    assert not at.exception, f"{where}: {[e.value for e in at.exception]}"
    assert not at.error, f"{where}: {[e.value for e in at.error]}"


def test_login_page_renders(live_api):
    at = AppTest.from_file(FRONTEND, default_timeout=30).run()
    assert_clean(at, "login")
    assert [t.label for t in at.text_input] == ["שם משתמש", "סיסמה"]


def test_login_flow_through_ui(live_api):
    at = AppTest.from_file(FRONTEND, default_timeout=30).run()
    at.text_input[0].input(ADMIN)
    at.text_input[1].input(NEW_PASSWORD)
    at.button[0].click().run()
    assert at.session_state["username"] == ADMIN and at.session_state["role"] == "admin"


@pytest.mark.parametrize("username", [ADMIN, MANAGER, CONTRACTOR])
def test_every_page_renders_for_every_role(live_api, client, auth, sample_project, username):
    pages = ["views/home.py", "views/projects.py", "views/work_log.py", "views/calendar.py"]
    if username != CONTRACTOR:
        pages.append("views/dashboard.py")
    for page in pages:
        at = logged_in_app(client, auth, username)
        at.switch_page(page).run()
        assert_clean(at, f"{username} {page}")
    at = logged_in_app(client, auth, username)
    at.switch_page("views/projects.py")
    at.query_params["id"] = str(sample_project)
    at.run()
    assert_clean(at, f"{username} project page")
    assert any("פרויקט עשן" in t.value for t in at.title)


def test_ui_hides_actions_by_role(live_api, client, auth, sample_project):
    def project_page(username):
        at = logged_in_app(client, auth, username)
        at.switch_page("views/projects.py")
        at.query_params["id"] = str(sample_project)
        return at.run()

    admin = project_page(ADMIN)
    contractor = project_page(CONTRACTOR)
    admin_buttons = {b.label for b in admin.button}
    contractor_buttons = {b.label for b in contractor.button}
    assert "הוסף משימה לפרויקט" in admin_buttons
    assert "הוסף משימה לפרויקט" not in contractor_buttons
    assert "הגדרות" in section_options(admin)  # האימוג׳י מוצג בנפרד כאייקון
    assert "הגדרות" not in section_options(contractor)
    # הקבלן יכול לשנות סטטוס של המשימה שלו (כפתורי סטטוס = button_group ב-AppTest)
    status = [b for b in contractor.get("button_group") if f"p_{sample_project}_t_" in b.proto.id][0]
    assert not status.proto.disabled
    # ואין לו כפתורי מחיקת משימה
    assert not [b for b in contractor.button if b.key and b.key.startswith(f"p_{sample_project}_del_")]
    assert [b for b in admin.button if b.key and b.key.startswith(f"p_{sample_project}_del_")]


def test_users_page_admin_only(live_api, client, auth):
    admin = logged_in_app(client, auth, ADMIN)
    admin.switch_page("views/users.py").run()
    assert_clean(admin, "admin users page")
    assert len(admin.dataframe[0].value) >= 6


def test_home_shows_my_open_tasks(live_api, client, auth, sample_project):
    at = logged_in_app(client, auth, CONTRACTOR)
    at.switch_page("views/home.py").run()
    assert_clean(at, "contractor home")
    text = " ".join(m.value for m in at.markdown)
    assert "משימה" in text  # המשימה של הקבלן מהפרויקט לדוגמה
    labels = [m.label for m in at.metric]
    assert labels == ["המשימות שלי", "דחופות", "חסימות פתוחות", "פגישות היום"]
    assert int(at.metric[0].value) >= 1


def test_dashboard_hidden_from_contractor(live_api, client, auth):
    at = logged_in_app(client, auth, CONTRACTOR)
    at.switch_page("views/dashboard.py").run()
    # הדף לא רשום בניווט של קבלן בכלל - Streamlit מציג במקומו את מסך הבית
    titles = [t.value for t in at.title]
    assert not any("הנהלה" in t for t in titles) and any("היום" in t for t in titles)


def test_cache_families():
    """ניקוי ממוקד: כל נתיב שייך למשפחה הנכונה, ושינוי מרענן רק את המשפחות שלו."""
    assert api.family_of("/projects/") == api.PROJECT_LISTS
    assert api.family_of("/tasks/open") == api.PROJECT_LISTS
    assert api.family_of("/dashboard/summary") == api.PROJECT_LISTS
    assert api.family_of("/projects/7") == "project:7"
    assert api.family_of("/personal_tasks/") == api.PERSONAL
    assert api.family_of("/users/") == api.USERS
    before = {f: api._version(f) for f in ("project:7", "project:8", api.PROJECT_LISTS, api.PERSONAL)}
    api.invalidate(*api._project_change(7))
    assert api._version("project:7") == before["project:7"] + 1
    assert api._version(api.PROJECT_LISTS) == before[api.PROJECT_LISTS] + 1
    assert api._version("project:8") == before["project:8"]      # פרויקט אחר נשאר ב-cache
    assert api._version(api.PERSONAL) == before[api.PERSONAL]    # וגם היומן האישי


# =========================================================
# חלק 3: סטטוס קבלנים ועריכה בטבלה
# =========================================================
def task(tid, title="t", who="דנה", prio=3, status="ממתין", reason=None, since=None):
    return {"id": tid, "title": title, "assigned_to": who, "priority": prio, "status": status,
            "blocked_reason": reason, "blocked_since": since}


def test_diff_task_table_sends_only_changes():
    tasks = [task("1", "א"), task("2", "ב", status="חסום", reason="ישן")]
    rows = ui.tasks_to_table(tasks).to_dict("records")
    assert ui.diff_task_table(tasks, rows) == ([], [])                     # בלי שינוי - אין מה לשלוח
    rows[0].update({ui.COL_TITLE: " א חדש ", ui.COL_PRIORITY: 5, ui.COL_ASSIGNEE: "אבי"})
    rows[1].update({ui.COL_REASON: "חדש"})
    updates, errors = ui.diff_task_table(tasks, rows)
    assert errors == []
    assert updates == [{"id": "1", "title": "א חדש", "assigned_to": "אבי", "priority": 5},
                       {"id": "2", "blocked_reason": "חדש"}]


def test_diff_task_table_validation():
    tasks = [task("1", "א"), task("2", "ב"), task("3", "ג")]
    rows = ui.tasks_to_table(tasks).to_dict("records")
    rows[0][ui.COL_TITLE] = "  "
    rows[1][ui.COL_STATUS] = "חסום"            # בלי סיבה
    rows[2][ui.COL_PRIORITY] = float("nan")
    updates, errors = ui.diff_task_table(tasks, rows)
    assert updates == [] and len(errors) == 3


def test_contractor_status():
    tasks = [task("1", who="דנה", status="חסום"), task("2", who="דנה", status="בוצע"),
             task("3", who="אבי", status="בתהליך"), task("4", who="יוצא", status="ממתין")]
    logs = [{"author": "יוסי", "log_date": "2026-11-01", "crew": [{"name": "דנה", "workers": 2}]},
            {"author": "דנה", "log_date": "2026-11-05", "crew": []}]
    rows = {r["name"]: r for r in ui.contractor_status(["דנה", "אבי", "רוני"], tasks, logs)}
    assert [r["name"] for r in ui.contractor_status(["דנה", "אבי", "רוני"], tasks, logs)][0] == "דנה"  # חסומים קודם
    assert rows["דנה"]["חסום"] == 1 and rows["דנה"]["done_pct"] == 50 and rows["דנה"]["last_report"] == "2026-11-05"
    assert rows["רוני"]["total"] == 0 and rows["רוני"]["done_pct"] is None and rows["רוני"]["last_report"] is None
    assert "יוצא" in rows  # אחראי שכבר לא שותף עדיין מופיע


def test_open_load_and_days_ago():
    import datetime as dt
    today = dt.date.today()
    open_tasks = [dict(task("1", who="דנה", status="חסום", since=(today - dt.timedelta(days=4)).isoformat()),
                       project_name="פ1"),
                  dict(task("2", who="דנה"), project_name="פ2"), dict(task("3", who="אבי"), project_name="פ1")]
    rows = ui.open_load_by_assignee(open_tasks)
    assert rows[0]["name"] == "דנה" and rows[0]["max_blocked_days"] == 4 and rows[0]["projects"] == {"פ1", "פ2"}
    assert ui.days_ago(None) == "—" and ui.days_ago(today.isoformat()) == "היום"
    assert ui.days_ago((today - dt.timedelta(days=3)).isoformat()) == "לפני 3 ימים"


def project_section(client, auth, username, pid, **state):
    at = logged_in_app(client, auth, username)
    at.switch_page("views/projects.py")
    at.query_params["id"] = str(pid)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def test_team_section_renders(live_api, client, auth, sample_project):
    at = project_section(client, auth, ADMIN, sample_project, project_section="👷 צוות")
    assert_clean(at, "team section")
    names = list(at.dataframe[0].value["שם"])
    assert CONTRACTOR in names and MANAGER in names


def test_table_mode_renders_for_manager(live_api, client, auth, sample_project):
    at = project_section(client, auth, ADMIN, sample_project, **{f"table_mode_{sample_project}": True})
    assert_clean(at, "table mode")
    assert "💾 שמירת השינויים" in [b.label for b in at.button]
    # במצב טבלה אין כרטיסים (ואין כפתורי סטטוס של כרטיסים)
    assert not [b for b in at.get("button_group") if f"p_{sample_project}_t_" in b.proto.id]
    # לקבלן אין מצב טבלה בכלל
    contractor = project_section(client, auth, CONTRACTOR, sample_project)
    assert "✏️ עריכה בטבלה" not in [t.label for t in contractor.toggle]
