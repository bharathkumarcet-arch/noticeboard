import os
import io
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from fastapi.testclient import TestClient

from app.config import settings
from app.database import init_db, get_db_ctx
from main import app

TEST_DB_PATH = settings.BASE_DIR / "test_notice_board.db"
settings.DATABASE_PATH = TEST_DB_PATH

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    init_db(TEST_DB_PATH)
    yield
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass

@pytest.fixture
def client():
    return TestClient(app)

def test_institution_name_rendering(client):
    # Verify exact institution name is returned across public pages
    res = client.get("/login")
    assert res.status_code == 200
    assert "Shree Devi Institute of Technology" in res.text

    res_reg = client.get("/register")
    assert res_reg.status_code == 200
    assert "Shree Devi Institute of Technology" in res_reg.text

    res_student_reg = client.get("/register/student")
    assert res_student_reg.status_code == 200
    assert "Shree Devi Institute of Technology" in res_student_reg.text

    res_faculty_reg = client.get("/register/faculty")
    assert res_faculty_reg.status_code == 200
    assert "Shree Devi Institute of Technology" in res_faculty_reg.text

def test_initial_faculty_creation_and_login(client):
    from app.security import hash_password
    with get_db_ctx(TEST_DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO users (id, name, email, password_hash, role, department, is_approved)
            VALUES (1, 'Dr. Alan Turing', 'turing@sdit.ac.in', ?, 'faculty', 'Computer Science & Engineering', 1)
        """, (hash_password("SuperSecret123!"),))
        conn.commit()

    # Login as Faculty
    res = client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["user"]["role"] == "faculty"
    assert data["user"]["is_approved"] is True
    assert settings.SESSION_COOKIE_NAME in res.cookies

def test_student_signup_flow_and_validations(client):
    # 1. Password mismatch validation
    mismatch_res = client.post("/api/auth/register-student", json={
        "name": "Jane Student",
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "confirm_password": "DifferentPass123!",
        "student_id": "4SD23CS999",
        "department": "Computer Science & Engineering",
        "course": "B.E. CSE"
    })
    assert mismatch_res.status_code == 400
    assert "do not match" in mismatch_res.json()["detail"]

    # 2. Successful student registration
    res = client.post("/api/auth/register-student", json={
        "name": "Jane Student",
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "confirm_password": "StudentPass123!",
        "student_id": "4SD23CS999",
        "department": "Computer Science & Engineering",
        "course": "B.E. CSE - 3rd Year"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["user"]["role"] == "student"
    assert data["user"]["name"] == "Jane Student"

    # 3. Duplicate email handling
    dup_email_res = client.post("/api/auth/register-student", json={
        "name": "Another Jane",
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "confirm_password": "StudentPass123!",
        "student_id": "4SD23CS888",
        "department": "Computer Science & Engineering",
        "course": "B.E. CSE"
    })
    assert dup_email_res.status_code == 409
    assert "email address already exists" in dup_email_res.json()["detail"]

    # 4. Duplicate student ID handling
    dup_id_res = client.post("/api/auth/register-student", json={
        "name": "New Student",
        "email": "new.student@student.sdit.ac.in",
        "password": "StudentPass123!",
        "confirm_password": "StudentPass123!",
        "student_id": "4SD23CS999",
        "department": "Computer Science & Engineering",
        "course": "B.E. CSE"
    })
    assert dup_id_res.status_code == 409
    assert "Student ID or registration number is already registered" in dup_id_res.json()["detail"]

    # 5. Attempt sign in under wrong tab
    wrong_role_res = client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "faculty"
    })
    assert wrong_role_res.status_code == 403

    # 6. Correct sign in
    correct_res = client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })
    assert correct_res.status_code == 200

def test_faculty_signup_and_approval_workflow(client):
    from app.cli import run_approve_faculty

    # 1. Faculty signup with invalid / missing invite code -> registers as pending approval
    pending_res = client.post("/api/auth/register-faculty", json={
        "name": "Prof. Charles Babbage",
        "email": "babbage@sdit.ac.in",
        "password": "FacultyPass123!",
        "confirm_password": "FacultyPass123!",
        "department": "Information Science & Engineering",
        "invite_code": ""
    })
    assert pending_res.status_code == 201
    assert pending_res.json()["is_approved"] is False

    # Pending faculty is logged in, but BLOCKED from creating notices
    create_blocked = client.post("/api/faculty/notices", data={
        "title": "Unauthorized Notice",
        "body": "Should fail because account is pending approval",
        "category": "Academic",
        "priority": "normal",
        "status": "published"
    })
    assert create_blocked.status_code == 403
    assert "pending administrative approval" in create_blocked.json()["detail"]

    # Pending faculty is BLOCKED from readership analytics
    readership_blocked = client.get("/api/faculty/notices/1/readership")
    assert readership_blocked.status_code == 403

    # 2. Administrator approves the pending faculty account via CLI helper
    run_approve_faculty("babbage@sdit.ac.in")

    # Now faculty can publish notices
    client.post("/api/auth/login", json={
        "email": "babbage@sdit.ac.in",
        "password": "FacultyPass123!",
        "role": "faculty"
    })
    create_allowed = client.post("/api/faculty/notices", data={
        "title": "Babbage Official Announcement",
        "body": "Successfully published after administrative approval.",
        "category": "Academic",
        "priority": "normal",
        "status": "published"
    })
    assert create_allowed.status_code == 201

    # 3. Faculty signup WITH valid institute invitation code -> approved immediately
    auto_res = client.post("/api/auth/register-faculty", json={
        "name": "Dr. Grace Hopper",
        "email": "hopper@sdit.ac.in",
        "password": "FacultyPass123!",
        "confirm_password": "FacultyPass123!",
        "department": "Computer Science & Engineering",
        "invite_code": settings.FACULTY_INVITE_CODE
    })
    assert auto_res.status_code == 201
    assert auto_res.json()["is_approved"] is True

def test_rbac_student_blocked_from_faculty_operations(client):
    # Log in as student
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })

    # Student cannot create notice
    create_res = client.post("/api/faculty/notices", data={
        "title": "Hacked Notice",
        "body": "Should be blocked",
        "category": "Academic",
        "priority": "urgent",
        "status": "published"
    })
    assert create_res.status_code == 403

    # Student cannot access faculty metrics
    metrics_res = client.get("/api/faculty/metrics")
    assert metrics_res.status_code == 403

    # Student cannot access faculty notice management
    list_res = client.get("/api/faculty/notices")
    assert list_res.status_code == 403

    # Student cannot access readership analytics
    read_res = client.get("/api/faculty/notices/1/readership")
    assert read_res.status_code == 403

def test_notice_lifecycle_and_unique_readership_tracking(client):
    # 1. Log in as Faculty
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Create a draft notice
    draft_res = client.post("/api/faculty/notices", data={
        "title": "Midterm Examination Dates (Draft)",
        "body": "This is a draft notice for testing student visibility and readership.",
        "category": "Examination",
        "priority": "urgent",
        "status": "draft"
    })
    assert draft_res.status_code == 201
    notice_id = draft_res.json()["notice_id"]

    # 2. Switch to Student
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })

    # Student should NOT see draft notice in list
    active_notices = client.get("/api/notices").json()["notices"]
    assert not any(n["id"] == notice_id for n in active_notices)

    # Student should NOT be able to view draft notice detail directly
    detail_res = client.get(f"/api/notices/{notice_id}")
    assert detail_res.status_code == 403

    # 3. Switch back to Faculty and Publish notice
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })
    pub_res = client.patch(f"/api/faculty/notices/{notice_id}/status", json={"status": "published"})
    assert pub_res.status_code == 200

    # 4. Student views the published notice for the first time
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })

    student_view_res = client.get(f"/api/notices/{notice_id}")
    assert student_view_res.status_code == 200
    assert "my_first_viewed_at" in student_view_res.json()["notice"]
    first_view_time = student_view_res.json()["notice"]["my_first_viewed_at"]
    assert first_view_time is not None

    # 5. Student reopens / refreshes notice multiple times
    for _ in range(3):
        repeat_res = client.get(f"/api/notices/{notice_id}")
        assert repeat_res.status_code == 200
        # First viewed timestamp should remain exactly the same
        assert repeat_res.json()["notice"]["my_first_viewed_at"] == first_view_time

    # 6. Switch back to Faculty: verify unique readership count is exactly 1
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Faculty visits notice detail - verify faculty view does not increment student readership
    fac_detail = client.get(f"/api/notices/{notice_id}")
    assert fac_detail.status_code == 200
    assert fac_detail.json()["notice"]["readership_count"] == 1

    # Faculty views readership analytics
    analytics_res = client.get(f"/api/faculty/notices/{notice_id}/readership")
    assert analytics_res.status_code == 200
    analytics = analytics_res.json()
    assert analytics["total_unique_readers"] == 1
    assert analytics["views"][0]["student_email"] == "jane@student.sdit.ac.in"
    assert analytics["views"][0]["student_name"] == "Jane Student"

def test_attachment_upload_and_authorized_download(client):
    # Log in as faculty
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Create dummy PDF file
    dummy_pdf = io.BytesIO(b"%PDF-1.4 test dummy content")
    files = {"attachment": ("syllabus_fall.pdf", dummy_pdf, "application/pdf")}
    data = {
        "title": "Fall Syllabus with Attachment",
        "body": "Download the official syllabus attached.",
        "category": "Academic",
        "priority": "important",
        "status": "published"
    }

    create_res = client.post("/api/faculty/notices", data=data, files=files)
    assert create_res.status_code == 201

    # Retrieve notice to get attachment URL
    notice_id = create_res.json()["notice_id"]
    n_res = client.get(f"/api/notices/{notice_id}")
    att_url = n_res.json()["notice"]["attachment_url"]
    assert att_url is not None
    assert att_url.startswith("/api/uploads/")

    # Download attachment as authenticated user
    download_res = client.get(att_url)
    assert download_res.status_code == 200
    assert download_res.content == b"%PDF-1.4 test dummy content"

    # Reject unsupported extension (e.g. .exe)
    bad_file = io.BytesIO(b"malicious script")
    bad_files = {"attachment": ("danger.exe", bad_file, "application/octet-stream")}
    bad_res = client.post("/api/faculty/notices", data=data, files=bad_files)
    assert bad_res.status_code == 400
    assert "Invalid file format" in bad_res.json()["detail"]

def test_search_and_filter_notices(client):
    # Login as student
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })

    # Search by keyword matching title
    res_search = client.get("/api/notices?q=Syllabus")
    assert res_search.status_code == 200
    notices = res_search.json()["notices"]
    assert len(notices) >= 1
    assert "Syllabus" in notices[0]["title"]

    # Filter by category
    res_cat = client.get("/api/notices?category=Academic")
    assert res_cat.status_code == 200
    for n in res_cat.json()["notices"]:
        assert n["category"] == "Academic"

    # Filter by priority
    res_prio = client.get("/api/notices?priority=urgent")
    assert res_prio.status_code == 200
    for n in res_prio.json()["notices"]:
        assert n["priority"] == "urgent"

def test_expired_notice_hidden_from_students(client):
    # Login as faculty to create an expired notice
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    past_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    past_publish = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    
    expired_res = client.post("/api/faculty/notices", data={
        "title": "Expired Emergency Notice",
        "body": "This notice has already reached its expiration date.",
        "category": "Administrative",
        "priority": "normal",
        "status": "published",
        "publish_at": past_publish,
        "expires_at": past_date
    })
    assert expired_res.status_code == 201
    exp_notice_id = expired_res.json()["notice_id"]

    # Student cannot view expired notice
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })

    # Hidden from student list
    res_list = client.get("/api/notices")
    assert not any(n["id"] == exp_notice_id for n in res_list.json()["notices"])

    # Hidden from direct access
    res_detail = client.get(f"/api/notices/{exp_notice_id}")
    assert res_detail.status_code == 403

def test_notice_update_and_delete(client):
    # Login as faculty
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Create notice to delete
    create_res = client.post("/api/faculty/notices", data={
        "title": "Notice to be Deleted",
        "body": "Temporary notice content",
        "category": "General",
        "priority": "normal",
        "status": "published"
    })
    target_id = create_res.json()["notice_id"]

    # Update notice
    update_res = client.put(f"/api/faculty/notices/{target_id}", data={
        "title": "Updated Notice Title",
        "body": "Updated notice content",
        "category": "General",
        "priority": "important",
        "status": "published"
    })
    assert update_res.status_code == 200

    # Delete notice
    del_res = client.delete(f"/api/faculty/notices/{target_id}")
    assert del_res.status_code == 200

    # Verify notice is gone
    get_res = client.get(f"/api/notices/{target_id}")
    assert get_res.status_code == 404

def test_password_change_flow(client):
    # Login as student
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "StudentPass123!",
        "role": "student"
    })

    # Change password with wrong current password
    fail_res = client.post("/api/auth/change-password", json={
        "current_password": "WrongPassword!",
        "new_password": "NewSecretPass456!"
    })
    assert fail_res.status_code == 400

    # Change password successfully
    success_res = client.post("/api/auth/change-password", json={
        "current_password": "StudentPass123!",
        "new_password": "NewSecretPass456!"
    })
    assert success_res.status_code == 200

    # Log in with new password
    new_login = client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "NewSecretPass456!",
        "role": "student"
    })
    assert new_login.status_code == 200

def test_pin_notice_flow_and_permissions(client):
    # Faculty logs in
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Create notice
    c_res = client.post("/api/faculty/notices", data={
        "title": "Semester Registration Mandatory Guidelines",
        "body": "All students must submit elective choices by Friday.",
        "category": "Academics",
        "priority": "important",
        "status": "published"
    })
    assert c_res.status_code == 201
    notice_id = c_res.json()["notice_id"]

    # Pin the notice
    pin_res = client.post(f"/api/faculty/notices/{notice_id}/pin")
    assert pin_res.status_code == 200
    assert pin_res.json()["is_pinned"] is True

    # Student logs in
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "NewSecretPass456!",
        "role": "student"
    })

    # Student sees pinned notice at the top
    feed_res = client.get("/api/notices")
    assert feed_res.status_code == 200
    notices = feed_res.json()["notices"]
    pinned_notice = next((n for n in notices if n["id"] == notice_id), None)
    assert pinned_notice is not None
    assert pinned_notice["is_pinned"] == 1

    # Student cannot pin/unpin
    student_pin_res = client.post(f"/api/faculty/notices/{notice_id}/pin")
    assert student_pin_res.status_code == 403

def test_readership_csv_export(client):
    # Faculty logs in
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Create published notice
    create_res = client.post("/api/faculty/notices", data={
        "title": "Placement Drive Orientation",
        "body": "Campus placement orientation in Main Auditorium.",
        "category": "Placements",
        "priority": "important",
        "status": "published"
    })
    notice_id = create_res.json()["notice_id"]

    # Student views it
    client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "NewSecretPass456!",
        "role": "student"
    })
    client.get(f"/api/notices/{notice_id}")

    # Student cannot export CSV
    student_csv = client.get(f"/api/faculty/notices/{notice_id}/readership/csv")
    assert student_csv.status_code == 403

    # Faculty exports CSV
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })
    csv_res = client.get(f"/api/faculty/notices/{notice_id}/readership/csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Shree Devi Institute of Technology" in csv_res.text
    assert "Jane Student" in csv_res.text
    assert "jane@student.sdit.ac.in" in csv_res.text

def test_forgot_and_reset_password_flow(client):
    # 1. Request password reset
    forgot_res = client.post("/api/auth/forgot-password", json={
        "email": "jane@student.sdit.ac.in"
    })
    assert forgot_res.status_code == 200
    data = forgot_res.json()
    assert "password reset instructions" in data["message"]
    token = data["reset_token"]
    assert token is not None

    # 2. Reset with wrong confirmation
    bad_res = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "NewPass2026!Updated",
        "confirm_password": "WrongMismatchPassword"
    })
    assert bad_res.status_code == 400

    # 3. Successful reset
    ok_res = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "NewPass2026!Updated",
        "confirm_password": "NewPass2026!Updated"
    })
    assert ok_res.status_code == 200
    assert "reset successfully" in ok_res.json()["message"]

    # 4. Token cannot be reused
    reuse_res = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "AnotherPassword123!",
        "confirm_password": "AnotherPassword123!"
    })
    assert reuse_res.status_code == 400

    # 5. Log in with reset password
    login_res = client.post("/api/auth/login", json={
        "email": "jane@student.sdit.ac.in",
        "password": "NewPass2026!Updated",
        "role": "student"
    })
    assert login_res.status_code == 200

def test_notice_audit_logs(client):
    # Faculty logs in
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # Create notice
    c_res = client.post("/api/faculty/notices", data={
        "title": "Sports Day Registration Open",
        "body": "Annual track and field events registration.",
        "category": "Events",
        "priority": "normal",
        "status": "published"
    })
    n_id = c_res.json()["notice_id"]

    # Update notice
    client.put(f"/api/faculty/notices/{n_id}", data={
        "title": "Sports Day Registration Open (Extended)",
        "body": "Annual track and field events registration extended deadline.",
        "category": "Events",
        "priority": "important",
        "status": "published"
    })

    # Pin notice
    client.post(f"/api/faculty/notices/{n_id}/pin")

    # Fetch audit logs
    audit_res = client.get(f"/api/faculty/notices/{n_id}/audit")
    assert audit_res.status_code == 200
    logs = audit_res.json()["audit_logs"]
    assert len(logs) >= 3
    actions = [l["action"] for l in logs]
    assert any("created" in a for a in actions)
    assert "edited" in actions
    assert "pinned" in actions

def test_admin_faculty_account_management(client):
    from app.security import hash_password
    # Grant turing admin status in DB
    with get_db_ctx(TEST_DB_PATH) as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = 'turing@sdit.ac.in'")
        # Insert a pending faculty
        conn.execute("""
            INSERT INTO users (name, email, password_hash, role, department, is_approved, is_active, is_admin)
            VALUES ('Pending Prof', 'pending.prof@sdit.ac.in', ?, 'faculty', 'Physics', 0, 1, 0)
        """, (hash_password("PendingPass123!"),))
        conn.commit()

    # Login as admin faculty
    client.post("/api/auth/login", json={
        "email": "turing@sdit.ac.in",
        "password": "SuperSecret123!",
        "role": "faculty"
    })

    # View accounts
    admin_list = client.get("/api/faculty/admin/users")
    assert admin_list.status_code == 200
    users = admin_list.json()["users"]
    pending = next((u for u in users if u["email"] == "pending.prof@sdit.ac.in"), None)
    assert pending is not None
    assert pending["is_approved"] == 0

    # Approve pending faculty
    appr_res = client.post(f"/api/faculty/admin/users/{pending['id']}/status", json={"action": "approve"})
    assert appr_res.status_code == 200

    # Deactivate account
    deact_res = client.post(f"/api/faculty/admin/users/{pending['id']}/status", json={"action": "deactivate"})
    assert deact_res.status_code == 200

    # Deactivated account cannot login
    client.post("/api/auth/logout")
    fail_login = client.post("/api/auth/login", json={
        "email": "pending.prof@sdit.ac.in",
        "password": "PendingPass123!",
        "role": "faculty"
    })
    assert fail_login.status_code == 403
    assert "deactivated" in fail_login.json()["detail"].lower()
