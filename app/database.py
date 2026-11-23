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

        CREATE TABLE IF NOT EXISTS notice_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
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

        # Dynamic migrations: ensure is_pinned exists on notices
        cursor.execute("PRAGMA table_info(notices)")
        notice_cols = [row["name"] for row in cursor.fetchall()]
        if "is_pinned" not in notice_cols:
            cursor.execute("ALTER TABLE notices ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")

        # Now safely create all indexes
        conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_notices_status_dates ON notices(status, publish_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_notices_pinned ON notices(is_pinned);
        CREATE INDEX IF NOT EXISTS idx_notices_category ON notices(category);
        CREATE INDEX IF NOT EXISTS idx_notices_priority ON notices(priority);
        CREATE INDEX IF NOT EXISTS idx_notices_author ON notices(author_id);
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

        # Ensure at least one faculty has admin rights for approval management
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'faculty' AND is_admin = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT id FROM users WHERE role = 'faculty' ORDER BY id ASC LIMIT 1")
            first_faculty = cursor.fetchone()
            if first_faculty:
                cursor.execute("UPDATE users SET is_admin = 1, is_approved = 1, is_active = 1 WHERE id = ?", (first_faculty["id"],))

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
