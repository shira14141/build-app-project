"""סכמות Pydantic: ולידציה לכל קלט שמגיע מהלקוח, ומבנה קבוע לכל תשובה."""
import datetime as dt
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from constants import (DEKEL_CATALOG, MAX_CREW_ROWS, MAX_WORKERS_PER_ROW, MIN_PASSWORD_LENGTH, ROLE_ADMIN,
                       ROLE_CONTRACTOR, ROLE_MANAGER, ROLE_VIEWER, STATUS_BLOCKED, STATUS_DONE, STATUS_IN_PROGRESS,
                       STATUS_PENDING, WEATHER_OPTIONS)

Status = Literal[STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_DONE]
PersonalStatus = Literal[STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_DONE]
Role = Literal[ROLE_ADMIN, ROLE_MANAGER, ROLE_CONTRACTOR, ROLE_VIEWER]
NonEmpty = Field(min_length=1, max_length=200)
Password = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


def _strip(value):
    value = value.strip()
    if not value:
        raise ValueError("must not be empty")
    return value


# ---------------- משתמשים והתחברות ----------------

class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: Role
    must_change_password: bool
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Password


class UserCreate(BaseModel):
    username: str = NonEmpty
    password: str = Password
    role: Role
    _clean = field_validator("username")(_strip)


class UserUpdate(BaseModel):
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=128)  # איפוס סיסמה ע"י מנהל - המשתמש יחויב להחליף בכניסה הבאה


# ---------------- פרויקטים ----------------

class ProjectCreate(BaseModel):
    name: str = NonEmpty
    initial_budget: float = Field(ge=0)
    members: List[str] = []
    _clean = field_validator("name")(_strip)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    initial_budget: Optional[float] = Field(default=None, ge=0)
    members: Optional[List[str]] = None


class TaskCreate(BaseModel):
    title: str = NonEmpty
    assigned_to: str
    priority: int = Field(ge=1, le=5)
    _clean = field_validator("title")(_strip)


class StatusUpdate(BaseModel):
    status: Status
    blocked_reason: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_required_when_blocked(self):
        if self.status == STATUS_BLOCKED:
            if not (self.blocked_reason or "").strip():
                raise ValueError("blocked_reason is required when status is blocked")
            self.blocked_reason = self.blocked_reason.strip()
        return self


class TaskBulkItem(BaseModel):
    """שורה אחת מעריכה בטבלה. רק שדות שנשלחו (ושונים מהקיים) משתנים."""
    id: str
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    assigned_to: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    status: Optional[Status] = None
    blocked_reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value):
        return None if value is None else _strip(value)


class TaskBulkUpdate(BaseModel):
    updates: List[TaskBulkItem] = Field(min_length=1, max_length=200)


class PersonalStatusUpdate(BaseModel):
    status: PersonalStatus


class ExpenseCreate(BaseModel):
    catalog_id: str
    custom_price: Optional[float] = Field(default=None, gt=0)

    @field_validator("catalog_id")
    @classmethod
    def _known_catalog_item(cls, value):
        if value not in DEKEL_CATALOG:
            raise ValueError("unknown catalog item")
        return value


class TaskOut(BaseModel):
    id: str
    title: str
    assigned_to: str
    priority: int
    status: str
    blocked_reason: Optional[str] = None
    blocked_since: Optional[dt.date] = None


class ExpenseOut(BaseModel):
    id: int
    catalog_id: str
    title: str
    final_price: float


class FileOut(BaseModel):
    id: str
    filename: str
    uploaded_by: str
    size: Optional[int]
    work_log_id: Optional[int] = None
    view_url: str       # קישורים חתומים לזמן מוגבל - עובדים גם בלשונית דפדפן חדשה בלי טוקן
    download_url: str


class ProjectSummary(BaseModel):
    """שורה ברשימת הפרויקטים - סכומים מחושבים במסד, בלי לטעון משימות/הוצאות/קבצים."""
    id: int
    name: str
    initial_budget: float
    members: List[str]
    spent: float
    remaining: float
    spent_pct: float
    tasks: int
    done: int
    open: int
    done_pct: float
    blocked: int
    files: int


class ProjectDetail(ProjectSummary):
    task_list: List[TaskOut]
    expense_list: List[ExpenseOut]
    file_list: List[FileOut]


class OpenTaskOut(TaskOut):
    project_id: int
    project_name: str


class DashboardOut(BaseModel):
    projects: List[ProjectSummary]
    status_counts: dict
    open_by_assignee: dict


# ---------------- יומן אישי ----------------

class PersonalTaskCreate(BaseModel):
    title: str = NonEmpty
    priority: int = Field(ge=1, le=5)
    date: dt.date
    _clean = field_validator("title")(_strip)


class PersonalTaskOut(BaseModel):
    id: str
    title: str
    assigned_to: str
    priority: int
    status: str
    date: str


# ---------------- יומן עבודה ----------------

class CrewEntry(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    workers: int = Field(ge=0, le=MAX_WORKERS_PER_ROW)
    _clean = field_validator("name")(_strip)


class WorkLogCreate(BaseModel):
    log_date: dt.date
    weather: Optional[Literal[tuple(WEATHER_OPTIONS)]] = None
    crew: List[CrewEntry] = Field(default=[], max_length=MAX_CREW_ROWS)
    work_done: str = Field(min_length=3, max_length=4000)
    issues: Optional[str] = Field(default=None, max_length=4000)
    _clean = field_validator("work_done")(_strip)

    @field_validator("log_date")
    @classmethod
    def _not_in_future(cls, value):
        if value > dt.date.today():
            raise ValueError("log date cannot be in the future")
        return value


class WorkLogOut(BaseModel):
    id: int
    project_id: int
    log_date: dt.date
    author: str
    weather: Optional[str]
    crew: List[CrewEntry]
    total_workers: int
    work_done: str
    issues: Optional[str]
    created_at: dt.datetime
    photos: List[FileOut]
