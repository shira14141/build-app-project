"""בדיקות API: התחברות, הרשאות לפי תפקיד ושותפות, ולידציה, קבצים ויומן אישי."""
from conftest import NEW_PASSWORD, SEED_PASSWORDS

TEMP_PASSWORD = "Temp-Pass-2026"

ADMIN, MANAGER, MANAGER2, CONTRACTOR, CONTRACTOR2 = "שירה", "יוסי הקבלן", "משה מפקח הבנייה", "דנה האדריכלית", "אבי אינסטלטור"


def make_project(client, auth, user=ADMIN, members=(CONTRACTOR,), name="פרויקט בדיקה", budget=1000):
    res = client.post("/projects/", headers=auth(user),
                      json={"name": name, "initial_budget": budget, "members": list(members)})
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------- התחברות ----------------

def test_requires_login(client):
    assert client.get("/projects/").status_code == 401
    assert client.get("/projects/", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_wrong_password_rejected(client):
    assert client.post("/auth/login", json={"username": ADMIN, "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"username": "לא קיים", "password": "x"}).status_code == 401


def test_first_login_must_change_password(client):
    res = client.post("/auth/login", json={"username": "רוני קבלן חשמל", "password": "1234"})
    assert res.status_code == 200 and res.json()["user"]["must_change_password"] is True
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/projects/", headers=headers).status_code == 403          # חסום עד ההחלפה
    assert client.get("/auth/me", headers=headers).status_code == 200            # 'אני' מותר
    short = client.post("/auth/change-password", headers=headers,
                        json={"current_password": "1234", "new_password": "short"})
    assert short.status_code == 422
    ok = client.post("/auth/change-password", headers=headers,
                     json={"current_password": "1234", "new_password": NEW_PASSWORD})
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert client.get("/projects/", headers=headers).status_code == 200
    assert client.post("/auth/login", json={"username": "רוני קבלן חשמל", "password": "1234"}).status_code == 401


# ---------------- נראות פרויקטים ----------------

def test_members_see_project_others_dont(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    assert pid in [p["id"] for p in client.get("/projects/", headers=auth(CONTRACTOR)).json()]
    assert pid not in [p["id"] for p in client.get("/projects/", headers=auth(MANAGER2)).json()]
    assert client.get(f"/projects/{pid}", headers=auth(MANAGER2)).status_code == 404
    assert client.get(f"/projects/{pid}", headers=auth(ADMIN)).status_code == 200


def test_manager_creating_project_becomes_member(client, auth):
    pid = make_project(client, auth, user=MANAGER, members=[CONTRACTOR])
    detail = client.get(f"/projects/{pid}", headers=auth(MANAGER)).json()
    assert set(detail["members"]) == {MANAGER, CONTRACTOR}


def test_contractor_cannot_create_or_manage(client, auth):
    assert client.post("/projects/", headers=auth(CONTRACTOR),
                       json={"name": "x", "initial_budget": 1, "members": []}).status_code == 403
    pid = make_project(client, auth, members=[CONTRACTOR])
    h = auth(CONTRACTOR)
    assert client.post(f"/projects/{pid}/tasks/", headers=h,
                       json={"title": "t", "assigned_to": CONTRACTOR, "priority": 3}).status_code == 403
    assert client.post(f"/projects/{pid}/expenses/", headers=h, json={"catalog_id": "101"}).status_code == 403
    assert client.patch(f"/projects/{pid}", headers=h, json={"name": "חדש"}).status_code == 403
    assert client.delete(f"/projects/{pid}", headers=h).status_code == 403


# ---------------- משימות ----------------

def test_task_status_own_vs_others(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR, CONTRACTOR2])
    mine = client.post(f"/projects/{pid}/tasks/", headers=auth(ADMIN),
                       json={"title": "שלי", "assigned_to": CONTRACTOR, "priority": 3}).json()["id"]
    other = client.post(f"/projects/{pid}/tasks/", headers=auth(ADMIN),
                        json={"title": "של אחר", "assigned_to": CONTRACTOR2, "priority": 3}).json()["id"]
    h = auth(CONTRACTOR)
    assert client.patch(f"/projects/{pid}/tasks/{mine}", headers=h, json={"status": "בוצע"}).status_code == 200
    assert client.patch(f"/projects/{pid}/tasks/{other}", headers=h, json={"status": "בוצע"}).status_code == 403
    assert client.patch(f"/projects/{pid}/tasks/{mine}", headers=h, json={"status": "לא קיים"}).status_code == 422


def test_task_assignee_must_be_member(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR])
    res = client.post(f"/projects/{pid}/tasks/", headers=auth(ADMIN),
                      json={"title": "t", "assigned_to": CONTRACTOR2, "priority": 3})
    assert res.status_code == 422


# ---------------- ולידציה ----------------

def test_validation(client, auth):
    h = auth(ADMIN)
    assert client.post("/projects/", headers=h, json={"name": "  ", "initial_budget": 1}).status_code == 422
    assert client.post("/projects/", headers=h, json={"name": "x", "initial_budget": -5}).status_code == 422
    assert client.post("/projects/", headers=h,
                       json={"name": "x", "initial_budget": 1, "members": ["לא קיים"]}).status_code == 422
    pid = make_project(client, auth)
    assert client.post(f"/projects/{pid}/expenses/", headers=h, json={"catalog_id": "999"}).status_code == 422
    assert client.post(f"/projects/{pid}/tasks/", headers=h,
                       json={"title": "t", "assigned_to": CONTRACTOR, "priority": 9}).status_code == 422


# ---------------- תקציב ----------------

def test_expenses_and_summary(client, auth):
    pid = make_project(client, auth, budget=1000)
    h = auth(ADMIN)
    client.post(f"/projects/{pid}/expenses/", headers=h, json={"catalog_id": "101"})            # 350 מהקטלוג
    eid = client.post(f"/projects/{pid}/expenses/", headers=h,
                      json={"catalog_id": "102", "custom_price": 500}).json()["id"]
    detail = client.get(f"/projects/{pid}", headers=h).json()
    assert detail["spent"] == 850 and detail["remaining"] == 150 and round(detail["spent_pct"]) == 85
    assert client.delete(f"/projects/{pid}/expenses/{eid}", headers=h).status_code == 204
    assert client.get(f"/projects/{pid}", headers=h).json()["spent"] == 350


# ---------------- קבצים ----------------

def test_file_upload_view_delete(client, auth, upload_dir):
    pid = make_project(client, auth, members=[CONTRACTOR, CONTRACTOR2])
    content = b"%PDF-1.4 test content"
    res = client.post(f"/projects/{pid}/files/", headers=auth(CONTRACTOR),
                      files={"file": ("תוכנית קומה.pdf", content, "application/pdf")})
    assert res.status_code == 201, res.text
    f = client.get(f"/projects/{pid}", headers=auth(CONTRACTOR)).json()["file_list"][0]
    assert f["uploaded_by"] == CONTRACTOR and f["size"] == len(content)
    assert (upload_dir / str(pid) / f["id"]).read_bytes() == content

    view = client.get(f["view_url"])                       # קישור חתום - בלי טוקן התחברות
    assert view.status_code == 200 and view.content == content
    disposition = view.headers["content-disposition"].lower()
    assert "inline" in disposition and "utf-8''" in disposition  # שם בעברית מקודד לפי RFC 5987
    assert client.get(f["download_url"]).status_code == 200
    assert client.get(f"/files/{f['id']}/view?sig=forged").status_code == 403
    assert client.get(f"/files/{f['id']}/view").status_code == 422

    assert client.delete(f"/files/{f['id']}", headers=auth(CONTRACTOR2)).status_code == 403
    assert client.delete(f"/files/{f['id']}", headers=auth(CONTRACTOR)).status_code == 204
    assert not (upload_dir / str(pid) / f["id"]).exists()


def test_upload_size_limit(client, auth, upload_dir):
    pid = make_project(client, auth)
    big = b"0" * (1024 * 1024 + 1)  # מעל מגבלת 1MB שהוגדרה לבדיקות
    res = client.post(f"/projects/{pid}/files/", headers=auth(ADMIN), files={"file": ("big.bin", big)})
    assert res.status_code == 413
    assert not any((upload_dir / str(pid)).glob("*")) if (upload_dir / str(pid)).exists() else True


def test_delete_project_removes_everything(client, auth, upload_dir):
    pid = make_project(client, auth, members=[CONTRACTOR])
    h = auth(ADMIN)
    client.post(f"/projects/{pid}/tasks/", headers=h, json={"title": "t", "assigned_to": CONTRACTOR, "priority": 1})
    client.post(f"/projects/{pid}/files/", headers=h, files={"file": ("a.txt", b"abc")})
    fid = client.get(f"/projects/{pid}", headers=h).json()["file_list"][0]["id"]
    assert client.delete(f"/projects/{pid}", headers=h).status_code == 204
    assert client.get(f"/projects/{pid}", headers=h).status_code == 404
    assert not (upload_dir / str(pid) / fid).exists()


# ---------------- עדכון פרויקט ----------------

def test_update_project_members(client, auth):
    pid = make_project(client, auth, user=MANAGER, members=[CONTRACTOR])
    res = client.patch(f"/projects/{pid}", headers=auth(MANAGER),
                       json={"name": "שם חדש", "initial_budget": 5000, "members": [CONTRACTOR2]})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "שם חדש" and body["initial_budget"] == 5000
    assert set(body["members"]) == {CONTRACTOR2, MANAGER}   # המנהל לא מוציא את עצמו
    assert client.get(f"/projects/{pid}", headers=auth(CONTRACTOR)).status_code == 404


# ---------------- יומן אישי ----------------

def test_personal_tasks_are_private(client, auth):
    tid = client.post("/personal_tasks/", headers=auth(CONTRACTOR),
                      json={"title": "פגישה", "priority": 3, "date": "2026-12-01"}).json()["id"]
    assert tid in [t["id"] for t in client.get("/personal_tasks/", headers=auth(CONTRACTOR)).json()]
    assert tid not in [t["id"] for t in client.get("/personal_tasks/", headers=auth(CONTRACTOR2)).json()]
    assert client.patch(f"/personal_tasks/{tid}", headers=auth(CONTRACTOR2), json={"status": "בוצע"}).status_code == 404
    assert client.delete(f"/personal_tasks/{tid}", headers=auth(CONTRACTOR2)).status_code == 404
    assert client.patch(f"/personal_tasks/{tid}", headers=auth(CONTRACTOR), json={"status": "בוצע"}).status_code == 200
    assert client.delete(f"/personal_tasks/{tid}", headers=auth(CONTRACTOR)).status_code == 204


# ---------------- לוח בקרה ----------------

def test_dashboard_only_visible_projects(client, auth):
    make_project(client, auth, members=[CONTRACTOR2], name="סודי")
    names = [p["name"] for p in client.get("/dashboard/summary", headers=auth(MANAGER2)).json()["projects"]]
    assert "סודי" not in names
    admin_view = client.get("/dashboard/summary", headers=auth(ADMIN)).json()
    assert "סודי" in [p["name"] for p in admin_view["projects"]]
    assert set(admin_view["status_counts"]) == {"ממתין", "בתהליך", "חסום", "בוצע"}


# ---------------- ניהול משתמשים ----------------

def test_user_management(client, auth):
    h = auth(ADMIN)
    assert client.post("/users/", headers=auth(MANAGER),
                       json={"username": "x", "password": NEW_PASSWORD, "role": "viewer"}).status_code == 403
    assert client.post("/users/", headers=h,
                       json={"username": "צופה", "password": TEMP_PASSWORD, "role": "viewer"}).status_code == 201
    SEED_PASSWORDS["צופה"] = TEMP_PASSWORD  # משתמש חדש חייב להחליף סיסמה - ה-fixture יעשה זאת
    assert client.post("/users/", headers=h,
                       json={"username": "צופה", "password": NEW_PASSWORD, "role": "viewer"}).status_code == 409
    # צופה: רואה פרויקט שהוא שותף בו, אבל לא יכול להעלות קבצים
    pid = make_project(client, auth, members=["צופה"])
    viewer = auth("צופה")
    assert client.get(f"/projects/{pid}", headers=viewer).status_code == 200
    assert client.post(f"/projects/{pid}/files/", headers=viewer, files={"file": ("a.txt", b"a")}).status_code == 403
    # השבתה מנתקת מיד
    assert client.patch("/users/צופה", headers=h, json={"is_active": False}).status_code == 200
    assert client.get("/projects/", headers=viewer).status_code == 401
    # מנהל לא יכול להוריד או להשבית את עצמו
    assert client.patch(f"/users/{ADMIN}", headers=h, json={"role": "viewer"}).status_code == 400
    assert client.patch(f"/users/{ADMIN}", headers=h, json={"is_active": False}).status_code == 400
    # משתמש רגיל רואה רק משתמשים פעילים
    assert "צופה" not in [u["username"] for u in client.get("/users/", headers=auth(MANAGER)).json()]
    assert "צופה" in [u["username"] for u in client.get("/users/", headers=h).json()]


# ---------------- משימות פתוחות (מסך 'היום') ----------------

def test_open_tasks_only_visible_and_not_done(client, auth):
    pid = make_project(client, auth, members=[CONTRACTOR], name="פרויקט היום")
    h = auth(ADMIN)
    open_id = client.post(f"/projects/{pid}/tasks/", headers=h,
                          json={"title": "פתוחה", "assigned_to": CONTRACTOR, "priority": 5}).json()["id"]
    done_id = client.post(f"/projects/{pid}/tasks/", headers=h,
                          json={"title": "גמורה", "assigned_to": CONTRACTOR, "priority": 1}).json()["id"]
    client.patch(f"/projects/{pid}/tasks/{done_id}", headers=h, json={"status": "בוצע"})

    mine = {t["id"]: t for t in client.get("/tasks/open", headers=auth(CONTRACTOR)).json()}
    assert open_id in mine and done_id not in mine
    assert mine[open_id]["project_name"] == "פרויקט היום" and mine[open_id]["project_id"] == pid
    # מי שלא שותף בפרויקט לא רואה את המשימות שלו
    assert open_id not in [t["id"] for t in client.get("/tasks/open", headers=auth(MANAGER2)).json()]


def test_dashboard_requires_manager_role(client, auth):
    assert client.get("/dashboard/summary", headers=auth(CONTRACTOR)).status_code == 403
    assert client.get("/dashboard/summary", headers=auth(MANAGER)).status_code == 200
