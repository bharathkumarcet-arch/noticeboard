import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
import sqlite3

from app.config import settings
from app.database import get_db
from app.models import NoticeCreate, NoticeUpdate, NoticeStatusUpdate
from app.security import require_faculty, require_approved_faculty
from app.routes.uploads import save_uploaded_file

router = APIRouter(prefix="/api/faculty", tags=["faculty"])

@router.get("/metrics")
def get_faculty_metrics(
    user: dict = Depends(require_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Get summary totals for faculty dashboard:
    - Published notices
    - Draft notices
    - Archived notices
    - Total unique student readership views
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN status = 'published' THEN 1 END) as total_published,
            COUNT(CASE WHEN status = 'draft' THEN 1 END) as total_draft,
            COUNT(CASE WHEN status = 'archived' THEN 1 END) as total_archived,
            COUNT(*) as total_all
        FROM notices
    """)
    totals = dict(cursor.fetchone())
    
    # Total unique reads across all notices
    cursor.execute("SELECT COUNT(*) FROM notice_views")
    totals["total_views"] = cursor.fetchone()[0]
    
    # Active notices right now
    cursor.execute("""
        SELECT COUNT(*) FROM notices
        WHERE status = 'published'
          AND datetime(publish_at) <= datetime('now')
          AND (expires_at IS NULL OR datetime(expires_at) >= datetime('now'))
    """)
    totals["total_active"] = cursor.fetchone()[0]
    
    return {"success": True, "metrics": totals}

@router.get("/notices")
def list_faculty_notices(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    user: dict = Depends(require_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Comprehensive list of notices with readership counts and status.
    Protected for faculty/admin.
    """
    cursor = conn.cursor()
    where_clauses = ["1=1"]
    params = []
    
    if status_filter and status_filter.strip() and status_filter != "all":
        where_clauses.append("n.status = ?")
        params.append(status_filter.strip())
        
    if category and category.strip() and category != "all":
        where_clauses.append("n.category = ?")
        params.append(category.strip())
        
    if priority and priority.strip() and priority != "all":
        where_clauses.append("n.priority = ?")
        params.append(priority.strip())
        
    if q and q.strip():
        term = f"%{q.strip()}%"
        where_clauses.append("(n.title LIKE ? OR n.body LIKE ?)")
        params.extend([term, term])
        
    where_sql = " AND ".join(where_clauses)
    
    # Count total
    count_sql = f"SELECT COUNT(*) FROM notices n WHERE {where_sql}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]
    
    offset = (page - 1) * page_size
    query_sql = f"""
        SELECT 
            n.id, n.title, n.body, n.category, n.priority, n.status,
            n.author_id, n.attachment_url, n.attachment_name, n.attachment_size,
            n.publish_at, n.expires_at, n.created_at, n.updated_at,
            u.name as author_name,
            (SELECT COUNT(*) FROM notice_views nv WHERE nv.notice_id = n.id) as readership_count,
            CASE 
                WHEN n.status = 'published' 
                     AND datetime(n.publish_at) <= datetime('now') 
                     AND (n.expires_at IS NULL OR datetime(n.expires_at) >= datetime('now')) 
                THEN 1 ELSE 0 
            END as is_currently_active
        FROM notices n
        JOIN users u ON n.author_id = u.id
        WHERE {where_sql}
        ORDER BY n.created_at DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(query_sql, params + [page_size, offset])
    rows = cursor.fetchall()
    
    notices = [dict(r) for r in rows]
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
        "notices": notices
    }

@router.post("/notices", status_code=status.HTTP_201_CREATED)
async def create_notice(
    title: str = Form(...),
    body: str = Form(...),
    category: str = Form(...),
    priority: str = Form("normal"),
    notice_status: str = Form("draft", alias="status"),
    publish_at: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    attachment: Optional[UploadFile] = File(None),
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Create a new notice with optional attachment.
    """
    title = title.strip()
    body = body.strip()
    category = category.strip()
    priority = priority.strip().lower()
    notice_status = notice_status.strip().lower()
    
    if len(title) < 3 or len(title) > 200:
        raise HTTPException(status_code=400, detail="Title must be between 3 and 200 characters.")
    if len(body) < 5:
        raise HTTPException(status_code=400, detail="Notice content must be at least 5 characters.")
    if priority not in ("normal", "important", "urgent"):
        raise HTTPException(status_code=400, detail="Invalid priority level.")
    if notice_status not in ("draft", "published", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status.")
        
    # Handle optional file attachment
    attachment_url = None
    attachment_name = None
    attachment_size = None
    if attachment and attachment.filename:
        attachment_url, attachment_name, attachment_size = save_uploaded_file(attachment)
        
    publish_val = publish_at if publish_at and publish_at.strip() else None
    expires_val = expires_at if expires_at and expires_at.strip() else None
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notices (
            title, body, category, priority, status, author_id,
            attachment_url, attachment_name, attachment_size,
            publish_at, expires_at, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            COALESCE(?, CURRENT_TIMESTAMP), ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """, (
        title, body, category, priority, notice_status, user["id"],
        attachment_url, attachment_name, attachment_size,
        publish_val, expires_val
    ))
    conn.commit()
    notice_id = cursor.lastrowid
    
    return {
        "success": True,
        "message": f"Notice '{title}' created successfully.",
        "notice_id": notice_id
    }

@router.put("/notices/{notice_id}")
async def update_notice(
    notice_id: int,
    title: str = Form(...),
    body: str = Form(...),
    category: str = Form(...),
    priority: str = Form("normal"),
    notice_status: str = Form("draft", alias="status"),
    publish_at: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    remove_attachment: bool = Form(False),
    attachment: Optional[UploadFile] = File(None),
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Update an existing notice.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, attachment_url FROM notices WHERE id = ?", (notice_id,))
    existing = cursor.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Notice not found.")
        
    title = title.strip()
    body = body.strip()
    category = category.strip()
    priority = priority.strip().lower()
    notice_status = notice_status.strip().lower()
    
    if len(title) < 3 or len(title) > 200:
        raise HTTPException(status_code=400, detail="Title must be between 3 and 200 characters.")
    if len(body) < 5:
        raise HTTPException(status_code=400, detail="Notice content must be at least 5 characters.")
    if priority not in ("normal", "important", "urgent"):
        raise HTTPException(status_code=400, detail="Invalid priority level.")
    if notice_status not in ("draft", "published", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status.")
        
    attachment_url = existing["attachment_url"]
    attachment_name = None
    attachment_size = None
    
    # Handle attachment removal
    if remove_attachment and existing["attachment_url"]:
        old_path = settings.BASE_DIR / existing["attachment_url"].lstrip("/")
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass
        attachment_url = None
        
    # Handle new attachment upload
    if attachment and attachment.filename:
        # Remove old attachment if existed
        if existing["attachment_url"]:
            old_path = settings.BASE_DIR / existing["attachment_url"].lstrip("/")
            if old_path.exists():
                try:
                    old_path.unlink()
                except Exception:
                    pass
        attachment_url, attachment_name, attachment_size = save_uploaded_file(attachment)
        
    publish_val = publish_at if publish_at and publish_at.strip() else None
    expires_val = expires_at if expires_at and expires_at.strip() else None
    
    if attachment_name is not None:
        cursor.execute("""
            UPDATE notices
            SET title = ?, body = ?, category = ?, priority = ?, status = ?,
                publish_at = COALESCE(?, publish_at), expires_at = ?,
                attachment_url = ?, attachment_name = ?, attachment_size = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, body, category, priority, notice_status, publish_val, expires_val,
              attachment_url, attachment_name, attachment_size, notice_id))
    elif remove_attachment:
        cursor.execute("""
            UPDATE notices
            SET title = ?, body = ?, category = ?, priority = ?, status = ?,
                publish_at = COALESCE(?, publish_at), expires_at = ?,
                attachment_url = NULL, attachment_name = NULL, attachment_size = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, body, category, priority, notice_status, publish_val, expires_val, notice_id))
    else:
        cursor.execute("""
            UPDATE notices
            SET title = ?, body = ?, category = ?, priority = ?, status = ?,
                publish_at = COALESCE(?, publish_at), expires_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, body, category, priority, notice_status, publish_val, expires_val, notice_id))
        
    conn.commit()
    return {"success": True, "message": "Notice updated successfully."}

