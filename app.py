from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
import sqlite3
import hashlib
import random
import os
import json
import time
from datetime import datetime
from functools import wraps
import threading
import pyotp

# Create the Flask app and configure it
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a secure secret key
app.config['otp_secrets'] = {}

# Ensure Jinja2 environment is initialized and filter is registered in the app context
with app.app_context():
    # Safe JSON parsing function for Jinja2 filter
    def safe_json_parse(data):
        if not data or data == 'null':
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}

    # Register the json_parse filter in the Jinja2 environment (place this at the top, before any routes or functions)
    app.jinja_env.filters['json_parse'] = safe_json_parse
    app.logger.debug("JSON parse filter registered: %s", app.jinja_env.filters.get('json_parse'))

# Thread-local SQLite connection
_local = threading.local()

def get_db():
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect('school.db', check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

def get_cursor():
    return get_db().cursor()

# Decorator to ensure database connection is closed after each request
def with_db(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = get_db()
        cursor = get_cursor()
        try:
            return f(cursor, *args, **kwargs)
        finally:
            cursor.close()
            # Do not close the connection here to keep it thread-local; it will be closed at app shutdown
    return decorated_function

# ... (rest of your app.py code starting from create_tables on line 49)

# ... (rest of your app.py code starting from create_tables on line 49)



# Create tables function to accept cursor or handle None for startup
def create_tables(cursor=None):
    conn = None
    try:
        if cursor is None:
            # Create a temporary connection for startup (not thread-local)
            conn = sqlite3.connect('school.db', check_same_thread=False)
            cursor = conn.cursor()
        
        # Create tables (including new educational_achievements table)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                password TEXT,
                subject TEXT,
                phone_number TEXT DEFAULT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                password TEXT,
                profile_data TEXT,
                profile_image TEXT DEFAULT 'default.jpg',
                class_timetable TEXT DEFAULT '10B.jpg'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resource_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_email TEXT,
                student_id INTEGER,
                subject TEXT,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_email) REFERENCES teachers(email),
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                subject TEXT,
                teacher_email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                max_marks INTEGER DEFAULT 20,
                FOREIGN KEY (teacher_email) REFERENCES teachers(email)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER,
                student_id INTEGER,
                marks INTEGER,
                remarks TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_id) REFERENCES tests(id),
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                class_name TEXT,
                date TEXT,
                status TEXT CHECK(status IN ('Present', 'Absent')),
                teacher_email TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (teacher_email) REFERENCES teachers(email)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS extracurricular_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                teacher_name TEXT,
                achievement TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS educational_achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                teacher_name TEXT,
                achievement TEXT,
                subject TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS holidays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                description TEXT
            )
        ''')
        if conn:
            conn.commit()
    except sqlite3.Error as e:
        app.logger.error(f"Database error creating tables: {str(e)}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor and not conn:  # If using provided cursor, let the caller handle commit
            get_db().commit()
        if conn:
            cursor.close()
            conn.close()

# Run table creation on app startup
create_tables(None)

def generate_and_display_otp(phone_number):
    if 'otp_secrets' not in app.config:
        app.config['otp_secrets'] = {}
    
    # Check if OTP exists and is still valid (within 120 seconds)
    if phone_number in app.config['otp_secrets']:
        timestamp = app.config['otp_secrets'][phone_number]['timestamp']
        if (time.time() - timestamp) <= 120:  # OTP valid for 120 seconds
            secret = app.config['otp_secrets'][phone_number]['secret']
            otp = pyotp.TOTP(secret).now()
            app.logger.info(f"Reusing OTP for phone number {phone_number}: {otp} (Valid for remaining {120 - (time.time() - timestamp):.0f} seconds)")
            return otp, secret
        else:
            # OTP expired, remove it from config so user must log in again
            del app.config['otp_secrets'][phone_number]
            app.logger.warning(f"OTP expired for {phone_number}, user must log in again")

    # Generate a new OTP if none exists or expired, ensuring no zeros
    while True:
        secret = pyotp.random_base32()  # Generate a TOTP secret
        totp = pyotp.TOTP(secret)
        otp = totp.now()
        # Check if OTP has any zeros (convert to string and ensure no '0')
        if '0' not in otp:
            break

    app.config['otp_secrets'][phone_number] = {'secret': secret, 'timestamp': time.time()}
    app.logger.info(f"Generated OTP for {phone_number}: {otp} (valid for 120 seconds, no zeros)")
    return otp, secret  # Return OTP and secret for validation

    # Generate a new OTP if none exists or expired, ensuring no zeros
    while True:
        secret = pyotp.random_base32()  # Generate a TOTP secret
        totp = pyotp.TOTP(secret)
        otp = totp.now()
        # Check if OTP has any zeros (convert to string and ensure no '0')
        if '0' not in otp:
            break

    app.config['otp_secrets'][phone_number] = {'secret': secret, 'timestamp': time.time()}
    app.logger.info(f"Generated OTP for {phone_number}: {otp} (valid for 120 seconds, no zeros)")
    return otp, secret  # Return OTP and secret for validation

@with_db
def update_teacher_count(cursor):
    count = cursor.execute('SELECT COUNT(*) FROM teachers').fetchone()[0]
    app.logger.info(f"Total Teachers: {count}")

@with_db
def update_student_count(cursor):
    count = cursor.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    app.logger.info(f"Total Students: {count}")

@with_db
def create_teacher(cursor, name, email, password, subject, phone_number=None):
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    # Check teacher limit (exactly 6 now, including Nikhil)
    if cursor.execute('SELECT COUNT(*) FROM teachers').fetchone()[0] >= 6:
        flash("Maximum teacher limit (6) reached", "error")
        return False, "Maximum teacher limit (6) reached"
    # Check for duplicate subjects (except for PE teacher Nikhil)
    if subject != "PE" and cursor.execute('SELECT 1 FROM teachers WHERE subject = ? AND subject != "PE"', (subject,)).fetchone():
        flash("Subject already assigned to another teacher", "error")
        return False, "Subject already assigned to another teacher"
    try:
        cursor.execute('INSERT INTO teachers (name, email, password, subject, phone_number) VALUES (?, ?, ?, ?, ?)',
                       (name, email, hashed_password, subject, phone_number))
        get_db().commit()
        update_teacher_count(None)
        flash("Teacher created successfully", "success")
        return True, "Teacher created"
    except sqlite3.IntegrityError:
        flash("Email already exists", "error")
        return False, "Email already exists"

@with_db
def create_student(cursor, name, email, password, phone_number, profile_data, class_timetable="10B.jpg"):
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    # Validate phone number (10 digits, integers only)
    if not (phone_number.isdigit() and len(phone_number) == 10):
        flash("Phone number must be exactly 10 digits (integers only)", "error")
        return False, "Phone number must be exactly 10 digits (integers only)"
    
    try:
        # Parse the profile_data if it's a string, or use empty dict if parsing fails
        if isinstance(profile_data, str):
            try:
                profile_data_dict = json.loads(profile_data)
            except json.JSONDecodeError:
                profile_data_dict = {}
        else:
            profile_data_dict = profile_data

        # Ensure profile_data_dict is a dictionary
        if not isinstance(profile_data_dict, dict):
            profile_data_dict = {}

        # Add or update phone_number in profile_data
        profile_data_dict['phone_number'] = phone_number
        
        # Initialize other required fields if they don't exist
        if 'notifications' not in profile_data_dict:
            profile_data_dict['notifications'] = []
        if 'messages' not in profile_data_dict:
            profile_data_dict['messages'] = []

        cursor.execute('''
            INSERT INTO students (name, email, password, profile_data, profile_image, class_timetable) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, email, hashed_password, json.dumps(profile_data_dict), 'default.jpg', class_timetable))
        
        get_db().commit()
        update_student_count(None)
        flash("Student created successfully", "success")
        return True, "Student created"
    except sqlite3.IntegrityError:
        flash("Email already exists", "error")
        return False, "Email already exists"
    except Exception as e:
        flash(f"Error creating student: {str(e)}", "error")
        return False, f"Error creating student: {str(e)}"

