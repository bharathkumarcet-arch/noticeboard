from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional
import sqlite3
from datetime import datetime

from app.database import get_db
from app.security import get_current_user

router = APIRouter(prefix="/api/notices", tags=["notices"])

@router.get("")
def list_active_notices(
    q: Optional[str] = Query(None, description="Search term in title or body"),
    category: Optional[str] = Query(None, description="Filter by category"),
    priority: Optional[str] = Query(None, description="Filter by priority (normal, important, urgent)"),
    date: Optional[str] = Query(None, description="Filter by publish date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    List active, published notices for students.
    Only returns notices that are published and within valid publish_at/expires_at range.
    Includes indicator if notice is new (< 48 hrs) or if requesting student has viewed it.
    Pinned notices appear at the top.
    """
    cursor = conn.cursor()
    
    # Base query for active published notices
    where_clauses = [
        "n.status = 'published'",
        "datetime(n.publish_at) <= datetime('now')",
        "(n.expires_at IS NULL OR datetime(n.expires_at) >= datetime('now'))"
    ]
    params = []
    
    if q and q.strip():
        term = f"%{q.strip()}%"
        where_clauses.append("(n.title LIKE ? OR n.body LIKE ?)")
        params.extend([term, term])
        
    if category and category.strip() and category != "all":
        where_clauses.append("n.category = ?")
        params.append(category.strip())
        
    if priority and priority.strip() and priority != "all":
        where_clauses.append("n.priority = ?")
        params.append(priority.strip())

    if date and date.strip():
        where_clauses.append("date(n.publish_at) = date(?)")
        params.append(date.strip())
        
    where_sql = " AND ".join(where_clauses)
    
    # Count total matching
    count_sql = f"SELECT COUNT(*) FROM notices n WHERE {where_sql}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]
    
    # Fetch paginated notices
    offset = (page - 1) * page_size
    query_sql = f"""
        SELECT 
            n.id, n.title, n.body, n.category, n.priority, n.status, n.is_pinned,
            n.attachment_url, n.attachment_name, n.attachment_size,
            n.publish_at, n.expires_at, n.created_at, n.updated_at,
            u.name as author_name, u.department as author_department,
            CASE 
                WHEN datetime(n.publish_at) >= datetime('now', '-2 days') THEN 1 
                ELSE 0 
            END as is_new,
            CASE 
                WHEN EXISTS (SELECT 1 FROM notice_views nv WHERE nv.notice_id = n.id AND nv.student_id = ?) THEN 1 
                ELSE 0 
            END as has_viewed
        FROM notices n
        JOIN users u ON n.author_id = u.id
        WHERE {where_sql}
        ORDER BY 
            n.is_pinned DESC,
            CASE n.priority 
                WHEN 'urgent' THEN 1 
                WHEN 'important' THEN 2 
                ELSE 3 
            END ASC,
            n.publish_at DESC
        LIMIT ? OFFSET ?
    """
    
    exec_params = [user["id"]] + params + [page_size, offset]
    cursor.execute(query_sql, exec_params)
    rows = cursor.fetchall()
    
    notices = []
    for r in rows:
        d = dict(r)
        # Generate summary snippet for card view
        body_clean = d["body"]
        d["summary"] = body_clean[:180] + ("..." if len(body_clean) > 180 else "")
        notices.append(d)
        
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
        "notices": notices
    }

@router.get("/{notice_id}")
def get_notice_detail(
    notice_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    View notice details.
    If viewed by an authenticated student:
    - Verifies the notice is active and published
    - Records the unique readership view idempotently
    - Does NOT leak other students' views
    If viewed by faculty:
    - Author can see any notice (even draft or archived)
    - Faculty views are NOT recorded in notice_views
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            n.id, n.title, n.body, n.category, n.priority, n.status, n.is_pinned,
            n.author_id, n.attachment_url, n.attachment_name, n.attachment_size,
            n.publish_at, n.expires_at, n.created_at, n.updated_at,
            u.name as author_name, u.department as author_department
        FROM notices n
        JOIN users u ON n.author_id = u.id
        WHERE n.id = ?
    """, (notice_id,))
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notice not found.")
        
    notice = dict(row)
    
    # Permission and visibility check for students
    if user["role"] == "student":
        cursor.execute("""
            SELECT 1 FROM notices
            WHERE id = ? 
              AND status = 'published'
              AND datetime(publish_at) <= datetime('now')
              AND (expires_at IS NULL OR datetime(expires_at) >= datetime('now'))
        """, (notice_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This notice is not currently active or published."
            )
            
        # Record student view idempotently!
        # UNIQUE(notice_id, student_id) ensures one view per student per notice
        cursor.execute("""
            INSERT OR IGNORE INTO notice_views (notice_id, student_id, first_viewed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (notice_id, user["id"]))
        conn.commit()
        
        # Check first_viewed_at for this student
        cursor.execute("""
            SELECT first_viewed_at FROM notice_views WHERE notice_id = ? AND student_id = ?
        """, (notice_id, user["id"]))
        view_row = cursor.fetchone()
        notice["my_first_viewed_at"] = view_row["first_viewed_at"] if view_row else None
        
    elif user["role"] == "faculty":
        # Faculty can see total unique readers count
        cursor.execute("SELECT COUNT(*) FROM notice_views WHERE notice_id = ?", (notice_id,))
        notice["readership_count"] = cursor.fetchone()[0]
        
    return {"success": True, "notice": notice}