@router.patch("/notices/{notice_id}/status")
def update_notice_status(
    notice_id: int,
    data: NoticeStatusUpdate,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Quick status toggle (e.g. publish, unpublish, archive).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM notices WHERE id = ?", (notice_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Notice not found.")
        
    cursor.execute("""
        UPDATE notices 
        SET status = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (data.status, notice_id))
    conn.commit()
    
    return {"success": True, "message": f"Notice status changed to '{data.status}'."}

@router.delete("/notices/{notice_id}")
def delete_notice(
    notice_id: int,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Delete notice and clean up its attachment file and view records.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, attachment_url FROM notices WHERE id = ?", (notice_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Notice not found.")
        
    if row["attachment_url"]:
        file_path = settings.BASE_DIR / row["attachment_url"].lstrip("/")
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
                
    cursor.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    conn.commit()
    
    return {"success": True, "message": f"Notice '{row['title']}' deleted successfully."}

@router.get("/notices/{notice_id}/readership")
def get_notice_readership_analytics(
    notice_id: int,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Faculty/admin viewership analytics:
    Returns the total unique readership count and the list of student views
    with first-viewed timestamps.
    Protected strictly for faculty/admin.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, category, priority, status, publish_at 
        FROM notices 
        WHERE id = ?
    """, (notice_id,))
    notice = cursor.fetchone()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found.")
        
    cursor.execute("""
        SELECT 
            nv.id as view_id,
            nv.first_viewed_at,
            u.id as student_user_id,
            u.name as student_name,
            u.email as student_email,
            u.student_id,
            u.department,
            u.course
        FROM notice_views nv
        JOIN users u ON nv.student_id = u.id
        WHERE nv.notice_id = ?
        ORDER BY nv.first_viewed_at DESC
    """, (notice_id,))
    views = [dict(r) for r in cursor.fetchall()]
    
    return {
        "success": True,
        "notice": dict(notice),
        "total_unique_readers": len(views),
        "views": views,
        "privacy_policy": {
            "purpose": "Academic compliance and communication tracking",
            "retention": "Readership records are retained during active academic semester",
            "visibility": "Visible exclusively to authorized college faculty and administration"
        }
    }
