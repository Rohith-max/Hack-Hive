# School Management System

A simple Flask-based system for managing students, teachers, and HODs, with a chatbot powered by Ollama’s Mistral model and SQLite storage.

## Overview
This project offers login for students (via phone/OTP), teachers (via email/password), and HOD for management, plus a multilingual chatbot for queries and tasks.

## Prerequisites
- Python 3.8+, Git, Ollama (install via [ollama.com](https://ollama.com/), pull `mistral` model)
- Dependencies: `pip install flask requests deep_translator pyotp`

## Setup
1. Clone: `git clone https://github.com/your-username/school-management-system.git`
2. Navigate: `cd school-management-system`
3. Install: `pip install -r requirements.txt` (create with `pip freeze > requirements.txt`)
4. Start Ollama: `ollama serve && ollama pull mistral`
5. Populate DB: `python load_data.py`
6. Run: `python app.py`

## Usage
- Student: `http://localhost:5000/` (phone: 1234567890, OTP via terminal)
- Teacher: `http://localhost:5000/teacher/login` (email: rohith@cambridge.edu.in, password: rohithpass123)
- HOD: `http://localhost:5000/hod/` (implement login as needed)
- Chatbot: Use chatbox on any page for queries (e.g., “What’s my schedule?”) or commands.
