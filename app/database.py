import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional
from app.config import settings

def get_connection(db_path=None) -> sqlite3.Connection:
    path = db_path or settings.DATABASE_PATH
    conn = sqlite3.connect(str(path), timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = DELETE;")
    return conn

@contextmanager
def get_db_ctx(db_path=None) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_db() -> Generator[sqlite3.Connection, None, None]:
    with get_db_ctx() as conn:
        yield conn

def init_db(db_path=None):
    with get_db_ctx(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('faculty', 'student')),
            department TEXT,
            course TEXT,
            semester INTEGER CHECK (semester IS NULL OR (semester >= 1 AND semester <= 8)),
            student_id TEXT,
            is_approved INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('normal', 'important', 'urgent')),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
            is_pinned INTEGER NOT NULL DEFAULT 0,
            target_type TEXT NOT NULL DEFAULT 'all' CHECK (target_type IN ('all', 'targeted')),
            target_summary TEXT NOT NULL DEFAULT 'All Students',
            author_id INTEGER NOT NULL,
            attachment_url TEXT,
            attachment_name TEXT,
            attachment_size INTEGER,
            publish_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS notice_audiences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            department TEXT,
            semester INTEGER,
            FOREIGN KEY (notice_id) REFERENCES notices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notice_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            student_department TEXT,
            student_semester INTEGER,
            first_viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (notice_id) REFERENCES notices(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(notice_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS notice_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER,
            notice_title TEXT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL COLLATE NOCASE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Dynamic migrations: ensure all new columns exist on users
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [row["name"] for row in cursor.fetchall()]
        if "is_approved" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 1")
        if "is_active" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "is_admin" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        if "semester" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN semester INTEGER CHECK (semester IS NULL OR (semester >= 1 AND semester <= 8))")

        # Dynamic migrations: ensure is_pinned, target_type, target_summary exist on notices
        cursor.execute("PRAGMA table_info(notices)")
        notice_cols = [row["name"] for row in cursor.fetchall()]
        if "is_pinned" not in notice_cols:
            cursor.execute("ALTER TABLE notices ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")
        if "target_type" not in notice_cols:
            cursor.execute("ALTER TABLE notices ADD COLUMN target_type TEXT NOT NULL DEFAULT 'all'")
        if "target_summary" not in notice_cols:
            cursor.execute("ALTER TABLE notices ADD COLUMN target_summary TEXT NOT NULL DEFAULT 'All Students'")

        # Dynamic migrations: ensure student_department and student_semester exist on notice_views
        cursor.execute("PRAGMA table_info(notice_views)")
        view_cols = [row["name"] for row in cursor.fetchall()]
        if "student_department" not in view_cols:
            cursor.execute("ALTER TABLE notice_views ADD COLUMN student_department TEXT")
        if "student_semester" not in view_cols:
            cursor.execute("ALTER TABLE notice_views ADD COLUMN student_semester INTEGER")

        # Now safely create all indexes
        conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_dept_sem ON users(department, semester);
        CREATE INDEX IF NOT EXISTS idx_notices_status_dates ON notices(status, publish_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_notices_pinned ON notices(is_pinned);
        CREATE INDEX IF NOT EXISTS idx_notices_category ON notices(category);
        CREATE INDEX IF NOT EXISTS idx_notices_priority ON notices(priority);
        CREATE INDEX IF NOT EXISTS idx_notices_author ON notices(author_id);
        CREATE INDEX IF NOT EXISTS idx_notices_target_type ON notices(target_type);
        CREATE INDEX IF NOT EXISTS idx_notice_audiences_notice ON notice_audiences(notice_id);
        CREATE INDEX IF NOT EXISTS idx_notice_audiences_dept_sem ON notice_audiences(department, semester);
        CREATE INDEX IF NOT EXISTS idx_views_notice ON notice_views(notice_id);
        CREATE INDEX IF NOT EXISTS idx_views_student ON notice_views(student_id);
        CREATE INDEX IF NOT EXISTS idx_audit_notice ON notice_audit_logs(notice_id);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON notice_audit_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token);
        """)

        # Standardize existing categories to: Academics, Exams, Events, Placements, General
        cursor.execute("UPDATE notices SET category = 'Academics' WHERE category IN ('Academic', 'academics')")
        cursor.execute("UPDATE notices SET category = 'Exams' WHERE category IN ('Examination', 'Exam', 'exams')")
        cursor.execute("UPDATE notices SET category = 'Events' WHERE category IN ('Cultural', 'Event', 'events')")
        cursor.execute("UPDATE notices SET category = 'Placements' WHERE category IN ('Placement', 'placements')")
        cursor.execute("UPDATE notices SET category = 'General' WHERE category IN ('Administrative', 'general')")

        # Standardize existing department names
        cursor.execute("UPDATE users SET department = 'Electronics & Communication Engineering' WHERE department = 'Electronics & Communication'")

        # Safely migrate existing student semesters based on their registered course text if semester is currently NULL
        cursor.execute("SELECT id, course FROM users WHERE role = 'student' AND semester IS NULL")
        for st in cursor.fetchall():
            c_text = (st["course"] or "").lower()
            sem_val = None
            if "1st year" in c_text or "first year" in c_text:
                sem_val = 1
            elif "2nd year" in c_text or "second year" in c_text:
                sem_val = 3
            elif "3rd year" in c_text or "third year" in c_text:
                sem_val = 5
            elif "4th year" in c_text or "fourth year" in c_text:
                sem_val = 7
            if sem_val:
                cursor.execute("UPDATE users SET semester = ? WHERE id = ?", (sem_val, st["id"]))

        # Treat existing notices as 'all' students unless already configured
        cursor.execute("UPDATE notices SET target_type = 'all', target_summary = 'All Students' WHERE target_type IS NULL OR target_summary IS NULL")

        # Ensure at least one faculty has admin rights for approval management
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'faculty' AND is_admin = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT id FROM users WHERE role = 'faculty' ORDER BY id ASC LIMIT 1")
            first_faculty = cursor.fetchone()
            if first_faculty:
                cursor.execute("UPDATE users SET is_admin = 1, is_approved = 1, is_active = 1 WHERE id = ?", (first_faculty["id"],))

def format_audience_summary(target_type: str, departments: list, semesters: list) -> str:
    """
    Build a crystal-clear human readable audience description.
    e.g. "All Students", "Semester 7 · Computer Science & Engineering",
         "Semesters 5, 7 · Computer Science & Engineering, Electronics & Communication Engineering",
         "Semester 7 · All Branches", "All Semesters · Information Science & Engineering"
    """
    if target_type == "all" or (not departments and not semesters):
        return "All Students"
    
    # Process semesters description
    sem_text = ""
    valid_sems = sorted(list({int(s) for s in semesters if str(s).isdigit() and 1 <= int(s) <= 8}))
    if len(valid_sems) == 0 or len(valid_sems) == 8:
        sem_text = "All Semesters"
    elif len(valid_sems) == 1:
        sem_text = f"Semester {valid_sems[0]}"
    else:
        sem_text = f"Semesters {', '.join(str(s) for s in valid_sems)}"

    # Process departments description
    dept_text = ""
    cleaned_depts = [d.strip() for d in departments if d and d.strip()]
    if len(cleaned_depts) == 0 or len(cleaned_depts) >= len(settings.DEPARTMENTS):
        dept_text = "All Branches"
    elif len(cleaned_depts) == 1:
        dept_text = cleaned_depts[0]
    else:
        dept_text = ", ".join(cleaned_depts)

    if sem_text == "All Semesters" and dept_text == "All Branches":
        return "All Students"
    
    return f"{sem_text} · {dept_text}"

def set_notice_audience(
    conn: sqlite3.Connection,
    notice_id: int,
    target_type: str,
    departments: list,
    semesters: list
) -> str:
    """
    Normalized persistence for notice audience rules.
    If target_type == 'all': clears notice_audiences and marks notice target_type='all'.
    If target_type == 'targeted': persists normalized branch x semester pairings.
    Returns the computed human-readable summary string.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notice_audiences WHERE notice_id = ?", (notice_id,))

    if target_type == "all":
        summary = "All Students"
        cursor.execute("""
            UPDATE notices
            SET target_type = 'all', target_summary = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (summary, notice_id))
        return summary

    cleaned_depts = [d.strip() for d in departments if d and d.strip()]
    valid_sems = sorted(list({int(s) for s in semesters if str(s).isdigit() and 1 <= int(s) <= 8}))

    if not cleaned_depts and not valid_sems:
        # Default back to all if empty rules given
        summary = "All Students"
        cursor.execute("""
            UPDATE notices
            SET target_type = 'all', target_summary = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (summary, notice_id))
        return summary

    summary = format_audience_summary("targeted", cleaned_depts, valid_sems)

    # Determine normalization structure
    is_all_depts = (len(cleaned_depts) == 0 or len(cleaned_depts) >= len(settings.DEPARTMENTS))
    is_all_sems = (len(valid_sems) == 0 or len(valid_sems) == 8)

    if is_all_depts and not is_all_sems:
        # Targets specific semester(s) across all departments
        for s in valid_sems:
            cursor.execute("INSERT INTO notice_audiences (notice_id, department, semester) VALUES (?, NULL, ?)", (notice_id, s))
    elif not is_all_depts and is_all_sems:
        # Targets specific department(s) across all semesters
        for d in cleaned_depts:
            cursor.execute("INSERT INTO notice_audiences (notice_id, department, semester) VALUES (?, ?, NULL)", (notice_id, d))
    else:
        # Targets specific department and semester combinations
        for d in cleaned_depts:
            for s in valid_sems:
                cursor.execute("INSERT INTO notice_audiences (notice_id, department, semester) VALUES (?, ?, ?)", (notice_id, d, s))

    cursor.execute("""
        UPDATE notices
        SET target_type = 'targeted', target_summary = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (summary, notice_id))

    return summary

def get_notice_audience(conn: sqlite3.Connection, notice_id: int) -> dict:
    """
    Retrieve notice targeting rules and distinct departments/semesters.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT target_type, target_summary FROM notices WHERE id = ?", (notice_id,))
    nrow = cursor.fetchone()
    if not nrow:
        return {"target_type": "all", "target_summary": "All Students", "departments": [], "semesters": []}

    target_type = nrow["target_type"] or "all"
    target_summary = nrow["target_summary"] or "All Students"

    cursor.execute("SELECT DISTINCT department, semester FROM notice_audiences WHERE notice_id = ?", (notice_id,))
    rows = cursor.fetchall()
    depts = sorted(list({r["department"] for r in rows if r["department"] is not None}))
    sems = sorted(list({r["semester"] for r in rows if r["semester"] is not None}))

    return {
        "target_type": target_type,
        "target_summary": target_summary,
        "departments": depts,
        "semesters": sems
    }

def record_audit_log(
    conn: sqlite3.Connection,
    user_id: int,
    action: str,
    notice_id: Optional[int] = None,
    notice_title: Optional[str] = None,
    details: Optional[str] = None
):
    """
    Records an immutable audit event for critical notice actions.
    """
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notice_audit_logs (notice_id, notice_title, user_id, action, details, created_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (notice_id, notice_title, user_id, action, details))
