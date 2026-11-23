# College Notice Board Management System
### Shree Devi Institute of Technology

A full-stack, responsive, and secure institutional web application designed for **Shree Devi Institute of Technology** to publish, manage, and verify circulars and announcements with guaranteed unique student readership tracking, notice pinning, automated scheduling and expiration, audit trails, and role-based administrative controls.

---

## 🏛 Features Overview

### 1. Categories, Search & Filters
- **Standardized Categories:** `Academics`, `Exams`, `Events`, `Placements`, and `General`.
- **Search Capabilities:** Search circulars by title, full content, or issuing author in real-time.
- **Multi-Parameter Filtering:** Filter by Category, Priority (`Urgent`, `Important`, `Regular`), and Date.
- **Mobile Responsive:** Adaptive touch-friendly filter bars with instant reset buttons.
- **Accessible Status Indicators:** Distinct badges and visual icons (e.g., 🚨 Urgent, ⚠️ Important, ℹ️ Regular) ensuring clarity without relying on color alone.

### 2. Notice Pinning
- **Faculty / Admin Pin Controls:** Faculty can pin or unpin notices with a single click or during notice creation/editing.
- **Student Board Prominence:** Pinned notices are pinned prominently to the top of the student board, highlighted with a distinct pin indicator.
- **Strict Authorization:** Only approved faculty and administrators can change pin status; student pin modification is blocked on the backend.

### 3. Scheduling and Expiry
- **Lifecycle Management:** Save notices as drafts, publish immediately, or schedule for future release dates.
- **Automatic Expiration:** Set an optional expiry date and time. After expiration, notices automatically disappear from student feeds while remaining archived in faculty records.
- **Date Validation:** Server validates that expiration dates must follow publication dates.
- **Clear Statuses:** Distinguishes between `Active`, `Scheduled`, `Expired`, `Draft`, and `Archived`.

### 4. Unique Readership Reports & CSV Export
- **Idempotency Guarantee:** When an authenticated student opens a notice, their first view is recorded in `notice_views`. Subsequent refreshes or repeat visits maintain the original timestamp and do not inflate the count.
- **Database-Level Constraint:** Enforced with `UNIQUE(notice_id, student_id)` and transaction-safe parameterization.
- **Faculty Exclusion:** Views by faculty members or administrators are never counted toward student readership.
- **Readership Dashboard:** Per-notice analytics showing reader count, first-view timestamps, student IDs, departments, and course/year.
- **CSV Export:** Authorized faculty/administrators can export notice readership reports as CSV files (`/faculty/notices/{id}/readership/csv`).

### 5. Attachments
- **Allowed Formats:** Official PDFs and images (PNG, JPG, JPEG, WEBP).
- **Server-Side Validation:** Enforces 5 MB file size limit and verifies file extension and MIME type.
- **Limits Shown Upfront:** Allowed formats and 5 MB limit are clearly displayed on the upload form before submission.
- **Secure File Access:** Secure endpoints verify user session before serving downloads.

### 6. Faculty Approval & Account Management
- **Student Signup:** Open registration with name, student ID / USN, department, course, and institutional email.
- **Controlled Faculty Onboarding:**
  - Faculty register with their institutional email and academic department.
  - Option 1: Fast-track instant approval with the institute secret joining code (`SDIT-FACULTY-2026`).
  - Option 2: Pending registration (`is_approved = 0`) awaiting administrative approval.
  - Pending faculty cannot publish, edit, pin, or delete notices or view analytics.
- **Admin Account Management Screen (`/faculty/admin/users`):**
  - Administrators can review all institutional accounts.
  - One-click actions to Approve, Revoke Approval, Activate, or Deactivate accounts.
  - Deactivated accounts cannot sign in.

### 7. Password Recovery ("Forgot Password?")
- **Recovery Hub (`/forgot-password`):** Secure self-service password reset request.
- **Anti-Enumeration:** The system returns a generic confirmation message regardless of whether an email exists, preventing account enumeration attacks.
- **Secure Time-Limited Tokens:** Generates 32-byte cryptographic reset tokens valid for 1 hour.
- **Reset Page (`/reset-password?token=...`):** Validates the token and updates the user's password securely with bcrypt hashing.

