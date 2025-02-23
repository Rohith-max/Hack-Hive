from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
from chatbot_mistral_ollama import generate_response
import sqlite3
import hashlib
import random
import os
import json
import time
from deep_translator import GoogleTranslator  # Open-source, easy-to-use translation
import pyotp  # For OTP generation in terminal (replace with Kannel later)
from datetime import datetime
from functools import wraps
import threading
import requests  # For checking Ollama health (optional)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Needed for session management and flash messages

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

# Create tables function to accept cursor or handle None for startup
def create_tables(cursor=None):
    if cursor is None:
        # Create a temporary connection for startup (not thread-local)
        conn = sqlite3.connect('school.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            # Create tables
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
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    else:
        # Use the provided cursor for thread-safe operations
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
        get_db().commit()

# Run table creation on app startup
create_tables(None)

# Add JSON filter to Jinja2 environment
app.jinja_env.filters['json_parse'] = json.loads

# Generate and display OTP in terminal (for now, replace with Kannel later)
def generate_and_display_otp(phone_number):
    if 'otp_secrets' not in app.config:
        app.config['otp_secrets'] = {}
    
    # Check if OTP exists and is still valid (within 30 seconds)
    if phone_number in app.config['otp_secrets']:
        timestamp = app.config['otp_secrets'][phone_number]['timestamp']
        if (time.time() - timestamp) <= 30:
            secret = app.config['otp_secrets'][phone_number]['secret']
            otp = pyotp.TOTP(secret).now()
            print(f"Reusing OTP for phone number {phone_number}: {otp} (Valid for remaining {30 - (time.time() - timestamp):.0f} seconds)")
            return otp, secret

    # Generate new OTP if none exists or expired
    secret = pyotp.random_base32()  # Generate a secret key for TOTP
    totp = pyotp.TOTP(secret)  # Create TOTP instance
    otp = totp.now()  # Generate current OTP
    app.config['otp_secrets'][phone_number] = {'secret': secret, 'timestamp': time.time()}
    print(f"OTP for phone number {phone_number}: {otp} (Valid for 30 seconds)")  # Display in terminal
    return otp, secret  # Return OTP and secret for validation

@with_db
def update_teacher_count(cursor):
    count = cursor.execute('SELECT COUNT(*) FROM teachers').fetchone()[0]
    print(f"Total Teachers: {count}")

@with_db
def update_student_count(cursor):
    count = cursor.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    print(f"Total Students: {count}")

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
    full_profile_data = {**json.loads(profile_data), "phone_number": phone_number, "notifications": [], "messages": []}
    try:
        cursor.execute('INSERT INTO students (name, email, password, profile_data, profile_image, class_timetable) VALUES (?, ?, ?, ?, ?, ?)',
                       (name, email, hashed_password, json.dumps(full_profile_data), 'default.jpg', class_timetable))
        get_db().commit()
        update_student_count(None)
        flash("Student created successfully", "success")
        return True, "Student created"
    except sqlite3.IntegrityError:
        flash("Email or phone number already exists", "error")
        return False, "Email or phone number already exists"

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
                if teacher[3] != "PE":  # Don’t replace PE teacher Nikhil
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
        print(f"Error logging resource change: {e}")

@with_db
def create_test(cursor, teacher_email, test_name, subject):
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject or subject not in ["Java", "Math", "Python", "DSA", "Communication", "PE"]:
        flash("Cannot create test for invalid or unauthorized subject", "error")
        return False, "Cannot create test for invalid or unauthorized subject"
    if subject != teacher_subject and subject != "PE":
        flash("Cannot create test for other subjects", "error")
        return False, "Cannot create test for other subjects"
    try:
        cursor.execute('INSERT INTO tests (name, subject, teacher_email) VALUES (?, ?, ?)',
                       (test_name, subject, teacher_email))
        get_db().commit()
        flash("Test created successfully", "success")
        return True, "Test created"
    except sqlite3.Error as e:
        flash(f"Error creating test: {str(e)}", "error")
        return False, f"Error creating test: {str(e)}"

@with_db
def update_test_results(cursor, teacher_email, test_name, student_id, marks, remarks):
    # Validate marks (0-100)
    try:
        marks = int(marks)
        if not (0 <= marks <= 100):
            flash("Marks must be between 0 and 100", "error")
            return False, "Marks must be between 0 and 100"
    except ValueError:
        flash("Marks must be a valid integer", "error")
        return False, "Marks must be a valid integer"
    
    test = cursor.execute('SELECT id, subject FROM tests WHERE name = ? AND teacher_email = ?', (test_name, teacher_email)).fetchone()
    if not test:
        flash("Test not found", "error")
        return False, "Test not found"
    test_id, subject = test
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject or subject not in ["Java", "Math", "Python", "DSA", "Communication", "PE"]:
        flash("Cannot update results for invalid or unauthorized subject", "error")
        return False, "Cannot update results for invalid or unauthorized subject"
    if subject != teacher_subject and subject != "PE":
        flash("Cannot update results for other subjects", "error")
        return False, "Cannot update results for other subjects"
    try:
        cursor.execute('INSERT INTO test_results (test_id, student_id, marks, remarks) VALUES (?, ?, ?, ?)',
                       (test_id, student_id, marks, remarks))
        get_db().commit()
        log_resource_change(None, teacher_email, student_id, subject, "Updated Test Results", f"Test: {test_name}, Marks: {marks}, Remarks: '{remarks}'")
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
                profile_data = json.loads(student[0]) if student[0] else {"class": "", "grade": "", "phone_number": "", "notifications": [], "messages": []}  # Parse JSON or default
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
        print(f"Error logging extracurricular update: {e}")

@with_db
def update_marks(cursor, teacher_email, student_id, subject, marks, remarks):
    # Validate marks (0-100)
    try:
        marks = int(marks)
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
    
    profile_data = json.loads(cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,)).fetchone()[0]) if cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,)).fetchone()[0] else {"marks": {}, "remarks": {}, "notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}
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

# Function to translate text using deep_translator (offline with caching, open-source, for chatbot only)
def translate_text(text, target_lang):
    if target_lang == 'en':
        return text
    try:
        # Map language codes to deep_translator codes (e.g., 'kn' -> 'kannada', 'hi' -> 'hindi', 'en' -> 'english')
        lang_map = {'kn': 'kannada', 'hi': 'hindi', 'en': 'english'}
        if target_lang not in lang_map:
            raise ValueError(f"Language code {target_lang} not supported by deep_translator")
        translator = GoogleTranslator(source='english', target=lang_map[target_lang])
        translated = translator.translate(text)
        return translated
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # Fallback to English if translation fails

# Function to check if Ollama is running and Mistral is available
def check_ollama_health():
    try:
        response = requests.get("http://localhost:8080", timeout=5)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False

# Default language for chatbot (English unless switched)
CHATBOT_LANGUAGE = 'en'

@app.route('/set_chatbot_language/<lang>')
def set_chatbot_language(lang):
    global CHATBOT_LANGUAGE
    if lang in ['en', 'kn', 'hi']:
        CHATBOT_LANGUAGE = lang
    return redirect(request.referrer or '/')

# Student routes (phone number and OTP login, no email, port 5000)
@app.route('/')
def index():
    return render_template('student_login.html')

@app.route('/student/login', methods=['POST'])
@with_db
def student_login(cursor):
    phone_number = request.form['phone_number']  # Use phone number instead of email
    # Validate phone number format (exactly 10 digits, integers only)
    if not (phone_number.isdigit() and len(phone_number) == 10):
        flash("Phone number must be exactly 10 digits (integers only)", "error")
        return jsonify({"error": "Phone number must be exactly 10 digits (integers only)"}), 400
    
    cursor.execute('SELECT id, name, profile_data, profile_image, class_timetable FROM students WHERE json_extract(profile_data, "$.phone_number") = ?', (phone_number,))
    student = cursor.fetchone()
    
    if student:
        # Check if OTP exists and hasn't expired (within 30 seconds)
        if 'otp_secrets' not in app.config:
            app.config['otp_secrets'] = {}
        
        if phone_number in app.config['otp_secrets']:
            timestamp = app.config['otp_secrets'][phone_number]['timestamp']
            if (time.time() - timestamp) <= 30:
                secret = app.config['otp_secrets'][phone_number]['secret']
                otp = pyotp.TOTP(secret).now()
                print(f"Reusing OTP for phone number {phone_number}: {otp} (Valid for remaining {30 - (time.time() - timestamp):.0f} seconds)")
            else:
                # OTP expired, generate new one
                otp, secret = generate_and_display_otp(phone_number)
        else:
            # No OTP exists, generate new one
            otp, secret = generate_and_display_otp(phone_number)

        entered_otp = request.form.get('otp')  # Get OTP from form (user enters it manually for now)
        if entered_otp:
            if phone_number in app.config['otp_secrets'] and (time.time() - app.config['otp_secrets'][phone_number]['timestamp']) <= 30:
                totp = pyotp.TOTP(app.config['otp_secrets'][phone_number]['secret'])
                if totp.verify(entered_otp):
                    student_id, name, profile_data, profile_image, class_timetable = student
                    profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": phone_number, "grade": "", "class": ""}  # Parse JSON or default
                    # Store user_id in session for chatbox
                    session['user_id'] = student_id
                    session['user_type'] = 'student'
                    session['name'] = name  # Store name for display
                    del app.config['otp_secrets'][phone_number]  # Clear secret after successful login
                    flash("Login successful", "success")
                    return jsonify({"message": "Login successful", "student_id": student_id, "name": name, "profile_data": profile_data, "profile_image": profile_image, "class_timetable": class_timetable})
                flash("Invalid OTP", "error")
                return jsonify({"error": "Invalid OTP"}), 401
            flash("OTP expired or not generated", "error")
            return jsonify({"error": "OTP expired or not generated"}), 401
        flash("OTP generated, enter it below", "success")
        return jsonify({"message": "OTP generated, enter it below"}), 200  # Return success to trigger OTP input
    flash("Phone number not found", "error")
    return jsonify({"error": "Phone number not found"}), 401

@app.route('/student/home')
@with_db
def student_home(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    cursor.execute('SELECT name, profile_data, profile_image, class_timetable FROM students WHERE id=?', (student_id,))
    student = cursor.fetchone()
    if student:
        name, profile_data, profile_image, class_timetable = student
        profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
        # Set unread notifications count in session
        cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,))
        profile_data_db_str = cursor.fetchone()[0]
        profile_data_db = json.loads(profile_data_db_str) if profile_data_db_str else {"notifications": []}  # Parse JSON or default
        if not isinstance(profile_data_db, dict):
            profile_data_db = {"notifications": []}  # Fallback
        unread_count = len([n for n in profile_data_db.get('notifications', []) if n not in session.get('read_notifications', [])])
        session['unread_notifications'] = unread_count
        return render_template('student_home.html', name=name, profile_data=profile_data, profile_image=profile_image, student_id=student_id, class_timetable=class_timetable, unread_notifications=unread_count)
    flash("Student not found", "error")
    return jsonify({"error": "Student not found"}), 404

