"""אימות והרשאות: הצפנת סיסמאות, טוקני JWT, ובדיקות גישה לפרויקטים.

כל בדיקת הרשאה נעשית כאן בשרת. הממשק רק מסתיר כפתורים - הוא לא מקור האמת.
"""
import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from constants import PERM_SEE_ALL_PROJECTS, has_permission
from server.config import ACCESS_TOKEN_HOURS, FILE_LINK_MINUTES, SECRET_KEY
from server.db import get_db
from server.models import Project, ProjectMember, User

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


# ---------------- סיסמאות ----------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# ---------------- טוקנים ----------------

def _encode(payload: dict, lifetime: dt.timedelta) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({**payload, "iat": now, "exp": now + lifetime}, SECRET_KEY, algorithm=ALGORITHM)


def _decode(token: str, expected_type: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == expected_type else None


def create_access_token(user: User) -> str:
    return _encode({"sub": user.username, "typ": "access"}, dt.timedelta(hours=ACCESS_TOKEN_HOURS))


def create_file_token(file_id: str) -> str:
    """טוקן קצר-מועד לקובץ אחד בלבד - מאפשר לפתוח קובץ בלשונית חדשה בלי לחשוף את טוקן ההתחברות."""
    return _encode({"sub": file_id, "typ": "file"}, dt.timedelta(minutes=FILE_LINK_MINUTES))


def verify_file_token(token: str, file_id: str) -> bool:
    payload = _decode(token, "file")
    return bool(payload) and payload.get("sub") == file_id


# ---------------- המשתמש הנוכחי ----------------

def _unauthorized(detail="Not authenticated"):
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_user_allow_password_change(request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer),
                                   db: Session = Depends(get_db)) -> User:
    """משתמש מחובר - גם אם הוא עדיין חייב להחליף סיסמה (לשימוש בנתיבי 'אני' והחלפת סיסמה)."""
    if creds is None:
        raise _unauthorized()
    payload = _decode(creds.credentials, "access")
    if payload is None:
        raise _unauthorized("Invalid or expired token")
    user = db.query(User).filter_by(username=payload["sub"]).first()
    if user is None or not user.is_active:
        raise _unauthorized("User is inactive")
    request.state.username = user.username  # לשורת הלוג של הבקשה
    return user


def get_current_user(user: User = Depends(get_user_allow_password_change)) -> User:
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Password change required")
    return user


def require(user: User, permission: str):
    if not has_permission(user.role, permission):
        raise HTTPException(status_code=403, detail="Permission denied")


def require_permission(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        require(user, permission)
        return user
    return dependency


# ---------------- גישה לפרויקטים ----------------

def can_see_all(user: User) -> bool:
    return has_permission(user.role, PERM_SEE_ALL_PROJECTS)


def visible_projects_query(db: Session, user: User):
    query = db.query(Project)
    if not can_see_all(user):
        query = query.join(ProjectMember).filter(ProjectMember.username == user.username)
    return query


def get_project_for(db: Session, user: User, project_id: int, permission: str = None) -> Project:
    """מחזיר פרויקט רק אם המשתמש רשאי לראות אותו (ולבצע בו את הפעולה, אם צוינה).
    פרויקט שהמשתמש לא שותף בו מחזיר 404 - כדי לא לחשוף שהוא קיים."""
    project = db.get(Project, project_id)
    if project is None or not (can_see_all(user) or user.username in project.member_names):
        raise HTTPException(status_code=404, detail="Project not found")
    if permission:
        require(user, permission)
    return project
