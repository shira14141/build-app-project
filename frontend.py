"""נקודת הכניסה של הממשק: התחברות, תפריט צד (יומן יומי) וניווט בין הדפים.

הרצה:  streamlit run frontend.py
הדפים עצמם נמצאים בתיקייה views/.
"""
from datetime import date

import streamlit as st

import api
import ui
from constants import PERM_MANAGE_USERS, PERM_VIEW_DASHBOARD, ROLE_LABELS

st.set_page_config(page_title="מערכת ניהול בנייה", page_icon="🏗️", layout="wide")
ui.inject_css()


# =========================================================
# התחברות והחלפת סיסמה
# =========================================================
def login_page():
    st.title("🔐 התחברות למערכת")
    ui.show_flash()
    with st.form("login_form"):
        username = st.text_input("שם משתמש")
        password = st.text_input("סיסמה", type="password")
        if st.form_submit_button("התחבר", type="primary"):
            try:
                ui.start_session(api.login(username.strip(), password))
            except api.ApiError as e:
                st.error("שם משתמש או סיסמה שגויים." if e.status_code == 401 else str(e))
            else:
                st.rerun()


def first_password_page():
    st.title("🔑 החלפת סיסמה")
    st.info(f"שלום **{ui.current_user()}**! זו הכניסה הראשונה שלך (או שהסיסמה אופסה). "
            "יש לבחור סיסמה אישית לפני שממשיכים.")
    ui.show_flash()
    ui.change_password_form("first_password_form")
    st.button("התנתק", on_click=ui.end_session)


PAGE_PATHS = ["home", "dashboard", "projects", "work-log", "calendar", "users"]


def gate(page_fn, title, icon):
    """לפני כניסה מלאה: כל כתובת של האפליקציה מציגה את מסך ההתחברות/החלפת הסיסמה, והכתובת
    (כולל ?id=) נשמרת - כך שקישור ישיר לפרויקט מוביל אליו מיד אחרי ההתחברות."""
    gate_pages = [st.Page(page_fn, title=title, icon=icon, default=True)]
    gate_pages += [st.Page(page_fn, title=title, icon=icon, url_path=path) for path in PAGE_PATHS]
    st.navigation(gate_pages, position="hidden").run()
    st.stop()


if not ui.is_logged_in():
    gate(login_page, "התחברות", "🔐")
if st.session_state.get("must_change_password"):
    gate(first_password_page, "החלפת סיסמה", "🔑")

# =========================================================
# ניווט
# =========================================================
home_page = st.Page("views/home.py", title="היום", icon="🏠", url_path="home", default=True)
calendar_page = st.Page("views/calendar.py", title="הפגישות שלי", icon="📅", url_path="calendar")
pages = [
    home_page,
    st.Page("views/projects.py", title="פרויקטים", icon="🏗️", url_path="projects"),
    st.Page("views/work_log.py", title="יומן עבודה", icon="📝", url_path="work-log"),
    calendar_page,
]
if ui.can(PERM_VIEW_DASHBOARD):
    pages.append(st.Page("views/dashboard.py", title="הנהלה", icon="📊", url_path="dashboard"))
if ui.can(PERM_MANAGE_USERS):
    pages.append(st.Page("views/users.py", title="משתמשים", icon="👥", url_path="users"))
# בטלפון Streamlit מכווץ את הניווט העליון לתפריט אוטומטית
page = st.navigation(pages, position="top")


# =========================================================
# תפריט הצד - יומן יומי
# =========================================================
def daily_calendar():
    ui.show_flash()  # הודעות מפעולות בתוך היומן (כשרק הוא מתרענן)
    st.subheader("📅 יומן פגישות יומי")
    selected_date = st.date_input("בחר תאריך להצגת לו\"ז:", value=date.today(), key="sidebar_date")
    selected_str = selected_date.strftime("%Y-%m-%d")

    tasks, error = ui.load(api.get_personal_tasks)
    if error:
        st.error(f"שגיאה בטעינת היומן: {error}")
        return

    daily = sorted((t for t in tasks if t.get("date") == selected_str), key=lambda t: t["priority"], reverse=True)
    if not daily:
        st.info("אין משימות או פגישות לתאריך זה.")
    for pt in daily:
        ui.personal_task_row(pt, "side")

    with st.expander(f"➕ הוסף פגישה ל-{selected_date.strftime('%d/%m/%Y')}"):
        ui.personal_task_form("quick_add_task_form", fixed_date=selected_date)


ui.show_flash()  # לפני היומן בצד, כדי שהודעות של הדף הראשי יוצגו בדף ולא בתפריט

with st.sidebar:
    st.title("👤 אזור אישי")
    st.success(f"שלום, **{ui.current_user()}**!")
    st.caption(f"תפקיד: {ROLE_LABELS.get(st.session_state.get('role'), '')}")
    c1, c2 = st.columns(2)
    with c1.popover("🔑 סיסמה"):
        ui.change_password_form("sidebar_password_form")
    c2.button("🚪 התנתק", on_click=ui.end_session)
    st.divider()
    if page.url_path == home_page.url_path:
        # במסך 'היום' הפגישות של היום כבר מוצגות במסך עצמו (וגם בטלפון, שבו תפריט הצד מוסתר)
        st.caption("הפגישות של היום מוצגות במסך הראשי.")
    elif page.url_path == calendar_page.url_path:
        # בדף היומן - רענון מלא, כדי שהרשימה בדף והיומן בצד יישארו מסונכרנים
        daily_calendar()
    else:
        # בשאר הדפים - fragment: בחירת תאריך או שינוי סטטוס מרעננים רק את היומן ולא את כל הדף
        st.fragment(daily_calendar)()

page.run()
