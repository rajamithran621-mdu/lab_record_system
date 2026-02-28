"""
Digital Lab Record Entry Management System
==========================================
A Flask-based web application to manage student lab entries.

Admin Credentials:
    Username: admin
    Password: admin123

Run Instructions:
    1. pip install flask
    2. python app.py
    3. Open http://127.0.0.1:5000 in your browser
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from datetime import datetime, date
import sqlite3
import csv
import io
import os

# ─── App Configuration ────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "labrecord_secret_key_2024"  # Change in production

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
DATABASE = "database.db"

# ─── Database Helpers ─────────────────────────────────────────────────────────

def get_db():
    """Open a new database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


def init_db():
    """Create tables if they don't already exist."""
    conn = get_db()
    cursor = conn.cursor()

    # Students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT    NOT NULL,
            reg_no  TEXT    NOT NULL UNIQUE,
            dept    TEXT    NOT NULL
        )
    """)

    # Entries table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL,
            lab_name    TEXT    NOT NULL DEFAULT 'Computer Lab',
            system_no   TEXT,
            time_in     TEXT    NOT NULL,
            time_out    TEXT,
            date        TEXT    NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    # Add system_no column to existing databases (safe migration)
    try:
        cursor.execute("ALTER TABLE entries ADD COLUMN system_no TEXT")
    except Exception:
        pass  # Column already exists — ignore

    conn.commit()
    conn.close()


# ─── Auth Helpers ─────────────────────────────────────────────────────────────

def is_logged_in():
    """Check if admin session is active."""
    return session.get("admin_logged_in") is True


def login_required(f):
    """Decorator to protect admin routes."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please login to access the admin panel.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ─── Public Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Landing page — student entry form."""
    return render_template("index.html")


