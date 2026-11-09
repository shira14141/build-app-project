"""רכיבי ממשק ועזרים משותפים לכל הדפים."""
from datetime import date

import streamlit as st

import api
from constants import (MIN_PASSWORD_LENGTH, OVER_BUDGET_WARN_PCT, PERM_MANAGE_TASKS, PERM_UPDATE_OWN_TASKS,
                       PERSONAL_STATUSES, RISK_DONE_PCT, RISK_SPENT_PCT, STATUSES, STATUS_BLOCKED, STATUS_DONE,
                       STATUS_IN_PROGRESS, STATUS_PENDING, URGENT_PRIORITY, has_permission)

SESSION_KEYS = ("token", "username", "role", "must_change_password")


# =========================================================
# משתמש מחובר והרשאות
# =========================================================
def start_session(login_response):
    user = login_response["user"]
    st.session_state.update(token=login_response["access_token"], username=user["username"], role=user["role"],
                            must_change_password=user["must_change_password"])


def end_session():
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)


def is_logged_in():
    return bool(st.session_state.get("token"))


def current_user():
    return st.session_state.get("username")


def can(permission):
    """הממשק מסתיר כפתורים לפי ההרשאות - אבל הבדיקה האמיתית נעשית בשרת."""
    return has_permission(st.session_state.get("role"), permission)


def can_update_task(task):
    return can(PERM_MANAGE_TASKS) or (can(PERM_UPDATE_OWN_TASKS) and task["assigned_to"] == current_user())


# =========================================================
# הודעות, טעינה ופעולות
# =========================================================
def flash(kind, message):
    """שומר הודעה שתוצג בריצה הבאה (אחרי הרענון שמגיע מיד אחרי פעולה)."""
    st.session_state["flash"] = (kind, message)


def show_flash():
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        if kind == "success":
            st.toast(message, icon="✅")
        else:
            st.error(message)


def _handle_session_errors(error):
    """טוקן שפג תוקפו או משתמש שהושבת -> חזרה למסך ההתחברות. מחזיר True אם טופל."""
    if error.status_code == 401:
        end_session()
        flash("error", "ההתחברות פגה או שהמשתמש הושבת - יש להתחבר מחדש.")
        return True
    if error.detail == "Password change required":
        st.session_state["must_change_password"] = True
        return True
    return False


def load(fn, *args):
    """מחזיר (נתונים, None) או (None, הודעת שגיאה) - בלי לזרוק חריגה לתוך המסך."""
    try:
        return fn(*args), None
    except api.ApiError as e:
        if _handle_session_errors(e):
            st.rerun()
        return None, str(e)


def action(fn, *args, success=None, **kwargs):
    """מריץ פעולת כתיבה. מתאים ל-on_click של כפתור (Streamlit מרענן אוטומטית אחריו).
    מחזיר True בהצלחה."""
    try:
        fn(*args, **kwargs)
    except api.ApiError as e:
        if not _handle_session_errors(e):
            flash("error", str(e))
        return False
    if success:
        flash("success", success)
    return True


def submit_action(fn, *args, success=None, **kwargs):
    """מריץ פעולת כתיבה מתוך טופס ומרענן את כל המסך כדי להציג את הנתונים החדשים."""
    action(fn, *args, success=success, **kwargs)
    st.rerun()


# =========================================================
# חישובים משותפים
# =========================================================
def money(amount):
    return f"₪{amount:,.0f}"


def file_size(num_bytes):
    if num_bytes is None:
        return ""
    for unit in ("B", "KB", "MB"):
        if num_bytes < 1024 or unit == "MB":
            return f"{num_bytes:,.0f} {unit}" if unit == "B" else f"{num_bytes:,.1f} {unit}"
        num_bytes /= 1024


def project_risk(summary):
    """מחזיר (רמה, הודעה) או None. רמה: 'high' / 'warn'. הסכומים עצמם מחושבים בשרת."""
    if summary["initial_budget"] <= 0:
        return None
    spent, done = summary["spent_pct"], summary["done_pct"]
    if spent > RISK_SPENT_PCT and done < RISK_DONE_PCT:
        return "high", (f"🚨 **סיכון גבוה '{summary['name']}':** נוצלו {spent:.0f}% מהתקציב, "
                        f"אבל רק {done:.0f}% מהמשימות הושלמו!")
    if spent > OVER_BUDGET_WARN_PCT:
        return "warn", f"⚠️ **חריגת תקציב קרובה '{summary['name']}':** נוצלו {spent:.0f}% מהתקציב ההתחלתי."
    return None


