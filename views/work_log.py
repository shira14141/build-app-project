"""דף יומן עבודה - דיווח יומי מהאתר, מותאם לטלפון.

הטופס עטוף ב-st.form (אין רענון בזמן הקלדה). הוא לא מתרוקן כשיש שגיאת ולידציה - טקסט ארוך
שנכתב בשטח לא הולך לאיבוד. אחרי שמירה מוצלחת הטופס נבנה מחדש ריק (key חדש).
צוותים נערכים ישירות בטבלה (st.data_editor).
"""
from datetime import date

import pandas as pd
import streamlit as st

import api
import ui
import worklog_ui
from constants import MAX_WORKERS_PER_ROW, PERM_UPLOAD_FILES, PERM_WRITE_WORK_LOG, WEATHER_OPTIONS
from worklog_ui import CREW_NAME, CREW_WORKERS
PHOTO_TYPES = ["jpg", "jpeg", "png", "webp"]

st.title("📝 יומן עבודה")

projects, error = ui.load(api.get_projects)
if error:
    st.error(f"לא ניתן לטעון את הפרויקטים: {error}")
    st.stop()
if not projects:
    st.info("אין עדיין פרויקטים שאתה שותף בהם.")
    st.stop()

# בחירת פרויקט: מקישור (?id=) -> הבחירה הקודמת -> הראשון ברשימה
names = {p["id"]: p["name"] for p in projects}
requested = st.query_params.get("id")
if requested and requested.isdigit() and int(requested) in names:
    st.session_state["wl_project"] = int(requested)
    st.query_params.pop("id", None)
if st.session_state.get("wl_project") not in names:
    st.session_state.pop("wl_project", None)
project_id = st.selectbox("פרויקט", list(names), format_func=names.get, key="wl_project")

project, error = ui.load(api.get_project, project_id)
if error:
    st.error(error)
    st.stop()

worklog_ui.render_open_blockers(project)


def save(log_date, weather, crew, work_done, issues, photos):
    log_id, error = ui.load(api.create_work_log, project_id, log_date.isoformat(), weather, crew,
                            work_done.strip(), issues.strip() or None)
    if error:
        st.error(f"הדיווח לא נשמר: {error}")
        return
    failed = []
    for photo in photos:
        _, photo_error = ui.load(api.upload_file, project_id, photo.name, photo.getvalue(), log_id)
        if photo_error:
            failed.append(f"{photo.name} ({photo_error})")
    if failed:
        ui.flash("error", "הדיווח נשמר, אבל חלק מהתמונות לא הועלו: " + ", ".join(failed))
    else:
        extra = f" עם {len(photos)} תמונות" if photos else ""
        ui.flash("success", f"הדיווח ל-{log_date:%d/%m/%Y} נשמר{extra}.")
    st.session_state["wl_form_no"] = st.session_state.get("wl_form_no", 0) + 1  # טופס חדש וריק
    st.rerun()


if ui.can(PERM_WRITE_WORK_LOG):
    st.subheader("דיווח חדש")
    form_no = st.session_state.get("wl_form_no", 0)
    can_attach = ui.can(PERM_UPLOAD_FILES)
    use_camera = can_attach and st.toggle("📷 צילום במצלמה", key="wl_camera",
                                          help="מאפשר לצלם ישירות מהטלפון. אפשר גם לבחור תמונות מהגלריה בטופס.")
    with st.form(f"work_log_form_{project_id}_{form_no}"):
        log_date = st.date_input("תאריך", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
        weather = st.segmented_control("מזג אוויר", WEATHER_OPTIONS, default=WEATHER_OPTIONS[0])

        st.markdown("**👷 צוותים באתר**")
        st.caption("עורכים ישירות בטבלה. שורות עם 0 עובדים לא נשמרות; אפשר להוסיף שורה לצוות חיצוני.")
        crew_df = st.data_editor(
            pd.DataFrame([{CREW_NAME: m, CREW_WORKERS: 0} for m in project["members"]],
                         columns=[CREW_NAME, CREW_WORKERS]),
            num_rows="dynamic", hide_index=True, use_container_width=True, key=f"wl_crew_{project_id}_{form_no}",
            column_config={
                CREW_NAME: st.column_config.TextColumn(max_chars=100),
                CREW_WORKERS: st.column_config.NumberColumn(min_value=0, max_value=MAX_WORKERS_PER_ROW, step=1,
                                                            format="%d"),
            })

        work_done = st.text_area("מה בוצע היום? *", height=120, max_chars=4000,
                                 placeholder="למשל: יציקת רצפה בקומה 2, פירוק תבניות בגרם המדרגות")
        issues = st.text_area("עיכובים ובעיות", height=80, max_chars=4000,
                              placeholder="אופציונלי. חסימה שמונעת התקדמות במשימה - סמנו גם על המשימה עצמה.")
        photos = (st.file_uploader("📎 תמונות מהאתר", type=PHOTO_TYPES, accept_multiple_files=True)
                  if can_attach else [])
        camera_photo = st.camera_input("צילום") if use_camera else None
        submitted = st.form_submit_button("שמירת דיווח", type="primary")

    if submitted:
        errors, crew = worklog_ui.validate_work_log(log_date, crew_df.to_dict("records"), work_done)
        if errors:
            for message in errors:
                st.error(message)
        else:
            save(log_date, weather, crew, work_done, issues, list(photos or []) + ([camera_photo] if camera_photo else []))
else:
    st.info("לתפקיד שלך יש הרשאת צפייה ביומן בלבד.")

st.subheader("דיווחים קודמים")
worklog_ui.render_history(project_id)
