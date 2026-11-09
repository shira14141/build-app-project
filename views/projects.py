"""דף ניהול פרויקטים.

בלי פרמטר בכתובת: רשימת הפרויקטים שהמשתמש רשאי לראות, בטבלה עם חיפוש וסינון.
עם ?id=<מזהה>: דף פרויקט בודד (אפשר לשמור אותו כסימנייה או לשלוח קישור).
הכפתורים מוצגים לפי ההרשאות של המשתמש; השרת בודק את ההרשאות שוב בכל פעולה.
"""
import pandas as pd
import streamlit as st

import api
import ui
import worklog_ui
from constants import (PERM_WRITE_WORK_LOG, DEKEL_CATALOG, PERM_CREATE_PROJECT, PERM_DELETE_ANY_FILE, PERM_DELETE_PROJECT,
                       PERM_EDIT_PROJECT, PERM_MANAGE_BUDGET, PERM_MANAGE_TASKS, PERM_UPLOAD_FILES, STATUS_BLOCKED, STATUS_DONE,
                       STATUS_IN_PROGRESS, STATUS_PENDING, STATUSES)

SECTION_TASKS, SECTION_TEAM, SECTION_LOG, SECTION_BUDGET, SECTION_FILES, SECTION_SETTINGS = (
    "📋 משימות", "👷 צוות", "📝 יומן", "💰 תקציב", "📂 קבצים", "⚙️ הגדרות")
FILTER_ALL, FILTER_RISK, FILTER_BLOCKED, FILTER_OPEN = "הכל", "בסיכון", "עם חסימות", "עם משימות פתוחות"


def open_project(project_id):
    st.query_params["id"] = str(project_id)


def close_project():
    st.query_params.pop("id", None)


def active_usernames():
    users, error = ui.load(api.get_users)
    if error:
        st.error(f"לא ניתן לטעון את רשימת המשתמשים: {error}")
        return []
    return [u["username"] for u in users if u["is_active"]]


# =========================================================
# רשימת הפרויקטים
# =========================================================
def render_create_form():
    with st.expander("➕ יצירת פרויקט חדש"):
        with st.form("new_project_form"):
            col1, col2 = st.columns(2)
            name = col1.text_input("שם הפרויקט")
            budget = col1.number_input("תקציב ראשוני", min_value=0.0, step=1000.0)
            members = col2.multiselect("שותפי עבודה", options=[u for u in active_usernames() if u != ui.current_user()],
                                       help="רק שותפים יראו את הפרויקט. אתה מצורף אוטומטית.")
            if st.form_submit_button("צור פרויקט חדש", type="primary"):
                if not name.strip():
                    st.warning("יש למלא שם לפרויקט.")
                else:
                    ui.submit_action(api.create_project, name.strip(), budget, members,
                                     success=f"הפרויקט '{name.strip()}' נוצר בהצלחה!")


def render_list():
    st.title("🏗️ פרויקטים")
    if ui.can(PERM_CREATE_PROJECT):
        render_create_form()

    projects, error = ui.load(api.get_projects)
    if error:
        st.error(f"לא ניתן לטעון את הפרויקטים: {error}")
        return
    if not projects:
        st.info("אין עדיין פרויקטים שאתה שותף בהם.")
        return

    f1, f2, f3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    search = f1.text_input("🔍 חיפוש לפי שם פרויקט או שותף", key="projects_search")
    status_filter = f2.segmented_control("סינון", [FILTER_ALL, FILTER_RISK, FILTER_BLOCKED, FILTER_OPEN],
                                         default=FILTER_ALL, key="projects_filter") or FILTER_ALL
    only_mine = f3.toggle("רק שלי", key="projects_only_mine")

    rows = []
    for p in projects:
        risk = ui.project_risk(p)
        if search and search not in p["name"] and not any(search in m for m in p["members"]):
            continue
        if only_mine and ui.current_user() not in p["members"]:
            continue
        if status_filter == FILTER_RISK and not risk:
            continue
        if status_filter == FILTER_OPEN and not p["open"]:
            continue
        if status_filter == FILTER_BLOCKED and not p["blocked"]:
            continue
        # העמודות החשובות ראשונות - כך הן נראות גם בטלפון בלי גלילה הצידה
        rows.append({
            "מצב": {"high": "🚨", "warn": "⚠️"}[risk[0]] if risk else "✅", "שם": p["name"],
            "ניצול": p["spent_pct"], "משימות פתוחות": p["open"], "חסומות": p["blocked"],
            "התקדמות": p["done_pct"],
            "תקציב": p["initial_budget"], "הוצאות": p["spent"], "שותפים": ", ".join(p["members"]),
            "קבצים": p["files"], "id": p["id"],
        })

    st.caption(f"מוצגים {len(rows)} מתוך {len(projects)} פרויקטים · הקש על שורה כדי לפתוח את הפרויקט")
    if not rows:
        st.info("אין פרויקטים שמתאימים לסינון.")
        return

    event = st.dataframe(
        pd.DataFrame(rows), hide_index=True, on_select="rerun", selection_mode="single-row", key="projects_table",
        column_config={
            "id": st.column_config.NumberColumn("מזהה", width="small"),
            "מצב": st.column_config.TextColumn(width="small"),
            "משימות פתוחות": st.column_config.NumberColumn("פתוחות", width="small"),
            "חסומות": st.column_config.NumberColumn("🚧", width="small", help="משימות חסומות"),
            "תקציב": st.column_config.NumberColumn("תקציב (₪)", format="localized"),
            "הוצאות": st.column_config.NumberColumn("הוצאות (₪)", format="localized"),
            "ניצול": st.column_config.ProgressColumn("ניצול תקציב", format="%.0f%%", min_value=0, max_value=100),
            "התקדמות": st.column_config.ProgressColumn("משימות שהושלמו", format="%.0f%%", min_value=0,
                                                       max_value=100),
        },
    )
    if event.selection.rows:
        open_project(rows[event.selection.rows[0]]["id"])
        st.rerun()