def contractor_status(members, tasks, logs):
    """סטטוס לכל שותף בפרויקט: משימות לפי סטטוס, התקדמות ומתי דיווח לאחרונה ביומן.
    'דיווח אחרון' = הדיווח האחרון שהוא כתב או שהצוות שלו מופיע בו. ממוין: חסומים קודם."""
    rows = {}
    for name in list(members) + [t["assigned_to"] for t in tasks]:  # גם אחראים שכבר לא שותפים
        rows.setdefault(name, {"name": name, STATUS_PENDING: 0, STATUS_IN_PROGRESS: 0, STATUS_BLOCKED: 0,
                               STATUS_DONE: 0, "last_report": None})
    for t in tasks:
        rows[t["assigned_to"]][t["status"]] += 1
    for log in logs:
        for name in {log["author"], *(c["name"] for c in log.get("crew", []))}:
            if name in rows and (rows[name]["last_report"] is None or log["log_date"] > rows[name]["last_report"]):
                rows[name]["last_report"] = log["log_date"]
    for row in rows.values():
        total = sum(row[s] for s in STATUSES)
        row["total"] = total
        row["done_pct"] = row[STATUS_DONE] / total * 100 if total else None
    return sorted(rows.values(), key=lambda r: (-r[STATUS_BLOCKED], -(r[STATUS_PENDING] + r[STATUS_IN_PROGRESS]),
                                                 r["name"]))


COL_TITLE, COL_ASSIGNEE, COL_PRIORITY, COL_STATUS, COL_REASON = "משימה", "אחראי", "דחיפות", "סטטוס", "סיבת חסימה"
TABLE_COLUMNS = [COL_TITLE, COL_ASSIGNEE, COL_PRIORITY, COL_STATUS, COL_REASON]  # עמודת id מוסתרת


def tasks_to_table(tasks):
    import pandas as pd
    return pd.DataFrame([{"id": t["id"], COL_TITLE: t["title"], COL_ASSIGNEE: t["assigned_to"],
                          COL_PRIORITY: t["priority"], COL_STATUS: t["status"],
                          COL_REASON: t.get("blocked_reason") or ""} for t in tasks],
                        columns=["id", *TABLE_COLUMNS])


def diff_task_table(tasks, edited_rows):
    """משווה את הטבלה הערוכה למשימות המקוריות. מחזיר (עדכונים לשליחה, שגיאות בעברית).
    נשלחים רק שדות שהשתנו; ולידציה כאן חוסכת בקשה שתיכשל (השרת בודק שוב)."""
    original = {t["id"]: t for t in tasks}
    updates, errors = [], []
    for row in edited_rows:
        task = original.get(row.get("id"))
        if task is None:
            continue
        title = str(row.get(COL_TITLE) or "").strip()
        reason = str(row.get(COL_REASON) or "").strip()
        status = row.get(COL_STATUS)
        priority = row.get(COL_PRIORITY)
        if not title:
            errors.append(f"למשימה '{task['title']}' חסרה כותרת.")
            continue
        if status == STATUS_BLOCKED and not reason:
            errors.append(f"המשימה '{title}' מסומנת כחסומה - יש לכתוב סיבת חסימה.")
            continue
        if priority is None or priority != priority or not 1 <= int(priority) <= 5:  # priority != priority -> NaN
            errors.append(f"דחיפות של '{title}' חייבת להיות בין 1 ל-5.")
            continue
        change = {}
        if title != task["title"]:
            change["title"] = title
        if row.get(COL_ASSIGNEE) and row.get(COL_ASSIGNEE) != task["assigned_to"]:
            change["assigned_to"] = row[COL_ASSIGNEE]
        if int(priority) != task["priority"]:
            change["priority"] = int(priority)
        if status and status != task["status"]:
            change["status"] = status
        if status == STATUS_BLOCKED and reason != (task.get("blocked_reason") or ""):
            change["blocked_reason"] = reason
        if change:
            updates.append({"id": task["id"], **change})
    return updates, errors


