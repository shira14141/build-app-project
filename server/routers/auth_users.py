"""התחברות, החלפת סיסמה וניהול משתמשים."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from constants import PERM_MANAGE_USERS, has_permission
from server.auth import (create_access_token, get_current_user, get_user_allow_password_change, hash_password,
                         require_permission, verify_password)
from server.db import get_db
from server.logging_setup import audit
from server.models import User
from server.ratelimit import login_limiter
from server.schemas import ChangePasswordRequest, LoginRequest, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter()

# hash אמיתי (של מחרוזת אקראית) כדי שבדיקת משתמש שלא קיים תיקח אותו זמן כמו משתמש קיים
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _user_out(user: User) -> UserOut:
    return UserOut(username=user.username, role=user.role, must_change_password=user.must_change_password,
                   is_active=user.is_active)


@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    username = req.username.strip()
    client_ip = request.client.host if request.client else "-"
    retry_after = login_limiter.retry_after(username)
    if retry_after:
        audit.warning("Login blocked (too many failures) user=%s ip=%s", username, client_ip)
        raise HTTPException(status_code=429, detail="Too many failed attempts",
                            headers={"Retry-After": str(retry_after)})
    user = db.query(User).filter_by(username=username).first()
    if not verify_password(req.password, user.password_hash if user else _DUMMY_HASH) or not user.is_active:
        login_limiter.record_failure(username)
        audit.warning("Login failed user=%s ip=%s", username, client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    login_limiter.reset(username)
    audit.info("Login ok user=%s role=%s ip=%s", user.username, user.role, client_ip)
    return TokenOut(access_token=create_access_token(user), user=_user_out(user))


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: User = Depends(get_user_allow_password_change)):
    return _user_out(user)


@router.post("/auth/change-password", response_model=UserOut, tags=["auth"])
def change_password(req: ChangePasswordRequest, user: User = Depends(get_user_allow_password_change),
                    db: Session = Depends(get_db)):
    if not verify_password(req.current_password, user.password_hash):
        audit.warning("Password change failed (wrong current password) user=%s", user.username)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    user.password_hash = hash_password(req.new_password)
    user.must_change_password = False
    db.commit()
    audit.info("Password changed user=%s", user.username)
    return _user_out(user)


@router.get("/users/", response_model=list[UserOut], tags=["users"])
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """מנהל מערכת רואה את כולם; שאר המשתמשים רואים רק משתמשים פעילים (לבחירת שותפים ואחראים)."""
    query = db.query(User).order_by(User.username)
    if not has_permission(user.role, PERM_MANAGE_USERS):
        query = query.filter(User.is_active.is_(True))
    return [_user_out(u) for u in query]


@router.post("/users/", response_model=UserOut, status_code=201, tags=["users"])
def create_user(req: UserCreate, admin: User = Depends(require_permission(PERM_MANAGE_USERS)),
                db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=req.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=req.username, password_hash=hash_password(req.password), role=req.role,
                must_change_password=True, is_active=True)
    db.add(user)
    db.commit()
    audit.info("User created user=%s role=%s by=%s", user.username, user.role, admin.username)
    return _user_out(user)


@router.patch("/users/{username}", response_model=UserOut, tags=["users"])
def update_user(username: str, req: UserUpdate, admin: User = Depends(require_permission(PERM_MANAGE_USERS)),
                db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and (req.role not in (None, user.role) or req.is_active is False):
        raise HTTPException(status_code=400, detail="You cannot demote or deactivate yourself")
    if req.role is not None:
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.new_password is not None:
        user.password_hash = hash_password(req.new_password)
        user.must_change_password = True
    db.commit()
    changes = [name for name in ("role", "is_active") if getattr(req, name) is not None]
    if req.new_password is not None:
        changes.append("password_reset")  # רק העובדה שאופסה - לא הסיסמה עצמה
    audit.info("User updated user=%s changes=%s role=%s active=%s by=%s", user.username, ",".join(changes),
               user.role, user.is_active, admin.username)
    return _user_out(user)