@app.route("/entry", methods=["POST"])
def student_entry():
    """
    Handle student check-in.
    - If student not inside → mark Time In.
    - If already inside → show warning.
    """
    reg_no    = request.form.get("reg_no", "").strip().upper()
    system_no = request.form.get("system_no", "").strip()
    if not reg_no:
        flash("Please enter a Register Number.", "danger")
        return redirect(url_for("index"))
    if not system_no:
        flash("Please enter a System Number.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    # Look up the student
    student = conn.execute(
        "SELECT * FROM students WHERE reg_no = ?", (reg_no,)
    ).fetchone()

    if not student:
        conn.close()
        flash(f"Register Number '{reg_no}' not found. Please contact admin.", "danger")
        return redirect(url_for("index"))

    # Check if that system is already occupied today
    today = date.today().isoformat()
    sys_busy = conn.execute(
        """SELECT e.id, s.name FROM entries e
           JOIN students s ON e.student_id = s.id
           WHERE e.system_no = ? AND e.date = ? AND e.time_out IS NULL""",
        (system_no, today)
    ).fetchone()

    if sys_busy:
        conn.close()
        flash(f"⚠️ System {system_no} is already occupied by {sys_busy['name']}. Please choose another system.", "warning")
        return redirect(url_for("index"))

    # Check for an open entry (no time_out) for today
    open_entry = conn.execute(
        """SELECT * FROM entries
           WHERE student_id = ? AND date = ? AND time_out IS NULL""",
        (student["id"], today)
    ).fetchone()

    if open_entry:
        conn.close()
        flash(f"⚠️ {student['name']} is already inside the lab on System {open_entry['system_no']}!", "warning")
        return redirect(url_for("index"))

    # Mark Time In with system number
    now = datetime.now().strftime("%H:%M:%S")
    conn.execute(
        "INSERT INTO entries (student_id, lab_name, system_no, time_in, date) VALUES (?, ?, ?, ?, ?)",
        (student["id"], "Computer Lab", system_no, now, today)
    )
    conn.commit()
    conn.close()

    flash(f"✅ Welcome, {student['name']}! Assigned to System {system_no}. Time In: {now}.", "success")
    return redirect(url_for("index"))


@app.route("/exit", methods=["POST"])
def student_exit():
    """
    Handle student check-out.
    Finds the open entry for today and sets time_out.
    """
    reg_no = request.form.get("reg_no", "").strip().upper()
    if not reg_no:
        flash("Please enter a Register Number.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    student = conn.execute(
        "SELECT * FROM students WHERE reg_no = ?", (reg_no,)
    ).fetchone()

    if not student:
        conn.close()
        flash(f"Register Number '{reg_no}' not found.", "danger")
        return redirect(url_for("index"))

    today = date.today().isoformat()
    open_entry = conn.execute(
        """SELECT * FROM entries
           WHERE student_id = ? AND date = ? AND time_out IS NULL""",
        (student["id"], today)
    ).fetchone()

    if not open_entry:
        conn.close()
        flash(f"No open entry found for {student['name']} today. Please check in first.", "info")
        return redirect(url_for("index"))

    now = datetime.now().strftime("%H:%M:%S")
    conn.execute(
        "UPDATE entries SET time_out = ? WHERE id = ?",
        (now, open_entry["id"])
    )
    conn.commit()
    conn.close()

    flash(f"👋 Goodbye, {student['name']}! Time Out recorded at {now}.", "success")
    return redirect(url_for("index"))


# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin login page."""
    if is_logged_in():
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Welcome back, Admin!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials. Please try again.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Clear admin session."""
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    """
    Admin dashboard with:
    - Total entries today
    - Students currently inside
    - Total registered students
    """
    conn = get_db()
    today = date.today().isoformat()

    total_today = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE date = ?", (today,)
    ).fetchone()[0]

    inside_now = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE date = ? AND time_out IS NULL", (today,)
    ).fetchone()[0]

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    # Latest 10 entries for quick view
    recent_entries = conn.execute("""
        SELECT e.id, s.name, s.reg_no, s.dept,
               e.lab_name, e.system_no, e.time_in, e.time_out, e.date
        FROM entries e
        JOIN students s ON e.student_id = s.id
        WHERE e.date = ?
        ORDER BY e.id DESC
        LIMIT 10
    """, (today,)).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_today=total_today,
        inside_now=inside_now,
        total_students=total_students,
        recent_entries=recent_entries,
        today=today
    )


@app.route("/admin/entries")
@login_required
def admin_entries():
    """View all entries with optional date filter."""
    filter_date = request.args.get("filter_date", "")
    conn = get_db()

    if filter_date:
        entries = conn.execute("""
            SELECT e.id, s.name, s.reg_no, s.dept,
                   e.lab_name, e.system_no, e.time_in, e.time_out, e.date
            FROM entries e
            JOIN students s ON e.student_id = s.id
            WHERE e.date = ?
            ORDER BY e.id DESC
        """, (filter_date,)).fetchall()
    else:
        entries = conn.execute("""
            SELECT e.id, s.name, s.reg_no, s.dept,
                   e.lab_name, e.system_no, e.time_in, e.time_out, e.date
            FROM entries e
            JOIN students s ON e.student_id = s.id
            ORDER BY e.id DESC
            LIMIT 200
        """).fetchall()

    conn.close()
    return render_template("admin_entries.html", entries=entries, filter_date=filter_date)


@app.route("/admin/students")
@login_required
def admin_students():
    """View all registered students."""
    conn = get_db()
    students = conn.execute(
        "SELECT * FROM students ORDER BY name"
    ).fetchall()
    conn.close()
    return render_template("admin_students.html", students=students)


@app.route("/admin/students/add", methods=["POST"])
@login_required
def admin_add_student():
    """Add a new student to the database."""
    name   = request.form.get("name", "").strip()
    reg_no = request.form.get("reg_no", "").strip().upper()
    dept   = request.form.get("dept", "").strip()

    if not all([name, reg_no, dept]):
        flash("All fields are required.", "danger")
        return redirect(url_for("admin_students"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO students (name, reg_no, dept) VALUES (?, ?, ?)",
            (name, reg_no, dept)
        )
        conn.commit()
        flash(f"Student '{name}' added successfully.", "success")
    except sqlite3.IntegrityError:
        flash(f"Register Number '{reg_no}' already exists.", "danger")
    finally:
        conn.close()

    return redirect(url_for("admin_students"))


@app.route("/admin/students/delete/<int:student_id>", methods=["POST"])
@login_required
def admin_delete_student(student_id):
    """Delete a student (and their entries via cascade logic)."""
    conn = get_db()
    student = conn.execute(
        "SELECT name FROM students WHERE id = ?", (student_id,)
    ).fetchone()

    if student:
        # Also delete all entries for this student
        conn.execute("DELETE FROM entries WHERE student_id = ?", (student_id,))
        conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()
        flash(f"Student '{student['name']}' deleted.", "success")
    else:
        flash("Student not found.", "danger")

    conn.close()
    return redirect(url_for("admin_students"))


@app.route("/admin/export")
@login_required
def admin_export():
    """Export all entries to a CSV file."""
    filter_date = request.args.get("filter_date", "")
    conn = get_db()

    if filter_date:
        rows = conn.execute("""
            SELECT s.name, s.reg_no, s.dept, e.lab_name, e.system_no, e.time_in, e.time_out, e.date
            FROM entries e JOIN students s ON e.student_id = s.id
            WHERE e.date = ?
            ORDER BY e.id DESC
        """, (filter_date,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT s.name, s.reg_no, s.dept, e.lab_name, e.system_no, e.time_in, e.time_out, e.date
            FROM entries e JOIN students s ON e.student_id = s.id
            ORDER BY e.id DESC
        """).fetchall()

    conn.close()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Reg No", "Department", "Lab", "System No", "Time In", "Time Out", "Date"])
    for row in rows:
        writer.writerow(list(row))

    output.seek(0)
    filename = f"lab_entries_{filter_date or 'all'}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Initialize the database on first run
    init_db()
    print("=" * 55)
    print("  Digital Lab Record Entry Management System")
    print("=" * 55)
    print("  URL      : http://127.0.0.1:5000")
    print("  Admin    : http://127.0.0.1:5000/admin/login")
    print("  Username : admin")
    print("  Password : admin123")
    print("=" * 55)
    app.run(debug=True)