def days_ago(iso_date):
    if not iso_date:
        return "—"
    days = (date.today() - date.fromisoformat(str(iso_date))).days
    return {0: "היום", 1: "אתמול"}.get(days, f"לפני {days} ימים")


def open_load_by_assignee(open_tasks):
    """לוח הנהלה: עומס פתוח לכל אחראי בכל הפרויקטים (מתוך המשימות הפתוחות)."""
    rows = {}
    for t in open_tasks:
        row = rows.setdefault(t["assigned_to"], {"name": t["assigned_to"], STATUS_PENDING: 0, STATUS_IN_PROGRESS: 0,
                                                 STATUS_BLOCKED: 0, "projects": set(), "max_blocked_days": 0})
        row[t["status"]] += 1
        row["projects"].add(t["project_name"])
        if t["status"] == STATUS_BLOCKED:
            row["max_blocked_days"] = max(row["max_blocked_days"], blocked_days(t))
    return sorted(rows.values(), key=lambda r: (-r[STATUS_BLOCKED], -(r[STATUS_PENDING] + r[STATUS_IN_PROGRESS])))


# =========================================================
# רכיבים
# =========================================================
def metrics_grid(items, key):
    """שורת מדדים. בטלפון נשארת בגריד של 2 בשורה (במקום מדד אחד לשורה) - ראו CSS ב-inject_css.
    items: רשימה של (תווית, ערך) או (תווית, ערך, {פרמטרים נוספים ל-st.metric})."""
    with st.container(key=f"kpis-{key}"):
        for column, item in zip(st.columns(len(items)), items):
            label, value, *extra = item
            column.metric(label, value, **(extra[0] if extra else {}))


def money_delta(amount):
    """לשדה delta של st.metric: מחרוזת עם סימן (Streamlit צובע לפי המינוס בהתחלה)."""
    return f"{'-' if amount < 0 else '+'}₪{abs(amount):,.0f}"


def budget_metrics(summary):
    metrics_grid([("תקציב", money(summary["initial_budget"])),
                  ("הוצאות", money(summary["spent"])),
                  ("יתרה", money(summary["remaining"]), {"delta": money_delta(summary["remaining"])})],
                 key="budget")


# =========================================================
# עיצוב: עברית מימין לשמאל, כפתורים נוחים ללחיצה, והתאמה לטלפון
# =========================================================
_CSS = """
<style>
/* עברית: התוכן והתפריט מימין לשמאל. טבלאות, גרפים, סליידרים ומספרים נשארים משמאל לימין */
[data-testid="stMain"], [data-testid="stSidebar"] { direction: rtl; }
[data-testid="stDataFrame"], [data-testid="stVegaLiteChart"], [data-testid="stSlider"],
[data-testid="stNumberInput"] input { direction: ltr; }

/* יעד לחיצה של 44px לפחות (ההמלצה המקובלת למסכי מגע) */
.stButton button, .stFormSubmitButton button, .stLinkButton a, .stDownloadButton button,
[data-testid="stButtonGroup"] button { min-height: 44px; }
[data-testid="stPageLink"] a { min-height: 40px; display: flex; align-items: center; }

/* מדדים ככרטיסים עדינים */
[data-testid="stMetric"] { background: rgba(128, 128, 128, 0.08); border-radius: 0.6rem; padding: 0.6rem 0.9rem; }

@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: 1.2rem 0.75rem 4rem; }
  [data-testid="stMain"] h1 { font-size: 1.55rem; }
  [data-testid="stMetricValue"] { font-size: 1.35rem; }
  /* מדדים: 2 בשורה במקום אחד */
  [class*="st-key-kpis"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.5rem; }
  [class*="st-key-kpis"] [data-testid="stColumn"] { flex: 1 1 calc(50% - 0.5rem) !important;
                                                    min-width: calc(50% - 0.5rem) !important; }
  /* כפתורי שליחה ופעולה ראשית לרוחב המסך */
  .stFormSubmitButton button, .stButton button[kind="primary"] { width: 100%; }
}
</style>
"""


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def task_label(task, show_assignee=False):
    status_icon = {STATUS_DONE: "✅ ", STATUS_BLOCKED: "🚧 "}.get(task["status"], "")
    urgency = "🔥" if task["priority"] >= URGENT_PRIORITY else "📌"
    assignee = f" (אחראי: {task['assigned_to']})" if show_assignee else ""
    return f"{status_icon}{urgency} **{task['title']}**{assignee}"