# =========================================================
# דף פרויקט בודד
# =========================================================
def render_tasks(proj):
    if not proj["task_list"]:
        st.info("אין משימות בפרויקט.")
    manage = ui.can(PERM_MANAGE_TASKS)
    # חסומות קודם (דורשות טיפול), אחר כך לפי דחיפות; שהושלמו - בסוף, מקופלות
    tasks = sorted(proj["task_list"],
                   key=lambda x: (x["status"] == STATUS_DONE, x["status"] != STATUS_BLOCKED, -x["priority"]))
    open_tasks = [t for t in tasks if t["status"] != STATUS_DONE]
    done_tasks = [t for t in tasks if t["status"] == STATUS_DONE]
    if manage and tasks and st.toggle("✏️ עריכה בטבלה", key=f"table_mode_{proj['id']}",
                                      help="עריכה מרוכזת של כמה משימות בבת אחת - נוח במשרד. בטלפון עדיפים הכרטיסים."):
        render_tasks_table(proj, tasks)
        tasks = []  # במצב טבלה לא מציגים כרטיסים
        open_tasks, done_tasks = [], []
    for task in open_tasks:
        ui.task_card(task, proj["id"], f"p_{proj['id']}", allow_delete=manage)
    if done_tasks:
        # משימות שהושלמו מקופלות - פחות עומס ויזואלי, במיוחד בטלפון
        with st.expander(f"✅ הושלמו ({len(done_tasks)})"):
            for task in done_tasks:
                ui.task_card(task, proj["id"], f"p_{proj['id']}", allow_delete=manage)

    if manage:
        with st.form(f"add_task_{proj['id']}", clear_on_submit=True):
            st.markdown("**➕ משימה חדשה**")
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("מה צריך לעשות?")
            assignee = c2.selectbox("שייך למי?", options=proj["members"], placeholder="אין שותפים בפרויקט")
            priority = c3.slider("דחיפות", 1, 5, 3)
            if st.form_submit_button("הוסף משימה לפרויקט"):
                if not title.strip():
                    st.warning("יש לכתוב מה צריך לעשות.")
                elif not assignee:
                    st.warning("יש לצרף שותפים לפרויקט (בהגדרות) לפני שמשייכים משימות.")
                else:
                    ui.submit_action(api.add_task, proj["id"], title, assignee, priority, success="המשימה נוספה.")


def render_tasks_table(proj, tasks):
    """עריכה מרוכזת ב-st.data_editor: משנים כמה תאים ושומרים פעם אחת. השרת שומר הכל או כלום."""
    pid = proj["id"]
    version = st.session_state.get(f"table_version_{pid}", 0)  # מתחלף אחרי שמירה - הטבלה נטענת מחדש מהשרת
    with st.form(f"tasks_table_{pid}_{version}"):
        edited = st.data_editor(
            ui.tasks_to_table(tasks), key=f"tasks_editor_{pid}_{version}", hide_index=True,
            use_container_width=True, num_rows="fixed", column_order=ui.TABLE_COLUMNS,
            column_config={
                ui.COL_TITLE: st.column_config.TextColumn(required=True, max_chars=200, width="large"),
                ui.COL_ASSIGNEE: st.column_config.SelectboxColumn(options=proj["members"], required=True),
                ui.COL_PRIORITY: st.column_config.NumberColumn(min_value=1, max_value=5, step=1, format="%d",
                                                               width="small", required=True),
                ui.COL_STATUS: st.column_config.SelectboxColumn(options=STATUSES, required=True),
                ui.COL_REASON: st.column_config.TextColumn(max_chars=500, help="חובה כשהסטטוס 'חסום'"),
            })
        submitted = st.form_submit_button("💾 שמירת השינויים", type="primary")
    if not submitted:
        return
    updates, errors = ui.diff_task_table(tasks, edited.to_dict("records"))
    if errors:
        for message in errors:
            st.error(message)
    elif not updates:
        st.info("לא בוצעו שינויים.")
    else:
        count, error = ui.load(api.bulk_update_tasks, pid, updates)
        if error:
            st.error(f"השינויים לא נשמרו: {error}")
            return
        ui.flash("success", "משימה אחת עודכנה." if count == 1 else f"עודכנו {count} משימות.")
        st.session_state[f"table_version_{pid}"] = version + 1
        st.rerun()