@with_db
def remove_teacher(cursor, teacher_id):
    # Check if removing would leave fewer than 6 teachers
    if cursor.execute('SELECT COUNT(*) FROM teachers').fetchone()[0] <= 6:
        teacher = cursor.execute('SELECT name, email, password, subject, phone_number FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
        if teacher:
            try:
                cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
                get_db().commit()
                update_teacher_count(None)
                if teacher[3] != "PE":  # Don't replace PE teacher Nikhil
                    new_email = f"new_{teacher[1].split('@')[0]}@cambridge.edu.in"
                    new_password = f"new{teacher[2][3:]}123"
                    new_subject = f"New_{teacher[3]}"
                    while cursor.execute('SELECT 1 FROM teachers WHERE subject = ? AND subject != "PE"', (new_subject,)).fetchone():
                        new_subject += "_1"
                    create_teacher(None, "New Teacher", new_email, new_password, new_subject, phone_number=teacher[4])
                flash("Teacher removed and replaced (if applicable)", "success")
                return True, "Teacher removed and replaced (if applicable)"
            except sqlite3.Error as e:
                flash(f"Error removing teacher: {str(e)}", "error")
                return False, f"Error removing teacher: {str(e)}"
    flash("Cannot remove teacher (limit of 6 must be maintained)", "error")
    return False, "Cannot remove teacher (limit of 6 must be maintained)"

@with_db
def remove_student(cursor, student_id):
    try:
        cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
        get_db().commit()
        update_student_count(None)
        flash("Student removed successfully", "success")
        return True, "Student removed"
    except sqlite3.Error as e:
        flash(f"Error removing student: {str(e)}", "error")
        return False, f"Error removing student: {str(e)}"

@with_db
def log_resource_change(cursor, teacher_email, student_id, subject, action, details):
    try:
        cursor.execute('INSERT INTO resource_logs (teacher_email, student_id, subject, action, details) VALUES (?, ?, ?, ?, ?)',
                       (teacher_email, student_id, subject, action, details))
        get_db().commit()
    except sqlite3.Error as e:
        app.logger.error(f"Error logging resource change: {e}")

@with_db
def create_test(cursor, teacher_email, test_name, subject, max_marks=20):
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject or subject not in ["Java", "Math", "Python", "DSA", "Communication", "PE"]:
        flash("Cannot create test for invalid or unauthorized subject", "error")
        return False, "Cannot create test for invalid or unauthorized subject"
    if subject != teacher_subject and subject != "PE":
        flash("Cannot create test for other subjects", "error")
        return False, "Cannot create test for other subjects"
    try:
        cursor.execute('INSERT INTO tests (name, subject, teacher_email, max_marks) VALUES (?, ?, ?, ?)',
                       (test_name, subject, teacher_email, max_marks))
        get_db().commit()
        flash("Test created successfully", "success")
        return True, "Test created"
    except sqlite3.Error as e:
        flash(f"Error creating test: {str(e)}", "error")
        return False, f"Error creating test: {str(e)}"

@with_db
def update_test_results(cursor, teacher_email, test_name, student_id, marks, remarks):
    # Validate marks (0-100, but allow customization based on max_marks)
    try:
        marks = int(marks)
        test = cursor.execute('SELECT id, max_marks FROM tests WHERE name = ? AND teacher_email = ?', (test_name, teacher_email)).fetchone()
        if not test:
            flash("Test not found", "error")
            return False, "Test not found"
        test_id, max_marks = test
        if not (0 <= marks <= max_marks):
            flash(f"Marks must be between 0 and {max_marks}", "error")
            return False, f"Marks must be between 0 and {max_marks}"
    except ValueError:
        flash("Marks must be a valid integer", "error")
        return False, "Marks must be a valid integer"
    
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject or cursor.execute('SELECT subject FROM tests WHERE id = ?', (test_id,)).fetchone()[0] not in ["Java", "Math", "Python", "DSA", "Communication", "PE"]:
        flash("Cannot update results for invalid or unauthorized subject", "error")
        return False, "Cannot update results for invalid or unauthorized subject"
    if cursor.execute('SELECT subject FROM tests WHERE id = ?', (test_id,)).fetchone()[0] != teacher_subject and cursor.execute('SELECT subject FROM tests WHERE id = ?', (test_id,)).fetchone()[0] != "PE":
        flash("Cannot update results for other subjects", "error")
        return False, "Cannot update results for other subjects"
    try:
        cursor.execute('INSERT INTO test_results (test_id, student_id, marks, remarks) VALUES (?, ?, ?, ?)',
                       (test_id, student_id, marks, remarks))
        get_db().commit()
        log_resource_change(None, teacher_email, student_id, cursor.execute('SELECT subject FROM tests WHERE id = ?', (test_id,)).fetchone()[0], "Updated Test Results", f"Test: {test_name}, Marks: {marks}, Remarks: '{remarks}'")
        flash("Test results updated successfully", "success")
        return True, "Test results updated"
    except sqlite3.Error as e:
        flash(f"Error updating test results: {str(e)}", "error")
        return False, f"Error updating test results: {str(e)}"

@with_db
def update_attendance(cursor, teacher_email, class_name, date, student_statuses):
    current_date = datetime.now().strftime('%Y-%m-%d')
    if date != current_date:
        flash("Date must be today's date only", "error")
        return False, "Date must be today's date only"
    try:
        for student_id, status in student_statuses.items():
            student = cursor.execute('SELECT profile_data FROM students WHERE id = ?', (student_id,)).fetchone()
            if student:
                profile_data = json.loads(student[0]) if student[0] else {"class": "", "grade": "", "phone_number": "", "notifications": [], "messages": []}
                if profile_data.get('class') == class_name[-1] and profile_data.get('grade', '') == class_name[:-1]:
                    cursor.execute('INSERT INTO attendance (student_id, class_name, date, status, teacher_email) VALUES (?, ?, ?, ?, ?)',
                                  (student_id, class_name, date, status, teacher_email))
        get_db().commit()
        flash("Attendance updated successfully", "success")
        return True, "Attendance updated"
    except sqlite3.Error as e:
        flash(f"Error updating attendance: {str(e)}", "error")
        return False, f"Error updating attendance: {str(e)}"

@with_db
def log_extracurricular_update(cursor, teacher_name, student_id, achievement):
    try:
        cursor.execute('INSERT INTO extracurricular_updates (student_id, teacher_name, achievement) VALUES (?, ?, ?)',
                       (student_id, teacher_name, achievement))
        get_db().commit()
    except sqlite3.Error as e:
        app.logger.error(f"Error logging extracurricular update: {e}")

@with_db
def update_marks(cursor, teacher_email, student_id, subject, marks, remarks):
    # Validate marks (0-100, but allow customization based on subject max_marks if needed)
    try:
        marks = int(marks)
        # Assuming subject-specific max marks (e.g., 100 for all subjects here, adjust as needed)
        if not (0 <= marks <= 100):
            flash("Marks must be between 0 and 100", "error")
            return False, "Marks must be between 0 and 100"
    except ValueError:
        flash("Marks must be a valid integer", "error")
        return False, "Marks must be a valid integer"
    
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject or subject not in ["Java", "Math", "Python", "DSA", "Communication", "PE"]:
        flash("Cannot update marks for invalid or unauthorized subject", "error")
        return False, "Cannot update marks for invalid or unauthorized subject"
    if subject != teacher_subject and subject != "PE":
        flash("Cannot update marks for other subjects", "error")
        return False, "Cannot update marks for other subjects"
    
    profile_data = json.loads(cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,)).fetchone()[0]) if cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,)).fetchone()[0] else {"marks": {}, "remarks": {}, "notifications": [], "messages": [], "phone_number": "", "grade": "", "class": "", "roll": "N/A"}
    old_marks = profile_data.get('marks', {}).get(subject, 'N/A')
    old_remarks = profile_data.get('remarks', {}).get(subject, 'N/A')
    profile_data.setdefault('marks', {})[subject] = marks
    profile_data.setdefault('remarks', {})[subject] = remarks
    try:
        cursor.execute('UPDATE students SET profile_data=? WHERE id=?', (json.dumps(profile_data), student_id))
        get_db().commit()
        details = f"Marks updated from {old_marks} to {marks}, Remarks updated from '{old_remarks}' to '{remarks}'"
        log_resource_change(None, teacher_email, student_id, subject, "Updated Marks/Remarks", details)
        flash("Marks updated successfully", "success")
        return True, "Marks updated"
    except sqlite3.Error as e:
        flash(f"Error updating marks: {str(e)}", "error")
        return False, f"Error updating marks: {str(e)}"