@app.route('/student/profile', methods=['GET', 'POST'])
@with_db
def student_profile(cursor):
    student_id = request.args.get('student_id') or session.get('user_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    
    if request.method == 'POST':
        new_image = request.files['profile_image']
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
    if student:
        name, profile_data, profile_image, class_timetable = student
        profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
        cursor.execute('SELECT marks, remarks FROM test_results WHERE student_id = ? ORDER BY timestamp DESC', (student_id,))
        test_results = cursor.fetchall()
        cursor.execute('SELECT achievement, teacher_name, timestamp FROM extracurricular_updates WHERE student_id = ?', (student_id,))
        extracurricular_updates = cursor.fetchall()
        cursor.execute('SELECT status, date FROM attendance WHERE student_id = ? AND date = ?', (student_id, datetime.now().strftime('%Y-%m-%d')))
        attendance = cursor.fetchone()
        # Set unread notifications count in session
        cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,))
        profile_data_db_str = cursor.fetchone()[0]
        profile_data_db = json.loads(profile_data_db_str) if profile_data_db_str else {"notifications": []}  # Parse JSON or default
        if not isinstance(profile_data_db, dict):
            profile_data_db = {"notifications": []}  # Fallback
        unread_count = len([n for n in profile_data_db.get('notifications', []) if n not in session.get('read_notifications', [])])
        session['unread_notifications'] = unread_count
        return render_template('student_profile.html', name=name, profile_data=profile_data, profile_image=profile_image, student_id=student_id, class_timetable=class_timetable, test_results=test_results, extracurricular_updates=extracurricular_updates, attendance=attendance, unread_notifications=unread_count)
    flash("Student not found", "error")
    return jsonify({"error": "Student not found"}), 404

