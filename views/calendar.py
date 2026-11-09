"""דף היומן האישי - כל המשימות והפגישות של המשתמש, מקובצות לפי תאריך."""
from datetime import date, datetime
from itertools import groupby

import streamlit as st

import api
import ui

st.title("📅 הפגישות שלי")
st.caption("פגישות ומשימות אישיות - רק אתה רואה אותן. הפגישות של היום מופיעות גם במסך הראשי.")

with st.expander("➕ הוספה ליומן"):
    ui.personal_task_form("calendar_page_add_form")

tasks, error = ui.load(api.get_personal_tasks)
if error:
    st.error(f"שגיאה בטעינת היומן: {error}")
    st.stop()

today = date.today().strftime("%Y-%m-%d")
upcoming = sorted((t for t in tasks if t.get("date", "") >= today), key=lambda t: (t["date"], -t["priority"]))
past = [t for t in tasks if t.get("date", "") < today]


def render_by_date(items, key_prefix):
    for day, group in groupby(items, key=lambda t: t["date"]):
        label = "היום" if day == today else datetime.strptime(day, "%Y-%m-%d").strftime("%d/%m/%Y")
        st.markdown(f"#### {label}")
        for pt in group:
            ui.personal_task_row(pt, key_prefix)


st.subheader(f"הקרובים ({len(upcoming)})")
if upcoming:
    render_by_date(upcoming, "cal")
else:
    st.info("אין משימות או פגישות קרובות.")

if past:
    with st.expander(f"עבר ({len(past)})"):
        render_by_date(sorted(past, key=lambda t: t["date"], reverse=True), "cal_past")
