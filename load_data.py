import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
import os

# Connect to the database
conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# Create tables (ensure they match app.py's create_tables)
cursor.executescript("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        subject TEXT,
        phone_number TEXT DEFAULT NULL
    );
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_data TEXT,
        profile_image TEXT DEFAULT 'default.jpg',
        class_timetable TEXT DEFAULT '10B.jpg'
    );
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
    );
    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        subject TEXT,
        teacher_email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        max_marks INTEGER DEFAULT 20,
        FOREIGN KEY (teacher_email) REFERENCES teachers(email)
    );
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_id INTEGER,
        student_id INTEGER,
        marks INTEGER,
        remarks TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (test_id) REFERENCES tests(id),
        FOREIGN KEY (student_id) REFERENCES students(id)
    );
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
    );
    CREATE TABLE IF NOT EXISTS extracurricular_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        teacher_name TEXT,
        achievement TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );
    CREATE TABLE IF NOT EXISTS holidays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE,
        description TEXT
    );
""")

# Helper function to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Function to load JSON data with custom path option
def load_json_data(file_path='student_data.json'):
    possible_paths = [
        file_path,  # Default or specified path
        os.path.join(os.getcwd(), file_path),  # Current working directory
        os.path.abspath(file_path)  # Absolute path
    ]
    
    for path in possible_paths:
        try:
            if os.path.exists(path):
                with open(path, 'r') as file:
                    return json.load(file)
        except (IOError, OSError) as e:
            continue
    
    raise FileNotFoundError(f"Could not find 'student_data.json' at any of the following paths: {', '.join(possible_paths)}. Please ensure the file exists and the path is correct.")

# Load student data from student_data.json
try:
    data = load_json_data()
except FileNotFoundError as e:
    print(e)
    exit(1)
except json.JSONDecodeError as e:
    print(f"Error: student_data.json is invalid or corrupted. Please check the file format. Error: {e}")
    exit(1)

# Insert teachers from student_data.json
teachers = data.get('teachers', [])
for teacher in teachers:
    name = teacher.get('name', 'Unknown')
    email = teacher.get('email', f"{name.lower().replace(' ', '.')}.teacher@cambridge.edu.in")
    password = teacher.get('password', 'defaultpass123')
    subject = teacher.get('subject', 'Math')
    phone_number = teacher.get('phone_number', f"98765432{teachers.index(teacher)}")
    cursor.execute('INSERT OR IGNORE INTO teachers (name, email, password, subject, phone_number) VALUES (?, ?, ?, ?, ?)',
                   (name, email, hash_password(password), subject, phone_number))

# Insert students from student_data.json
students = data.get('students', [])
for student in students:
    name = student.get('name', 'Unknown')
    phone_number = student.get('phone_number', f"12345678{students.index(student)}")
    password = student.get('password', 'defaultpass123')
    profile_data = json.dumps(student.get('profile_data', {
        "phone_number": phone_number,
        "grade": "10",
        "class": "B",
        "notifications": [],
        "messages": []
    }))
    profile_image = student.get('profile_image', 'default.jpg')
    class_timetable = student.get('class_timetable', '10B.jpg')
    # Generate a unique email based on name if not provided
    email = f"{name.lower().replace(' ', '.')}.student@school.edu"
    cursor.execute('INSERT OR IGNORE INTO students (name, email, password, profile_data, profile_image, class_timetable) VALUES (?, ?, ?, ?, ?, ?)',
                   (name, email, hash_password(password), profile_data, profile_image, class_timetable))

# Insert sample tests (created by teachers, using the teacher from student_data.json)
tests = [
    ("FA-1", "Math", "rohith@cambridge.edu.in"),
    ("FA-2", "Math", "rohith@cambridge.edu.in"),
    ("FA-3", "Math", "rohith@cambridge.edu.in"),
]

for name, subject, teacher_email in tests:
    cursor.execute('INSERT OR IGNORE INTO tests (name, subject, teacher_email, max_marks) VALUES (?, ?, ?, ?)',
                   (name, subject, teacher_email, 20))

# Insert sample test results for students (using student IDs from the inserted students)
test_results = []
for i, (test_id, student_index, marks, remarks) in enumerate([
    (1, 0, 18, "Good performance"),  # Alice Smith in FA-1 Math
    (2, 0, 15, "Needs improvement"),  # Alice Smith in FA-2 Math
    (3, 0, 17, "Excellent work"),     # Alice Smith in FA-3 Math
    (1, 1, 16, "Steady progress"),    # Bob Johnson in FA-1 Math
    (2, 1, 14, "Average"),            # Bob Johnson in FA-2 Math
    (3, 1, 19, "Outstanding"),        # Bob Johnson in FA-3 Math
    (1, 2, 15, "Fair performance"),   # Charlie Brown in FA-1 Math
    (2, 2, 16, "Good progress"),      # Charlie Brown in FA-2 Math
    (3, 2, 14, "Needs improvement"),  # Charlie Brown in FA-3 Math
    (1, 3, 17, "Excellent"),          # Diana Prince in FA-1 Math
    (2, 3, 18, "Very good"),          # Diana Prince in FA-2 Math
    (3, 3, 16, "Good"),               # Diana Prince in FA-3 Math
    (1, 4, 14, "Average"),            # Eve Adams in FA-1 Math
    (2, 4, 15, "Fair"),               # Eve Adams in FA-2 Math
    (3, 4, 13, "Needs work"),         # Eve Adams in FA-3 Math
    (1, 5, 19, "Outstanding"),        # Frank Wilson in FA-1 Math
    (2, 5, 20, "Perfect"),            # Frank Wilson in FA-2 Math
    (3, 5, 18, "Great"),              # Frank Wilson in FA-3 Math
    (1, 6, 16, "Good progress"),      # Grace Lee in FA-1 Math
    (2, 6, 17, "Very good"),          # Grace Lee in FA-2 Math
    (3, 6, 15, "Fair"),               # Grace Lee in FA-3 Math
    (1, 7, 15, "Average"),            # Henry Clark in FA-1 Math
    (2, 7, 16, "Good"),               # Henry Clark in FA-2 Math
    (3, 7, 14, "Needs improvement"),  # Henry Clark in FA-3 Math
    (1, 8, 18, "Excellent"),          # Ivy Parker in FA-1 Math
    (2, 8, 19, "Outstanding"),        # Ivy Parker in FA-2 Math
    (3, 8, 17, "Very good"),          # Ivy Parker in FA-3 Math
    (1, 9, 16, "Good progress"),      # Jack Turner in FA-1 Math
    (2, 9, 15, "Fair"),               # Jack Turner in FA-2 Math
    (3, 9, 17, "Good"),               # Jack Turner in FA-3 Math
]):
    cursor.execute('SELECT id FROM students LIMIT 1 OFFSET ?', (student_index,))
    student_id = cursor.fetchone()[0]
    test_results.append((test_id, student_id, marks, remarks))

for test_id, student_id, marks, remarks in test_results:
    cursor.execute('INSERT OR IGNORE INTO test_results (test_id, student_id, marks, remarks) VALUES (?, ?, ?, ?)',
                   (test_id, student_id, marks, remarks))

# Insert sample attendance records (for today and recent days, using student IDs from the inserted students)
current_date = datetime.now().strftime('%Y-%m-%d')
recent_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(5)]
attendance_data = []
for i, (student_index, class_name, date, status, teacher_email) in enumerate([
    (0, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Alice Smith
    (1, "10B", current_date, "Absent", "rohith@cambridge.edu.in"),   # Bob Johnson
    (2, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Charlie Brown
    (3, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Diana Prince
    (4, "10B", current_date, "Absent", "rohith@cambridge.edu.in"),   # Eve Adams
    (5, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Frank Wilson
    (6, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Grace Lee
    (7, "10B", current_date, "Absent", "rohith@cambridge.edu.in"),   # Henry Clark
    (8, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Ivy Parker
    (9, "10B", current_date, "Present", "rohith@cambridge.edu.in"),  # Jack Turner
]):
    cursor.execute('SELECT id FROM students LIMIT 1 OFFSET ?', (student_index,))
    student_id = cursor.fetchone()[0]
    attendance_data.append((student_id, class_name, date, status, teacher_email))

for student_id, class_name, date, status, teacher_email in attendance_data:
    cursor.execute('INSERT OR IGNORE INTO attendance (student_id, class_name, date, status, teacher_email) VALUES (?, ?, ?, ?, ?)',
                   (student_id, class_name, date, status, teacher_email))

# Insert sample extracurricular updates (only Rohith can update, using student IDs from the inserted students)
extracurricular_updates = [
    (0, "Rohith", "Won first prize in math Olympiad", datetime.now() - timedelta(days=10)),  # Alice Smith
    (1, "Rohith", "Participated in science fair", datetime.now() - timedelta(days=5)),      # Bob Johnson
    (2, "Rohith", "Excelled in debate competition", datetime.now() - timedelta(days=3)),    # Charlie Brown
    (3, "Rohith", "Led the sports team", datetime.now() - timedelta(days=7)),              # Diana Prince
    (4, "Rohith", "Won art contest", datetime.now() - timedelta(days=4)),                  # Eve Adams
    (5, "Rohith", "Top performer in coding club", datetime.now() - timedelta(days=6)),     # Frank Wilson
    (6, "Rohith", "Music band leader", datetime.now() - timedelta(days=2)),                # Grace Lee
    (7, "Rohith", "Volunteered for community service", datetime.now() - timedelta(days=8)), # Henry Clark
    (8, "Rohith", "Chess champion", datetime.now() - timedelta(days=1)),                   # Ivy Parker
    (9, "Rohith", "Drama club star", datetime.now() - timedelta(days=9)),                  # Jack Turner
]

for student_index, teacher_name, achievement, timestamp in extracurricular_updates:
    cursor.execute('SELECT id FROM students LIMIT 1 OFFSET ?', (student_index,))
    student_id = cursor.fetchone()[0]
    cursor.execute('INSERT OR IGNORE INTO extracurricular_updates (student_id, teacher_name, achievement, timestamp) VALUES (?, ?, ?, ?)',
                   (student_id, teacher_name, achievement, timestamp))

# Insert sample holidays (from student_leaves.html)
holidays = {
    "2024-06-08": "Second Saturday",
    "2024-06-17": "Bakrid",
    "2024-06-22": "Fourth Saturday",
    "2024-07-13": "Second Saturday",
    "2024-07-17": "Muharram",
    "2024-07-27": "Fourth Saturday",
    "2024-08-10": "Second Saturday",
    "2024-08-15": "Independence Day",
    "2024-08-24": "Fourth Saturday",
    "2024-08-26": "Janmashtami",
    "2024-09-14": "Second Saturday",
    "2024-09-16": "Eid e Milad",
    "2024-09-28": "Fourth Saturday",
    "2024-10-02": "Gandhi Jayanti",
    "2024-10-12": "Second Saturday",
    "2024-10-13": "Vijaya Dashami",
    "2024-10-26": "Fourth Saturday",
    "2024-11-09": "Second Saturday",
    "2024-11-15": "Guru Nanak Jayanti",
    "2024-11-23": "Fourth Saturday",
    "2024-12-14": "Second Saturday",
    "2024-12-25": "Christmas Day",
    "2024-12-28": "Fourth Saturday",
    "2025-01-11": "Second Saturday",
    "2025-01-25": "Fourth Saturday",
    "2025-01-26": "Republic Day",
    "2025-02-08": "Second Saturday",
    "2025-02-22": "Fourth Saturday",
    "2025-02-26": "Maha Shivaratri",
    "2025-03-08": "Second Saturday",
    "2025-03-14": "Holi",
    "2025-03-22": "Fourth Saturday"
}

for date, description in holidays.items():
    cursor.execute('INSERT OR IGNORE INTO holidays (date, description) VALUES (?, ?)', (date, description))

# Commit changes and close connection
conn.commit()
cursor.close()
conn.close()

print("Database 'school.db' populated with sample data from student_data.json successfully.")