@app.route('/student/results')
@with_db
def student_results(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    cursor.execute('SELECT name, profile_data FROM students WHERE id=?', (student_id,))
    student = cursor.fetchone()
    if student:
        name, profile_data = student
        profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
        cursor.execute('''
            SELECT t.name, tr.marks, tr.remarks
            FROM test_results tr
            JOIN tests t ON tr.test_id = t.id
            WHERE tr.student_id = ?
            ORDER BY tr.timestamp DESC
        ''', (student_id,))
        test_results = cursor.fetchall()
        total_marks = sum(result[1] for result in test_results if result[1] is not None) if test_results else 0
        total_possible_marks = 600  # 100 per subject for 6 subjects
        # Set unread notifications count in session
        cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,))
        profile_data_db_str = cursor.fetchone()[0]
        profile_data_db = json.loads(profile_data_db_str) if profile_data_db_str else {"notifications": []}  # Parse JSON or default
        if not isinstance(profile_data_db, dict):
            profile_data_db = {"notifications": []}  # Fallback
        unread_count = len([n for n in profile_data_db.get('notifications', []) if n not in session.get('read_notifications', [])])
        session['unread_notifications'] = unread_count
        return render_template('student_results.html', name=name, profile_data=profile_data, student_id=student_id, test_results=test_results, total_marks=total_marks, total_possible_marks=total_possible_marks, unread_notifications=unread_count)
    flash("Student not found", "error")
    return jsonify({"error": "Student not found"}), 404

