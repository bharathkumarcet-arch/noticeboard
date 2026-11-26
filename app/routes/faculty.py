import os
import io
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response, status
import sqlite3

from app.config import settings
from app.database import get_db, record_audit_log, set_notice_audience, get_notice_audience, format_audience_summary
from app.models import (
    NoticeCreate,
    NoticeUpdate,
    NoticeStatusUpdate,
    NoticePinUpdate,
    UserStatusUpdate,
    ALLOWED_CATEGORIES
)
from app.security import require_faculty, require_approved_faculty, require_admin
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
    date: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    target_department: Optional[str] = Query(None),
    target_semester: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    user: dict = Depends(require_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Comprehensive list of notices with readership counts, pin status, and lifecycle state.
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

    if date and date.strip():
        where_clauses.append("date(n.publish_at) = date(?)")
        params.append(date.strip())
        
    if q and q.strip():
        term = f"%{q.strip()}%"
        where_clauses.append("(n.title LIKE ? OR n.body LIKE ?)")
        params.extend([term, term])

    if target_department and target_department.strip() and target_department != "all":
        where_clauses.append("""(
            n.target_type = 'all' OR EXISTS (
                SELECT 1 FROM notice_audiences na WHERE na.notice_id = n.id AND (na.department IS NULL OR na.department = ?)
            )
        )""")
        params.append(target_department.strip())

    if target_semester and target_semester > 0:
        where_clauses.append("""(
            n.target_type = 'all' OR EXISTS (
                SELECT 1 FROM notice_audiences na WHERE na.notice_id = n.id AND (na.semester IS NULL OR na.semester = ?)
            )
        )""")
        params.append(target_semester)
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
            n.id, n.title, n.body, n.category, n.priority, n.status, n.is_pinned,
            n.target_type, n.target_summary,
            n.author_id, n.attachment_url, n.attachment_name, n.attachment_size,
            n.publish_at, n.expires_at, n.created_at, n.updated_at,
            u.name as author_name,
            (SELECT COUNT(*) FROM notice_views nv WHERE nv.notice_id = n.id) as readership_count,
            CASE 
                WHEN n.status = 'draft' THEN 'draft'
                WHEN n.status = 'archived' THEN 'archived'
                WHEN n.status = 'published' AND datetime(n.publish_at) > datetime('now') THEN 'scheduled'
                WHEN n.status = 'published' AND n.expires_at IS NOT NULL AND datetime(n.expires_at) < datetime('now') THEN 'expired'
                WHEN n.status = 'published' AND datetime(n.publish_at) <= datetime('now') AND (n.expires_at IS NULL OR datetime(n.expires_at) >= datetime('now')) THEN 'published'
                ELSE n.status
            END as lifecycle_status,
            CASE 
                WHEN n.status = 'published' 
                     AND datetime(n.publish_at) <= datetime('now') 
                     AND (n.expires_at IS NULL OR datetime(n.expires_at) >= datetime('now')) 
                THEN 1 ELSE 0 
            END as is_currently_active
        FROM notices n
        JOIN users u ON n.author_id = u.id
        WHERE {where_sql}
        ORDER BY n.is_pinned DESC, n.created_at DESC
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
    is_pinned: bool = Form(False),
    publish_at: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    target_type: str = Form("all"),
    target_departments: Optional[str] = Form(None),
    target_semesters: Optional[str] = Form(None),
    attachment: Optional[UploadFile] = File(None),
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Create a new notice with optional attachment, pin, scheduled dates, and audience targeting.
    """
    title = title.strip()
    body = body.strip()
    category = category.strip()
    priority = priority.strip().lower()
    notice_status = notice_status.strip().lower()
    target_type = target_type.strip().lower()
    if target_type not in ("all", "targeted"):
        target_type = "all"
        
    # Parse target departments & semesters
    depts: List[str] = []
    if target_departments:
        try:
            parsed = json.loads(target_departments)
            if isinstance(parsed, list):
                depts = [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            depts = [x.strip() for x in target_departments.split(",") if x.strip()]

    sems: List[int] = []
    if target_semesters:
        try:
            parsed = json.loads(target_semesters)
            if isinstance(parsed, list):
                sems = [int(x) for x in parsed if str(x).strip().isdigit() and 1 <= int(x) <= 8]
        except Exception:
            for x in target_semesters.split(","):
                x = x.strip()
                if x.isdigit() and 1 <= int(x) <= 8:
                    sems.append(int(x))

    if target_type == "targeted" and not depts and not sems:
        raise HTTPException(
            status_code=400,
            detail="For targeted notices, please select at least one department or semester, or choose 'All Students'."
        )

    summary_text = format_audience_summary(target_type, depts, sems)
    
    if len(title) < 3 or len(title) > 200:
        raise HTTPException(status_code=400, detail="Title must be between 3 and 200 characters.")
    if len(body) < 5:
        raise HTTPException(status_code=400, detail="Notice content must be at least 5 characters.")
    if priority not in ("normal", "important", "urgent"):
        raise HTTPException(status_code=400, detail="Invalid priority level.")
    if notice_status not in ("draft", "published", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status.")

    # Standardize category matching allowed categories
    cat_match = next((c for c in ALLOWED_CATEGORIES if c.lower() == category.lower()), None)
    if not cat_match:
        cat_match = "General" if category.lower() in ("general", "administrative", "other") else category
    category = cat_match
        
    publish_val = publish_at.strip() if publish_at and publish_at.strip() else None
    expires_val = expires_at.strip() if expires_at and expires_at.strip() else None

    # Date sanity validation
    if publish_val and expires_val:
        if expires_val <= publish_val:
            raise HTTPException(status_code=400, detail="Expiry date must be after publication date.")
        
    # Handle optional file attachment
    attachment_url = None
    attachment_name = None
    attachment_size = None
    if attachment and attachment.filename:
        attachment_url, attachment_name, attachment_size = save_uploaded_file(attachment)
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notices (
            title, body, category, priority, status, is_pinned, author_id,
            target_type, target_summary,
            attachment_url, attachment_name, attachment_size,
            publish_at, expires_at, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            COALESCE(?, CURRENT_TIMESTAMP), ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """, (
        title, body, category, priority, notice_status, 1 if is_pinned else 0, user["id"],
        target_type, summary_text,
        attachment_url, attachment_name, attachment_size,
        publish_val, expires_val
    ))
    conn.commit()
    notice_id = cursor.lastrowid

    # Persist normalized audience targeting rules
    set_notice_audience(conn, notice_id, target_type, depts, sems)
    conn.commit()

    # Record immutable audit event
    action_name = "scheduled" if (notice_status == "published" and publish_val and publish_val > datetime.now().isoformat()) else notice_status
    record_audit_log(
        conn=conn,
        user_id=user["id"],
        action=f"created_{action_name}",
        notice_id=notice_id,
        notice_title=title,
        details=f"Created with priority '{priority}', category '{category}', pinned={bool(is_pinned)}, audience='{summary_text}'"
    )
    conn.commit()
    
    return {
        "success": True,
        "message": f"Notice '{title}' created successfully for {summary_text}.",
        "notice_id": notice_id,
        "target_summary": summary_text
    }