def render_team(proj):
    """סטטוס קבלנים: לכל שותף - משימות לפי סטטוס, התקדמות ומתי דיווח לאחרונה ביומן."""
    logs, error = ui.load(api.get_work_logs, proj["id"])
    if error:
        st.warning(f"לא ניתן לטעון את היומן - עמודת 'דיווח אחרון' לא תוצג: {error}")
        logs = []
    rows = ui.contractor_status(proj["members"], proj["task_list"], logs)
    if not rows:
        st.info("אין שותפים בפרויקט. אפשר לצרף אותם באזור ההגדרות.")
        return
    blocked_people = [r["name"] for r in rows if r[STATUS_BLOCKED]]
    if blocked_people:
        st.warning(f"🚧 יש חסימות פתוחות אצל: {', '.join(blocked_people)}")
    st.dataframe(pd.DataFrame([{
        "שם": r["name"],
        "🚧 חסומות": r[STATUS_BLOCKED],
        "⏳ פתוחות": r[STATUS_PENDING] + r[STATUS_IN_PROGRESS],
        "דיווח אחרון": ui.days_ago(r["last_report"]),
        "התקדמות": r["done_pct"],
        "🔨 בתהליך": r[STATUS_IN_PROGRESS],
        "✅ הושלמו": r[STATUS_DONE],
    } for r in rows]), hide_index=True, use_container_width=True, column_config={
        "התקדמות": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
    })
    st.caption("'דיווח אחרון' - הדיווח האחרון ביומן העבודה שהשותף כתב או שהצוות שלו מופיע בו.")


def render_log(proj):
    if ui.can(PERM_WRITE_WORK_LOG):
        st.page_link("views/work_log.py", label="דיווח יומן עבודה לפרויקט הזה", icon="📝",
                     query_params={"id": str(proj["id"])})
    worklog_ui.render_history(proj["id"])


def render_budget(proj):
    if proj["initial_budget"] > 0:
        st.progress(min(proj["spent_pct"], 100) / 100, text=f"נוצלו {proj['spent_pct']:.0f}% מהתקציב")
    expenses = proj["expense_list"]
    if expenses:
        st.dataframe(pd.DataFrame([{"סעיף דקל": e["catalog_id"], "תיאור": e["title"], "מחיר": e["final_price"]}
                                   for e in expenses]),
                     hide_index=True, column_config={"מחיר": st.column_config.NumberColumn("מחיר (₪)",
                                                                                          format="localized")})
    else:
        st.info("לא נרשמו הוצאות בפרויקט.")

    if not ui.can(PERM_MANAGE_BUDGET):
        return
    with st.form(f"add_exp_{proj['id']}", clear_on_submit=True):
        st.markdown("**➕ הוצאה חדשה**")
        c1, c2 = st.columns(2)
        catalog_id = c1.selectbox("סעיף דקל", list(DEKEL_CATALOG),
                                  format_func=lambda x: f"{x} - {DEKEL_CATALOG[x]['title']} "
                                                        f"({ui.money(DEKEL_CATALOG[x]['default_price'])})")
        price = c2.number_input("מחיר מותאם (0 = מחיר הקטלוג)", min_value=0.0, step=50.0)
        if st.form_submit_button("הוסף הוצאה"):
            ui.submit_action(api.add_expense, proj["id"], catalog_id, price if price > 0 else None,
                             success="ההוצאה נוספה.")
    if expenses:
        with st.popover("🗑️ מחיקת הוצאה"):
            labels = {e["id"]: f"{e['title']} - {ui.money(e['final_price'])}" for e in expenses}
            expense_id = st.selectbox("איזו הוצאה למחוק?", list(labels), format_func=labels.get,
                                      key=f"del_exp_pick_{proj['id']}")
            st.button("מחק הוצאה", key=f"del_exp_{proj['id']}", on_click=ui.action,
                      args=(api.delete_expense, proj["id"], expense_id), kwargs={"success": "ההוצאה נמחקה."})


