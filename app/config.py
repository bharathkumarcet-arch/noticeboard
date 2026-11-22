import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    BASE_DIR: Path = BASE_DIR
    APP_NAME: str = os.getenv("APP_NAME", "College Notice Board Management System")
    COLLEGE_NAME: str = os.getenv("COLLEGE_NAME", "Shree Devi Institute of Technology")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production-c0ll3g3-n0t1c3-2026")
    
    # Faculty Registration Invite Code
    FACULTY_INVITE_CODE: str = os.getenv("FACULTY_INVITE_CODE", "SDIT-FACULTY-2026")
    
    # Database
    DATABASE_PATH: Path = BASE_DIR / os.getenv("DATABASE_FILE", "notice_board.db")
    
    # Uploads
    UPLOAD_DIR: Path = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(5 * 1024 * 1024)))  # 5 MB
    ALLOWED_EXTENSIONS: set = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
    
    # Session
    SESSION_COOKIE_NAME: str = "cnb_session"
    SESSION_MAX_AGE_SECONDS: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(24 * 3600)))  # 24 hours
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    COOKIE_SAMESITE: str = "lax"

settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