@router.put("/notices/{notice_id}")
async def update_notice(
    notice_id: int,
    title: str = Form(...),
    body: str = Form(...),
    category: str = Form(...),
    priority: str = Form("normal"),
    notice_status: str = Form("draft", alias="status"),
    is_pinned: Optional[bool] = Form(None),
    publish_at: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    target_type: Optional[str] = Form(None),
    target_departments: Optional[str] = Form(None),
    target_semesters: Optional[str] = Form(None),
    remove_attachment: bool = Form(False),
    attachment: Optional[UploadFile] = File(None),
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Update an existing notice.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, is_pinned, attachment_url, target_type, target_summary FROM notices WHERE id = ?", (notice_id,))
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

    cat_match = next((c for c in ALLOWED_CATEGORIES if c.lower() == category.lower()), None)
    if not cat_match:
        cat_match = "General" if category.lower() in ("general", "administrative", "other") else category
    category = cat_match

    publish_val = publish_at.strip() if publish_at and publish_at.strip() else None
    expires_val = expires_at.strip() if expires_at and expires_at.strip() else None

    if publish_val and expires_val and expires_val <= publish_val:
        raise HTTPException(status_code=400, detail="Expiry date must be after publication date.")

    # Audience targeting update
    new_target_type = target_type.strip().lower() if target_type else existing["target_type"]
    if new_target_type not in ("all", "targeted"):
        new_target_type = "all"
        
    depts: List[str] = []
    if target_departments is not None:
        try:
            parsed = json.loads(target_departments)
            if isinstance(parsed, list):
                depts = [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            depts = [x.strip() for x in target_departments.split(",") if x.strip()]

    sems: List[int] = []
    if target_semesters is not None:
        try:
            parsed = json.loads(target_semesters)
            if isinstance(parsed, list):
                sems = [int(x) for x in parsed if str(x).strip().isdigit() and 1 <= int(x) <= 8]
        except Exception:
            for x in target_semesters.split(","):
                x = x.strip()
                if x.isdigit() and 1 <= int(x) <= 8:
                    sems.append(int(x))

    if target_type is not None:
        if new_target_type == "targeted" and not depts and not sems:
            raise HTTPException(
                status_code=400,
                detail="For targeted notices, please select at least one department or semester, or choose 'All Students'."
            )
        target_summary_val = format_audience_summary(new_target_type, depts, sems)
    else:
        target_summary_val = existing["target_summary"]
        
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
        if existing["attachment_url"]:
            old_path = settings.BASE_DIR / existing["attachment_url"].lstrip("/")
            if old_path.exists():
                try:
                    old_path.unlink()
                except Exception:
                    pass
        attachment_url, attachment_name, attachment_size = save_uploaded_file(attachment)

    pinned_val = (1 if is_pinned else 0) if is_pinned is not None else existing["is_pinned"]
    
    if attachment_name is not None:
        cursor.execute("""
            UPDATE notices
            SET title = ?, body = ?, category = ?, priority = ?, status = ?, is_pinned = ?,
                target_type = ?, target_summary = ?,
                publish_at = COALESCE(?, publish_at), expires_at = ?,
                attachment_url = ?, attachment_name = ?, attachment_size = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, body, category, priority, notice_status, pinned_val,
              new_target_type, target_summary_val,
              publish_val, expires_val,
              attachment_url, attachment_name, attachment_size, notice_id))
    elif remove_attachment:
        cursor.execute("""
            UPDATE notices
            SET title = ?, body = ?, category = ?, priority = ?, status = ?, is_pinned = ?,
                target_type = ?, target_summary = ?,
                publish_at = COALESCE(?, publish_at), expires_at = ?,
                attachment_url = NULL, attachment_name = NULL, attachment_size = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, body, category, priority, notice_status, pinned_val,
              new_target_type, target_summary_val,
              publish_val, expires_val, notice_id))
    else:
        cursor.execute("""
            UPDATE notices
            SET title = ?, body = ?, category = ?, priority = ?, status = ?, is_pinned = ?,
                target_type = ?, target_summary = ?,
                publish_at = COALESCE(?, publish_at), expires_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, body, category, priority, notice_status, pinned_val,
              new_target_type, target_summary_val,
              publish_val, expires_val, notice_id))

    if target_type is not None:
        set_notice_audience(conn, notice_id, new_target_type, depts, sems)

    record_audit_log(
        conn=conn,
        user_id=user["id"],
        action="edited",
        notice_id=notice_id,
        notice_title=title,
        details=f"Updated notice details (status: {notice_status}, priority: {priority}, pinned: {bool(pinned_val)}, audience: {target_summary_val})"
    )
    conn.commit()
    return {"success": True, "message": "Notice updated successfully.", "target_summary": target_summary_val}

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
    cursor.execute("SELECT id, title, status FROM notices WHERE id = ?", (notice_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Notice not found.")
        
    cursor.execute("""
        UPDATE notices 
        SET status = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (data.status, notice_id))
    
    record_audit_log(
        conn=conn,
        user_id=user["id"],
        action=data.status,
        notice_id=notice_id,
        notice_title=row["title"],
        details=f"Status changed from '{row['status']}' to '{data.status}' by {user['name']}"
    )
    conn.commit()
    
    return {"success": True, "message": f"Notice status changed to '{data.status}'."}

@router.post("/notices/{notice_id}/pin")
def toggle_notice_pin(
    notice_id: int,
    data: Optional[NoticePinUpdate] = None,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Pin or unpin a notice. Pinned notices appear highlighted at the top of the feed.
    Enforces pinning permissions: students cannot call this route.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, is_pinned FROM notices WHERE id = ?", (notice_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Notice not found.")

    new_pin = not bool(row["is_pinned"]) if data is None else data.is_pinned
    new_val = 1 if new_pin else 0

    cursor.execute("UPDATE notices SET is_pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_val, notice_id))
    action_type = "pinned" if new_val else "unpinned"
    record_audit_log(
        conn=conn,
        user_id=user["id"],
        action=action_type,
        notice_id=notice_id,
        notice_title=row["title"],
        details=f"Notice was {action_type} by {user['name']}"
    )
    conn.commit()

    return {
        "success": True,
        "is_pinned": bool(new_val),
        "message": f"Notice has been {action_type} successfully."
    }

@router.delete("/notices/{notice_id}")
def delete_notice(
    notice_id: int,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Delete notice, record audit entry, and clean up attachment file.
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

    record_audit_log(
        conn=conn,
        user_id=user["id"],
        action="deleted",
        notice_id=notice_id,
        notice_title=row["title"],
        details=f"Notice '{row['title']}' permanently deleted by {user['name']}"
    )
                
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
        SELECT id, title, category, priority, status, is_pinned, publish_at 
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
            nv.student_department,
            nv.student_semester,
            u.id as student_user_id,
            u.name as student_name,
            u.email as student_email,
            u.student_id,
            COALESCE(nv.student_department, u.department) as department,
            COALESCE(nv.student_semester, u.semester) as semester,
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

@router.get("/notices/{notice_id}/readership/csv")
def export_notice_readership_csv(
    notice_id: int,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Export readership report as CSV. Restricted strictly to authorized faculty/admin.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, priority FROM notices WHERE id = ?", (notice_id,))
    notice = cursor.fetchone()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found.")

    cursor.execute("""
        SELECT 
            u.name as student_name,
            u.email as student_email,
            u.student_id,
            COALESCE(nv.student_department, u.department) as department,
            COALESCE(nv.student_semester, u.semester) as semester,
            u.course,
            nv.first_viewed_at
        FROM notice_views nv
        JOIN users u ON nv.student_id = u.id
        WHERE nv.notice_id = ?
        ORDER BY nv.first_viewed_at ASC
    """, (notice_id,))
    rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Institution", settings.COLLEGE_NAME])
    writer.writerow(["Notice ID", notice["id"]])
    writer.writerow(["Notice Title", notice["title"]])
    writer.writerow(["Category", notice["category"]])
    writer.writerow(["Priority", notice["priority"]])
    writer.writerow([])
    writer.writerow(["Student Name", "Email Address", "Student ID", "Department", "Semester", "Course / Year", "First Viewed At (UTC)"])

    for r in rows:
        writer.writerow([
            r["student_name"],
            r["student_email"],
            r["student_id"] or "N/A",
            r["department"] or "N/A",
            f"Semester {r['semester']}" if r["semester"] else "N/A",
            r["course"] or "N/A",
            r["first_viewed_at"]
        ])

    csv_data = output.getvalue()
    filename = f"readership_notice_{notice_id}_{settings.COLLEGE_NAME.replace(' ', '_')}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.get("/notices/{notice_id}/audit")
def get_notice_audit_history(
    notice_id: int,
    user: dict = Depends(require_approved_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Get immutable audit history for a specific notice.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            a.id, a.action, a.details, a.created_at,
            u.name as user_name, u.email as user_email, u.role as user_role
        FROM notice_audit_logs a
        JOIN users u ON a.user_id = u.id
        WHERE a.notice_id = ?
        ORDER BY a.created_at DESC
    """, (notice_id,))
    logs = [dict(r) for r in cursor.fetchall()]

    return {"success": True, "notice_id": notice_id, "audit_logs": logs}

@router.get("/notices/{notice_id}/audience")
def get_notice_audience_details(
    notice_id: int,
    user: dict = Depends(require_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Get detailed normalized audience targeting rules for a notice.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, target_type, target_summary FROM notices WHERE id = ?", (notice_id,))
    notice = cursor.fetchone()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found.")
        
    audience = get_notice_audience(conn, notice_id)
    return {
        "success": True,
        "notice_id": notice_id,
        "title": notice["title"],
        "target_type": notice["target_type"],
        "target_summary": notice["target_summary"],
        "audience": audience
    }

# --- Administrator Faculty & User Account Management ---

@router.get("/admin/users")
def list_accounts_admin(
    role_filter: Optional[str] = Query(None, alias="role"),
    user: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Admin-only screen data: list faculty and student accounts with approval and activation status.
    """
    cursor = conn.cursor()
    where = "1=1"
    params = []
    if role_filter and role_filter in ("faculty", "student"):
        where += " AND role = ?"
        params.append(role_filter)

    cursor.execute(f"""
        SELECT id, name, email, role, department, course, student_id, is_approved, is_active, is_admin, created_at
        FROM users
        WHERE {where}
        ORDER BY role ASC, is_approved ASC, created_at DESC
    """, params)
    rows = [dict(r) for r in cursor.fetchall()]

    return {"success": True, "users": rows}

@router.post("/admin/users/{target_user_id}/status")
def update_user_status_admin(
    target_user_id: int,
    data: UserStatusUpdate,
    user: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Admin-only endpoint to approve, reject, activate, or deactivate accounts.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, is_admin FROM users WHERE id = ?", (target_user_id,))
    target = cursor.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="User account not found.")

    if target["id"] == user["id"] and data.action in ("deactivate", "reject"):
        raise HTTPException(status_code=400, detail="Administrators cannot deactivate or reject their own account.")

    action = data.action
    if action == "approve":
        cursor.execute("UPDATE users SET is_approved = 1, is_active = 1 WHERE id = ?", (target_user_id,))
        msg = f"Account for {target['name']} has been approved and activated."
    elif action == "reject":
        cursor.execute("UPDATE users SET is_approved = 0 WHERE id = ?", (target_user_id,))
        msg = f"Account for {target['name']} has been marked as unapproved."
    elif action == "activate":
        cursor.execute("UPDATE users SET is_active = 1 WHERE id = ?", (target_user_id,))
        msg = f"Account for {target['name']} has been activated."
    elif action == "deactivate":
        cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (target_user_id,))
        msg = f"Account for {target['name']} has been deactivated."

    conn.commit()
    return {"success": True, "message": msg}
