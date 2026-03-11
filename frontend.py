import streamlit as st
import requests
from datetime import datetime

API_URL = "https://build-app-project.onrender.com"

st.set_page_config(page_title="מערכת ניהול בנייה", page_icon="🏗️", layout="wide")

AVAILABLE_PARTNERS = [
    "יוסי הקבלן", "דנה האדריכלית", "משה מפקח הבנייה",
    "אבי אינסטלטור", "שירה", "רוני קבלן חשמל"
]

# =========================================================
# מערכת התחברות (Login)
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["current_user"] = ""

if not st.session_state["logged_in"]:
    st.title("🔐 התחברות למערכת")
    st.write("אנא הזן שם משתמש וסיסמה כדי לגשת לפרויקטים ולמשימות.")

    with st.form("login_form"):
        username = st.selectbox("שם משתמש", options=AVAILABLE_PARTNERS)
        password = st.text_input("סיסמה", type="password")
        submit = st.form_submit_button("התחבר")

        if submit:
            try:
                res = requests.post(f"{API_URL}/login/", json={"username": username, "password": password})
                if res.status_code == 200:
                    st.session_state["logged_in"] = True
                    st.session_state["current_user"] = username
                    st.success("התחברת בהצלחה! מעביר אותך למערכת...")
                    st.rerun()
                else:
                    st.error("סיסמה שגויה. (הסיסמה של שירה היא admin, ושל השאר 1234)")
            except:
                st.error("שגיאת התחברות לשרת הנתונים. ודאי ש-main.py פועל.")
    st.stop()

# =========================================================
# תפריט הצד (Sidebar) - לוח השנה והיומן
# =========================================================
current_user = st.session_state["current_user"]

st.sidebar.title("👤 אזור אישי")
st.sidebar.success(f"שלום, **{current_user}**!")
if st.sidebar.button("🚪 התנתק"):
    st.session_state["logged_in"] = False
    st.session_state["current_user"] = ""
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("📅 יומן פגישות יומי")

selected_date = st.sidebar.date_input("בחר תאריך להצגת לו\"ז:")
selected_date_str = selected_date.strftime("%Y-%m-%d")

try:
    res_personal = requests.get(f"{API_URL}/personal_tasks/{current_user}")
    if res_personal.status_code == 200:
        personal_tasks = res_personal.json()
        daily_tasks = [pt for pt in personal_tasks if pt.get("date") == selected_date_str]

        if not daily_tasks:
            st.sidebar.info("אין משימות או פגישות לתאריך זה.")
        else:
            for pt in sorted(daily_tasks, key=lambda x: x['priority'], reverse=True):
                urgency = "🔥" if pt['priority'] >= 4 else "📌"
                done = "✅" if pt['status'] == "בוצע" else ""

                st.sidebar.markdown(f"**{done} {urgency} {pt['title']}**")

                col1, col2 = st.sidebar.columns(2)
                curr_idx = ["ממתין", "בתהליך", "בוצע"].index(pt['status'])
                new_status = col1.selectbox("סטטוס", ["ממתין", "בתהליך", "בוצע"], index=curr_idx,
                                            key=f"side_status_{pt['id']}", label_visibility="collapsed")

                if new_status != pt['status']:
                    requests.patch(f"{API_URL}/personal_tasks/{pt['id']}/status?new_status={new_status}")
                    st.rerun()

                if col2.button("🗑️ מחק", key=f"side_del_{pt['id']}"):
                    requests.delete(f"{API_URL}/personal_tasks/{pt['id']}")
                    st.rerun()
                st.sidebar.divider()

        with st.sidebar.expander(f"➕ הוסף פגישה ל-{selected_date.strftime('%d/%m/%Y')}"):
            with st.form("quick_add_task_form"):
                quick_title = st.text_input("שם הפגישה/משימה")
                quick_priority = st.slider("דחיפות", 1, 5, 3, key="quick_slider")
                if st.form_submit_button("שמור ביומן"):
                    if quick_title:
                        requests.post(f"{API_URL}/personal_tasks/", json={
                            "title": quick_title,
                            "assigned_to": current_user,
                            "priority": quick_priority,
                            "date": selected_date_str
                        })
                        st.rerun()
except Exception as e:
    st.sidebar.error("שגיאה בטעינת היומן.")