@app.route('/student/teachers_contact')
@with_db
def student_teachers_contact(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    cursor.execute('SELECT name, profile_data FROM students WHERE id=?', (student_id,))
    student = cursor.fetchone()
    if student:
        name, profile_data = student
        profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
        cursor.execute('SELECT name, phone_number, subject FROM teachers')
        teachers = cursor.fetchall()
        # Set unread notifications count in session
        cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,))
        profile_data_db_str = cursor.fetchone()[0]
        profile_data_db = json.loads(profile_data_db_str) if profile_data_db_str else {"notifications": []}  # Parse JSON or default
        if not isinstance(profile_data_db, dict):
            profile_data_db = {"notifications": []}  # Fallback
        unread_count = len([n for n in profile_data_db.get('notifications', []) if n not in session.get('read_notifications', [])])
        session['unread_notifications'] = unread_count
        return render_template('student_teachers_contact.html', name=name, profile_data=profile_data, student_id=student_id, teachers=teachers, unread_notifications=unread_count)
    flash("Student not found", "error")
    return jsonify({"error": "Student not found"}), 404

@app.route('/student/notifications')
@with_db
def student_notifications(cursor):
    student_id = request.args.get('student_id')
    if not student_id or not session.get('user_type') == 'student':
        flash("Access denied. Please log in as a student.", "error")
        return redirect('/')
    cursor.execute('SELECT profile_data FROM students WHERE id=?', (student_id,))
    profile_data_str = cursor.fetchone()[0]
    profile_data = json.loads(profile_data_str) if profile_data_str else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
    if not isinstance(profile_data, dict):
        profile_data = {"notifications": []}  # Fallback
    notifications = profile_data.get('notifications', [])
    # Clear unread count and mark all as read
    session['read_notifications'] = notifications
    session['unread_notifications'] = 0
    return render_template('student_notifications.html', notifications=notifications, student_id=student_id)

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
            # Store user_id in session for chatbox and dashboard
            session['user_id'] = email
            session['user_type'] = 'teacher'
            session['name'] = name  # Store name for display
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
    
    result = cursor.execute('SELECT subject FROM teachers WHERE email = ?', (teacher_email,)).fetchone()
    teacher_subject = result[0] if result else None
    if not teacher_subject:
        flash("Teacher not found or no subject assigned", "error")
        return jsonify({"error": "Teacher not found or no subject assigned"}), 404
    
    cursor.execute('SELECT id, name, profile_data, profile_image, class_timetable FROM students')
    students = cursor.fetchall()
    return render_template('teacher_dashboard.html', students=students, teacher_email=teacher_email, teacher_subject=teacher_subject)

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
    return render_template('teacher_academics.html', students=students, teacher_email=teacher_email, teacher_subject=teacher_subject)