def get_default_profile_data():
    """Return a default profile data structure"""
    return {
        "notifications": [],
        "messages": [],
        "phone_number": "",
        "grade": "",
        "class": "",
        "roll": "N/A"
    }

def parse_profile_data(data):
    """Safely parse profile data and ensure proper structure"""
    try:
        if isinstance(data, str):
            try:
                profile_data = json.loads(data)
            except json.JSONDecodeError:
                return get_default_profile_data()
        elif isinstance(data, dict):
            profile_data = data
        else:
            return get_default_profile_data()
            
        # Ensure all required keys exist
        default_data = get_default_profile_data()
        for key, default_value in default_data.items():
            if key not in profile_data:
                profile_data[key] = default_value
            # Ensure lists are actually lists
            if isinstance(default_value, list) and not isinstance(profile_data[key], list):
                profile_data[key] = []
                
        return profile_data
    except Exception:
        return get_default_profile_data()

# Student routes (phone number and OTP login, no email, port 5000)
@app.route('/')
def index():
    return render_template('student_login.html')

@app.route('/student/login', methods=['POST'])
@with_db
def student_login(cursor):
    phone_number = request.form.get('phone_number', '').strip()
    app.logger.info(f"Attempting login with phone_number: {phone_number}")
    
    # Validate phone number format (exactly 10 digits, integers only)
    if not (phone_number.isdigit() and len(phone_number) == 10):
        app.logger.error(f"Invalid phone number format: {phone_number}")
        return jsonify({"error": "Phone number must be exactly 10 digits (integers only)"}), 401
    
    # Check if phone number exists in profile_data
    cursor.execute('''
        SELECT id, name, profile_data, profile_image, class_timetable 
        FROM students 
        WHERE json_extract(profile_data, '$.phone_number') = ?
    ''', (phone_number,))
    
    student = cursor.fetchone()
    
    if student:
        app.logger.info(f"Found student with phone_number: {phone_number}")
        # Check if OTP exists and hasn't expired (within 120 seconds)
        if 'otp_secrets' not in app.config:
            app.config['otp_secrets'] = {}
        
        if phone_number in app.config['otp_secrets']:
            timestamp = app.config['otp_secrets'][phone_number]['timestamp']
            if (time.time() - timestamp) <= 120:  # OTP valid for 120 seconds
                secret = app.config['otp_secrets'][phone_number]['secret']
                app.logger.info(f"OTP exists for {phone_number}, waiting for input")
            else:
                # OTP expired, remove it and redirect to login
                del app.config['otp_secrets'][phone_number]
                app.logger.warning(f"OTP expired for {phone_number}, redirecting to login")
                flash("OTP has expired. Please log in again.", "error")
                return redirect('/')
        else:
            # No OTP exists, generate a new one
            otp, secret = generate_and_display_otp(phone_number)
            app.logger.info(f"OTP generated for {phone_number}, waiting for input")

        entered_otp = request.form.get('otp', '').strip()
        if entered_otp:
            app.logger.info(f"Verifying OTP: {entered_otp} for {phone_number}")
            if phone_number in app.config['otp_secrets'] and (time.time() - app.config['otp_secrets'][phone_number]['timestamp']) <= 120:
                totp = pyotp.TOTP(app.config['otp_secrets'][phone_number]['secret'])
                if totp.verify(entered_otp):
                    student_id, name, profile_data, profile_image, class_timetable = student
                    profile_data = json.loads(profile_data) if profile_data and isinstance(profile_data, str) else {"notifications": [], "messages": [], "phone_number": phone_number, "grade": "", "class": "", "roll": "N/A"}
                    session['user_id'] = student_id
                    session['user_type'] = 'student'
                    session['name'] = name
                    del app.config['otp_secrets'][phone_number]
                    app.logger.info(f"Login successful for student ID: {student_id}")
                    flash("Login successful", "success")
                    return jsonify({"message": "Login successful", "student_id": student_id, "redirect": f"/student/home?student_id={student_id}"})
                app.logger.error(f"Invalid OTP for {phone_number}: {entered_otp} (Expected: {totp.now()})")
                return jsonify({"error": "Invalid OTP"}), 401
            app.logger.error(f"OTP expired or not generated for {phone_number}")
            flash("OTP has expired. Please log in again.", "error")
            return redirect('/')
        app.logger.info(f"Waiting for OTP input for {phone_number}")
        return jsonify({"message": "OTP generated, enter it below"}), 200
    app.logger.error(f"Phone number not found: {phone_number}")
    return jsonify({"error": "Phone number not found"}), 401

