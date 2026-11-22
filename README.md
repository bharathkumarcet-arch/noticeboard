# College Notice Board Management System
### Shree Devi Institute of Technology

A full-stack, responsive, and secure institutional web application designed for **Shree Devi Institute of Technology** to publish, manage, and verify circulars and announcements with guaranteed unique student readership tracking.

---

## 🏛 Features Overview

### 1. Two-Tier Role-Based Access Control (RBAC)
- **Faculty / Administration Portal:**
  - Create, edit, draft, publish, schedule, unpublish, archive, and delete official notices.
  - Upload verified PDF or image attachments (up to 5 MB).
  - Dashboard analytics displaying published, draft, archived circulars, and campus-wide reach.
  - **Unique Readership Tracking:** Monitor the exact unique count and list of enrolled students who opened each notice, complete with their first-view timestamps.
  - Student and classmate visibility lists are strictly hidden from students.
  - Profile management and secure credential changes.
  - **Controlled Faculty Approval Flow:** Newly registered faculty must provide an active Institute Invitation Code or obtain administrative approval before publishing and analytics permissions are unlocked.

- **Student Portal:**
  - View published, currently active circulars in real-time.
  - Live full-text search across titles and descriptions.
  - Category filtering (`Academic`, `Examination`, `Placement`, `Cultural`, `Sports`, `Administrative`, `General`).
  - Priority filtering (`Urgent`, `Important`, `Normal`) with visual urgency badges.
  - "New" indicators for circulars issued in the last 48 hours and "Read" vs "Unread" badges.
  - Secure attachment preview and download.
  - Automatic, idempotent first-read recording upon opening a notice.
  - Profile settings and self-service registration.

### 2. Complete Signup & Registration Flows
- **Sign-in Screen Entry Points (`/login`):**
  - Direct link to “Create a student account” (`/register/student`)
  - Direct link to “Create a faculty account” (`/register/faculty`)
  - Role selection hub (`/register` / `/signup`)
  - Links back to sign-in from every signup page.

- **Student Registration (`/register/student`):**
  - Collects Full Name, Student ID / Registration No. / USN (e.g. `4SD23CS045`), College Email Address, Department, Course & Year, Password & Confirm Password.
  - Server-enforced `student` role.
  - Automatic sign-in and redirect to the Student Notice Board dashboard.

- **Faculty Registration (`/register/faculty`):**
  - Collects Full Name, Official Institute Email (`@sdit.ac.in`), Department, Password & Confirm Password (min 8 chars), and an optional/required Institute Faculty Invitation Code.
  - Server-enforced `faculty` role (users cannot assign their own permissions).
  - **Instant Verification:** If the valid `FACULTY_INVITE_CODE` is provided, the account is verified immediately (`is_approved = 1`).
  - **Administrative Review:** If submitted without the code, the account is saved in pending state (`is_approved = 0`). Until approved, the faculty member cannot publish, edit, or delete notices or access readership analytics.

### 3. High-Assurance Readership Tracking
- **Idempotency Guarantee:** When a student opens a notice, their first view is recorded in `notice_views`. Subsequent refreshes or visits maintain the original timestamp and do not inflate the tally.
- **Database-Level Constraint:** Enforced with `UNIQUE(notice_id, student_id)` and transaction-safe parameterization.
- **Faculty Exclusion:** Views by authors and administrators do not count toward student readership statistics.
- **Privacy Policy Transparency:** Dedicated privacy statement explains data collection, audit rationale, and role restrictions.

---

## 🛠 Technology Stack

- **Institution:** Shree Devi Institute of Technology
- **Backend:** Python 3.12, FastAPI (high-performance asynchronous ASGI framework), Starlette.
- **Database:** SQLite with foreign key enforcement (`PRAGMA foreign_keys = ON`), parameterized queries, and composite indexes.
- **Security & Cryptography:** `bcrypt` for one-way salted password hashing, HMAC-SHA256 signed session tokens stored in HTTP-only cookies (`SameSite=Lax`).
- **Frontend:** Jinja2 SSR combined with responsive, component-driven modern CSS design system, responsive mobile layout, accessible modal dialogs, and toast notifications.
- **Testing:** `pytest` test suite verifying authorization, RBAC boundaries, file safety, and readership idempotency.

---

## 📁 Project Structure

```text
├── app/
│   ├── config.py             # Configuration & environment variables
│   ├── database.py           # SQLite connection pool, schema initialization, and indices
│   ├── security.py           # Bcrypt hashing, HMAC session tokens, and RBAC dependencies
│   ├── models.py             # Pydantic schemas and input validation
│   ├── cli.py                # Administrative CLI commands (init-db, seed, create-faculty, approve-faculty)
│   ├── routes/
│   │   ├── auth.py           # Login, student/faculty signup, password change, logout
│   │   ├── notices.py        # Active notices listing & student detail (with view recording)
│   │   ├── faculty.py        # Faculty metrics, CRUD operations, and readership analytics
│   │   ├── uploads.py        # Safe attachment uploads and authorized downloads
│   │   └── pages.py          # HTML page routers
│   ├── static/
│   │   ├── css/app.css       # Polished institutional design system & responsive styling
│   │   └── js/app.js         # Interactive modals, toasts, debounced search, status toggles
│   └── templates/
│       ├── base.html         # Base template with responsive navigation & footer
│       ├── login.html        # Dual-tab Faculty & Student sign-in with signup links
│       ├── register_choice.html # Role selection hub (Student vs Faculty signup)
│       ├── register_student.html# Approved student registration flow
│       ├── register_faculty.html# Secure faculty registration flow with invite code
│       ├── student_dashboard.html # Active notice board with live search & filters
│       ├── notice_detail.html     # Notice content & attachment download
│       ├── faculty_dashboard.html # Metrics cards & recent engagement table
│       ├── faculty_notices.html   # Full management table with action buttons
│       ├── notice_form.html       # Create/edit notice with live preview
│       ├── readership.html        # Detailed audit table of unique student readers
│       ├── profile.html           # Account info & password change form
│       ├── privacy.html           # Readership tracking disclosure & compliance policy
│       ├── 403.html               # Access forbidden page
│       └── 404.html               # Page not found error view
├── tests/
│   └── test_notice_board.py  # Automated end-to-end test suite (11 tests)
├── uploads/                  # Secure attachment storage directory
├── main.py                   # FastAPI server entry point
├── manage.py                 # Management CLI runner
├── requirements.txt          # Production dependencies
├── .env.example              # Template environment configuration
└── README.md                 # Project documentation
```