@app.route('/teacher/student_profile')
@with_db
def teacher_student_profile(cursor):
    student_id = request.args.get('student_id')
    teacher_email = request.args.get('teacher_email') or session.get('user_id')
    if not teacher_email or not session.get('user_type') == 'teacher':
        flash("Access denied. Please log in as a teacher.", "error")
        return redirect('/teacher/login')
    
    cursor.execute('SELECT name, profile_data, profile_image, class_timetable FROM students WHERE id=?', (student_id,))
    student = cursor.fetchone()
    if student:
        name, profile_data, profile_image, class_timetable = student
        profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
        cursor.execute('SELECT t.name, tr.marks, tr.remarks FROM test_results tr JOIN tests t ON tr.test_id = t.id WHERE tr.student_id = ? ORDER BY tr.timestamp DESC', (student_id,))
        test_results = cursor.fetchall()
        cursor.execute('SELECT achievement, teacher_name, timestamp FROM extracurricular_updates WHERE student_id = ?', (student_id,))
        extracurricular_updates = cursor.fetchall()
        cursor.execute('SELECT status, date FROM attendance WHERE student_id = ? AND date = ?', (student_id, datetime.now().strftime('%Y-%m-%d')))
        attendance = cursor.fetchone()
        return render_template('teacher_student_profile.html', name=name, profile_data=profile_data, profile_image=profile_image, teacher_email=teacher_email, class_timetable=class_timetable, test_results=test_results, extracurricular_updates=extracurricular_updates, attendance=attendance)
    flash("Student not found", "error")
    return jsonify({"error": "Student not found"}), 404

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
    return render_template('teacher_resources.html', teacher_email=teacher_email, teacher_subject=teacher_subject, resource_logs=resource_logs)

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
        profile_data = json.loads(student[2]) if student[2] else {"class": "", "grade": "", "phone_number": "", "notifications": [], "messages": []}  # Parse JSON or default
        classes.add(f"{profile_data.get('grade', '')}{profile_data.get('class', '')}")
    return render_template('teacher_attendance.html', teacher_email=teacher_email, teacher_subject=teacher_subject, students=students, classes=sorted(classes))

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
    success, message = create_test(None, teacher_email, test_name, subject)
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
    result = cursor.execute('SELECT name FROM teachers WHERE email=?', (teacher_email,)).fetchone()
    teacher = result
    if not teacher or teacher[0] != "Nikhil":
        flash("Only Nikhil can update extracurricular achievements", "error")
        return jsonify({"error": "Only Nikhil can update extracurricular achievements"}), 403
    teacher_name = teacher[0]
    student_id = request.form['student_id']
    achievement = request.form['achievement']
    try:
        log_extracurricular_update(None, teacher_name, student_id, achievement)
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
        profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
        # Move message to notifications instead of messages
        notification = f"Message from {teacher_name} ({teacher_subject}): {message_text} (Sent on {timestamp})"
        profile_data.setdefault('notifications', []).append(notification)
        # Clear messages if any (ensuring no duplicates)
        profile_data['messages'] = []
        try:
            cursor.execute('UPDATE students SET profile_data=? WHERE id=?', (json.dumps(profile_data), student_id))
            get_db().commit()
            flash(f"Message sent to {student_name} as notification", "success")
            print(f"Notification added to {student_name}'s notifications: {notification}")  # Debug print
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
                    profile_data = json.loads(profile_data) if profile_data else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
                    # Move message to notifications instead of messages
                    notification = f"Message from {teacher_name} ({teacher_subject}): {message_text} (Sent on {timestamp})"
                    profile_data.setdefault('notifications', []).append(notification)
                    # Clear messages if any
                    profile_data['messages'] = []
                    cursor.execute('UPDATE students SET profile_data=? WHERE id=?', (json.dumps(profile_data), student_id))
                    print(f"Notification added to {student_name}'s notifications: {notification}")  # Debug print
            get_db().commit()
            flash(f"Message sent to {len(selected_students)} selected students as notifications", "success")
            return jsonify({"message": f"Message sent to {len(selected_students)} selected students as notifications"})
        except sqlite3.Error as e:
            flash(f"Error sending messages: {str(e)}", "error")
            return jsonify({"error": f"Error sending messages: {str(e)}"}), 500

    flash("Invalid message type", "error")
    return jsonify({"error": "Invalid message type"}), 400