@app.route('/student/home')
@with_db
def student_home(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image, class_timetable FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data_str, profile_image, class_timetable = student
        profile_data = parse_profile_data(profile_data_str)  # Safely parse, returns dict

        # Get the student's class section (e.g., "10B")
        class_section = f"{profile_data.get('grade', '10')}{profile_data.get('class', 'B')}"

        # Fetch total count of students in the same class
        cursor.execute('''
            SELECT COUNT(*) 
            FROM students 
            WHERE json_extract(profile_data, "$.grade") = ? 
            AND json_extract(profile_data, "$.class") = ?
        ''', (profile_data.get('grade', '10'), profile_data.get('class', 'B')))
        student_count = cursor.fetchone()[0]

        # Fetch the latest attendance record for the student
        cursor.execute('''
            SELECT status, date 
            FROM attendance 
            WHERE student_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        ''', (student_id,))
        attendance = cursor.fetchone()
        attendance_data = {'status': attendance[0] if attendance else 'Unknown', 'date': attendance[1] if attendance and attendance[1] else 'N/A'} if attendance else None
        
        return render_template('student_home.html', 
                              name=name, 
                              profile_data=profile_data,  # Pass dict directly
                              profile_image=profile_image, 
                              student_id=student_id, 
                              class_timetable=class_timetable,
                              attendance=attendance_data,
                              student_count=student_count,
                              class_section=class_section)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/class_students')
@with_db
def student_class_list(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT profile_data, name, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        profile_data_str, name, profile_image = student
        profile_data = parse_profile_data(profile_data_str)
        class_section = f"{profile_data.get('grade', '10')}{profile_data.get('class', 'B')}"
        
        # Fetch alphabetically ordered names of students in the same class
        cursor.execute('''
            SELECT name 
            FROM students 
            WHERE json_extract(profile_data, "$.grade") = ? 
            AND json_extract(profile_data, "$.class") = ? 
            ORDER BY name ASC
        ''', (profile_data.get('grade', '10'), profile_data.get('class', 'B')))
        class_students = cursor.fetchall()
        student_names = [row['name'] for row in class_students]

        return render_template('student_class_list.html', 
                              student_id=student_id, 
                              class_section=class_section, 
                              student_names=student_names,
                              name=name, 
                              profile_image=profile_image,
                              profile_data=profile_data)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    
@app.route('/student/chatbot', methods=['POST'])
@with_db
def student_chatbot(cursor):
    student_id = request.args.get('student_id') or session.get('user_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return jsonify({"error": "Access denied"}), 401
    
    message = request.form.get('message', '').strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400
    
    # Simple bot logic (expand as needed)
    response = "I'm a simple bot. How can I help?"
    if message.lower().includes("hello"):
        response = "Hello! How can I assist you today?"
    elif message.lower().includes("help"):
        response = "You can ask about your profile, attendance, or contact teachers."
    elif message.lower().includes("bye"):
        response = "Goodbye! Feel free to chat again."

    return jsonify({"response": response})

@app.route('/student/profile', methods=['GET', 'POST'])
@with_db
def student_profile(cursor):
    student_id = request.args.get('student_id') or session.get('user_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        if request.method == 'POST':
            new_image = request.files.get('profile_image')
            if new_image:
                filename = f"student_{student_id}_{new_image.filename}"
                file_path = os.path.join('uploads', filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                new_image.save(file_path)
                try:
                    cursor.execute('UPDATE students SET profile_image=? WHERE id=?', (filename, student_id))
                    get_db().commit()
                    flash("Profile image updated successfully", "success")
                except sqlite3.Error as e:
                    flash(f"Error updating profile image: {str(e)}", "error")
                    return jsonify({"error": f"Error updating profile image: {str(e)}"}), 500
            return redirect(url_for('student_profile', student_id=student_id))
        
        cursor.execute('SELECT name, profile_data, profile_image, class_timetable FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data_str, profile_image, class_timetable = student
        profile_data = parse_profile_data(profile_data_str)  # Safely parse, returns dict

        return render_template('student_profile.html', 
                              name=name, 
                              profile_data=profile_data,  # Pass dict directly
                              profile_image=profile_image, 
                              student_id=student_id, 
                              class_timetable=class_timetable)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
        
@app.route('/student/achievements')
@with_db
def student_achievements(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data_str, profile_image = student
        profile_data = parse_profile_data(profile_data_str)
        class_section = f"{profile_data.get('grade', '10')}{profile_data.get('class', 'B')}"
        
        # Fetch educational achievements
        cursor.execute('''
            SELECT achievement, teacher_name, subject, timestamp 
            FROM educational_achievements 
            WHERE student_id = ? 
            ORDER BY timestamp DESC
        ''', (student_id,))
        educational_achievements = cursor.fetchall() or []

        # Fetch extracurricular achievements (only by PE teacher)
        cursor.execute('''
            SELECT achievement, teacher_name, timestamp 
            FROM extracurricular_updates 
            WHERE student_id = ? 
            ORDER BY timestamp DESC
        ''', (student_id,))
        extracurricular_achievements = cursor.fetchall() or []

        return render_template('student_achievements.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              class_section=class_section,
                              educational_achievements=educational_achievements,
                              extracurricular_achievements=extracurricular_achievements)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/fee')
@with_db
def student_fee(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data_str, profile_image = student
        profile_data = parse_profile_data(profile_data_str)
        class_section = f"{profile_data.get('grade', '10')}{profile_data.get('class', 'B')}"
        roll = profile_data.get('roll', 'N/A')

        # Example fee data (replace with actual database query or logic)
        fees = {
            'pending': '0.00',
            'total': '28000.00',
            'paid': '28000.00',
            'payments': [
                {'amount': '18000.00', 'receipt': '0302', 'mode': 'ONLINE'},
                {'amount': '10000.00', 'receipt': '2418', 'mode': 'DD'}
            ]
        }

        return render_template('student_fee.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              fees=fees)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/fee_payment')
@with_db
def student_fee_payment(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data_str, profile_image = student
        profile_data = parse_profile_data(profile_data_str)
        class_section = f"{profile_data.get('grade', '10')}{profile_data.get('class', 'B')}"
        roll = profile_data.get('roll', 'N/A')

        # Example fee data (replace with actual database query or logic)
        fees = {
            'pending': '0.00',
            'total': '28000.00',
            'paid': '28000.00',
            'payments': [
                {'amount': '18000.00', 'receipt': '0302', 'mode': 'ONLINE'},
                {'amount': '10000.00', 'receipt': '2418', 'mode': 'DD'}
            ]
        }

        return render_template('student_fee_payment.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              fees=fees)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/results')
@with_db
def student_results(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data, profile_image = student
        profile_data = parse_profile_data(profile_data)

        # Fetch all tests created by teachers, assuming max_marks is 20
        cursor.execute('''
            SELECT id, name, subject, created_at 
            FROM tests 
            ORDER BY created_at DESC
        ''')
        tests = [{'id': row['id'], 'name': row['name'], 'subject': row['subject'], 'created_at': row['created_at'], 'max_marks': 20} for row in cursor.fetchall()] if cursor.fetchall() else []

        # Fetch test results for the student, grouped by test name, with default marks of 0 if none
        test_results = {}
        for test in tests:
            cursor.execute('''
                SELECT t.subject, COALESCE(tr.marks, 0) as marks 
                FROM test_results tr 
                RIGHT JOIN tests t ON tr.test_id = t.id 
                WHERE tr.student_id = ? AND t.name = ?
            ''', (student_id, test['name']))
            results = [{'subject': row[0], 'marks': row[1]} for row in cursor.fetchall()]
            test_results[test['name']] = results if results else []

        # Calculate overall subject performance for pie charts (average marks across all tests, scaled to 100)
        subjects = {}
        subject_tests = {}
        for test in tests:
            for result in test_results.get(test['name'], []):
                subject = result['subject']
                marks = result['marks']
                if subject not in subject_tests:
                    subject_tests[subject] = []
                subject_tests[subject].append(marks)

        for subject, marks_list in subject_tests.items():
            if marks_list:  # Avoid division by zero
                avg_marks = sum(marks_list) / len(marks_list)
                # Scale to 100 (assuming each test is out of 20, so max total is 20 * number of tests)
                total_max_possible = 20 * len(marks_list)
                subjects[subject] = int((avg_marks / total_max_possible * 100) if total_max_possible > 0 else 0)

        return render_template('student_results.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              tests=tests, 
                              test_results=test_results, 
                              subjects=subjects)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/teachers_contact')
@with_db
def student_teachers_contact(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data, profile_image = student
        profile_data = parse_profile_data(profile_data)
        
        cursor.execute('SELECT name, phone_number, subject FROM teachers')
        teachers = cursor.fetchall()

        return render_template('student_teachers_contact.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              teachers=teachers)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/notifications')
@with_db
def student_notifications(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,))
        profile_data_str = cursor.fetchone()[0]
        profile_data = json.loads(profile_data_str) if profile_data_str and isinstance(profile_data_str, str) else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": "", "roll": "N/A"}  # Parse JSON or default with safety check
        if not isinstance(profile_data, dict):
            profile_data = {"notifications": []}  # Fallback
        notifications = profile_data.get('notifications', [])
        # Clear unread count and mark all as read
        session['read_notifications'] = notifications
        session['unread_notifications'] = 0

        cursor.execute('SELECT name, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_image = student

        return render_template('student_notifications.html', 
                              notifications=notifications, 
                              student_id=student_id,
                              name=name,
                              profile_image=profile_image)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/timetable')
@with_db
def student_timetable(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image, class_timetable FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data, profile_image, class_timetable = student
        profile_data = parse_profile_data(profile_data)
        class_section = f"{profile_data.get('grade', '10')}{profile_data.get('class', 'B')}"
        
        return render_template('student_timetable.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              class_timetable=class_timetable, 
                              class_section=class_section)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/attendance')
@with_db
def student_attendance(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data_str, profile_image = student
        profile_data = parse_profile_data(profile_data_str)

        # Fetch attendance data from the attendance table
        cursor.execute('''
            SELECT COUNT(*) as total_days, SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent_count
            FROM attendance 
            WHERE student_id = ? AND date <= ?
        ''', (student_id, datetime.now().strftime('%Y-%m-%d')))
        attendance_summary = cursor.fetchone()
        working_days = attendance_summary['total_days'] - attendance_summary['absent_count'] if attendance_summary['total_days'] else 0
        absent_days = attendance_summary['absent_count'] if attendance_summary['absent_count'] else 0

        # Fetch absent dates
        cursor.execute('''
            SELECT date 
            FROM attendance 
            WHERE student_id = ? AND status = 'Absent' 
            ORDER BY date DESC
        ''', (student_id,))
        absent_dates = [row['date'] for row in cursor.fetchall()] or []

        return render_template('student_attendance.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id,
                              working_days=working_days,
                              absent_days=absent_days,
                              absent_dates=absent_dates)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/student/upload_leave_letter', methods=['POST'])
@with_db
def upload_leave_letter(cursor):
    student_id = request.form.get('student_id')
    date = request.form.get('date')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return jsonify({"error": "Access denied"}), 401
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if file:
        filename = f"leave_letter_{student_id}_{date}_{file.filename}"
        file_path = os.path.join('uploads/leave_letters', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)
        
        # Log the upload (optional, for tracking or teacher notification)
        cursor.execute('''
            INSERT INTO resource_logs (teacher_email, student_id, subject, action, details)
            VALUES (NULL, ?, 'Attendance', 'Uploaded Leave Letter', ?)
        ''', (student_id, f"Leave letter for date {date}"))
        get_db().commit()
        
        return jsonify({"success": True, "message": "Leave letter uploaded successfully"})
    return jsonify({"error": "Upload failed"}), 500

@app.route('/student/leaves')
@with_db
def student_leaves(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data, profile_image = student
        profile_data = parse_profile_data(profile_data)

        # Fetch holidays from the database
        cursor.execute('SELECT date, description FROM holidays')
        holidays = {row['date']: row['description'] for row in cursor.fetchall()}

        return render_template('student_leaves.html', 
                              name=name, 
                              profile_data=profile_data, 
                              profile_image=profile_image,
                              student_id=student_id, 
                              holidays=holidays)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

# Teacher routes (no OTP required)
@app.route('/teacher/login', methods=['GET', 'POST'])
@with_db
def teacher_login(cursor):
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute('SELECT id, name, email, subject FROM teachers WHERE email=? AND password=?', (email, hashed_password))
        teacher = cursor.fetchone()
        
        if teacher:
            teacher_id, name, email, subject = teacher
            session['user_id'] = email
            session['user_type'] = 'teacher'
            session['name'] = name
            flash("Login successful", "success")
            return jsonify({"message": "Login successful", "teacher_id": teacher_id, "name": name, "email": email, "subject": subject})
        flash("Invalid credentials", "error")
        return jsonify({"error": "Invalid credentials"}), 401
    return render_template('teacher_login.html')

@app.route('/teacher/dashboard')
@with_db
def teacher_dashboard(cursor):
    teacher_email = request.args.get('teacher_email') or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return redirect('/teacher/login')
    
    # Fetch teacher details explicitly, ensuring we get a Row object or dict
    cursor.execute('SELECT name, email, subject FROM teachers WHERE email = ?', (teacher_email,))
    teacher_data = cursor.fetchone()
    
    if not teacher_data:
        flash("Teacher not found", "error")
        return jsonify({"error": "Teacher not found"}), 404
    
    # Convert Row object to dict for consistent Jinja2 access
    teacher_data_dict = dict(teacher_data)
    teacher_subject = teacher_data_dict['subject']
    
    # Fetch all students, ensuring profile_data is handled safely
    cursor.execute('SELECT id, name, profile_data, profile_image, class_timetable FROM students')
    students = cursor.fetchall()
    
    # Convert student Row objects to dicts for safety
    students_list = [dict(student) for student in students]
    
    # Debug logging to verify Jinja2 filters and data
    app.logger.debug("Jinja2 filters: %s", app.jinja_env.filters)
    app.logger.debug("Rendering teacher_dashboard with students: %s, teacher_data: %s", students_list, teacher_data_dict)
    
    return render_template('teacher_dashboard.html', 
                          students=students_list,  # Pass as list of dicts
                          teacher_email=teacher_email, 
                          teacher_subject=teacher_subject, 
                          teacher_data=teacher_data_dict)

@app.route('/teacher/academics')
@with_db
def teacher_academics(cursor):
    teacher_email = request.args.get('teacher_email') or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return redirect('/teacher/login')
    
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject:
        flash("Teacher not found or no subject assigned", "error")
        return jsonify({"error": "Teacher not found or no subject assigned"}), 404
    
    cursor.execute('SELECT id, name, profile_data, profile_image FROM students')
    students = cursor.fetchall()
    return render_template('teacher_academics.html', students=students, teacher_email=teacher_email, teacher_subject=teacher_subject, teacher_data=dict(cursor.execute('SELECT name, subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()))

@app.route('/teacher/student_profile')
@with_db
def teacher_student_profile(cursor):
    student_id = request.args.get('student_id')
    teacher_email = request.args.get('teacher_email') or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return redirect('/teacher/login')
    
    try:
        cursor.execute('SELECT name, profile_data, profile_image, class_timetable FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        
        name, profile_data, profile_image, class_timetable = student
        profile_data = parse_profile_data(profile_data)
        
        cursor.execute('SELECT t.name, tr.marks, tr.remarks, t.max_marks FROM test_results tr JOIN tests t ON tr.test_id = t.id WHERE tr.student_id = ? ORDER BY tr.timestamp DESC', (student_id,))
        test_results = [{'name': row['name'], 'marks': row['marks'], 'remarks': row['remarks'], 'max_marks': row['max_marks']} for row in cursor.fetchall()] or []
        
        cursor.execute('SELECT achievement, teacher_name, timestamp FROM extracurricular_updates WHERE student_id = ?', (student_id,))
        extracurricular_updates = cursor.fetchall() or []
        
        cursor.execute('SELECT status, date FROM attendance WHERE student_id = ? AND date = ?', (student_id, datetime.now().strftime('%Y-%m-%d')))
        attendance = cursor.fetchone()

        cursor.execute('SELECT name, subject FROM teachers WHERE email = ?', (teacher_email,))
        teacher_data = dict(cursor.fetchone())

        return render_template('teacher_student_profile.html', 
                              name=name, 
                              profile_data={'id': student_id, 'profile_data': profile_data, 'profile_image': profile_image, 'class_timetable': class_timetable}, 
                              profile_image=profile_image, 
                              teacher_email=teacher_email, 
                              class_timetable=class_timetable, 
                              test_results=test_results, 
                              extracurricular_updates=extracurricular_updates, 
                              attendance=attendance,
                              teacher_data=teacher_data)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        flash(f"Profile data parsing error: {str(e)}", "error")
        return jsonify({"error": f"Profile data parsing error: {str(e)}"}), 500
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "error")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/teacher/resources')
@with_db
def teacher_resources(cursor):
    teacher_email = request.args.get('teacher_email') or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return redirect('/teacher/login')
    
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject:
        flash("Teacher not found or no subject assigned", "error")
        return jsonify({"error": "Teacher not found or no subject assigned"}), 404
    
    # Query resource logs for this teacher's updates
    cursor.execute('SELECT id, student_id, action, details, timestamp FROM resource_logs WHERE teacher_email = ? ORDER BY timestamp DESC', (teacher_email,))
    resource_logs = cursor.fetchall()
    cursor.execute('SELECT name, subject FROM teachers WHERE email = ?', (teacher_email,))
    teacher_data = dict(cursor.fetchone())
    return render_template('teacher_resources.html', teacher_email=teacher_email, teacher_subject=teacher_subject, resource_logs=resource_logs, teacher_data=teacher_data)

@app.route('/teacher/attendance', methods=['GET', 'POST'])
@with_db
def teacher_attendance(cursor):
    teacher_email = request.args.get('teacher_email') or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return redirect('/teacher/login')
    
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject:
        flash("Teacher not found or no subject assigned", "error")
        return jsonify({"error": "Teacher not found or no subject assigned"}), 404
    
    if request.method == 'POST':
        class_name = request.form['class_name']
        date = datetime.now().strftime('%Y-%m-%d')
        student_statuses = {}
        for key, value in request.form.items():
            if key.startswith('student_') and value in ['Present', 'Absent']:
                student_id = key.replace('student_', '')
                student_statuses[student_id] = value
        success, message = update_attendance(None, teacher_email, class_name, date, student_statuses)
        if not success:
            flash(message, "error")
            return jsonify({"error": message}), 400
        flash(message, "success")
        return jsonify({"message": message})
    
    cursor.execute('SELECT id, name, profile_data FROM students')
    students = cursor.fetchall()
    classes = set()
    for student in students:
        profile_data = json.loads(student[2]) if student[2] and isinstance(student[2], str) else {"class": "", "grade": "", "phone_number": "", "notifications": [], "messages": []}
        classes.add(f"{profile_data.get('grade', '')}{profile_data.get('class', '')}")
    cursor.execute('SELECT name, subject FROM teachers WHERE email = ?', (teacher_email,))
    teacher_data = dict(cursor.fetchone())
    return render_template('teacher_attendance.html', teacher_email=teacher_email, teacher_subject=teacher_subject, students=students, classes=sorted(classes), teacher_data=teacher_data)

@app.route('/teacher/update_marks', methods=['POST'])
@with_db
def update_marks_route(cursor):
    teacher_email = request.form['teacher_email'] or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return jsonify({"error": "Access denied"}), 401
    student_id = request.form['student_id']
    subject = request.form['subject']
    marks = request.form['marks']
    remarks = request.form['remarks']
    
    success, message = update_marks(None, teacher_email, student_id, subject, marks, remarks)
    if not success:
        flash(message, "error")
        return jsonify({"error": message}), 400
    flash(message, "success")
    return jsonify({"message": message})

@app.route('/teacher/create_test', methods=['POST'])
@with_db
def create_test_route(cursor):
    teacher_email = request.form['teacher_email'] or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return jsonify({"error": "Access denied"}), 401
    test_name = request.form['test_name']
    subject = request.form['subject']
    max_marks = request.form.get('max_marks', 20)  # Default to 20 if not provided
    success, message = create_test(None, teacher_email, test_name, subject, max_marks)
    if not success:
        flash(message, "error")
        return jsonify({"error": message}), 400
    flash(message, "success")
    return jsonify({"message": message})

@app.route('/teacher/update_test_results', methods=['POST'])
@with_db
def update_test_results_route(cursor):
    teacher_email = request.form['teacher_email'] or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return jsonify({"error": "Access denied"}), 401
    test_name = request.form['test_name']
    student_id = request.form['student_id']
    marks = request.form['marks']
    remarks = request.form['remarks']
    success, message = update_test_results(None, teacher_email, test_name, student_id, marks, remarks)
    if not success:
        flash(message, "error")
        return jsonify({"error": message}), 400
    flash(message, "success")
    return jsonify({"message": message})

@app.route('/teacher/extracurricular_updates', methods=['POST'])
@with_db
def extracurricular_updates_route(cursor):
    teacher_email = request.form['teacher_email'] or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return jsonify({"error": "Access denied"}), 401
    result = cursor.execute('SELECT name, subject FROM teachers WHERE email=?', (teacher_email,)).fetchone()
    if not result or result[1] != "PE":
        flash("Only the PE teacher can update extracurricular achievements", "error")
        return jsonify({"error": "Only the PE teacher can update extracurricular achievements"}), 403
    teacher_name = result[0]
    student_id = request.form['student_id']
    achievement = request.form['achievement']
    try:
        cursor.execute('INSERT INTO extracurricular_updates (student_id, teacher_name, achievement) VALUES (?, ?, ?)',
                       (student_id, teacher_name, achievement))
        get_db().commit()
        flash("Extracurricular update logged successfully", "success")
        return jsonify({"message": "Extracurricular update logged"})
    except sqlite3.Error as e:
        flash(f"Error logging extracurricular update: {str(e)}", "error")
        return jsonify({"error": f"Error logging extracurricular update: {str(e)}"}), 500

@app.route('/teacher/send_message', methods=['POST'])
@with_db
def teacher_send_message(cursor):
    teacher_email = request.form['teacher_email'] or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return jsonify({"error": "Access denied"}), 401
    result = cursor.execute('SELECT name, subject FROM teachers WHERE email=?', (teacher_email,)).fetchone()
    if not result:
        flash("Teacher not found", "error")
        return jsonify({"error": "Teacher not found"}), 404
    teacher_name, teacher_subject = result

    message_type = request.form['message_type']  # 'individual', 'multiple'
    message_text = request.form['message_text']
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    if message_type == 'individual':
        student_id = request.form['student_id']
        cursor.execute('SELECT id, name, profile_data FROM students WHERE id=?', (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student not found", "error")
            return jsonify({"error": "Student not found"}), 404
        student_id, student_name, profile_data = student
        profile_data = parse_profile_data(profile_data)
        # Move message to notifications instead of messages
        notification = f"Message from {teacher_name} ({teacher_subject}): {message_text} (Sent on {timestamp})"
        profile_data['notifications'].append(notification)
        # Clear messages if any (ensuring no duplicates)
        profile_data['messages'] = []
        try:
            cursor.execute('UPDATE students SET profile_data=? WHERE id=?', (json.dumps(profile_data), student_id))
            get_db().commit()
            flash(f"Message sent to {student_name} as notification", "success")
            return jsonify({"message": f"Message sent to {student_name} as notification"})
        except sqlite3.Error as e:
            flash(f"Error sending message: {str(e)}", "error")
            return jsonify({"error": f"Error sending message: {str(e)}"}), 500

    elif message_type == 'multiple':
        selected_students = request.form.getlist('student_ids')  # Get list of checked student IDs
        if not selected_students:
            flash("No students selected", "error")
            return jsonify({"error": "No students selected"}), 400
        try:
            for student_id in selected_students:
                cursor.execute('SELECT id, name, profile_data FROM students WHERE id=?', (student_id,))
                student = cursor.fetchone()
                if student:
                    student_id, student_name, profile_data = student
                    profile_data = parse_profile_data(profile_data)
                    # Move message to notifications instead of messages
                    notification = f"Message from {teacher_name} ({teacher_subject}): {message_text} (Sent on {timestamp})"
                    profile_data['notifications'].append(notification)
                    # Clear messages if any
                    profile_data['messages'] = []
                    cursor.execute('UPDATE students SET profile_data=? WHERE id=?', (json.dumps(profile_data), student_id))
            get_db().commit()
            flash(f"Message sent to {len(selected_students)} selected students as notifications", "success")
            return jsonify({"message": f"Message sent to {len(selected_students)} selected students as notifications"})
        except sqlite3.Error as e:
            flash(f"Error sending messages: {str(e)}", "error")
            return jsonify({"error": f"Error sending messages: {str(e)}"}), 500

    flash("Invalid message type", "error")
    return jsonify({"error": "Invalid message type"}), 400

# HOD interface (persistent terminal, local network access, port 5000)
@app.route('/hod/')
@with_db
def hod_interface(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role (add logic in login if needed)
        flash("Access denied. HOD login required.", "error")
        return redirect('/')
    cursor.execute('SELECT id, name, email, profile_data, profile_image, class_timetable FROM students')
    students = cursor.fetchall()
    cursor.execute('SELECT id, name, email, subject, phone_number FROM teachers')
    teachers = cursor.fetchall()
    return render_template('hod_interface.html', students=students, teachers=teachers)

@app.route('/hod/create_teacher', methods=['POST'])
@with_db
def hod_create_teacher(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role (add logic in login if needed)
        flash("Access denied. HOD login required.", "error")
        return jsonify({"error": "Access denied"}), 401
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    subject = request.form['subject']
    phone_number = request.form.get('phone_number')  # Optional
    success, message = create_teacher(None, name, email, password, subject, phone_number)
    if not success:
        return jsonify({"error": message}), 400
    return jsonify({"message": message, "credentials": {"name": name, "email": email, "password": password, "subject": subject, "phone_number": phone_number}})

@app.route('/hod/timetables', methods=['GET', 'POST'])
@with_db
def hod_timetables(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role
        flash("Access denied. HOD login required.", "error")
        return redirect('/')
    
    if request.method == 'POST':
        grade = request.form['grade']
        section = request.form['section']
        timetable_image = request.files.get('timetable_image')
        if timetable_image:
            filename = f"{grade}{section}.jpg"
            file_path = os.path.join('uploads', filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            timetable_image.save(file_path)
            # Update all students in this class and section with the new timetable
            cursor.execute('''
                UPDATE students 
                SET class_timetable = ? 
                WHERE json_extract(profile_data, "$.grade") = ? 
                AND json_extract(profile_data, "$.class") = ?
            ''', (filename, grade, section))
            get_db().commit()
            flash(f"Timetable for class {grade}{section} updated successfully", "success")
        return redirect(url_for('hod_timetables'))
    
    # Fetch all unique grade-section combinations for the form
    cursor.execute('''
        SELECT DISTINCT json_extract(profile_data, "$.grade") as grade, json_extract(profile_data, "$.class") as section 
        FROM students 
        WHERE json_extract(profile_data, "$.grade") IS NOT NULL 
        AND json_extract(profile_data, "$.class") IS NOT NULL 
        ORDER BY grade, section
    ''')
    classes = cursor.fetchall()
    
    return render_template('hod_timetables.html', classes=classes)

@app.route('/student/login', methods=['GET'])
def student_login_page():
    return render_template('student_login.html')

@app.route('/hod/create_student', methods=['POST'])
@with_db
def hod_create_student(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role (add logic in login if needed)
        flash("Access denied. HOD login required.", "error")
        return jsonify({"error": "Access denied"}), 401
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    phone_number = request.form['phone_number']
    # Validate phone number (10 digits, integers only)
    if not (phone_number.isdigit() and len(phone_number) == 10):
        flash("Phone number must be exactly 10 digits (integers only)", "error")
        return jsonify({"error": "Phone number must be exactly 10 digits (integers only)"}), 400
    profile_data = request.form['profile_data']
    class_timetable = request.form['class_timetable'] or "10B.jpg"  # Default or specified
    success, message = create_student(None, name, email, password, phone_number, profile_data, class_timetable)
    if not success:
        return jsonify({"error": message}), 400
    return jsonify({"message": message, "credentials": {"name": name, "email": email, "password": password, "phone_number": phone_number, "class_timetable": class_timetable}})

@app.route('/hod/remove_teacher', methods=['POST'])
@with_db
def hod_remove_teacher(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role (add logic in login if needed)
        flash("Access denied. HOD login required.", "error")
        return jsonify({"error": "Access denied"}), 401
    teacher_id = request.form['teacher_id']
    success, message = remove_teacher(None, teacher_id)
    if not success:
        return jsonify({"error": message}), 400
    return jsonify({"message": message})

@app.route('/hod/remove_student', methods=['POST'])
@with_db
def hod_remove_student(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role (add logic in login if needed)
        flash("Access denied. HOD login required.", "error")
        return jsonify({"error": "Access denied"}), 401
    student_id = request.form['student_id']
    success, message = remove_student(None, student_id)
    if not success:
        return jsonify({"error": message}), 400
    return jsonify({"message": message})

@app.route('/hod/update_timetable', methods=['POST'])
@with_db
def hod_update_timetable(cursor):
    if not session.get('user_type') == 'hod':  # Assume HOD is a special role (add logic in login if needed)
        flash("Access denied. HOD login required.", "error")
        return jsonify({"error": "Access denied"}), 401
    student_id = request.form['student_id']
    class_timetable = request.form['class_timetable']
    try:
        cursor.execute('UPDATE students SET class_timetable = ? WHERE id = ?', (class_timetable, student_id))
        get_db().commit()
        flash("Timetable updated successfully", "success")
        return jsonify({"message": "Timetable updated"})
    except sqlite3.Error as e:
        flash(f"Error updating timetable: {str(e)}", "error")
        return jsonify({"error": f"Error updating timetable: {str(e)}"}), 500

# Serve uploaded profile images and resources (shared across roles)
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    try:
        return send_from_directory('uploads', filename)
    except Exception as e:
        flash(f"Error serving file: {str(e)}", "error")
        return jsonify({"error": f"File not found: {str(e)}"}), 404

# Close database connections at app shutdown
@app.teardown_appcontext
def close_db(exception):
    if hasattr(_local, "conn"):
        _local.conn.close()
        del _local.conn

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)