def render_files(proj):
    if not proj["file_list"]:
        st.info("אין קבצים מצורפים לפרויקט זה.")
    for f in proj["file_list"]:
        # כרטיס עם שורת כפתורים אופקית - נשבר לשורות בטלפון במקום להידחס בעמודות
        with st.container(border=True):
            st.markdown(f"📄 **{f['filename']}**  \n<small>מאת {f['uploaded_by']} · {ui.file_size(f['size'])}</small>",
                        unsafe_allow_html=True)
            with st.container(horizontal=True, vertical_alignment="center"):
                st.link_button("👁️ צפייה", api.absolute_url(f["view_url"]))
                st.link_button("⬇️ הורדה", api.absolute_url(f["download_url"]))
                if f["uploaded_by"] == ui.current_user() or ui.can(PERM_DELETE_ANY_FILE):
                    ui.delete_button(st, f"del_f_{f['id']}", api.delete_file, proj["id"], f["id"],
                                     success="הקובץ נמחק.")
                else:
                    st.caption("🔒 קריאה בלבד")

    if ui.can(PERM_UPLOAD_FILES):
        with st.form(f"add_file_{proj['id']}", clear_on_submit=True):
            uploaded = st.file_uploader("➕ הוספת קובץ (PDF, שרטוט, תמונה)")
            if st.form_submit_button("העלה קובץ"):
                if not uploaded:
                    st.warning("יש לבחור קובץ להעלאה.")
                else:
                    ui.submit_action(api.upload_file, proj["id"], uploaded.name, uploaded.getvalue(),
                                     success=f"הקובץ '{uploaded.name}' הועלה!")


def render_settings(proj):
    with st.form(f"edit_project_{proj['id']}"):
        name = st.text_input("שם הפרויקט", value=proj["name"])
        budget = st.number_input("תקציב", min_value=0.0, step=1000.0, value=float(proj["initial_budget"]))
        options = sorted(set(active_usernames()) | set(proj["members"]))
        members = st.multiselect("שותפי עבודה", options=options, default=proj["members"],
                                 help="משימות של שותף שהוסר נשארות בפרויקט.")
        if st.form_submit_button("שמור שינויים", type="primary"):
            if not name.strip():
                st.warning("יש למלא שם לפרויקט.")
            else:
                ui.submit_action(api.update_project, proj["id"], name=name.strip(), initial_budget=budget,
                                 members=members, success="הפרויקט עודכן.")

    if ui.can(PERM_DELETE_PROJECT):
        with st.popover("🚨 מחיקת הפרויקט"):
            st.write(f"למחוק את **{proj['name']}** יחד עם כל המשימות, ההוצאות והקבצים שלו? אי אפשר לבטל.")
            if st.button("כן, מחק לצמיתות", type="primary", key=f"confirm_del_{proj['id']}"):
                if ui.action(api.delete_project, proj["id"], success=f"הפרויקט '{proj['name']}' נמחק."):
                    close_project()
                st.rerun()


def render_project(project_id):
    proj, error = ui.load(api.get_project, project_id)
    if error:
        st.warning(error)
        st.button("→ חזרה לרשימה", on_click=close_project)
        return

    top_left, top_right = st.columns([5, 1], vertical_alignment="center")
    top_left.title(f"🏢 {proj['name']}")
    top_right.button("→ חזרה לרשימה", on_click=close_project, use_container_width=True)
    st.caption(f"מזהה: {proj['id']} · שותפים: {', '.join(proj['members']) or 'אין'}")

    risk = ui.project_risk(proj)
    if risk:
        st.warning(risk[1])
    ui.budget_metrics(proj)

    sections = [SECTION_TASKS, SECTION_TEAM, SECTION_LOG, SECTION_BUDGET, SECTION_FILES]
    if ui.can(PERM_EDIT_PROJECT) or ui.can(PERM_DELETE_PROJECT):
        sections.append(SECTION_SETTINGS)
    # בקרה עם key שומרת את הבחירה בין רענונים ומרנדרת רק את האזור שנבחר
    section = st.segmented_control("אזור", sections, default=SECTION_TASKS, key="project_section",
                                   label_visibility="collapsed")
    if section not in sections:
        section = SECTION_TASKS
    progress = f" ({proj['done']}/{proj['tasks']} הושלמו)" if section == SECTION_TASKS and proj["tasks"] else ""
    st.subheader(section + progress)
    {SECTION_TASKS: render_tasks, SECTION_TEAM: render_team, SECTION_LOG: render_log, SECTION_BUDGET: render_budget,
     SECTION_FILES: render_files, SECTION_SETTINGS: render_settings}[section](proj)


# =========================================================
selected_id = st.query_params.get("id")
if selected_id is None:
    render_list()
elif not selected_id.isdigit():
    st.warning("מזהה פרויקט לא תקין.")
    st.button("→ חזרה לרשימה", on_click=close_project)
else:
    render_project(int(selected_id))