# Chatbot route for real-time chatbox interactions
@app.route('/chatbot/send', methods=['POST'])
@with_db
def send_chat_message(cursor):
    try:
        user_message = request.form['message']
        user_type = session.get('user_type', 'student')
        user_id = session.get('user_id')

        if not user_type or not user_id:
            flash("User not logged in", "error")
            return jsonify({"error": "User not logged in"}), 401

        # Check if Ollama is running before calling generate_response
        if not check_ollama_health():
            flash("Ollama server is not running. Please start Ollama and pull the Mistral model.", "error")
            return jsonify({"error": "Ollama server is not running. Please start Ollama and pull the Mistral model."}), 500

        # Translate the prompt and message based on the chatbot's language setting
        language_prompt = translate_text("Respond in {language} only. ", CHATBOT_LANGUAGE).format(language=CHATBOT_LANGUAGE.capitalize())
        translated_message = translate_text(user_message, CHATBOT_LANGUAGE) if CHATBOT_LANGUAGE != 'en' else user_message
        response = generate_response(language_prompt + translated_message, user_type, user_id, CHATBOT_LANGUAGE)
        
        # Handle potential errors from generate_response
        if response.startswith("Error:"):
            print(f"Chatbot error from Ollama: {response}")
            error_msg = response.replace("Error: ", "").strip()
            if "Mistral model not found" in error_msg or "Ollama server not running" in error_msg:
                flash(f"Ollama error: {error_msg} Please ensure Ollama is running and the Mistral model is pulled.", "error")
                return jsonify({"error": f"Ollama error: {error_msg} Please ensure Ollama is running and the Mistral model is pulled."}), 500
            flash(f"Chatbot error: {error_msg}", "error")
            return jsonify({"error": f"Chatbot error: {error_msg}"}), 500
        else:
            translated_response = translate_text(response, 'en') if CHATBOT_LANGUAGE != 'en' else response

        if user_type == 'teacher' and user_id:
            # Teacher chatbot has full access
            if "update" in user_message.lower() and "marks" in user_message.lower():
                try:
                    import re
                    student_name_match = re.search(r"update (\w+)'s marks", user_message.lower())
                    if not student_name_match:
                        flash("Please specify the student's name, e.g., 'update Rohith's marks'", "error")
                        return jsonify({"response": "Please specify the student's name, e.g., 'update Rohith's marks'"})
                    student_name = student_name_match.group(1).capitalize()
                    cursor.execute('SELECT id FROM students WHERE name = ?', (student_name,))
                    student = cursor.fetchone()
                    if not student:
                        flash(f"Student {student_name} not found", "error")
                        return jsonify({"response": f"Student {student_name} not found"})
                    student_id = student[0]

                    marks_match = re.search(r"as (\d+)", user_message.lower())
                    remarks_match = re.search(r"and say (.*)", user_message.lower())
                    if not marks_match:
                        flash("Please specify the marks, e.g., 'update Rohith's marks as 100'", "error")
                        return jsonify({"response": "Please specify the marks, e.g., 'update Rohith's marks as 100'"})
                    marks = marks_match.group(1)
                    remarks = remarks_match.group(1) if remarks_match else None
                    if not remarks:
                        flash("What should the remark be?", "error")
                        return jsonify({"response": "What should the remark be?"})
                    
                    # Validate marks (0-100)
                    try:
                        marks = int(marks)
                        if not (0 <= marks <= 100):
                            flash("Marks must be between 0 and 100", "error")
                            return jsonify({"response": "Marks must be between 0 and 100"})
                    except ValueError:
                        flash("Marks must be a valid integer", "error")
                        return jsonify({"response": "Marks must be a valid integer"})
                    
                    result = cursor.execute('SELECT email, subject FROM teachers WHERE email = ?', (user_id,)).fetchone()
                    if not result:
                        flash("Teacher not found", "error")
                        return jsonify({"response": "Teacher not found"})
                    teacher_email, teacher_subject = result

                    success, message = update_test_results(None, teacher_email, "Default Test", student_id, marks, remarks)
                    if success:
                        log_resource_change(None, teacher_email, student_id, teacher_subject, "Chatbot Updated Marks/Results", f"Marks: {marks}, Remarks: '{remarks}'")
                        flash(f"Updated {student_name}'s marks to {marks} with remark: {remarks}", "success")
                        translated_response = f"Updated {student_name}'s marks to {marks} with remark: {remarks}"
                    else:
                        flash(message, "error")
                        translated_response = message
                except Exception as e:
                    flash(f"Error processing update: {str(e)}", "error")
                    return jsonify({"error": f"Error processing update: {str(e)}"}), 500

            elif "phone number" in user_message.lower() and "student" in user_message.lower():
                try:
                    student_name_match = re.search(r"phone number of (\w+)", user_message.lower())
                    if not student_name_match:
                        flash("Please specify the student's name, e.g., 'phone number of Alice'", "error")
                        return jsonify({"response": "Please specify the student's name, e.g., 'phone number of Alice'"})
                    student_name = student_name_match.group(1).capitalize()
                    cursor.execute('SELECT profile_data FROM students WHERE name = ?', (student_name,))
                    student = cursor.fetchone()
                    if not student:
                        flash(f"Student {student_name} not found", "error")
                        return jsonify({"response": f"Student {student_name} not found"})
                    profile_data = json.loads(student[0]) if student[0] else {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Parse JSON or default
                    phone = profile_data.get('phone_number', 'Not available')
                    flash(f"Phone number of {student_name}: {phone}", "success")
                    translated_response = f"Phone number of {student_name}: {phone}"
                except Exception as e:
                    flash(f"Error fetching phone number: {str(e)}", "error")
                    return jsonify({"error": f"Error fetching phone number: {str(e)}"}), 500

        # Student chatbot moves responses to notifications
        if user_type == 'student' and user_id:
            try:
                cursor.execute('SELECT profile_data FROM students WHERE id = ?', (user_id,))
                student = cursor.fetchone()
                if student:
                    profile_data_str = student[0]  # Fetch as string from database
                    try:
                        profile_data = json.loads(profile_data_str)  # Attempt to parse JSON
                    except json.JSONDecodeError:
                        # Handle invalid JSON (e.g., empty string, "null", or malformed JSON)
                        print(f"Invalid JSON in profile_data for student {user_id}: {profile_data_str}")
                        profile_data = {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}  # Default dictionary
                    if not isinstance(profile_data, dict):
                        # Fallback if parsing fails or data is not a dict
                        profile_data = {"notifications": [], "messages": [], "phone_number": "", "grade": "", "class": ""}
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    notification = f"Chatbot Response: {translated_response} (Received on {timestamp})"
                    profile_data.setdefault('notifications', []).append(notification)
                    profile_data['messages'] = []  # Clear messages
                    try:
                        cursor.execute('UPDATE students SET profile_data=? WHERE id=?', (json.dumps(profile_data), user_id))
                        get_db().commit()
                        flash("Notification added successfully", "success")
                        # Update unread notifications count in session
                        cursor.execute('SELECT profile_data FROM students WHERE id=?', (user_id,))
                        profile_data_db_str = cursor.fetchone()[0]
                        try:
                            profile_data_db = json.loads(profile_data_db_str)
                        except json.JSONDecodeError:
                            print(f"Invalid JSON in profile_data_db for student {user_id}: {profile_data_db_str}")
                            profile_data_db = {"notifications": []}  # Default for unread count
                        if not isinstance(profile_data_db, dict):
                            profile_data_db = {"notifications": []}  # Fallback
                        unread_count = len([n for n in profile_data_db.get('notifications', []) if n not in session.get('read_notifications', [])])
                        session['unread_notifications'] = unread_count
                    except sqlite3.Error as e:
                        flash(f"Error updating notifications: {str(e)}", "error")
                        return jsonify({"error": f"Error updating notifications: {str(e)}"}), 500
            except Exception as e:
                flash(f"Error processing student notification: {str(e)}", "error")
                return jsonify({"error": f"Error processing student notification: {str(e)}"}), 500

        flash("Response generated successfully", "success")
        return jsonify({"response": translated_response, "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')})

    except Exception as e:
        print(f"Unexpected error in send_chat_message: {e}")
        flash(f"Server error: {str(e)}", "error")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Serve uploaded profile images and resources (shared across roles)
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    try:
        return send_from_directory('uploads', filename)
    except Exception as e:
        flash(f"Error serving file: {str(e)}", "error")
        return jsonify({"error": f"File not found: {str(e)}"}), 404

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
    return render_template('hod_interface.html', students=students, teachers=teachers, json_parse=json.loads)

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

# Close database connections at app shutdown
@app.teardown_appcontext
def close_db(exception):
    if hasattr(_local, "conn"):
        _local.conn.close()
        del _local.conn

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)  # Single port for testing on one system