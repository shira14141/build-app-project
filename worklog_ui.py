"""רכיבי יומן העבודה - משותפים לדף 'יומן עבודה' ולאזור 'יומן' בדף הפרויקט."""
from datetime import date

import pandas as pd
import streamlit as st

import api
import ui
from constants import MAX_CREW_ROWS, MAX_WORKERS_PER_ROW, PERM_MANAGE_WORK_LOGS, STATUS_BLOCKED

CREW_NAME, CREW_WORKERS = "צוות / קבלן", "עובדים"


def validate_work_log(log_date, crew_rows, work_done):
    """ולידציה בממשק, לפני שליחה (השרת בודק שוב). מחזיר (רשימת שגיאות בעברית, צוותים נקיים לשמירה).
    crew_rows: השורות מטבלת הצוותים - שורות ריקות ושורות עם 0 עובדים מדולגות."""
    errors, crew = [], []
    if log_date > date.today():
        errors.append("אי אפשר לדווח על תאריך עתידי.")
    if len((work_done or "").strip()) < 3:
        errors.append("יש לכתוב מה בוצע היום (לפחות כמה מילים).")
    for i, row in enumerate(crew_rows, start=1):
        name = str(row.get(CREW_NAME) or "").strip()
        workers = row.get(CREW_WORKERS)
        workers = 0 if workers is None or pd.isna(workers) else workers
        if not name and not workers:
            continue
        if not name:
            errors.append(f"בשורה {i} בטבלת הצוותים חסר שם צוות.")
        elif workers != int(workers) or not 0 <= workers <= MAX_WORKERS_PER_ROW:
            errors.append(f"מספר העובדים בשורה {i} חייב להיות מספר שלם בין 0 ל-{MAX_WORKERS_PER_ROW}.")
        elif workers:
            crew.append({"name": name, "workers": int(workers)})
    if len(crew) > MAX_CREW_ROWS:
        errors.append(f"אפשר לדווח עד {MAX_CREW_ROWS} צוותים.")
    return errors, crew


def _date_label(iso):
    d = date.fromisoformat(iso)
    if d == date.today():
        return "היום"
    return d.strftime("%d/%m/%Y")


def render_open_blockers(project):
    """חסימות פתוחות בפרויקט - מוצג מעל הטופס, כדי שמי שמדווח יראה מה עדיין עוצר את העבודה."""
    blocked = [t for t in project.get("task_list", []) if t["status"] == STATUS_BLOCKED]
    if not blocked:
        return
    with st.expander(f"🚧 חסימות פתוחות בפרויקט ({len(blocked)})", expanded=True):
        for task in sorted(blocked, key=ui.blocked_days, reverse=True):
            st.markdown(f"**{task['title']}** · {task['assigned_to']}  \n{ui.blocked_text(task)}")


def render_history(project_id, limit_note=True):
    logs, error = ui.load(api.get_work_logs, project_id)
    if error:
        st.error(f"לא ניתן לטעון את היומן: {error}")
        return
    if not logs:
        st.info("עוד אין דיווחים בפרויקט הזה.")
        return
    me = ui.current_user()
    for i, log in enumerate(logs):
        parts = [_date_label(log["log_date"]), log["author"], f"👷 {log['total_workers']}"]
        if log["issues"]:
            parts.append("⚠️ עיכובים")
        if log["photos"]:
            parts.append(f"📷 {len(log['photos'])}")
        with st.expander(" · ".join(parts), expanded=(i == 0 and log["log_date"] == date.today().isoformat())):
            if log["weather"]:
                st.caption(f"מזג אוויר: {log['weather']}")
            st.markdown(log["work_done"])
            if log["issues"]:
                st.warning(f"**עיכובים ובעיות:** {log['issues']}")
            if log["crew"]:
                st.dataframe(pd.DataFrame([{"צוות / קבלן": c["name"], "עובדים": c["workers"]} for c in log["crew"]]),
                             hide_index=True)
            if log["photos"]:
                st.image([api.absolute_url(p["view_url"]) for p in log["photos"]],
                         caption=[p["filename"] for p in log["photos"]], width=160)
            if log["author"] == me or ui.can(PERM_MANAGE_WORK_LOGS):
                with st.popover("🗑️ מחיקת הדיווח"):
                    st.write("למחוק את הדיווח ואת התמונות שלו? אי אפשר לבטל.")
                    st.button("כן, מחק", type="primary", key=f"del_log_{log['id']}", on_click=ui.action,
                              args=(api.delete_work_log, project_id, log["id"]), kwargs={"success": "הדיווח נמחק."})
    if limit_note and len(logs) >= 30:
        st.caption("מוצגים 30 הדיווחים האחרונים.")