### 8. Immutable Audit History
- **Action Tracking:** Automatically logs critical notice events: `created`, `edited`, `published`, `scheduled`, `pinned`, `unpinned`, `archived`, and `deleted`.
- **Audit Details:** Records the actor name, user ID, notice title, action taken, and timestamp.
- **Audit Screen:** Faculty and administrators can view the complete audit log directly on the notice detail page.
- **Immutable Log:** Audit entries cannot be modified or deleted through ordinary application routes.

### 9. Student Experience & Accessibility
- **"Unread" Indicators:** Clearly identifies unread circulars with a blue `● UNREAD` badge based on recorded views.
- **Keyboard Navigation & Visible Focus:** Full focus rings (`:focus-visible`), skip-to-content links, and semantic HTML throughout.
- **Responsive Design:** Designed and tested across mobile, tablet, and desktop screens.
- **Confirmation Modals:** Accessible dialogs for destructive actions (e.g. notice deletion).

### 10. Institution Branding
- Explicitly branded for **Shree Devi Institute of Technology** across headers, navigation, footers, page titles, empty states, and exports.
- Product title **"College Notice Board Management System"** appears consistently as supporting text.

---

## 🛠 Technology Stack

- **Institution:** Shree Devi Institute of Technology
- **Backend:** Python 3.12, FastAPI, Starlette.
- **Database:** SQLite with foreign keys (`PRAGMA foreign_keys = ON`), transactions, and indexes.
- **Security:** `bcrypt` salted password hashing, HMAC-SHA256 session tokens in HTTP-only cookies (`SameSite=Lax`).
- **Frontend:** Jinja2 SSR, component-driven CSS design system with mobile responsiveness.
- **Testing:** `pytest` test suite with 16 automated tests covering all RBAC boundaries, pinning, CSV exports, audit trails, and recovery flows.

---

## 🚀 Quick Start Guide

### 1. Installation

```powershell
# 1. Clone repository
git clone https://github.com/bharathkumarcet-arch/noticeboard.git
cd noticeboard

# 2. Install Python dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```

Key environment variables:
- `COLLEGE_NAME`: "Shree Devi Institute of Technology"
- `SECRET_KEY`: Long secret key for signing session tokens
- `FACULTY_INVITE_CODE`: Institute code for faculty onboarding (default: `SDIT-FACULTY-2026`)
- `DATABASE_FILE`: SQLite database file path (default: `notice_board.db`)
- `MAX_UPLOAD_SIZE_BYTES`: Max upload size in bytes (default: `5242880` = 5 MB)

### 3. Database Initialization & Seeding

```powershell
# Initialize tables and apply automatic migrations
python manage.py init-db

# Seed with sample SDIT faculty, students, and circulars
python manage.py seed
```

### 4. Run the Server

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open your browser at: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🔑 Pre-Configured Test Credentials

| Role | Email Address | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Faculty (Admin)** | `faculty.vance@sdit.ac.in` | `FacultyPass123!` | Notices CRUD, Pinning, Readership, Account Approvals |
| **Faculty (Admin)** | `admin.faculty@sdit.edu` | `FacultyPass@2026` | Notices CRUD, Pinning, Readership, Account Approvals |
| **Faculty (Approved)** | `faculty.wright@sdit.ac.in` | `FacultyPass123!` | Notices CRUD, Pinning, Readership Reports |
| **Student** | `alice.cooper@student.sdit.ac.in` | `StudentPass123!` | Read active notices, Download attachments, Track views |
| **Student** | `bob.martinez@student.sdit.ac.in` | `StudentPass123!` | Read active notices, Download attachments, Track views |

---

## 🧪 Automated Verification Suite

Run all 16 automated integration and security tests:
```powershell
python -m pytest tests/test_notice_board.py -v
```

All 16 test suites verify:
1. Institution branding rendering across all pages.
2. Initial faculty login and session cookie handling.
3. Student registration, validations, and duplicate prevention.
4. Faculty registration and pending approval workflows.
5. Strict RBAC blocking students from administrative endpoints.
6. Notice lifecycle, expiration hiding, and unique student readership idempotency.
7. Safe file uploads and authorized downloads.
8. Live search and multi-parameter filtering.
9. Notice pinning and unpinning permissions.
10. Readership report CSV export with header metadata.
11. Secure time-limited password recovery tokens and reset flow.
12. Immutable audit history logging for all notice actions.
13. Administrator faculty approvals, rejections, and deactivations.