# =========================================================
# המסך הראשי
# =========================================================
st.title("🏗️ Build App")
# --- קוד קיים שלך ---
st.title("מערכת ניהול פרויקטים 🏗️")
st.write("ברוכים הבאים למערכת...")

# ==========================================
# פה את מדביקה את הדאשבורד החדש שלנו!
# ==========================================
st.markdown("### 📊 תמונת מצב פיננסית")

# יצירת 3 עמודות רוחב שוות
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="תקציב כולל", value="₪1,500,000")

with col2:
    st.metric(label="הוצאות בפועל", value="₪850,000", delta="-₪15,000 חריגה")

with col3:
    st.metric(label="יתרה מתקציב", value="₪650,000", delta="תקין", delta_color="normal")

st.divider()  # קו הפרדה יוקרתי
# ==========================================

# --- המשך הקוד הקיים שלך (טפסים, כפתורים וכו') ---

main_tab_dashboard, main_tab_projects, main_tab_personal = st.tabs([
    "📊 לוח בקרה הנהלה",
    "🏗️ ניהול פרויקטים",
    "➕ מרכז המשימות האישיות"
])

# ---------------------------------------------------------
# לשונית 1: לוח בקרה חזר במלואו!
# ---------------------------------------------------------
with main_tab_dashboard:
    st.subheader("📊 תמונת מצב כוללת - כל הפרויקטים")
    try:
        response = requests.get(f"{API_URL}/projects/")
        if response.status_code == 200:
            projects = response.json()
            if not projects:
                st.info("אין מספיק נתונים להצגת לוח בקרה. צור פרויקטים חדשים!")
            else:
                total_budget = sum(p['initial_budget'] for p in projects)
                total_expenses = sum(sum(exp['final_price'] for exp in p.get('expenses', [])) for p in projects)
                total_remaining = total_budget - total_expenses

                c1, c2, c3 = st.columns(3)
                c1.metric("סה\"כ תקציבים במערכת", f"₪{total_budget:,.0f}")
                c2.metric("סה\"כ הוצאות עד כה", f"₪{total_expenses:,.0f}")
                c3.metric("יתרה כוללת נותרת", f"₪{total_remaining:,.0f}", delta=float(total_remaining))

                st.divider()

                task_counts = {"ממתין": 0, "בתהליך": 0, "בוצע": 0}
                for p in projects:
                    for t in p.get('tasks', []):
                        if t['status'] in task_counts:
                            task_counts[t['status']] += 1

                g_col1, g_col2 = st.columns(2)
                with g_col1:
                    st.markdown("**התפלגות סטטוס משימות**")
                    st.bar_chart(task_counts, color="#FF4B4B")
                with g_col2:
                    st.markdown("**תקציב מול הוצאות לפי פרויקט**")
                    financial_data = {}
                    for p in projects:
                        p_exp = sum(e['final_price'] for e in p.get('expenses', []))
                        financial_data[p['name']] = {"תקציב": p['initial_budget'], "הוצאות": p_exp}
                    if financial_data:
                        st.bar_chart(financial_data)

                st.divider()
                st.subheader("🧠 מנוע תובנות וניהול סיכונים (AI Insights)")
                insights, task_load = [], {}
                for p in projects:
                    p_budget = p['initial_budget']
                    p_exp = sum(e['final_price'] for e in p.get('expenses', []))
                    if p_budget > 0:
                        spent_pct = (p_exp / p_budget) * 100
                        tasks = p.get('tasks', [])
                        done_pct = (len([t for t in tasks if t['status'] == 'בוצע']) / len(
                            tasks) * 100) if tasks else 100
                        if spent_pct > 80 and done_pct < 50:
                            insights.append(
                                f"🚨 **סיכון גבוה '{p['name']}':** נוצלו {spent_pct:.0f}% מהתקציב, אבל רק {done_pct:.0f}% מהמשימות הושלמו!")
                        elif spent_pct > 90:
                            insights.append(
                                f"⚠️ **חריגת תקציב קרובה '{p['name']}':** נוצלו {spent_pct:.0f}% מהתקציב ההתחלתי.")
                    for t in p.get('tasks', []):
                        if t['status'] != 'בוצע': task_load[t['assigned_to']] = task_load.get(t['assigned_to'], 0) + 1

                if insights:
                    for insight in insights: st.warning(insight)
                else:
                    st.success("✅ ניתוח נתונים: כל הפרויקטים מאוזנים ואין חריגות תקציב.")
                if task_load:
                    busiest_worker = max(task_load, key=task_load.get)
                    st.info(
                        f"💡 **ניהול משאבים (Scrum):** שים לב, **{busiest_worker}** עמוס כרגע ({task_load[busiest_worker]} משימות פתוחות).")
    except Exception as e:
        st.error("לא ניתן לטעון את נתוני לוח הבקרה.")

