"""קבועים משותפים לשרת ולממשק - מקור אמת אחד במקום עותקים בכל קובץ."""

STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_DONE = "ממתין", "בתהליך", "חסום", "בוצע"
STATUSES = [STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_DONE]
# ביומן האישי אין "חסום" - זה סטטוס של עבודה באתר
PERSONAL_STATUSES = [STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_DONE]
BLOCKED_ALERT_DAYS = 3       # חסימה פתוחה יותר מזה מופיעה בתובנות ההנהלה

# יומן עבודה
WEATHER_OPTIONS = ["☀️ בהיר", "⛅ מעונן", "🌧️ גשם", "🔥 חום קיצוני", "💨 רוח חזקה"]
MAX_CREW_ROWS = 30
MAX_WORKERS_PER_ROW = 500

DEKEL_CATALOG = {
    "101": {"title": "יציקת בטון", "default_price": 350.0},
    "102": {"title": "בניית קיר", "default_price": 120.0},
    "103": {"title": "נקודת חשמל", "default_price": 250.0},
}

URGENT_PRIORITY = 4          # מדחיפות זו ומעלה המשימה מסומנת 🔥
RISK_SPENT_PCT = 80          # ניצול תקציב שמעליו בודקים התקדמות
RISK_DONE_PCT = 50           # ...ואם פחות מזה מהמשימות הושלמו - סיכון גבוה
OVER_BUDGET_WARN_PCT = 90    # ניצול תקציב שמעליו מזהירים על חריגה קרובה

MIN_PASSWORD_LENGTH = 8

# =========================================================
# תפקידים והרשאות (RBAC)
# =========================================================
ROLE_ADMIN, ROLE_MANAGER, ROLE_CONTRACTOR, ROLE_VIEWER = "admin", "manager", "contractor", "viewer"
ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_CONTRACTOR, ROLE_VIEWER]
ROLE_LABELS = {
    ROLE_ADMIN: "מנהל מערכת",
    ROLE_MANAGER: "מנהל פרויקט",
    ROLE_CONTRACTOR: "קבלן / בעל מקצוע",
    ROLE_VIEWER: "צופה",
}

PERM_CREATE_PROJECT = "create_project"      # יצירת פרויקט חדש
PERM_EDIT_PROJECT = "edit_project"          # שינוי שם, תקציב ושותפים
PERM_DELETE_PROJECT = "delete_project"
PERM_MANAGE_TASKS = "manage_tasks"          # הוספה, מחיקה ושינוי סטטוס של כל משימה
PERM_UPDATE_OWN_TASKS = "update_own_tasks"  # שינוי סטטוס רק למשימות שמשויכות אליי
PERM_MANAGE_BUDGET = "manage_budget"        # הוספה ומחיקה של הוצאות
PERM_UPLOAD_FILES = "upload_files"
PERM_DELETE_ANY_FILE = "delete_any_file"    # מחיקת קבצים של אחרים (את שלי - תמיד מותר)
PERM_MANAGE_USERS = "manage_users"
PERM_SEE_ALL_PROJECTS = "see_all_projects"  # בלי זה - רואים רק פרויקטים שאני שותף בהם
PERM_VIEW_DASHBOARD = "view_dashboard"      # לוח בקרה הנהלה (גרפים ותובנות)
PERM_WRITE_WORK_LOG = "write_work_log"      # דיווח יומן עבודה בפרויקטים שאני שותף בהם
PERM_MANAGE_WORK_LOGS = "manage_work_logs"  # מחיקת דיווחים של אחרים (את שלי - תמיד מותר)

ROLE_PERMISSIONS = {
    ROLE_ADMIN: {PERM_CREATE_PROJECT, PERM_EDIT_PROJECT, PERM_DELETE_PROJECT, PERM_MANAGE_TASKS,
                 PERM_UPDATE_OWN_TASKS, PERM_MANAGE_BUDGET, PERM_UPLOAD_FILES, PERM_DELETE_ANY_FILE,
                 PERM_MANAGE_USERS, PERM_SEE_ALL_PROJECTS, PERM_VIEW_DASHBOARD, PERM_WRITE_WORK_LOG,
                 PERM_MANAGE_WORK_LOGS},
    ROLE_MANAGER: {PERM_CREATE_PROJECT, PERM_EDIT_PROJECT, PERM_DELETE_PROJECT, PERM_MANAGE_TASKS,
                   PERM_UPDATE_OWN_TASKS, PERM_MANAGE_BUDGET, PERM_UPLOAD_FILES, PERM_DELETE_ANY_FILE,
                   PERM_VIEW_DASHBOARD, PERM_WRITE_WORK_LOG, PERM_MANAGE_WORK_LOGS},
    ROLE_CONTRACTOR: {PERM_UPDATE_OWN_TASKS, PERM_UPLOAD_FILES, PERM_WRITE_WORK_LOG},
    ROLE_VIEWER: set(),
}


def has_permission(role, permission):
    return permission in ROLE_PERMISSIONS.get(role, set())
