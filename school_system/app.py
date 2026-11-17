
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import re
import random
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school_secret_key")

# ── Database connection ──────────────────────────────────────────────────────
mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
client = MongoClient(mongo_uri)
db_name = os.environ.get("DB_NAME", "school")
db = client[db_name]

users      = db["users"]
students   = db["students"]
teachers   = db["teachers"]
classes    = db["classes"]
attendance = db["attendance"]
results    = db["results"]
fees       = db["fees"]

# Create admin if not exists
if not users.find_one({"username": "Muhsin"}):
    users.insert_one({"username": "Muhsin", "password": "muhsin123@", "role": "admin"})


# ── Helper ───────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            flash_error("Please login first")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            flash_error("Access denied. Admin only.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") not in ["admin", "teacher"]:
            flash_error("Access denied. Teacher only.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "student":
            flash_error("Access denied. Student only.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

def generate_student_id():
    """Generate unique student ID"""
    while True:
        student_id = f"STU{random.randint(10000, 99999)}"
        if not students.find_one({"student_id": student_id}):
            return student_id

def validate_username(username):
    """Validate username format"""
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, ""

def validate_password(password):
    """Validate password strength"""
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters"
    return True, ""

def validate_email(email):
    """Validate email format"""
    if not email or not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return False, "Invalid email format"
    return True, ""

def calculate_fee_balance(fee_record):
    """Calculate balance and status for a fee record"""
    balance = fee_record.get("amount", 0) - fee_record.get("paid", 0)
    fee_record["balance"] = balance
    fee_record["status"] = "Paid" if balance <= 0 else "Pending"
    return balance

def flash_success(message):
    """Flash a success message"""
    flash(message, category="success")

def flash_error(message):
    """Flash an error message"""
    flash(message, category="error")


# ── AUTH ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    try:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            
            if not username or not password:
                flash_error("Username and password are required")
                return render_template("login.html")
            
            user = users.find_one({"username": username, "password": password})
            if user:
                if user.get("role") == "student" and not user.get("approved", False):
                    flash_error("Your account is pending approval from admin")
                    return render_template("login.html")
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["user_id"] = str(user.get("_id", ""))
                return redirect(url_for("dashboard"))
            flash_error("Invalid username or password")
        return render_template("login.html")
    except Exception as e:
        flash_error(f"An error occurred: {str(e)}")
        return render_template("login.html")

@app.route("/logout")
def logout():
    try:
        session.clear()
    except Exception as e:
        flash_error(f"Error during logout: {str(e)}")
    return redirect(url_for("login"))


# ── STUDENT REGISTRATION ───────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register_student():
    try:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            email = request.form.get("email", "").strip()
            full_name = request.form.get("full_name", "").strip()
            age = request.form.get("age", "").strip()
            grade = request.form.get("grade", "").strip()
            
            # Input validation
            valid_username, username_msg = validate_username(username)
            if not valid_username:
                flash_error(username_msg)
                return render_template("register.html")
            
            valid_password, password_msg = validate_password(password)
            if not valid_password:
                flash_error(password_msg)
                return render_template("register.html")
            
            if password != confirm_password:
                flash_error("Passwords do not match")
                return render_template("register.html")
            
            valid_email, email_msg = validate_email(email)
            if not valid_email:
                flash_error(email_msg)
                return render_template("register.html")
            
            if not full_name or len(full_name) < 2:
                flash_error("Full name is required")
                return render_template("register.html")
            
            if not age or not age.isdigit() or int(age) < 5 or int(age) > 25:
                flash_error("Please enter a valid age (5-25)")
                return render_template("register.html")
            
            if not grade:
                flash_error("Grade is required")
                return render_template("register.html")
            
            # Check if username already exists
            if users.find_one({"username": username}):
                flash_error("Username already exists")
                return render_template("register.html")
            
            # Generate unique student ID
            student_id = generate_student_id()
            
            # Create user account
            user_id = users.insert_one({
                "username": username,
                "password": password,
                "role": "student",
                "approved": False,
                "email": email,
                "full_name": full_name
            }).inserted_id
            
            # Create student record
            students.insert_one({
                "user_id": str(user_id),
                "student_id": student_id,
                "name": full_name,
                "username": username,
                "email": email,
                "age": int(age),
                "grade": grade,
                "approved": False
            })
            
            flash_success("Registration successful! Please wait for admin approval.")
            return redirect(url_for("login"))
        
        return render_template("register.html")
    except Exception as e:
        flash_error(f"Registration error: {str(e)}")
        return render_template("register.html")


# ── ADMIN APPROVAL ────────────────────────────────────────────────────────────

@app.route("/admin/approve_students")
@login_required
@admin_required
def approve_students():
    try:
        pending_students = list(students.find({"approved": False}))
        return render_template("approve_students.html", students=pending_students)
    except Exception as e:
        flash(f"Error loading pending students: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/admin/approve_student/<student_id>", methods=["POST"])
@login_required
@admin_required
def approve_student(student_id):
    try:
        student = students.find_one({"student_id": student_id})
        if student:
            students.update_one({"student_id": student_id}, {"$set": {"approved": True}})
            users.update_one({"username": student["username"]}, {"$set": {"approved": True}})
            flash_success(f"Student {student['name']} approved successfully")
        else:
            flash_error("Student not found")
    except Exception as e:
        flash_error(f"Error approving student: {str(e)}")
    return redirect(url_for("approve_students"))

@app.route("/admin/reject_student/<student_id>", methods=["POST"])
@login_required
@admin_required
def reject_student(student_id):
    try:
        student = students.find_one({"student_id": student_id})
        if student:
            students.delete_one({"student_id": student_id})
            users.delete_one({"username": student["username"]})
            flash_success(f"Student {student['name']} rejected and removed")
        else:
            flash_error("Student not found")
    except Exception as e:
        flash_error(f"Error rejecting student: {str(e)}")
    return redirect(url_for("approve_students"))


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    try:
        role = session.get("role")
        
        if role == "student":
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher_dashboard"))
        
        # Admin dashboard
        all_fees = list(fees.find())
        total_expected = sum(f.get("amount", 0) for f in all_fees)
        total_paid     = sum(f.get("paid", 0) for f in all_fees)
        pending_students = students.count_documents({"approved": False})

        return render_template("dashboard.html",
            username=session["username"],
            role=session["role"],
            student_count=students.count_documents({}),
            teacher_count=teachers.count_documents({}),
            class_count=classes.count_documents({}),
            total_expected=total_expected,
            total_paid=total_paid,
            total_balance=total_expected - total_paid,
            pending_students=pending_students
        )
    except Exception as e:
        flash_error(f"Error loading dashboard: {str(e)}")
        return redirect(url_for("login"))


# ── STUDENTS ─────────────────────────────────────────────────────────────────

@app.route("/students")
@login_required
@admin_required
def view_students():
    try:
        all_students = list(students.find())
        all_classes  = list(classes.find())
        return render_template("students.html", students=all_students, classes=all_classes, role=session["role"])
    except Exception as e:
        flash_error(f"Error loading students: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/students/add", methods=["POST"])
@login_required
@admin_required
def add_student():
    try:
        name = request.form.get("name", "").strip()
        grade = request.form.get("grade", "").strip()
        age = request.form.get("age", "").strip()
        class_name = request.form.get("class", "").strip()
        
        if not name or not grade or not age:
            flash_error("Name, grade, and age are required")
            return redirect(url_for("view_students"))
        
        if not age.isdigit() or int(age) < 5 or int(age) > 25:
            flash_error("Please enter a valid age (5-25)")
            return redirect(url_for("view_students"))
        
        students.insert_one({
            "name":  name,
            "grade": grade,
            "age":   int(age),
            "class": class_name,
            "approved": True
        })
        flash_success("Student added successfully")
    except Exception as e:
        flash_error(f"Error adding student: {str(e)}")
    return redirect(url_for("view_students"))

@app.route("/students/delete/<id>")
@login_required
@admin_required
def delete_student(id):
    try:
        students.delete_one({"_id": ObjectId(id)})
        flash_success("Student deleted successfully")
    except Exception as e:
        flash_error(f"Error deleting student: {str(e)}")
    return redirect(url_for("view_students"))


# ── TEACHERS ─────────────────────────────────────────────────────────────────

@app.route("/teachers")
@login_required
@admin_required
def view_teachers():
    try:
        all_teachers = list(teachers.find())
        return render_template("teachers.html", teachers=all_teachers, role=session["role"])
    except Exception as e:
        flash_error(f"Error loading teachers: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/teachers/add", methods=["POST"])
@login_required
@admin_required
def add_teacher():
    try:
        name = request.form.get("name", "").strip()
        subject = request.form.get("subject", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not name or not subject or not username or not password:
            flash_error("Name, subject, username, and password are required")
            return redirect(url_for("view_teachers"))
        
        valid_username, username_msg = validate_username(username)
        if not valid_username:
            flash_error(username_msg)
            return redirect(url_for("view_teachers"))
        
        valid_password, password_msg = validate_password(password)
        if not valid_password:
            flash_error(password_msg)
            return redirect(url_for("view_teachers"))
        
        if users.find_one({"username": username}):
            flash_error("Username already exists")
            return redirect(url_for("view_teachers"))
        
        # Create user account for teacher
        user_id = users.insert_one({
            "username": username,
            "password": password,
            "role": "teacher",
            "approved": True,
            "full_name": name
        }).inserted_id
        
        # Create teacher record
        teachers.insert_one({
            "user_id": str(user_id),
            "name": name,
            "username": username,
            "subject": subject
        })
        flash_success("Teacher added successfully")
    except Exception as e:
        flash_error(f"Error adding teacher: {str(e)}")
    return redirect(url_for("view_teachers"))

@app.route("/teachers/delete/<id>")
@login_required
@admin_required
def delete_teacher(id):
    try:
        teacher = teachers.find_one({"_id": ObjectId(id)})
        if teacher:
            teachers.delete_one({"_id": ObjectId(id)})
            if teacher.get("username"):
                users.delete_one({"username": teacher["username"]})
            flash_success("Teacher deleted successfully")
        else:
            flash_error("Teacher not found")
    except Exception as e:
        flash_error(f"Error deleting teacher: {str(e)}")
    return redirect(url_for("view_teachers"))


# ── CLASSES & SUBJECTS ───────────────────────────────────────────────────────

@app.route("/classes")
@login_required
@admin_required
def view_classes():
    try:
        all_classes = list(classes.find())
        return render_template("classes.html", classes=all_classes, role=session["role"])
    except Exception as e:
        flash_error(f"Error loading classes: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/classes/add", methods=["POST"])
@login_required
@admin_required
def add_class():
    try:
        name = request.form.get("name", "").strip()
        if not name:
            flash_error("Class name is required")
            return redirect(url_for("view_classes"))
        classes.insert_one({"name": name})
        flash_success("Class added successfully")
    except Exception as e:
        flash_error(f"Error adding class: {str(e)}")
    return redirect(url_for("view_classes"))

@app.route("/classes/delete/<id>")
@login_required
@admin_required
def delete_class(id):
    try:
        classes.delete_one({"_id": ObjectId(id)})
        flash_success("Class deleted successfully")
    except Exception as e:
        flash_error(f"Error deleting class: {str(e)}")
    return redirect(url_for("view_classes"))


# ── ATTENDANCE ────────────────────────────────────────────────────────────────

@app.route("/attendance")
@login_required
def view_attendance():
    try:
        role = session.get("role")
        all_students  = list(students.find())
        all_attendance = list(attendance.find())
        teacher_subject = ""
        
        if role == "teacher":
            teacher = teachers.find_one({"username": session["username"]})
            if teacher:
                teacher_subject = teacher.get("subject", "")
                all_attendance = [a for a in all_attendance if a.get("subject") == teacher_subject]
        
        return render_template("attendance.html", students=all_students, attendance=all_attendance, role=role, teacher_subject=teacher_subject)
    except Exception as e:
        flash_error(f"Error loading attendance: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/attendance/add", methods=["POST"])
@login_required
@teacher_required
def add_attendance():
    try:
        student_id = request.form.get("student_id", "").strip()
        student_name = request.form.get("student_name", "").strip()
        date = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip()
        subject = request.form.get("subject", "").strip()
        
        if not student_id or not student_name or not date or not status or not subject:
            flash_error("All fields are required")
            return redirect(url_for("view_attendance"))
        
        attendance.insert_one({
            "student_id":   student_id,
            "student_name": student_name,
            "date":         date,
            "status":       status,
            "subject":      subject
        })
        flash_success("Attendance recorded successfully")
    except Exception as e:
        flash_error(f"Error adding attendance: {str(e)}")
    return redirect(url_for("view_attendance"))

@app.route("/attendance/delete/<id>")
@login_required
@admin_required
def delete_attendance(id):
    try:
        attendance.delete_one({"_id": ObjectId(id)})
        flash_success("Attendance record deleted successfully")
    except Exception as e:
        flash_error(f"Error deleting attendance: {str(e)}")
    return redirect(url_for("view_attendance"))


# ── RESULTS & GRADES ─────────────────────────────────────────────────────────

def get_grade(score):
    score = float(score)
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    if score >= 50: return "D"
    return "F"

@app.route("/results")
@login_required
def view_results():
    try:
        role = session.get("role")
        all_students = list(students.find())
        all_results  = list(results.find())
        
        if role == "student":
            # Students can only see their own results
            student = students.find_one({"username": session["username"]})
            if student:
                all_results = [r for r in all_results if r.get("student_name") == student["name"]]
            else:
                all_results = []
        elif role == "teacher":
            # Teachers can only see results for their subject
            teacher = teachers.find_one({"username": session["username"]})
            if teacher:
                teacher_subject = teacher.get("subject", "")
                all_results = [r for r in all_results if r.get("subject") == teacher_subject]
            else:
                all_results = []
        
        return render_template("results.html", students=all_students, results=all_results, role=role)
    except Exception as e:
        flash_error(f"Error loading results: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/results/add", methods=["POST"])
@login_required
@teacher_required
def add_result():
    try:
        student_name = request.form.get("student_name", "").strip()
        subject = request.form.get("subject", "").strip()
        score = request.form.get("score", "").strip()
        term = request.form.get("term", "").strip()
        
        if not student_name or not subject or not score or not term:
            flash_error("All fields are required")
            return redirect(url_for("view_results"))
        
        try:
            score_float = float(score)
            if score_float < 0 or score_float > 100:
                flash_error("Score must be between 0 and 100")
                return redirect(url_for("view_results"))
        except ValueError:
            flash_error("Invalid score format")
            return redirect(url_for("view_results"))
        
        results.insert_one({
            "student_name": student_name,
            "subject":      subject,
            "score":        score_float,
            "grade":        get_grade(score_float),
            "term":         term
        })
        flash_success("Result added successfully")
    except Exception as e:
        flash_error(f"Error adding result: {str(e)}")
    return redirect(url_for("view_results"))

@app.route("/results/delete/<id>")
@login_required
@teacher_required
def delete_result(id):
    try:
        results.delete_one({"_id": ObjectId(id)})
        flash_success("Result deleted successfully")
    except Exception as e:
        flash_error(f"Error deleting result: {str(e)}")
    return redirect(url_for("view_results"))


# ── FEES ─────────────────────────────────────────────────────────────────────

@app.route("/fees")
@login_required
def view_fees():
    try:
        role = session.get("role")
        all_students = list(students.find())
        all_fees     = list(fees.find())
        
        if role == "student":
            # Students can only see their own fees
            student = students.find_one({"username": session["username"]})
            if student:
                all_fees = [f for f in all_fees if f.get("student_name") == student["name"]]
            else:
                all_fees = []
        
        # compute balance for each fee record
        for f in all_fees:
            calculate_fee_balance(f)
        return render_template("fees.html", students=all_students, fees=all_fees, role=role)
    except Exception as e:
        flash_error(f"Error loading fees: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/fees/add", methods=["POST"])
@login_required
@admin_required
def add_fee():
    try:
        student_name = request.form.get("student_name", "").strip()
        term = request.form.get("term", "").strip()
        amount = request.form.get("amount", "").strip()
        paid = request.form.get("paid", "0").strip()
        
        if not student_name or not term or not amount:
            flash_error("Student name, term, and amount are required")
            return redirect(url_for("view_fees"))
        
        try:
            amount_float = float(amount)
            paid_float = float(paid) if paid else 0
            if amount_float < 0 or paid_float < 0:
                flash_error("Amount and paid values must be positive")
                return redirect(url_for("view_fees"))
        except ValueError:
            flash_error("Invalid amount format")
            return redirect(url_for("view_fees"))
        
        fees.insert_one({
            "student_name": student_name,
            "term":         term,
            "amount":       amount_float,
            "paid":         paid_float,
            "balance":      amount_float - paid_float
        })
        flash_success("Fee record added successfully")
    except Exception as e:
        flash_error(f"Error adding fee: {str(e)}")
    return redirect(url_for("view_fees"))

@app.route("/fees/delete/<id>")
@login_required
@admin_required
def delete_fee(id):
    try:
        fees.delete_one({"_id": ObjectId(id)})
        flash_success("Fee record deleted successfully")
    except Exception as e:
        flash_error(f"Error deleting fee: {str(e)}")
    return redirect(url_for("view_fees"))


# ── REPORTS ───────────────────────────────────────────────────────────────────

@app.route("/reports")
@login_required
def view_reports():
    try:
        role = session.get("role")
        if role != "admin":
            flash_error("Access denied")
            return redirect(url_for("dashboard"))

        all_students   = list(students.find())
        all_results    = list(results.find())
        all_attendance = list(attendance.find())
        all_fees_data  = list(fees.find())

        # attendance summary per student
        att_summary = {}
        for a in all_attendance:
            name = a["student_name"]
            if name not in att_summary:
                att_summary[name] = {"present": 0, "absent": 0}
            if a["status"] == "Present":
                att_summary[name]["present"] += 1
            else:
                att_summary[name]["absent"] += 1

        # fees summary
        total_expected = sum(f.get("amount", 0) for f in all_fees_data)
        total_paid     = sum(f.get("paid", 0) for f in all_fees_data)

        return render_template("reports.html",
            role=role,
            student_count=len(all_students),
            result_count=len(all_results),
            att_summary=att_summary,
            all_results=all_results,
            total_expected=total_expected,
            total_paid=total_paid,
            total_balance=total_expected - total_paid
        )
    except Exception as e:
        flash_error(f"Error loading reports: {str(e)}")
        return redirect(url_for("dashboard"))


# ── USERS ─────────────────────────────────────────────────────────────────────

@app.route("/users")
@login_required
@admin_required
def view_users():
    try:
        all_users = list(users.find())
        return render_template("users.html", users=all_users, role=session["role"])
    except Exception as e:
        flash_error(f"Error loading users: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/users/add", methods=["POST"])
@login_required
@admin_required
def add_user():
    try:
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip()
        
        valid_username, username_msg = validate_username(username)
        if not valid_username:
            flash_error(username_msg)
            return redirect(url_for("view_users"))
        
        valid_password, password_msg = validate_password(password)
        if not valid_password:
            flash_error(password_msg)
            return redirect(url_for("view_users"))
        
        if role not in ["admin", "teacher", "student"]:
            flash_error("Invalid role")
            return redirect(url_for("view_users"))
        
        if users.find_one({"username": username}):
            flash_error("Username already exists")
            return redirect(url_for("view_users"))
        
        users.insert_one({
            "username": username,
            "password": password,
            "role":     role,
            "approved": True if role != "student" else False
        })
        flash_success("User added successfully")
    except Exception as e:
        flash_error(f"Error adding user: {str(e)}")
    return redirect(url_for("view_users"))

@app.route("/users/delete/<id>")
@login_required
@admin_required
def delete_user(id):
    try:
        users.delete_one({"_id": ObjectId(id)})
        flash_success("User deleted successfully")
    except Exception as e:
        flash_error(f"Error deleting user: {str(e)}")
    return redirect(url_for("view_users"))


# ── STUDENT DASHBOARD ───────────────────────────────────────────────────────────

@app.route("/student/dashboard")
@login_required
@student_required
def student_dashboard():
    try:
        student = students.find_one({"username": session["username"]})
        if not student:
            flash_error("Student record not found")
            return redirect(url_for("logout"))
        
        # Get student's results
        my_results = list(results.find({"student_name": student["name"]}))
        
        # Group results by term
        terms = sorted(set(r.get("term", "") for r in my_results))
        
        # Get student's attendance
        my_attendance = list(attendance.find({"student_name": student["name"]}))
        
        # Get student's fees
        my_fees = list(fees.find({"student_name": student["name"]}))
        total_balance = 0
        for f in my_fees:
            total_balance += calculate_fee_balance(f)
        
        return render_template("student_dashboard.html",
            student=student,
            results=my_results,
            terms=terms,
            attendance=my_attendance,
            fees=my_fees,
            total_balance=round(total_balance, 2)
        )
    except Exception as e:
        flash_error(f"Error loading student dashboard: {str(e)}")
        return redirect(url_for("dashboard"))


# ── TEACHER DASHBOARD ───────────────────────────────────────────────────────────

@app.route("/teacher/dashboard")
@login_required
@teacher_required
def teacher_dashboard():
    try:
        teacher = teachers.find_one({"username": session["username"]})
        if not teacher:
            flash_error("Teacher record not found")
            return redirect(url_for("logout"))
        
        teacher_subject = teacher.get("subject", "")
        
        # Get all approved students
        all_students = list(students.find({"approved": True}))
        
        # Filter results to only show this teacher's subject
        all_results = list(results.find({"subject": teacher_subject}))
        
        # Filter attendance to only show this teacher's subject (if attendance has subject field)
        all_attendance = list(attendance.find({"subject": teacher_subject}))
        
        all_classes = list(classes.find())
        
        return render_template("teacher_dashboard.html",
            teacher=teacher,
            teacher_subject=teacher_subject,
            students=all_students,
            results=all_results,
            attendance=all_attendance,
            classes=all_classes
        )
    except Exception as e:
        flash_error(f"Error loading teacher dashboard: {str(e)}")
        return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
