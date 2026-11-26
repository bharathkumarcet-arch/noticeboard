import hmac
import hashlib
import json
import base64
import time
from typing import Optional, Dict, Any, List
import bcrypt
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
import sqlite3

from app.config import settings
from app.database import get_db

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=10)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding < 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))

def create_session_token(user_id: int, role: str) -> str:
    now = int(time.time())
    payload = {
        "uid": user_id,
        "role": role,
        "iat": now,
        "exp": now + settings.SESSION_MAX_AGE_SECONDS
    }
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    payload_b64 = _b64encode(payload_bytes)
    
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_b64 = _b64encode(signature)
    
    return f"{payload_b64}.{sig_b64}"

def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256
        ).digest()
        actual_sig = _b64decode(sig_b64)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

def get_current_user_optional(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> Optional[Dict[str, Any]]:
    # Check session cookie or Authorization header
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
    if not token:
        return None
        
    payload = verify_session_token(token)
    if not payload:
        return None
        
    user_id = payload.get("uid")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, department, course, semester, student_id, is_approved, is_active, is_admin, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None
        
    user = dict(row)
    # Check if account has been deactivated by administrator
    if user.get("is_active", 1) != 1:
        return None

    # Ensure role from DB matches token
    if user["role"] != payload.get("role"):
        return None
        
    return user

def get_current_user(request: Request, user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)) -> Dict[str, Any]:
    if not user:
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login?error=Session+expired+or+account+inactive.+Please+log+in+again."}
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required or account inactive")
    return user

def require_role(allowed_roles: List[str]):
    def role_checker(request: Request, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user["role"] not in allowed_roles:
            if "text/html" in request.headers.get("accept", ""):
                # Redirect to appropriate dashboard with message
                dest = "/student" if user["role"] == "student" else "/faculty"
                raise HTTPException(
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                    headers={"Location": f"{dest}?error=Unauthorized+access+denied."}
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}"
            )
        return user
    return role_checker

def require_approved_faculty(request: Request, user: Dict[str, Any] = Depends(require_role(["faculty"]))) -> Dict[str, Any]:
    if user.get("is_approved", 1) != 1:
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/faculty?warning=Your+faculty+account+is+pending+administrative+approval."}
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is pending administrative approval. You cannot publish, edit, pin, or delete notices or view readership analytics until approved."
        )
    return user

def require_admin(request: Request, user: Dict[str, Any] = Depends(require_approved_faculty)) -> Dict[str, Any]:
    if user.get("is_admin", 0) != 1:
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/faculty?error=Administrator+privileges+required."}
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required for this action."
        )
    return user

require_faculty = require_role(["faculty"])
require_student = require_role(["student"])
