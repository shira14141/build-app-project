import json
import uuid
import mimetypes
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, LargeBinary
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

# =========================================================
# הגדרות מסד נתונים
# =========================================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./construction.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DBProject(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    initial_budget = Column(Float)
    partners = Column(String)
    tasks = relationship("DBTask", back_populates="project", cascade="all, delete-orphan")
    expenses = relationship("DBExpense", back_populates="project", cascade="all, delete-orphan")
    files = relationship("DBFile", back_populates="project", cascade="all, delete-orphan")


class DBTask(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String)
    assigned_to = Column(String)
    priority = Column(Integer)
    status = Column(String, default="ממתין")
    project = relationship("DBProject", back_populates="tasks")


class DBExpense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    catalog_id = Column(String)
    title = Column(String)
    final_price = Column(Float)
    project = relationship("DBProject", back_populates="expenses")


class DBFile(Base):
    __tablename__ = "files"
    id = Column(String, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    filename = Column(String)
    uploaded_by = Column(String)
    data = Column(LargeBinary)
    project = relationship("DBProject", back_populates="files")


class DBPersonalTask(Base):
    __tablename__ = "personal_tasks"
    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    assigned_to = Column(String)
    priority = Column(Integer)
    status = Column(String, default="ממתין")
    date = Column(String, default="")


Base.metadata.create_all(bind=engine)


# =========================================================
# סכמות API
# =========================================================
class TaskResponse(BaseModel):
    id: str;
    title: str;
    assigned_to: str;
    priority: int;
    status: str


class ExpenseResponse(BaseModel):
    catalog_id: str;
    title: str;
    final_price: float


class FileMetaResponse(BaseModel):
    id: str;
    filename: str;
    uploaded_by: str


class ProjectResponse(BaseModel):
    id: int;
    name: str;
    initial_budget: float;
    partners: List[str]
    tasks: List[TaskResponse] = []
    expenses: List[ExpenseResponse] = []
    files: List[FileMetaResponse] = []


class PersonalTaskResponse(BaseModel):
    id: str;
    title: str;
    assigned_to: str;
    priority: int;
    status: str;
    date: str


class LoginRequest(BaseModel):
    username: str;
    password: str


# =========================================================
# השרת שלנו (FastAPI)
# =========================================================
app = FastAPI(title="Construction Manager Pro")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


USERS_DB = {"יוסי הקבלן": "1234", "דנה האדריכלית": "1234", "משה מפקח הבנייה": "1234", "אבי אינסטלטור": "1234",
            "שירה": "admin", "רוני קבלן חשמל": "1234"}
dekel_catalog = {"101": {"title": "יציקת בטון", "default_price": 350.0},
                 "102": {"title": "בניית קיר", "default_price": 120.0},
                 "103": {"title": "נקודת חשמל", "default_price": 250.0}}


@app.post("/login/")
def login(req: LoginRequest):
    if req.username in USERS_DB and USERS_DB[req.username] == req.password: return {"message": "Login successful"}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/projects/")
def create_project(project: dict, db: Session = Depends(get_db)):
    new_proj = DBProject(id=project['id'], name=project['name'], initial_budget=project['initial_budget'],
                         partners=json.dumps(project['partners']))
    db.add(new_proj)
    db.commit()
    return {"message": "Created"}


@app.get("/projects/", response_model=List[ProjectResponse])
def get_projects(db: Session = Depends(get_db)):
    res = []
    for p in db.query(DBProject).all():
        tasks = [TaskResponse(**t.__dict__) for t in p.tasks]
        expenses = [ExpenseResponse(**e.__dict__) for e in p.expenses]
        files = [FileMetaResponse(id=f.id, filename=f.filename, uploaded_by=f.uploaded_by) for f in p.files]
        res.append(
            ProjectResponse(id=p.id, name=p.name, initial_budget=p.initial_budget, partners=json.loads(p.partners),
                            tasks=tasks, expenses=expenses, files=files))
    return res


@app.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    db.query(DBProject).filter(DBProject.id == project_id).delete();
    db.commit()
    return {"message": "Deleted"}


@app.post("/projects/{project_id}/tasks/")
def add_task(project_id: int, task: dict, db: Session = Depends(get_db)):
    db.add(DBTask(id=str(uuid.uuid4()), project_id=project_id, title=task['title'], assigned_to=task['assigned_to'],
                  priority=task['priority']))
    db.commit()
    return {"message": "Added"}


@app.delete("/projects/{project_id}/tasks/{task_id}")
def delete_task(project_id: int, task_id: str, db: Session = Depends(get_db)):
    db.query(DBTask).filter(DBTask.id == task_id).delete();
    db.commit()
    return {"message": "Deleted"}


@app.patch("/projects/{project_id}/tasks/{task_id}/status")
def update_task_status(project_id: int, task_id: str, new_status: str, db: Session = Depends(get_db)):
    db.query(DBTask).filter(DBTask.id == task_id).first().status = new_status;
    db.commit()
    return {"message": "Updated"}


# 🔥 השדרוג: עדכון תקציב הפרויקט
@app.patch("/projects/{project_id}/budget")
def update_project_budget(project_id: int, request: dict, db: Session = Depends(get_db)):
    project = db.query(DBProject).filter(DBProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.initial_budget = request.get("initial_budget")
    db.commit()
    return {"message": "Budget updated successfully"}


# 🔥 השדרוג: קבלת הוצאה כטקסט חופשי או כסעיף דקל
@app.post("/projects/{project_id}/expenses/")
def add_expense(project_id: int, expense: dict, db: Session = Depends(get_db)):
    if "title" in expense and "final_price" in expense:
        # זה טקסט חופשי!
        new_expense = DBExpense(project_id=project_id, catalog_id="חופשי", title=expense['title'],
                                final_price=expense['final_price'])
    else:
        # זו הוצאה ישנה מסעיף דקל
        price = expense['custom_price'] if expense['custom_price'] is not None else \
        dekel_catalog[expense['catalog_id']]["default_price"]
        title = dekel_catalog[expense['catalog_id']]["title"]
        new_expense = DBExpense(project_id=project_id, catalog_id=expense['catalog_id'], title=title, final_price=price)

    db.add(new_expense)
    db.commit()
    return {"message": "Expense added successfully"}


# --- ניהול קבצים ---
@app.post("/projects/{project_id}/files/")
def upload_file(project_id: int, file: UploadFile = File(...), uploaded_by: str = Form(...),
                db: Session = Depends(get_db)):
    db.add(DBFile(id=str(uuid.uuid4()), project_id=project_id, filename=file.filename, uploaded_by=uploaded_by,
                  data=file.file.read()))
    db.commit()
    return {"message": "File uploaded"}


@app.get("/files/{file_id}/view")
def view_file(file_id: str, db: Session = Depends(get_db)):
    db_file = db.query(DBFile).filter(DBFile.id == file_id).first()
    if not db_file: raise HTTPException(status_code=404)
    mime_type, _ = mimetypes.guess_type(db_file.filename)
    if not mime_type: mime_type = "application/octet-stream"
    return Response(content=db_file.data, media_type=mime_type,
                    headers={"Content-Disposition": f'inline; filename="{db_file.filename}"'})


@app.get("/files/{file_id}/download")
def download_file(file_id: str, db: Session = Depends(get_db)):
    db_file = db.query(DBFile).filter(DBFile.id == file_id).first()
    if not db_file: raise HTTPException(status_code=404)
    return Response(content=db_file.data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{db_file.filename}"'})


@app.delete("/files/{file_id}")
def delete_file(file_id: str, db: Session = Depends(get_db)):
    db.query(DBFile).filter(DBFile.id == file_id).delete();
    db.commit()
    return {"message": "Deleted"}


# --- משימות אישיות ---
@app.get("/personal_tasks/{user}", response_model=List[PersonalTaskResponse])
def get_personal_tasks(user: str, db: Session = Depends(get_db)):
    return [PersonalTaskResponse(**t.__dict__) for t in
            db.query(DBPersonalTask).filter(DBPersonalTask.assigned_to == user).all()]


@app.post("/personal_tasks/")
def add_personal_task(task: dict, db: Session = Depends(get_db)):
    db.add(DBPersonalTask(id=str(uuid.uuid4()), title=task['title'], assigned_to=task['assigned_to'],
                          priority=task['priority'], date=task['date']));
    db.commit()
    return {"message": "Added"}


@app.patch("/personal_tasks/{task_id}/status")
def update_pt_status(task_id: str, new_status: str, db: Session = Depends(get_db)):
    db.query(DBPersonalTask).filter(DBPersonalTask.id == task_id).first().status = new_status;
    db.commit()
    return {"message": "Updated"}


@app.delete("/personal_tasks/{task_id}")
def delete_pt(task_id: str, db: Session = Depends(get_db)):
    db.query(DBPersonalTask).filter(DBPersonalTask.id == task_id).delete();
    db.commit()
    return {"message": "Deleted"}