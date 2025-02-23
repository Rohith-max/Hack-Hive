import sqlite3
import json
import os

# Connect to or create a new database
conn = sqlite3.connect('school.db')
cursor = conn.cursor()

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

# Load data from JSON file
with open('school_data.json', 'r') as file:
    data = json.load(file)

# Insert teachers
for teacher in data['teachers']:
    cursor.execute('INSERT INTO teachers (name, email, password, subject, phone_number) VALUES (?, ?, ?, ?, ?)',
                   (teacher['name'], teacher['email'], teacher['password'], teacher['subject'], teacher['phone_number']))
conn.commit()

# Insert students
for student in data['students']:
    cursor.execute('INSERT INTO students (name, email, password, profile_data, profile_image, class_timetable) VALUES (?, ?, ?, ?, ?, ?)',
                   (student['name'], student['email'], student['password'], json.dumps(student['profile_data']), student['profile_image'], student['class_timetable']))
conn.commit()

print("Database initialized and populated with data from school_data.json")
conn.close()