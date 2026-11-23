import argparse
import sys
from datetime import datetime, timedelta
from app.config import settings
from app.database import init_db, get_db_ctx
from app.security import hash_password

def run_init_db():
    print(f"Initializing database at: {settings.DATABASE_PATH}...")
    init_db()
    print("Database tables and indexes created successfully.")

def run_create_faculty(name: str, email: str, password: str, department: str):
    init_db()
    with get_db_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,))
        if cursor.fetchone():
            print(f"Error: A user with email '{email}' already exists.")
            sys.exit(1)
            
        pw_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, department, is_approved)
            VALUES (?, ?, ?, 'faculty', ?, 1)
        """, (name, email.lower(), pw_hash, department))
        conn.commit()
        print(f"Faculty account created and approved for: {name} <{email}> (Department: {department})")

def run_approve_faculty(email: str):
    init_db()
    with get_db_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, role, is_approved FROM users WHERE email = ? COLLATE NOCASE", (email,))
        user = cursor.fetchone()
        if not user:
            print(f"Error: User with email '{email}' not found.")
            sys.exit(1)
        if user["role"] != "faculty":
            print(f"Error: User '{email}' is registered as {user['role']}, not faculty.")
            sys.exit(1)
        cursor.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (user["id"],))
        conn.commit()
        print(f"SUCCESS: Faculty account for '{user['name']}' <{email}> has been approved and activated.")

def run_make_admin(email: str):
    init_db()
    with get_db_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, role FROM users WHERE email = ? COLLATE NOCASE", (email,))
        user = cursor.fetchone()
        if not user:
            print(f"Error: User with email '{email}' not found.")
            sys.exit(1)
        cursor.execute("UPDATE users SET is_admin = 1, is_approved = 1, is_active = 1 WHERE id = ?", (user["id"],))
        conn.commit()
        print(f"SUCCESS: User '{user['name']}' <{email}> has been granted Administrator privileges.")

def run_seed_data():
    init_db()
    with get_db_ctx() as conn:
        cursor = conn.cursor()
        
        # Check if already seeded
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            print("Database already contains data. Clearing existing sample records...")
            cursor.execute("DELETE FROM notice_views")
            cursor.execute("DELETE FROM notice_audit_logs")
            cursor.execute("DELETE FROM notices")
            cursor.execute("DELETE FROM users")
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('notices', 'users', 'notice_views', 'notice_audit_logs')")
            except Exception:
                pass
            
        # 1. Seed Faculty Accounts (Shree Devi Institute of Technology)
        faculty_users = [
            ("Dr. Arthur Vance", "faculty.vance@sdit.ac.in", "FacultyPass123!", "Computer Science & Engineering", 1),
            ("Prof. Eleanor Wright", "faculty.wright@sdit.ac.in", "FacultyPass123!", "Academic Affairs", 0),
            ("Dr. Robert Chen", "faculty.chen@sdit.ac.in", "FacultyPass123!", "Training & Placement Cell", 0),
            ("Administrative Dean", "admin.faculty@sdit.edu", "FacultyPass@2026", "Administration & Governance", 1),
        ]
        
        faculty_ids = {}
        for name, email, pwd, dept, is_adm in faculty_users:
            cursor.execute("""
                INSERT INTO users (name, email, password_hash, role, department, is_approved, is_active, is_admin)
                VALUES (?, ?, ?, 'faculty', ?, 1, 1, ?)
            """, (name, email, hash_password(pwd), dept, is_adm))
            faculty_ids[email] = cursor.lastrowid
            
        # 2. Seed Student Accounts (Shree Devi Institute of Technology)
        students = [
            ("Alice Cooper", "alice.cooper@student.sdit.ac.in", "StudentPass123!", "4SD23CS014", "Computer Science & Engineering", "B.E. CSE - 3rd Year"),
            ("Bob Martinez", "bob.martinez@student.sdit.ac.in", "StudentPass123!", "4SD23CS029", "Computer Science & Engineering", "B.E. CSE - 3rd Year"),
            ("Carol Smith", "carol.smith@student.sdit.ac.in", "StudentPass123!", "4SD23EC008", "Electronics & Communication", "B.E. ECE - 2nd Year"),
            ("David Kim", "david.kim@student.sdit.ac.in", "StudentPass123!", "4SD23ME045", "Mechanical Engineering", "B.E. ME - 4th Year"),
            ("Emma Watson", "emma.watson@student.sdit.ac.in", "StudentPass123!", "4SD23IS088", "Information Science & Engineering", "B.E. ISE - 3rd Year"),
            ("Farhan Akhtar", "farhan.akhtar@student.sdit.ac.in", "StudentPass123!", "4SD23AE012", "Aeronautical Engineering", "B.E. AE - 1st Year"),
        ]
        
        student_ids = []
        for name, email, pwd, sid, dept, course in students:
            cursor.execute("""
                INSERT INTO users (name, email, password_hash, role, student_id, department, course, is_approved)
                VALUES (?, ?, ?, 'student', ?, ?, ?, 1)
            """, (name, email, hash_password(pwd), sid, dept, course))
            student_ids.append(cursor.lastrowid)
            
        # 3. Create Sample Notice Attachments (sample valid PDF file)
        sample_pdf_path = settings.UPLOAD_DIR / "exam_schedule_fall2026.pdf"
        if not sample_pdf_path.exists():
            with open(sample_pdf_path, "wb") as f:
                f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000117 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n206\n%%EOF")
                
        now = datetime.now()
        
        # 4. Seed Notices with Shree Devi Institute of Technology context
        notices_data = [
            {
                "title": "URGENT: Final Semester Examination Timetable & Seating Plan Released",
                "body": (
                    "All undergraduate and postgraduate students of Shree Devi Institute of Technology are hereby notified "
                    "that the End-Semester Examination schedule has been officially released by the Controller of Examinations.\n\n"
                    "Key Guidelines for Candidates:\n"
                    "1. Candidates must carry their valid Shree Devi Institute of Technology Identity Card and Examination Hall Ticket.\n"
                    "2. Entry into examination halls closes strictly 15 minutes before scheduled commencement.\n"
                    "3. Mobile phones, programmable scientific calculators, and smartwatches are strictly prohibited.\n\n"
                    "Please download the official notification attachment below for complete department-wise timetables "
                    "and hall seating allocations."
                ),
                "category": "Examination",
                "priority": "urgent",
                "status": "published",
                "author_id": faculty_ids["faculty.wright@sdit.ac.in"],
                "attachment_url": "/api/uploads/exam_schedule_fall2026.pdf",
                "attachment_name": "SDIT_Final_Exam_Schedule_2026.pdf",
                "attachment_size": 284100,
                "publish_at": (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "title": "Campus Placement Drive: TechNova Solutions Recruitment for 2026 Batch",
                "body": (
                    "The Training & Placement Cell of Shree Devi Institute of Technology is organizing an on-campus placement drive "
                    "with TechNova Solutions for final year engineering students.\n\n"
                    "Eligibility Criteria:\n"
                    "- B.E. (CSE / ISE / ECE) with minimum aggregate CGPA of 7.0 and no active backlogs.\n"
                    "- Open Roles: Associate Software Engineer, Cloud Infrastructure Engineer.\n"
                    "- Offered CTC: INR 8.5 - 12.0 LPA.\n\n"
                    "Registration Deadline: Upcoming Friday, 5:00 PM via the campus placement desk.\n"
                    "Pre-placement orientation will take place in the Main Auditorium at 10:00 AM."
                ),
                "category": "Placement",
                "priority": "important",
                "status": "published",
                "author_id": faculty_ids["faculty.chen@sdit.ac.in"],
                "attachment_url": None,
                "attachment_name": None,
                "attachment_size": None,
                "publish_at": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": (now + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "title": "SDIT Sambhram 2026: Annual Inter-College Cultural and Tech Fest Call for Volunteers",
                "body": (
                    "Shree Devi Institute of Technology cordially invites enthusiastic students across all engineering and management "
                    "departments to join the student organizing committees for our flagship annual fest: SDIT Sambhram 2026!\n\n"
                    "Open committees for student volunteers:\n"
                    "- Technical Hackathon & Robotics Arena Management\n"
                    "- Logistics, Hospitality, and Stage Coordination\n"
                    "- Public Relations, Media, and Photography Outreach\n"
                    "- Sponsorship & Industry Engagement\n\n"
                    "Interested candidates can register at the Student Affairs Desk or submit nominations to faculty coordinators."
                ),
                "category": "Cultural",
                "priority": "normal",
                "status": "published",
                "author_id": faculty_ids["faculty.vance@sdit.ac.in"],
                "attachment_url": None,
                "attachment_name": None,
                "attachment_size": None,
                "publish_at": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": (now + timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "title": "Central Library Extended Hours and IEEE Digital Xplore Access Renewal",
                "body": (
                    "The Central Library committee of Shree Devi Institute of Technology has expanded operational timings to support "
                    "students preparing for upcoming internals and capstone project submissions.\n\n"
                    "Revised Working Hours:\n"
                    "- Monday to Saturday: 8:00 AM to 10:00 PM\n"
                    "- Sunday and Gazetted Holidays: 10:00 AM to 4:00 PM\n\n"
                    "Institutional VPN credentials for off-campus IEEE Xplore, ScienceDirect, and Springer research databases "
                    "have been renewed. Check your student email for login instructions."
                ),
                "category": "Academic",
                "priority": "normal",
                "status": "published",
                "author_id": faculty_ids["faculty.wright@sdit.ac.in"],
                "attachment_url": None,
                "attachment_name": None,
                "attachment_size": None,
                "publish_at": (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": None,
            },
            {
                "title": "National Seminar on Generative AI & Autonomous Robotics - Call for Papers",
                "body": (
                    "Department of Computer Science & Engineering at Shree Devi Institute of Technology announces a two-day "
                    "National Seminar on 'Modern AI Architectures and Autonomous Robotics in Industry'. Undergraduates are encouraged "
                    "to submit technical poster presentations.\n\n"
                    "Important Dates:\n"
                    "- Abstract submission deadline: 15th of next month\n"
                    "- Acceptance notification: 22nd\n"
                    "- Registration fees waived for selected student technical presentations."
                ),
                "category": "Academic",
                "priority": "important",
                "status": "published",
                "author_id": faculty_ids["faculty.vance@sdit.ac.in"],
                "attachment_url": None,
                "attachment_name": None,
                "attachment_size": None,
                "publish_at": (now - timedelta(hours=18)).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": (now + timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "title": "Faculty Development Workshop on Outcome-Based Education (Internal Draft)",
                "body": (
                    "Draft agenda for the upcoming internal faculty development program on modern assessment methodologies "
                    "and NBA outcome-based education (OBE) metrics at Shree Devi Institute of Technology. Please review before academic senate approval."
                ),
                "category": "Administrative",
                "priority": "normal",
                "status": "draft",
                "author_id": faculty_ids["faculty.wright@sdit.ac.in"],
                "attachment_url": None,
                "attachment_name": None,
                "attachment_size": None,
                "publish_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": None,
            },
            {
                "title": "Archived: Autumn 2025 Semester Fee Payment and Course Enrollment Deadlines",
                "body": (
                    "Historical circular regarding previous semester fee payment windows and subject registration deadlines at Shree Devi Institute of Technology."
                ),
                "category": "Administrative",
                "priority": "normal",
                "status": "archived",
                "author_id": faculty_ids["faculty.wright@sdit.ac.in"],
                "attachment_url": None,
                "attachment_name": None,
                "attachment_size": None,
                "publish_at": (now - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": (now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        
        notice_ids = []
        for n in notices_data:
            cat = n["category"]
            if cat in ("Examination", "Exam"):
                cat = "Exams"
            elif cat in ("Placement",):
                cat = "Placements"
            elif cat in ("Cultural", "Event"):
                cat = "Events"
            elif cat in ("Academic",):
                cat = "Academics"
            elif cat in ("Administrative",):
                cat = "General"

            cursor.execute("""
                INSERT INTO notices (
                    title, body, category, priority, status, is_pinned, author_id,
                    attachment_url, attachment_name, attachment_size,
                    publish_at, expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                n["title"], n["body"], cat, n["priority"], n["status"], n.get("is_pinned", 0), n["author_id"],
                n["attachment_url"], n["attachment_name"], n["attachment_size"],
                n["publish_at"], n["expires_at"], n["publish_at"], n["publish_at"]
            ))
            notice_ids.append(cursor.lastrowid)
            
        # 5. Seed Realistic Student Readership Views
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[0], student_ids[0], (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[0], student_ids[1], (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[0], student_ids[2], (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[0], student_ids[4], (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")))
                       
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[1], student_ids[0], (now - timedelta(hours=22)).strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[1], student_ids[3], (now - timedelta(hours=18)).strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[1], student_ids[5], (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")))
                       
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[2], student_ids[1], (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("INSERT INTO notice_views (notice_id, student_id, first_viewed_at) VALUES (?, ?, ?)",
                       (notice_ids[2], student_ids[2], (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        
    print("\n=======================================================")
    print("SUCCESS: Database seeded for Shree Devi Institute of Technology!")
    print("=======================================================")
    print("Faculty accounts (Approved):")
    print("  - faculty.wright@sdit.ac.in / FacultyPass123! (Academic Affairs)")
    print("  - faculty.vance@sdit.ac.in  / FacultyPass123! (Computer Science)")
    print("  - faculty.chen@sdit.ac.in   / FacultyPass123! (Placement Cell)")
    print("\nStudent accounts:")
    print("  - alice.cooper@student.sdit.ac.in  / StudentPass123!")
    print("  - bob.martinez@student.sdit.ac.in  / StudentPass123!")
    print("  - carol.smith@student.sdit.ac.in   / StudentPass123!")
    print("=======================================================\n")

def main():
    parser = argparse.ArgumentParser(description="Shree Devi Institute of Technology - Notice Board CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # init-db
    subparsers.add_parser("init-db", help="Initialize SQLite tables, columns, and indexes")
    
    # seed
    subparsers.add_parser("seed", help="Seed database with realistic SDIT faculty, students, notices, and readership views")
    
    # create-faculty
    create_fac = subparsers.add_parser("create-faculty", help="Create an approved faculty administrator account")
    create_fac.add_argument("--name", required=True, help="Full name of faculty member")
    create_fac.add_argument("--email", required=True, help="Institutional email address")
    create_fac.add_argument("--password", required=True, help="Strong password (min 8 chars)")
    create_fac.add_argument("--department", required=True, help="Academic department")
    
    # approve-faculty
    approve_fac = subparsers.add_parser("approve-faculty", help="Approve and activate a pending faculty account")
    approve_fac.add_argument("--email", required=True, help="Institutional email of pending faculty member")
    
    # make-admin
    make_admin_p = subparsers.add_parser("make-admin", help="Grant administrator privileges to an existing faculty member")
    make_admin_p.add_argument("--email", required=True, help="Institutional email of faculty member")
    
    args = parser.parse_args()
    
    if args.command == "init-db":
        run_init_db()
    elif args.command == "seed":
        run_seed_data()
    elif args.command == "create-faculty":
        if len(args.password) < 8:
            print("Error: Password must be at least 8 characters long.")
            sys.exit(1)
        run_create_faculty(args.name, args.email, args.password, args.department)
    elif args.command == "approve-faculty":
        run_approve_faculty(args.email)
    elif args.command == "make-admin":
        run_make_admin(args.email)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
