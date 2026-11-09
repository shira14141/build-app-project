"""שכבת התקשורת בין ממשק Streamlit לשרת FastAPI.

- חיבור HTTP אחד שנשמר בין ריצות (requests.Session) עם timeout לכל בקשה.
- טוקן ההתחברות נשלח אוטומטית בכל בקשה (נשמר ב-session_state של המשתמש).
- שליפות קריאה שמורות ב-cache - לכל משתמש בנפרד (הטוקן הוא חלק מהמפתח).
- ניקוי ממוקד: כל נתיב שייך למשפחה (פרויקט מסוים, רשימות הפרויקטים, יומן אישי, משתמשים).
  שינוי מקדם את מספר הגרסה רק של המשפחות שהוא משפיע עליהן - לכל המשתמשים בבת אחת -
  ושאר הנתונים נשארים ב-cache. למשל: סימון פגישה ביומן לא מוחק את נתוני הפרויקטים.
- כל כשל מתורגם ל-ApiError עם הודעה ברורה בעברית שאפשר להציג למשתמש.
"""
import os

import requests
import streamlit as st


def _api_url():
    """כתובת השרת: משתנה סביבה BUILDAPP_API_URL, או מפתח API_URL ב-st.secrets (Streamlit Cloud),
    ובפיתוח מקומי - 127.0.0.1:8000."""
    if os.environ.get("BUILDAPP_API_URL"):
        return os.environ["BUILDAPP_API_URL"].rstrip("/")
    try:
        return str(st.secrets["API_URL"]).rstrip("/")
    except Exception:  # אין קובץ secrets או אין בו את המפתח
        return "http://127.0.0.1:8000"


API_URL = _api_url()
TIMEOUT = 15        # שניות - שרת תקוע לא יתקע את הממשק
CACHE_TTL = 30          # שניות - רשת ביטחון לשינויים שנעשו מחוץ לממשק הזה
USERS_CACHE_TTL = 300   # רשימת המשתמשים כמעט לא משתנה

STATUS_MESSAGES = {
    400: "הבקשה נדחתה.",
    401: "ההתחברות פגה - יש להתחבר מחדש.",
    403: "אין לך הרשאה לבצע את הפעולה הזו.",
    404: "הפריט לא נמצא - ייתכן שנמחק או שאין לך גישה אליו.",
    409: "הפריט כבר קיים.",
    413: "הקובץ גדול מדי.",
    422: "חלק מהנתונים שנשלחו אינם תקינים.",
    429: "יותר מדי ניסיונות התחברות כושלים. נסה שוב בעוד כמה דקות.",
}
DETAIL_MESSAGES = {
    "Current password is incorrect": "הסיסמה הנוכחית שגויה.",
    "New password must be different": "הסיסמה החדשה חייבת להיות שונה מהנוכחית.",
    "Username already exists": "שם המשתמש כבר קיים.",
    "You cannot demote or deactivate yourself": "אי אפשר להוריד הרשאות או להשבית את המשתמש של עצמך.",
    "Assignee must be a member of the project": "האחראי על המשימה חייב להיות שותף בפרויקט.",
    "Only the uploader or a manager can delete this file": "רק מי שהעלה את הקובץ או מנהל יכולים למחוק אותו.",
    "Password change required": "יש להחליף סיסמה לפני שממשיכים.",
    "Task not found": "אחת המשימות לא נמצאה - ייתכן שנמחקה בינתיים. רענן את הדף.",
    "Work log not found": "הדיווח לא נמצא - ייתכן שנמחק.",
    "Only the author or a manager can delete this work log": "רק מי שכתב את הדיווח או מנהל יכולים למחוק אותו.",
    "Only the author can attach photos to a work log": "רק מי שכתב את הדיווח יכול לצרף אליו תמונות.",
}


