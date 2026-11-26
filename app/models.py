from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
ALLOWED_CATEGORIES = ("Academics", "Exams", "Events", "Placements", "General")

class UserCreateStudent(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=6, max_length=128)
    confirm_password: Optional[str] = None
    student_id: str = Field(..., min_length=2, max_length=30)
    department: str = Field(..., min_length=2, max_length=100)
    semester: int = Field(..., ge=1, le=8)
    course: Optional[str] = Field(None, max_length=100)

class StudentProfileUpdate(BaseModel):
    department: str = Field(..., min_length=2, max_length=100)
    semester: int = Field(..., ge=1, le=8)

class UserCreateFaculty(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: Optional[str] = None
    department: str = Field(..., min_length=2, max_length=100)
    invite_code: Optional[str] = None

class UserLogin(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str
    role: str = Field(..., pattern="^(faculty|student)$")

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=128)

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN)

class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=6, max_length=128)
    confirm_password: Optional[str] = None

class UserStatusUpdate(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|activate|deactivate)$")

class NoticePinUpdate(BaseModel):
    is_pinned: bool = Field(...)

class NoticeCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    body: str = Field(..., min_length=5, max_length=20000)
    category: str = Field(..., min_length=2, max_length=50)
    priority: str = Field(default="normal", pattern="^(normal|important|urgent)$")
    status: str = Field(default="draft", pattern="^(draft|published|archived)$")
    is_pinned: Optional[bool] = False
    target_type: str = Field(default="all", pattern="^(all|targeted)$")
    target_departments: Optional[List[str]] = None
    target_semesters: Optional[List[int]] = None
    publish_at: Optional[str] = None
    expires_at: Optional[str] = None

class NoticeUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    body: Optional[str] = Field(None, min_length=5, max_length=20000)
    category: Optional[str] = Field(None, min_length=2, max_length=50)
    priority: Optional[str] = Field(None, pattern="^(normal|important|urgent)$")
    status: Optional[str] = Field(None, pattern="^(draft|published|archived)$")
    is_pinned: Optional[bool] = None
    target_type: Optional[str] = Field(None, pattern="^(all|targeted)$")
    target_departments: Optional[List[str]] = None
    target_semesters: Optional[List[int]] = None
    publish_at: Optional[str] = None
    expires_at: Optional[str] = None
    remove_attachment: Optional[bool] = False

class NoticeStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(draft|published|archived)$")