# ---------------------------------------------------------
# לשונית 2: ניהול פרויקטים - התקציב חזר במלואו!
# ---------------------------------------------------------
with main_tab_projects:
    with st.expander("➕ לחץ כאן ליצירת פרויקט חדש"):
        with st.form("new_project_form"):
            col1, col2 = st.columns(2)
            with col1:
                p_id = st.number_input("מזהה פרויקט (ID)", min_value=1, step=1)
                p_name = st.text_input("שם הפרויקט")
            with col2:
                p_budget = st.number_input("תקציב ראשוני", min_value=0.0, step=1000.0)
                p_partners = st.multiselect("בחר שותפי עבודה", options=AVAILABLE_PARTNERS)
            if st.form_submit_button("צור פרויקט חדש"):
                try:
                    res = requests.post(f"{API_URL}/projects/",
                                        json={"id": p_id, "name": p_name, "initial_budget": p_budget,
                                              "partners": p_partners, "tasks": [], "expenses": []})
                    if res.status_code == 200: st.success("נוצר בהצלחה!"); st.rerun()
                except:
                    st.error("שגיאת התחברות לשרת.")

    st.divider()
    st.subheader("📋 הפרויקטים הפעילים")
    try:
        response = requests.get(f"{API_URL}/projects/")
        if response.status_code == 200:
            projects = response.json()
            if not projects:
                st.info("אין פרויקטים.")
            else:
                for proj in projects:
                    with st.expander(f"🏢 {proj['name']} (מזהה: {proj['id']})"):
                        tab_tasks, tab_budget, tab_files = st.tabs(
                            ["📋 משימות הפרויקט", "💰 תקציב הפרויקט", "📂 קבצי הפרויקט"])

                        # -- משימות --
                        with tab_tasks:
                            if proj['tasks']:
                                for task in sorted(proj['tasks'], key=lambda x: x['priority'], reverse=True):
                                    t_c1, t_c2, t_c3 = st.columns([4, 2, 1])
                                    t_c1.write(
                                        f"{'✅' if task['status'] == 'בוצע' else ''} {'🔥' if task['priority'] >= 4 else '📌'} **{task['title']}** (אחראי: {task['assigned_to']})")
                                    new_status = t_c2.selectbox("סטטוס", ["ממתין", "בתהליך", "בוצע"],
                                                                index=["ממתין", "בתהליך", "בוצע"].index(task['status']),
                                                                key=f"p_{proj['id']}_t_{task['id']}",
                                                                label_visibility="collapsed")
                                    if new_status != task['status']: requests.patch(
                                        f"{API_URL}/projects/{proj['id']}/tasks/{task['id']}/status?new_status={new_status}"); st.rerun()
                                    if t_c3.button("🗑️ מחק", key=f"del_p_{proj['id']}_t_{task['id']}"): requests.delete(
                                        f"{API_URL}/projects/{proj['id']}/tasks/{task['id']}"); st.rerun()
                                    st.divider()
                            with st.form(f"add_task_{proj['id']}"):
                                c1, c2, c3 = st.columns(3)
                                t_title = c1.text_input("מה צריך לעשות?")
                                t_assignee = c2.selectbox("שייך למי?",
                                                          options=proj['partners'] if proj['partners'] else [
                                                              "אין שותפים"])
                                t_priority = c3.slider("דחיפות", 1, 5, 3)
                                if st.form_submit_button("הוסף משימה לפרויקט"):
                                    if t_title: requests.post(f"{API_URL}/projects/{proj['id']}/tasks/",
                                                              json={"title": t_title, "assigned_to": t_assignee,
                                                                    "priority": t_priority}); st.rerun()

                        # -- תקציב משוחזר! --
                        with tab_budget:
                            total_expenses = sum(exp['final_price'] for exp in proj.get('expenses', []))
                            remaining_budget = proj['initial_budget'] - total_expenses
                            m1, m2, m3 = st.columns(3)
                            m1.metric("תקציב", f"₪{proj['initial_budget']:,.0f}")
                            m2.metric("הוצאות", f"₪{total_expenses:,.0f}")
                            m3.metric("יתרה", f"₪{remaining_budget:,.0f}", delta=float(remaining_budget))

                            if proj.get('expenses'):
                                for exp in proj['expenses']:
                                    st.write(f"💸 **{exp['title']}** - ₪{exp['final_price']:,.0f}")

                            with st.form(f"add_exp_{proj['id']}"):
                                cat_opts = {"101": "יציקת בטון", "102": "בניית קיר", "103": "נקודת חשמל"}
                                e_cat = st.selectbox("סעיף דקל", list(cat_opts.keys()),
                                                     format_func=lambda x: f"{x} - {cat_opts[x]}")
                                e_price = st.number_input("מחיר מותאם (0 למקורי)", min_value=0.0, step=50.0)
                                if st.form_submit_button("הוסף הוצאה"):
                                    requests.post(f"{API_URL}/projects/{proj['id']}/expenses/",
                                                  json={"catalog_id": e_cat,
                                                        "custom_price": e_price if e_price > 0 else None})
                                    st.rerun()

                        # -- קבצים --
                        with tab_files:
                            if proj.get('files'):
                                for f in proj['files']:
                                    f_c1, f_c2, f_c3 = st.columns([3, 2, 1])
                                    f_c1.write(f"📄 **{f['filename']}** (מאת: {f['uploaded_by']})")

                                    view_link = f"{API_URL}/files/{f['id']}/view"
                                    dl_link = f"{API_URL}/files/{f['id']}/download"
                                    f_c2.markdown(
                                        f'<a href="{view_link}" target="_blank" style="text-decoration:none; margin-left:15px;">👁️ צפייה</a>'
                                        f'<a href="{dl_link}" target="_blank" style="text-decoration:none;">⬇️ הורדה</a>',
                                        unsafe_allow_html=True
                                    )

                                    if f['uploaded_by'] == current_user:
                                        if f_c3.button("🗑️ מחק", key=f"del_f_{f['id']}"):
                                            requests.delete(f"{API_URL}/files/{f['id']}")
                                            st.rerun()
                                    else:
                                        f_c3.markdown("<span style='color:gray; font-size:14px;'>🔒 קריאה בלבד</span>",
                                                      unsafe_allow_html=True)
                                    st.divider()
                            else:
                                st.info("אין קבצים מצורפים לפרויקט זה. היה הראשון להעלות שרטוט!")

                            with st.form(f"add_file_{proj['id']}"):
                                st.write("➕ **הוספת קובץ לפרויקט:**")
                                uploaded_file = st.file_uploader("בחר קובץ (PDF, שרטוט, תמונה)", key=f"up_{proj['id']}")
                                if st.form_submit_button("העלה קובץ"):
                                    if uploaded_file:
                                        files_payload = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                                        data_payload = {"uploaded_by": current_user}
                                        requests.post(f"{API_URL}/projects/{proj['id']}/files/", files=files_payload,
                                                      data=data_payload)
                                        st.success("הקובץ הועלה!")
                                        st.rerun()

                        if st.button("🚨 מחק פרויקט", key=f"del_proj_{proj['id']}"):
                            requests.delete(f"{API_URL}/projects/{proj['id']}")
                            st.rerun()
    except:
        st.error("שגיאת התחברות לשרת.")

# ---------------------------------------------------------
# לשונית 3: מרכז המשימות האישיות
# ---------------------------------------------------------
with main_tab_personal:
    st.info("💡 המשימות והפגישות שתוסיפי כאן יופיעו בלוח השנה בתפריט בצד. את יכולה גם להוסיף אותן ישירות משם!")

    with st.form("new_personal_task_form_main"):
        st.write("➕ טופס הוספה כללי ליומן:")
        c1, c2, c3 = st.columns([2, 1, 1])
        pt_title = c1.text_input("שם המשימה או הפגישה")
        pt_date = c2.date_input("תאריך הפגישה")
        pt_priority = c3.slider("רמת דחיפות", 1, 5, 3, key="main_slider")

        if st.form_submit_button("הוסף ליומן"):
            if pt_title:
                requests.post(f"{API_URL}/personal_tasks/", json={
                    "title": pt_title,
                    "assigned_to": current_user,
                    "priority": pt_priority,
                    "date": pt_date.strftime("%Y-%m-%d")
                })
                st.success("✅ התווסף בהצלחה ללוח השנה בצד!")

                st.rerun()