class ApiError(Exception):
    def __init__(self, message, status_code=None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


@st.cache_resource
def _session():
    return requests.Session()


def _token():
    return st.session_state.get("token")


def _message(res):
    try:
        detail = res.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, str):
        if detail in DETAIL_MESSAGES:
            return DETAIL_MESSAGES[detail], detail
        if detail.startswith("Blocked reason is required:"):
            return "חסרה סיבת חסימה למשימה:" + detail.split(":", 1)[1], detail
        if detail.startswith("Unknown or inactive users:"):
            return "משתמשים לא מוכרים או מושבתים:" + detail.split(":", 1)[1], detail
        if res.status_code == 413:
            return f"הקובץ גדול מדי ({detail.replace('File larger than', 'מקסימום')}).", detail
    return STATUS_MESSAGES.get(res.status_code, f"שגיאת שרת (קוד {res.status_code})."), detail


def _request(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    token = token or _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = _session().request(method, f"{API_URL}{path}", timeout=TIMEOUT, headers=headers, **kwargs)
    except requests.Timeout as e:
        raise ApiError("השרת לא הגיב בזמן. נסה שוב בעוד רגע.") from e
    except requests.RequestException as e:
        raise ApiError("אין חיבור לשרת הנתונים. ודאי ש-main.py פועל.") from e
    if not res.ok:
        message, detail = _message(res)
        raise ApiError(message, res.status_code, detail)
    return res


# ---------------- ניקוי cache ממוקד ----------------

PROJECT_LISTS = "projects"   # רשימת הפרויקטים, לוח הבקרה והמשימות הפתוחות (סכומים מכל הפרויקטים)
PERSONAL = "personal"
USERS = "users"
PROJECT_LIST_PATHS = ("/projects/", "/dashboard/summary", "/tasks/open")


def project_family(project_id):
    return f"project:{project_id}"


def family_of(path):
    """לאיזו משפחת cache שייך נתיב קריאה."""
    if path in PROJECT_LIST_PATHS:
        return PROJECT_LISTS
    if path.startswith("/projects/"):
        return project_family(path.split("/")[2])
    if path.startswith("/personal_tasks"):
        return PERSONAL
    if path.startswith("/users"):
        return USERS
    return "other"


@st.cache_resource
def _versions():
    """מספר גרסה לכל משפחה - משותף לכל המשתמשים של השרת הזה."""
    return {}


def _version(family):
    return _versions().get(family, 0)


def invalidate(*families):
    versions = _versions()
    for family in families:
        versions[family] = versions.get(family, 0) + 1


def _mutate(method, path, invalidates=(), **kwargs):
    """פעולת כתיבה: שולחת את הבקשה ומרעננת רק את הנתונים שהיא משפיעה עליהם."""
    res = _request(method, path, **kwargs)
    invalidate(*invalidates)
    return res


def _project_change(project_id):
    return (PROJECT_LISTS, project_family(project_id))


def absolute_url(path):
    return f"{API_URL}{path}"


# ---------------- קריאה (שמורה ב-cache, לכל משתמש בנפרד) ----------------

@st.cache_data(ttl=CACHE_TTL, max_entries=1000, show_spinner=False)
def _get(path, token, version):  # version - רק חלק ממפתח ה-cache; גרסה חדשה = שליפה מחדש
    return _request("GET", path, token=token).json()


@st.cache_data(ttl=USERS_CACHE_TTL, max_entries=100, show_spinner=False)
def _get_slow_changing(path, token, version):
    return _request("GET", path, token=token).json()


def _cached(path):
    return _get(path, _token(), _version(family_of(path)))


def get_projects():
    return _cached("/projects/")


def get_project(project_id):
    return _cached(f"/projects/{project_id}")


def get_dashboard():
    return _cached("/dashboard/summary")


def get_open_tasks():
    return _cached("/tasks/open")


def get_personal_tasks():
    return _cached("/personal_tasks/")


def get_users():
    return _get_slow_changing("/users/", _token(), _version(USERS))


# ---------------- התחברות ומשתמשים ----------------

def login(username, password):
    return _request("POST", "/auth/login", token="", json={"username": username, "password": password}).json()


def change_password(current_password, new_password):
    return _request("POST", "/auth/change-password",
                    json={"current_password": current_password, "new_password": new_password}).json()


def create_user(username, password, role):
    _mutate("POST", "/users/", invalidates=(USERS,), json={"username": username, "password": password, "role": role})


def update_user(username, **fields):
    # שינוי תפקיד/השבתה משפיע גם על מה שהמשתמש רואה בפרויקטים
    _mutate("PATCH", f"/users/{username}", invalidates=(USERS, PROJECT_LISTS), json=fields)


# ---------------- פרויקטים ----------------

def create_project(name, budget, members):
    return _mutate("POST", "/projects/", invalidates=(PROJECT_LISTS,),
                   json={"name": name, "initial_budget": budget, "members": members}).json()


def update_project(project_id, **fields):
    _mutate("PATCH", f"/projects/{project_id}", invalidates=_project_change(project_id), json=fields)


def delete_project(project_id):
    _mutate("DELETE", f"/projects/{project_id}", invalidates=_project_change(project_id))


def add_task(project_id, title, assigned_to, priority):
    _mutate("POST", f"/projects/{project_id}/tasks/", invalidates=_project_change(project_id),
            json={"title": title, "assigned_to": assigned_to, "priority": priority})


def delete_task(project_id, task_id):
    _mutate("DELETE", f"/projects/{project_id}/tasks/{task_id}", invalidates=_project_change(project_id))


def set_task_status(project_id, task_id, status, blocked_reason=None):
    _mutate("PATCH", f"/projects/{project_id}/tasks/{task_id}", invalidates=_project_change(project_id),
            json={"status": status, "blocked_reason": blocked_reason})


def bulk_update_tasks(project_id, updates):
    """עריכה בטבלה: כל השינויים בבקשה אחת - הכל נשמר או כלום. מחזיר כמה משימות השתנו."""
    return _mutate("PATCH", f"/projects/{project_id}/tasks/", invalidates=_project_change(project_id),
                   json={"updates": updates}).json()["updated"]


def add_expense(project_id, catalog_id, custom_price):
    _mutate("POST", f"/projects/{project_id}/expenses/", invalidates=_project_change(project_id),
            json={"catalog_id": catalog_id, "custom_price": custom_price})


def delete_expense(project_id, expense_id):
    _mutate("DELETE", f"/projects/{project_id}/expenses/{expense_id}", invalidates=_project_change(project_id))


# ---------------- קבצים ----------------

def upload_file(project_id, filename, content, work_log_id=None):
    data = {"work_log_id": str(work_log_id)} if work_log_id is not None else None
    _mutate("POST", f"/projects/{project_id}/files/", invalidates=_project_change(project_id),
            files={"file": (filename, content)}, data=data)


def delete_file(project_id, file_id):
    _mutate("DELETE", f"/files/{file_id}", invalidates=_project_change(project_id))


# ---------------- יומן עבודה ----------------

def get_work_logs(project_id):
    return _cached(f"/projects/{project_id}/work_logs")  # משפחת הפרויקט - מתרענן עם כל שינוי בו


def create_work_log(project_id, log_date, weather, crew, work_done, issues):
    return _mutate("POST", f"/projects/{project_id}/work_logs", invalidates=(project_family(project_id),),
                   json={"log_date": log_date, "weather": weather, "crew": crew, "work_done": work_done,
                         "issues": issues}).json()["id"]


def delete_work_log(project_id, log_id):
    _mutate("DELETE", f"/projects/{project_id}/work_logs/{log_id}", invalidates=_project_change(project_id))


# ---------------- יומן אישי ----------------

def add_personal_task(title, priority, date_str):
    _mutate("POST", "/personal_tasks/", invalidates=(PERSONAL,),
            json={"title": title, "priority": priority, "date": date_str})


def set_personal_task_status(task_id, status):
    _mutate("PATCH", f"/personal_tasks/{task_id}", invalidates=(PERSONAL,), json={"status": status})


def delete_personal_task(task_id):
    _mutate("DELETE", f"/personal_tasks/{task_id}", invalidates=(PERSONAL,))