def blocked_days(task):
    since = task.get("blocked_since")
    if not since:
        return 0
    return (date.today() - date.fromisoformat(str(since))).days


def blocked_text(task):
    days = blocked_days(task)
    when = "מהיום" if days == 0 else ("מאתמול" if days == 1 else f"כבר {days} ימים")
    return f"🚧 **חסום {when}:** {task.get('blocked_reason') or ''}"


BLOCKING_KEY = "blocking_task"  # המשימה שהמשתמש לחץ עליה "חסום" ועכשיו צריך לכתוב למה


def _on_status_change(setter, key, current_status, ids, blocking_id):
    """נקרא פעם אחת כשהמשתמש לוחץ על סטטוס (ולא בכל רינדור) - מונע לולאת רענון כשהשרת נכשל."""
    new_status = st.session_state.get(key)
    st.session_state.pop(key, None)
    # הכפתורים תמיד מציגים את מה שבשרת. הסרת הערך מ-session_state לא מאפסת את הווידג'ט בדפדפן כל עוד
    # ה-key זהה, ולכן מקדמים "דור" שהוא חלק מה-key: אחרי כל לחיצה הכפתורים נבנים מחדש מהשרת
    # (חשוב בביטול 'חסום', בשגיאת שמירה ובלחיצה חוזרת על הכפתור המסומן)
    st.session_state["_status_gen"] = st.session_state.get("_status_gen", 0) + 1
    if new_status is None or new_status == current_status:
        return  # לחיצה על הכפתור שכבר מסומן מבטלת את הבחירה - לא עושים כלום
    if new_status == STATUS_BLOCKED and blocking_id:
        st.session_state[BLOCKING_KEY] = blocking_id  # "חסום" דורש סיבה - פותחים טופס קצר בכרטיס
        return
    st.session_state.pop(BLOCKING_KEY, None)
    action(setter, *ids, new_status)


def status_buttons(current_status, key, setter, *ids, disabled=False, options=STATUSES, blocking_id=None):
    """כפתורי סטטוס גדולים - שינוי בלחיצה אחת, נוח במיוחד בטלפון."""
    # הסטטוס הנוכחי הוא חלק מה-key: אם הסטטוס השתנה במקום אחר (דף אחר, משתמש אחר),
    # הכפתורים נבנים מחדש עם הערך מהשרת במקום להציג ערך ישן ששמור אצלם
    key = (f"{key}_{options.index(current_status) if current_status in options else 'x'}"
           f"_{st.session_state.get('_status_gen', 0)}")
    st.segmented_control("סטטוס", options, default=current_status if current_status in options else None,
                         key=key, disabled=disabled, label_visibility="collapsed", width="stretch",
                         on_change=_on_status_change, args=(setter, key, current_status, ids, blocking_id),
                         help="רק מנהל או האחראי על המשימה יכולים לשנות סטטוס" if disabled else None)


def delete_button(container, key, fn, *args, success):
    container.button("🗑️", key=key, help="מחיקה", on_click=action, args=(fn, *args), kwargs={"success": success})


def _cancel_blocking():
    st.session_state.pop(BLOCKING_KEY, None)
    st.session_state["_status_gen"] = st.session_state.get("_status_gen", 0) + 1


