"""מודלים של מסד הנתונים. שינוי במבנה = מיגרציה חדשה בתיקייה migrations/versions."""
from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from constants import STATUS_PENDING
from server.db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    must_change_password = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    username = Column(String, ForeignKey("users.username", ondelete="CASCADE"), primary_key=True)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    initial_budget = Column(Float)
    members = relationship("ProjectMember", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="project", cascade="all, delete-orphan")
    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    work_logs = relationship("WorkLog", back_populates="project", cascade="all, delete-orphan")

    @property
    def member_names(self):
        return [m.username for m in self.members]


class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    title = Column(String)
    assigned_to = Column(String)
    priority = Column(Integer)
    status = Column(String, default=STATUS_PENDING)
    blocked_reason = Column(String)   # מה חוסם - חובה כשהסטטוס "חסום", מתאפס כשהחסימה נפתרת
    blocked_since = Column(Date)
    project = relationship("Project", back_populates="tasks")


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    catalog_id = Column(String)
    title = Column(String)
    final_price = Column(Float)
    project = relationship("Project", back_populates="expenses")


class File(Base):
    """מטא-דאטה של קובץ. התוכן עצמו שמור בדיסק (UPLOAD_DIR / storage_path), לא במסד."""
    __tablename__ = "files"
    id = Column(String, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    filename = Column(String)
    uploaded_by = Column(String)
    storage_path = Column(String)
    size = Column(Integer)
    content_type = Column(String)
    # תמונה שצורפה לדיווח יומן עבודה (אחרת - קובץ רגיל של הפרויקט)
    work_log_id = Column(Integer, ForeignKey("work_logs.id", ondelete="SET NULL"), index=True)
    project = relationship("Project", back_populates="files")


class WorkLog(Base):
    """דיווח יומי מהאתר: מזג אוויר, צוותים, מה בוצע ועיכובים."""
    __tablename__ = "work_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True, nullable=False)
    log_date = Column(Date, nullable=False, index=True)
    author = Column(String, nullable=False)
    weather = Column(String)
    crew = Column(JSON, nullable=False, default=list)   # [{"name": "...", "workers": 3}, ...]
    work_done = Column(Text, nullable=False)
    issues = Column(Text)
    created_at = Column(DateTime, nullable=False)
    project = relationship("Project", back_populates="work_logs")


class PersonalTask(Base):
    __tablename__ = "personal_tasks"
    id = Column(String, primary_key=True)
    title = Column(String)
    assigned_to = Column(String, index=True)
    priority = Column(Integer)
    status = Column(String, default=STATUS_PENDING)
    date = Column(String, default="")
