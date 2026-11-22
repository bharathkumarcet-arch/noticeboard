from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3

from app.config import settings
from app.database import get_db
from app.security import get_current_user_optional, require_faculty, require_student

templates_dir = settings.BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter(include_in_schema=False)

def common_context(request: Request, user: Optional[dict] = None) -> dict:
    return {
        "request": request,
        "user": user,
        "app_name": settings.APP_NAME,
        "college_name": settings.COLLEGE_NAME,
        "active_path": request.url.path
    }

def render_template(request: Request, name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    if "request" not in context:
        context["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)

@router.get("/", response_class=HTMLResponse)
def index(request: Request, user: Optional[dict] = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login")
    if user["role"] == "faculty":
        return RedirectResponse(url="/faculty")
    return RedirectResponse(url="/student")

@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: Optional[str] = None,
    success: Optional[str] = None,
    role: Optional[str] = "student",
    user: Optional[dict] = Depends(get_current_user_optional)
):
    if user:
        dest = "/faculty" if user["role"] == "faculty" else "/student"
        return RedirectResponse(url=dest)
        
    ctx = common_context(request, user)
    ctx.update({
        "error": error,
        "success": success,
        "default_role": role if role in ("faculty", "student") else "student"
    })
    return render_template(request, "login.html", ctx)

@router.get("/register", response_class=HTMLResponse)
@router.get("/signup", response_class=HTMLResponse)
def register_choice_page(
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    if user:
        dest = "/faculty" if user["role"] == "faculty" else "/student"
        return RedirectResponse(url=dest)
        
    ctx = common_context(request, user)
    return render_template(request, "register_choice.html", ctx)

@router.get("/register/student", response_class=HTMLResponse)
def register_student_page(
    request: Request,
    error: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    if user:
        dest = "/faculty" if user["role"] == "faculty" else "/student"
        return RedirectResponse(url=dest)
        
    ctx = common_context(request, user)
    ctx.update({"error": error})
    return render_template(request, "register_student.html", ctx)

@router.get("/register/faculty", response_class=HTMLResponse)
def register_faculty_page(
    request: Request,
    error: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    if user:
        dest = "/faculty" if user["role"] == "faculty" else "/student"
        return RedirectResponse(url=dest)
        
    ctx = common_context(request, user)
    ctx.update({"error": error})
    return render_template(request, "register_faculty.html", ctx)

@router.get("/student", response_class=HTMLResponse)
def student_dashboard(
    request: Request,
    user: dict = Depends(require_student)
):
    ctx = common_context(request, user)
    return render_template(request, "student_dashboard.html", ctx)

@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail_page(
    notice_id: int,
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional),
    conn: sqlite3.Connection = Depends(get_db)
):
    if not user:
        return RedirectResponse(url=f"/login?error=Please+log+in+to+view+notices.&next=/notices/{notice_id}")
        
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            n.id, n.title, n.body, n.category, n.priority, n.status,
            n.author_id, n.attachment_url, n.attachment_name, n.attachment_size,
            n.publish_at, n.expires_at, n.created_at, n.updated_at,
            u.name as author_name, u.department as author_department
        FROM notices n
        JOIN users u ON n.author_id = u.id
        WHERE n.id = ?
    """, (notice_id,))
    row = cursor.fetchone()
    
    if not row:
        ctx = common_context(request, user)
        ctx["error"] = "The requested notice does not exist or has been removed."
        return render_template(request, "404.html", ctx, status_code=404)
        
    notice = dict(row)
    
    # Check student visibility
    if user["role"] == "student":
        cursor.execute("""
            SELECT 1 FROM notices
            WHERE id = ? 
              AND status = 'published'
              AND datetime(publish_at) <= datetime('now')
              AND (expires_at IS NULL OR datetime(expires_at) >= datetime('now'))
        """, (notice_id,))
        if not cursor.fetchone():
            ctx = common_context(request, user)
            ctx["error"] = "This notice is no longer active or is in draft."
            return render_template(request, "403.html", ctx, status_code=403)
            
        # Record view idempotently
        cursor.execute("""
            INSERT OR IGNORE INTO notice_views (notice_id, student_id, first_viewed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (notice_id, user["id"]))
        conn.commit()
        
        cursor.execute("SELECT first_viewed_at FROM notice_views WHERE notice_id = ? AND student_id = ?", (notice_id, user["id"]))
        v = cursor.fetchone()
        notice["my_first_viewed_at"] = v["first_viewed_at"] if v else None
    else:
        # Faculty sees readership count
        cursor.execute("SELECT COUNT(*) FROM notice_views WHERE notice_id = ?", (notice_id,))
        notice["readership_count"] = cursor.fetchone()[0]
        
    ctx = common_context(request, user)
    ctx["notice"] = notice
    return render_template(request, "notice_detail.html", ctx)

@router.get("/faculty", response_class=HTMLResponse)
def faculty_dashboard(
    request: Request,
    warning: Optional[str] = None,
    user: dict = Depends(require_faculty)
):
    ctx = common_context(request, user)
    ctx["warning"] = warning
    return render_template(request, "faculty_dashboard.html", ctx)

@router.get("/faculty/notices", response_class=HTMLResponse)
def faculty_notices_page(
    request: Request,
    user: dict = Depends(require_faculty)
):
    ctx = common_context(request, user)
    return render_template(request, "faculty_notices.html", ctx)

@router.get("/faculty/notices/new", response_class=HTMLResponse)
def new_notice_page(
    request: Request,
    user: dict = Depends(require_faculty)
):
    if user.get("is_approved", 1) != 1:
        return RedirectResponse(url="/faculty?warning=Your+faculty+account+is+pending+administrative+approval.+Notice+creation+is+disabled+until+approved.")
    ctx = common_context(request, user)
    ctx["notice"] = None
    ctx["is_edit"] = False
    return render_template(request, "notice_form.html", ctx)

@router.get("/faculty/notices/{notice_id}/edit", response_class=HTMLResponse)
def edit_notice_page(
    notice_id: int,
    request: Request,
    user: dict = Depends(require_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    if user.get("is_approved", 1) != 1:
        return RedirectResponse(url="/faculty?warning=Your+faculty+account+is+pending+administrative+approval.+Notice+editing+is+disabled+until+approved.")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notices WHERE id = ?", (notice_id,))
    row = cursor.fetchone()
    if not row:
        ctx = common_context(request, user)
        ctx["error"] = "Notice not found."
        return render_template(request, "404.html", ctx, status_code=404)
        
    ctx = common_context(request, user)
    ctx["notice"] = dict(row)
    ctx["is_edit"] = True
    return render_template(request, "notice_form.html", ctx)

@router.get("/faculty/notices/{notice_id}/readership", response_class=HTMLResponse)
def notice_readership_page(
    notice_id: int,
    request: Request,
    user: dict = Depends(require_faculty),
    conn: sqlite3.Connection = Depends(get_db)
):
    if user.get("is_approved", 1) != 1:
        return RedirectResponse(url="/faculty?warning=Your+faculty+account+is+pending+administrative+approval.+Readership+analytics+is+restricted+until+approved.")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, u.name as author_name 
        FROM notices n 
        JOIN users u ON n.author_id = u.id 
        WHERE n.id = ?
    """, (notice_id,))
    row = cursor.fetchone()
    if not row:
        ctx = common_context(request, user)
        ctx["error"] = "Notice not found."
        return render_template(request, "404.html", ctx, status_code=404)
        
    cursor.execute("""
        SELECT 
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
    
    ctx = common_context(request, user)
    ctx["notice"] = dict(row)
    ctx["views"] = views
    ctx["total_readers"] = len(views)
    return render_template(request, "readership.html", ctx)

@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    if not user:
        return RedirectResponse(url="/login")
    ctx = common_context(request, user)
    return render_template(request, "profile.html", ctx)

@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    ctx = common_context(request, user)
    return render_template(request, "privacy.html", ctx)