def _blocking_form(task, project_id, key_prefix):
    """טופס קצר שנפתח בתוך הכרטיס אחרי לחיצה על 'חסום': מה עוצר את העבודה?"""
    with st.form(f"{key_prefix}_block_{task['id']}"):
        reason = st.text_input("מה חוסם את המשימה?", max_chars=500,
                               placeholder="למשל: ממתינים לאישור חשמל מהמפקח")
        with st.container(horizontal=True):
            submitted = st.form_submit_button("🚧 סמן כחסום", type="primary")
            st.form_submit_button("ביטול", on_click=_cancel_blocking)
    if submitted:
        if not reason.strip():
            st.warning("יש לכתוב מה חוסם - כך מי שצריך לטפל יודע מה לעשות.")
            return
        _cancel_blocking()
        submit_action(api.set_task_status, project_id, task["id"], STATUS_BLOCKED, reason.strip(),
                      success="המשימה סומנה כחסומה.")


def task_card(task, project_id, key_prefix, project_name=None, allow_delete=False):
    """כרטיס משימה: כותרת, אחראי, קישור לפרויקט (אם צריך), סיבת חסימה, כפתורי סטטוס ומחיקה."""
    with st.container(border=True):
        st.markdown(task_label(task, show_assignee=True))
        if project_name:
            st.page_link("views/projects.py", label=project_name, icon="🏗️", query_params={"id": str(project_id)})
        if task["status"] == STATUS_BLOCKED:
            st.warning(blocked_text(task))
        with st.container(horizontal=True, vertical_alignment="center"):
            status_buttons(task["status"], f"{key_prefix}_t_{task['id']}", api.set_task_status, project_id,
                           task["id"], disabled=not can_update_task(task), blocking_id=task["id"])
            if allow_delete:
                delete_button(st, f"{key_prefix}_del_{task['id']}", api.delete_task, project_id, task["id"],
                              success="המשימה נמחקה.")
        if st.session_state.get(BLOCKING_KEY) == task["id"]:
            _blocking_form(task, project_id, key_prefix)


def personal_task_row(pt, key_prefix):
    """כרטיס משימה אישית (יומן): כותרת, כפתורי סטטוס ומחיקה."""
    with st.container(border=True):
        st.markdown(task_label(pt))
        with st.container(horizontal=True, vertical_alignment="center"):
            status_buttons(pt["status"], f"{key_prefix}_status_{pt['id']}", api.set_personal_task_status, pt["id"],
                           options=PERSONAL_STATUSES)
            delete_button(st, f"{key_prefix}_del_{pt['id']}", api.delete_personal_task, pt["id"],
                          success="הפגישה נמחקה.")


def personal_task_form(form_key, fixed_date=None):
    """טופס הוספה ליומן. עם fixed_date - בלי שדה תאריך (התאריך שנבחר בצד)."""
    with st.form(form_key, clear_on_submit=True):
        if fixed_date is None:
            c1, c2, c3 = st.columns([2, 1, 1])
            title = c1.text_input("שם המשימה או הפגישה")
            task_date = c2.date_input("תאריך", value=date.today())
            priority = c3.slider("רמת דחיפות", 1, 5, 3)
        else:
            title = st.text_input("שם הפגישה/משימה")
            priority = st.slider("דחיפות", 1, 5, 3)
            task_date = fixed_date
        if st.form_submit_button("שמור ביומן"):
            if not title.strip():
                st.warning("יש למלא שם למשימה או לפגישה.")
            else:
                submit_action(api.add_personal_task, title, priority, task_date.strftime("%Y-%m-%d"),
                              success=f"נשמר ביומן ל-{task_date.strftime('%d/%m/%Y')}.")


def change_password_form(form_key):
    with st.form(form_key, clear_on_submit=True):
        current = st.text_input("סיסמה נוכחית", type="password")
        new = st.text_input(f"סיסמה חדשה (לפחות {MIN_PASSWORD_LENGTH} תווים)", type="password")
        confirm = st.text_input("אימות סיסמה חדשה", type="password")
        if st.form_submit_button("החלף סיסמה", type="primary"):
            if len(new) < MIN_PASSWORD_LENGTH:
                st.warning(f"הסיסמה החדשה חייבת להכיל לפחות {MIN_PASSWORD_LENGTH} תווים.")
            elif new != confirm:
                st.warning("הסיסמאות החדשות אינן תואמות.")
            elif action(api.change_password, current, new, success="הסיסמה הוחלפה בהצלחה."):
                st.session_state["must_change_password"] = False
                st.rerun()
            else:
                st.rerun()
