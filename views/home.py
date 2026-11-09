"""מסך 'היום' - נקודת הפתיחה לעבודה יומיומית בשטח.

מה שדורש טיפול מוצג בראש המסך, והסטטוס משתנה בלחיצה אחת. כל התוכן עטוף ב-fragment:
לחיצה על סטטוס מרעננת רק את המסך הזה, בלי תפריט הצד והניווט.
"""
from datetime import date

import streamlit as st

import api
import ui
from constants import PERM_MANAGE_TASKS, PERM_WRITE_WORK_LOG, STATUS_BLOCKED, STATUS_DONE, URGENT_PRIORITY

HEBREW_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
today = date.today()
today_str = today.strftime("%Y-%m-%d")

st.title("🏠 היום")
st.caption(f"יום {HEBREW_DAYS[today.weekday()]}, {today:%d/%m/%Y} · שלום {ui.current_user()}")

if ui.can(PERM_WRITE_WORK_LOG) and st.button("📝 דיווח יומן עבודה", type="primary", use_container_width=True):
    st.switch_page("views/work_log.py")


@st.fragment
def home():
    ui.show_flash()
    tasks, error = ui.load(api.get_open_tasks)
    meetings, meetings_error = ui.load(api.get_personal_tasks)
    if error:
        st.error(f"לא ניתן לטעון את המשימות: {error}")
        return

    me = ui.current_user()
    # שלי: חסומות קודם, אחר כך לפי דחיפות (השרת כבר מיין לפי דחיפות)
    mine = sorted((t for t in tasks if t["assigned_to"] == me), key=lambda t: t["status"] != STATUS_BLOCKED)
    blocked_others = [t for t in tasks if t["status"] == STATUS_BLOCKED and t["assigned_to"] != me]
    urgent_others = ([t for t in tasks if t["assigned_to"] != me and t["priority"] >= URGENT_PRIORITY
                      and t["status"] != STATUS_BLOCKED] if ui.can(PERM_MANAGE_TASKS) else [])
    todays = sorted((m for m in (meetings or []) if m.get("date") == today_str),
                    key=lambda m: (m["status"] == STATUS_DONE, -m["priority"]))

    ui.metrics_grid([
        ("המשימות שלי", len(mine)),
        ("דחופות", sum(t["priority"] >= URGENT_PRIORITY for t in mine) + len(urgent_others)),
        ("חסימות פתוחות", sum(t["status"] == STATUS_BLOCKED for t in tasks)),
        ("פגישות היום", sum(m["status"] != STATUS_DONE for m in todays)),
    ], key="home")

    st.subheader("דורש טיפול")
    if not mine:
        st.success("אין משימות פתוחות שמשויכות אליך.")
    for task in mine:
        ui.task_card(task, task["project_id"], "home", project_name=task["project_name"])

    if blocked_others:
        # חסימות של אחרים בפרויקטים שלי - כולם באתר צריכים לדעת מה עוצר את העבודה
        with st.expander(f"🚧 חסימות בפרויקטים שלך ({len(blocked_others)})", expanded=True):
            for task in sorted(blocked_others, key=ui.blocked_days, reverse=True):
                ui.task_card(task, task["project_id"], "home_blocked", project_name=task["project_name"])

    if urgent_others:
        with st.expander(f"🔥 דחוף בפרויקטים שלך ({len(urgent_others)})", expanded=not mine):
            for task in urgent_others:
                ui.task_card(task, task["project_id"], "home_urgent", project_name=task["project_name"])

    st.subheader("📅 הפגישות של היום")
    if meetings_error:
        st.error(f"לא ניתן לטעון את היומן: {meetings_error}")
    elif not todays:
        st.info("אין פגישות או משימות אישיות להיום.")
    for meeting in todays:
        ui.personal_task_row(meeting, "home_meeting")
    with st.expander("➕ הוספה ליומן של היום"):
        ui.personal_task_form("home_add_meeting", fixed_date=today)


home()

with st.container(horizontal=True):
    st.page_link("views/projects.py", label="כל הפרויקטים", icon="🏗️")
    st.page_link("views/calendar.py", label="היומן המלא", icon="📅")
