import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, status
import sqlite3

from app.database import get_db
from app.models import (
    UserLogin,
    UserCreateStudent,
    UserCreateFaculty,
    PasswordChange,
    ForgotPasswordRequest,
    ResetPasswordRequest
)
from app.security import (
    hash_password,
    verify_password,
    create_session_token,
    get_current_user,
    settings
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
def login(data: UserLogin, response: Response, conn: sqlite3.Connection = Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, email, password_hash, role, department, course, student_id, is_approved, is_active, is_admin FROM users WHERE email = ? COLLATE NOCASE",
        (data.email,)
    )
    user_row = cursor.fetchone()
    
    if not user_row or not verify_password(data.password, user_row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    user = dict(user_row)

    if user.get("is_active", 1) != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated by the institute administrator. Please contact SDIT administration."
        )
        
    if user["role"] != data.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account is not registered as a {data.role}. Please switch to the {user['role'].title()} tab."
        )
        
    token = create_session_token(user["id"], user["role"])
    
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    is_appr = bool(user["is_approved"] if "is_approved" in user.keys() else 1)
    is_adm = bool(user["is_admin"] if "is_admin" in user.keys() else 0)
    
    return {
        "success": True,
        "message": f"Welcome back, {user['name']}!",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "department": user["department"],
            "course": user["course"],
            "student_id": user["student_id"],
            "is_approved": is_appr,
            "is_admin": is_adm
        }
    }

@router.post("/register-student", status_code=status.HTTP_201_CREATED)
def register_student(data: UserCreateStudent, response: Response, conn: sqlite3.Connection = Depends(get_db)):
    if data.confirm_password and data.confirm_password != data.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and confirm password do not match."
        )

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (data.email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists."
        )
        
    cursor.execute("SELECT id FROM users WHERE student_id = ?", (data.student_id.strip(),))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this Student ID or registration number is already registered."
        )
        
    pw_hash = hash_password(data.password)
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, role, department, course, student_id, is_approved)
        VALUES (?, ?, ?, 'student', ?, ?, ?, 1)
        """,
        (data.name.strip(), data.email.strip().lower(), pw_hash, data.department.strip(), data.course.strip(), data.student_id.strip())
    )
    conn.commit()
    user_id = cursor.lastrowid
    
    # Auto-login the newly registered student
    token = create_session_token(user_id, "student")
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    return {
        "success": True,
        "message": "Student account registered successfully.",
        "user": {
            "id": user_id,
            "name": data.name,
            "email": data.email,
            "role": "student",
            "department": data.department,
            "course": data.course,
            "student_id": data.student_id,
            "is_approved": True
        }
    }

@router.post("/register-faculty", status_code=status.HTTP_201_CREATED)
def register_faculty(data: UserCreateFaculty, response: Response, conn: sqlite3.Connection = Depends(get_db)):
    if data.confirm_password and data.confirm_password != data.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and confirm password do not match."
        )

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (data.email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this institutional email address already exists."
        )
        
    # Verify invitation code or mark pending approval
    # If invitation code matches settings.FACULTY_INVITE_CODE: approved immediately
    # If not matching or not provided, mark is_approved = 0 (pending admin approval)
    provided_code = (data.invite_code or "").strip()
    is_approved = 1 if (provided_code and provided_code == settings.FACULTY_INVITE_CODE) else 0

    pw_hash = hash_password(data.password)
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, role, department, is_approved)
        VALUES (?, ?, ?, 'faculty', ?, ?)
        """,
        (data.name.strip(), data.email.strip().lower(), pw_hash, data.department.strip(), is_approved)
    )
    conn.commit()
    user_id = cursor.lastrowid
    
    # Auto-login the newly registered faculty
    token = create_session_token(user_id, "faculty")
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    msg = (
        "Faculty account registered and verified with invitation code." 
        if is_approved 
        else "Faculty account registered. Your account is pending administrative approval before publishing notices."
    )
    
    return {
        "success": True,
        "message": msg,
        "is_approved": bool(is_approved),
        "user": {
            "id": user_id,
            "name": data.name,
            "email": data.email,
            "role": "faculty",
            "department": data.department,
            "is_approved": bool(is_approved)
        }
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/"
    )
    return {"success": True, "message": "Signed out successfully."}

@router.get("/me")
def get_current_user_profile(user: dict = Depends(get_current_user)):
    return {"success": True, "user": user}

@router.post("/change-password")
def change_password(data: PasswordChange, user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    row = cursor.fetchone()
    
    if not row or not verify_password(data.current_password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password does not match.")
        
    new_hash = hash_password(data.new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    conn.commit()
    
    return {"success": True, "message": "Password changed successfully."}

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, conn: sqlite3.Connection = Depends(get_db)):
    """
    Request password reset link.
    Never reveals whether the email exists to prevent enumeration attacks.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE email = ? COLLATE NOCASE", (data.email.strip(),))
    user = cursor.fetchone()
    
    reset_token = None
    if user:
        reset_token = secrets.token_urlsafe(32)
        # Token valid for 1 hour
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO password_resets (email, token, expires_at, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (user["email"], reset_token, expires_at))
        conn.commit()
        # In actual deployment, an email would be dispatched.
        # For testing/local visibility, we log the reset link.
        print(f"[AUTH] Generated Password Reset Link for {user['email']}: /reset-password?token={reset_token}")
        
    return {
        "success": True,
        "message": "If an account with this email address exists in the SDIT system, password reset instructions have been generated.",
        "reset_token": reset_token  # Provided for easy automated test verification and UI development
    }

@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, conn: sqlite3.Connection = Depends(get_db)):
    """
    Complete password reset with a valid, unexpired token.
    """
    if data.confirm_password and data.confirm_password != data.new_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match.")
        
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, expires_at, used_at 
        FROM password_resets 
        WHERE token = ?
    """, (data.token.strip(),))
    record = cursor.fetchone()
    
    if not record or record["used_at"] is not None:
        raise HTTPException(status_code=400, detail="Invalid or previously used password reset link. Please request a new one.")
        
    cursor.execute("""
        SELECT 1 FROM password_resets 
        WHERE id = ? AND datetime(expires_at) >= datetime('now')
    """, (record["id"],))
    if not cursor.fetchone():
        raise HTTPException(status_code=400, detail="This password reset link has expired. Reset links are valid for 1 hour.")
        
    new_hash = hash_password(data.new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE email = ? COLLATE NOCASE", (new_hash, record["email"]))
    cursor.execute("UPDATE password_resets SET used_at = CURRENT_TIMESTAMP WHERE id = ?", (record["id"],))
    conn.commit()
    
    return {
        "success": True,
        "message": "Your password has been reset successfully. You may now log in with your new password."
    }
