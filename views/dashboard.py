"""דף הנהלה - תמונת מצב של הפרויקטים שהמשתמש רשאי לראות (למנהלים בלבד).
סדר המסך: מדדים, תובנות שדורשות פעולה, ואז הגרפים - שמקופלים כדי לא להעמיס בטלפון."""
import pandas as pd
import streamlit as st

import api
import ui
from constants import (BLOCKED_ALERT_DAYS, PERM_VIEW_DASHBOARD, STATUS_BLOCKED, STATUS_IN_PROGRESS,
                       STATUS_PENDING)

if not ui.can(PERM_VIEW_DASHBOARD):
    st.error("הדף הזה זמין למנהלים בלבד.")
    st.stop()

st.title("📊 הנהלה")

data, error = ui.load(api.get_dashboard)
if error:
    st.error(f"לא ניתן לטעון את נתוני לוח הבקרה: {error}")
    st.stop()
projects = data["projects"]
if not projects:
    st.info("אין עדיין פרויקטים שאתה שותף בהם. פרויקטים חדשים יופיעו כאן ברגע שיצרפו אותך.")
    st.stop()

total_budget = sum(p["initial_budget"] for p in projects)
total_spent = sum(p["spent"] for p in projects)
open_tasks = sum(p["open"] for p in projects)

ui.metrics_grid([
    ("סה\"כ תקציבים", ui.money(total_budget)),
    ("הוצאות עד כה", ui.money(total_spent)),
    ("יתרה כוללת", ui.money(total_budget - total_spent), {"delta": ui.money_delta(total_budget - total_spent)}),
    ("משימות פתוחות", open_tasks, {"help": f"מתוך {sum(p['tasks'] for p in projects)} משימות"}),
], key="dashboard")

st.subheader("🧠 תובנות וניהול סיכונים")
risks = [r for p in projects if (r := ui.project_risk(p))]
if risks:
    for _, message in risks:
        st.warning(message)
else:
    st.success("✅ ניתוח נתונים: כל הפרויקטים מאוזנים ואין חריגות תקציב.")
open_tasks_list, _ = ui.load(api.get_open_tasks)
stuck = sorted((t for t in open_tasks_list or []
                if t["status"] == STATUS_BLOCKED and ui.blocked_days(t) > BLOCKED_ALERT_DAYS),
               key=ui.blocked_days, reverse=True)
if stuck:
    with st.container(border=True):
        st.markdown(f"**🚧 חסימות שפתוחות יותר מ-{BLOCKED_ALERT_DAYS} ימים ({len(stuck)})**")
        for t in stuck:
            st.markdown(f"- **{t['title']}** ({t['project_name']} · {t['assigned_to']}) – "
                        f"{ui.blocked_days(t)} ימים: {t['blocked_reason']}")
load = data["open_by_assignee"]
if load:
    busiest = max(load, key=load.get)
    st.info(f"💡 **ניהול משאבים:** שים לב, **{busiest}** עמוס כרגע ({load[busiest]} משימות פתוחות).")

team = ui.open_load_by_assignee(open_tasks_list or [])
if team:
    st.subheader("👷 סטטוס קבלנים")
    st.dataframe(pd.DataFrame([{
        "שם": r["name"],
        "🚧 חסומות": r[STATUS_BLOCKED],
        "⏳ ממתינות": r[STATUS_PENDING],
        "🔨 בתהליך": r[STATUS_IN_PROGRESS],
        "חסימה ארוכה (ימים)": r["max_blocked_days"] if r[STATUS_BLOCKED] else None,
        "פרויקטים": ", ".join(sorted(r["projects"])),
    } for r in team]), hide_index=True, use_container_width=True)

with st.expander("📈 גרפים", expanded=True):
    g_col1, g_col2 = st.columns(2)
    with g_col1:
        st.markdown("**התפלגות סטטוס משימות**")
        st.bar_chart(data["status_counts"], color="#FF4B4B")
    with g_col2:
        st.markdown("**תקציב מול הוצאות לפי פרויקט**")
        st.bar_chart({p["name"]: {"תקציב": p["initial_budget"], "הוצאות": p["spent"]} for p in projects})