---

## 🚀 Installation and Quickstart

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- pip

### 2. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Key configuration parameters:
- `COLLEGE_NAME`: Set to `Shree Devi Institute of Technology`.
- `SECRET_KEY`: Cryptographic key for HMAC session signatures.
- `FACULTY_INVITE_CODE`: Institutional joining code for verified faculty signups (defaults to `SDIT-FACULTY-2026`).
- `DATABASE_FILE`: SQLite database path (defaults to `notice_board.db`).
- `MAX_UPLOAD_SIZE_BYTES`: Maximum attachment size (defaults to `5242880` bytes / 5 MB).

---

## 👥 Setup & Initial Accounts

### Option A: Quick Demo Seeding (Recommended)
Populate the database with sample Shree Devi Institute of Technology faculty members, enrolled students, realistic circulars (urgent, important, normal, draft, and archived), and verified student readership records:
```bash
python manage.py seed
```

**Pre-seeded Demo Accounts:**
| Role | Email | Password | Department / Notes |
| :--- | :--- | :--- | :--- |
| **Faculty** | `faculty.wright@sdit.ac.in` | `FacultyPass123!` | Academic Affairs (Approved) |
| **Faculty** | `faculty.vance@sdit.ac.in` | `FacultyPass123!` | Computer Science & Eng. (Approved) |
| **Faculty** | `faculty.chen@sdit.ac.in` | `FacultyPass123!` | Training & Placement (Approved) |
| **Student** | `alice.cooper@student.sdit.ac.in` | `StudentPass123!` | B.E. CSE (`4SD23CS014`) |
| **Student** | `bob.martinez@student.sdit.ac.in` | `StudentPass123!` | B.E. CSE (`4SD23CS029`) |
| **Student** | `carol.smith@student.sdit.ac.in` | `StudentPass123!` | B.E. ECE (`4SD23EC008`) |

---

### Option B: Approving a Pending Faculty Account via CLI
If a faculty member signs up without the invitation code, an administrator can approve and activate their account using:
```bash
python manage.py approve-faculty --email "faculty.member@sdit.ac.in"
```

---

### Option C: Direct Faculty Administrator Provisioning
To create a verified faculty administrator directly via CLI:
```bash
python manage.py create-faculty \
  --name "Dr. Rajesh Bhat" \
  --email "rajesh.bhat@sdit.ac.in" \
  --password "SecureFacultyPass999!" \
  --department "Computer Science & Engineering"
```

---

## 💻 Running the Web Application

Start the local server with hot reload:
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Once started, open your browser and navigate to:
```text
http://127.0.0.1:8000
```
- Click **"Sign In"** or go directly to `/login`.
- Choose **"Create a student account"** (`/register/student`) or **"Create a faculty account"** (`/register/faculty`).

---

## 🧪 Running the Automated Test Suite

Run the full end-to-end test suite:
```bash
python -m pytest tests/ -v
```

The automated test suite verifies:
1. Institution name rendering across login and signup pages.
2. Faculty creation, password hashing, and authentication.
3. Student registration, password match confirmation, duplicate email & student ID rejection.
4. Faculty signup with invitation code, pending approval enforcement, and CLI approval workflow.
5. Role-Based Access Control (RBAC): student denial on faculty creation, metrics, and analytics endpoints (403 Forbidden).
6. Notice lifecycle: draft creation -> student cannot see draft -> publication -> student sees active notice.
7. Unique readership tracking: recording first view timestamp on student access.
8. Readership idempotency: refreshing notices does not increment unique count; faculty visits do not count as student views.
9. Readership analytics: faculty access to student readership breakdown.
10. Safe attachment handling: type verification, size verification, and safe downloads.
11. Filtering by category, priority, keyword search, expired notice hiding, and password change workflow.

---

## 🔒 Security & Privacy Implementation Notes

1. **Password Security:** All passwords are salted and hashed using `bcrypt` (10 rounds). Plaintext passwords are never stored or logged.
2. **Session Security:** Sessions use HMAC-SHA256 signed tokens stored in `HttpOnly`, `SameSite=Lax` cookies, preventing XSS-based session hijacking.
3. **Faculty Approval Safeguard:** Role assignments are enforced on the backend. Unapproved faculty cannot publish, edit, or delete notices or access student readership data.
4. **Parameterization:** All database operations use SQLite parameterized bindings (`?`) to prevent SQL injection.
5. **Attachment Security:**
   - Files are validated against allowed formats (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`).
   - File sizes are checked before storage (5 MB ceiling).
   - Filenames are sanitized and prepended with a random UUID to prevent path traversal (`../`) attacks.
   - Downloads check user authentication and verify that students can only download attachments from published, active notices.
6. **Readership Privacy Compliance:** Notice readership logs are strictly accessible to faculty and administration. Students only see their own first-view acknowledgment.

---

## 📜 License
Developed for **Shree Devi Institute of Technology**. All rights reserved &copy; 2026.
