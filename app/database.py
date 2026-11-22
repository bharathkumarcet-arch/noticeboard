import sqlite3
from contextlib import contextmanager
from typing import Generator
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('normal', 'important', 'urgent')),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
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

        -- Indexes for high-performance filtering and lookups
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_notices_status_dates ON notices(status, publish_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_notices_category ON notices(category);
        CREATE INDEX IF NOT EXISTS idx_notices_priority ON notices(priority);
        CREATE INDEX IF NOT EXISTS idx_notices_author ON notices(author_id);
        CREATE INDEX IF NOT EXISTS idx_views_notice ON notice_views(notice_id);
        CREATE INDEX IF NOT EXISTS idx_views_student ON notice_views(student_id);
        """)

        # Migration: ensure is_approved exists on existing users table
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "is_approved" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 1")
