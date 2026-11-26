import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
import sqlite3

from app.config import settings
from app.database import get_db
from app.security import get_current_user

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

def save_uploaded_file(file: UploadFile) -> Tuple[str, str, int]:
    """
    Validates and securely stores an uploaded attachment.
    Returns (file_url, original_filename, file_size).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename provided.")
        
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format '{ext}'. Allowed formats: {allowed}"
        )
        
    # Read content to verify size
    contents = file.file.read()
    size = len(contents)
    if size > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum allowed size of {max_mb:.0f} MB."
        )
        
    # Generate random safe filename
    safe_filename = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    # Replace dangerous characters
    safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in "._-")
    
    file_path = settings.UPLOAD_DIR / safe_filename
    with open(file_path, "wb") as f:
        f.write(contents)
        
    return f"/api/uploads/{safe_filename}", file.filename, size

@router.get("/{filename}")
def download_attachment(
    filename: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Secure, authorized attachment download.
    Enforces authorization:
    - Must be logged in.
    - If user is student, the notice must be active and published.
    - Path traversal is strictly prevented.
    """
    # Strict path traversal check
    clean_filename = os.path.basename(filename)
    if clean_filename != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid attachment path.")
        
    file_path = settings.UPLOAD_DIR / clean_filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found.")
        
    # Lookup notice associated with this attachment
    cursor = conn.cursor()
    target_url = f"/api/uploads/{clean_filename}"
    cursor.execute("""
        SELECT id, title, status, publish_at, expires_at, attachment_name 
        FROM notices 
        WHERE attachment_url = ?
    """, (target_url,))
    notice = cursor.fetchone()
    
    if not notice:
        raise HTTPException(status_code=404, detail="Notice associated with this file not found.")
        
    # If student, verify notice is active, published, and audience-matched
    if user["role"] == "student":
        student_dept = user.get("department")
        student_sem = user.get("semester")
        cursor.execute("""
            SELECT 1 FROM notices n
            WHERE n.id = ? 
              AND n.status = 'published'
              AND datetime(n.publish_at) <= datetime('now')
              AND (n.expires_at IS NULL OR datetime(n.expires_at) >= datetime('now'))
              AND (
                  n.target_type = 'all' OR (
                      ? IS NOT NULL AND ? IS NOT NULL AND EXISTS (
                          SELECT 1 FROM notice_audiences na 
                          WHERE na.notice_id = n.id 
                            AND (na.department IS NULL OR na.department = ?)
                            AND (na.semester IS NULL OR na.semester = ?)
                      )
                  )
              )
        """, (notice["id"], student_dept, student_sem, student_dept, student_sem))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Access denied. This notice attachment is not accessible to your current academic profile (department/semester) or the notice is not active."
            )
            
    display_name = notice["attachment_name"] or clean_filename
    
    # Infer media type
    ext = Path(clean_filename).suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp"
    }
    media_type = media_types.get(ext, "application/octet-stream")
    
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=display_name,
        headers={"Content-Disposition": f'attachment; filename="{display_name}"'}
    )
