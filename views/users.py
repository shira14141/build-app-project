"""דף ניהול משתמשים - למנהל מערכת בלבד (גם הדף מוסתר וגם השרת חוסם אחרים)."""
import pandas as pd
import streamlit as st

import api
import ui
from constants import MIN_PASSWORD_LENGTH, PERM_MANAGE_USERS, ROLE_LABELS, ROLES

if not ui.can(PERM_MANAGE_USERS):
    st.error("הדף הזה זמין למנהל מערכת בלבד.")
    st.stop()

st.title("👥 ניהול משתמשים")

users, error = ui.load(api.get_users)
if error:
    st.error(f"לא ניתן לטעון את המשתמשים: {error}")
    st.stop()

st.dataframe(pd.DataFrame([{
    "שם משתמש": u["username"],
    "תפקיד": ROLE_LABELS.get(u["role"], u["role"]),
    "פעיל": "✅" if u["is_active"] else "⛔ מושבת",
    "חייב להחליף סיסמה": "כן" if u["must_change_password"] else "",
} for u in users]), hide_index=True)

with st.expander("ℹ️ מה כל תפקיד יכול לעשות?"):
    st.markdown(
        "- **מנהל מערכת** – הכל, כולל כל הפרויקטים וניהול משתמשים.\n"
        "- **מנהל פרויקט** – יצירת פרויקטים; בפרויקטים שהוא שותף בהם: משימות, תקציב, קבצים, הגדרות ומחיקה.\n"
        "- **קבלן / בעל מקצוע** – צפייה בפרויקטים שהוא שותף בהם, עדכון סטטוס של המשימות שלו והעלאת קבצים.\n"
        "- **צופה** – צפייה בלבד בפרויקטים שהוא שותף בהם.\n\n"
        "כל משתמש רואה רק פרויקטים שהוא שותף בהם (חוץ ממנהל מערכת), ורק את היומן האישי שלו."
    )
    st.caption("ההרשאות המדויקות מוגדרות ב-ROLE_PERMISSIONS בקובץ constants.py.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("➕ משתמש חדש")
    with st.form("new_user_form", clear_on_submit=True):
        username = st.text_input("שם משתמש")
        password = st.text_input(f"סיסמה זמנית (לפחות {MIN_PASSWORD_LENGTH} תווים)", type="password",
                                 help="המשתמש יחויב להחליף אותה בכניסה הראשונה.")
        role = st.selectbox("תפקיד", ROLES, index=ROLES.index("contractor"), format_func=ROLE_LABELS.get)
        if st.form_submit_button("צור משתמש", type="primary"):
            if not username.strip():
                st.warning("יש למלא שם משתמש.")
            elif len(password) < MIN_PASSWORD_LENGTH:
                st.warning(f"הסיסמה חייבת להכיל לפחות {MIN_PASSWORD_LENGTH} תווים.")
            else:
                ui.submit_action(api.create_user, username.strip(), password, role,
                                 success=f"המשתמש '{username.strip()}' נוצר.")

with col2:
    st.subheader("✏️ עריכת משתמש")
    by_name = {u["username"]: u for u in users}
    selected = st.selectbox("בחר משתמש", list(by_name), key="edit_user_pick")
    user = by_name[selected]
    is_me = selected == ui.current_user()
    with st.form(f"edit_user_form_{selected}"):
        role = st.selectbox("תפקיד", ROLES, index=ROLES.index(user["role"]), format_func=ROLE_LABELS.get,
                            disabled=is_me)
        active = st.toggle("משתמש פעיל", value=user["is_active"], disabled=is_me,
                           help="משתמש מושבת מנותק מיד ולא יכול להתחבר.")
        new_password = st.text_input("איפוס סיסמה (השאר ריק כדי לא לשנות)", type="password")
        if is_me:
            st.caption("את התפקיד והסטטוס של עצמך אי אפשר לשנות. את הסיסמה שלך מחליפים בתפריט הצד.")
        if st.form_submit_button("שמור", type="primary"):
            changes = {}
            if not is_me and role != user["role"]:
                changes["role"] = role
            if not is_me and active != user["is_active"]:
                changes["is_active"] = active
            if new_password:
                changes["new_password"] = new_password
            if new_password and len(new_password) < MIN_PASSWORD_LENGTH:
                st.warning(f"הסיסמה חייבת להכיל לפחות {MIN_PASSWORD_LENGTH} תווים.")
            elif not changes:
                st.info("לא בוצעו שינויים.")
            else:
                ui.submit_action(api.update_user, selected, **changes, success=f"המשתמש '{selected}' עודכן.")
