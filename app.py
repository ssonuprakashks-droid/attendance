from flask import Flask, render_template, request, redirect, session, jsonify, flash
from datetime import datetime
import sqlite3
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'attendance_tracker_secret_key_2026'
app.config['DATABASE'] = 'attendance.db'

# Database initialization
def init_db():
    """Initialize database with required tables"""
    if not os.path.exists(app.config['DATABASE']):
        with sqlite3.connect(app.config['DATABASE']) as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    email TEXT,
                    full_name TEXT,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Attendance table
            cursor.execute('''
                CREATE TABLE attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    check_in TIMESTAMP,
                    check_out TIMESTAMP,
                    date DATE,
                    status TEXT DEFAULT 'present',
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Add default admin user
            cursor.execute('''
                INSERT INTO users (username, password, email, full_name, role)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', 'admin123', 'admin@attendance.com', 'Admin User', 'admin'))
            
            conn.commit()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def get_user_by_username(username):
    """Get user from database by username"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        return cursor.fetchone()

def get_user_by_id(user_id):
    """Get user from database by ID"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()

# Routes
@app.route("/")
def index():
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
        return render_template("index.html", user=user)
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Username and password are required", "error")
            return render_template("login.html")
        
        user = get_user_by_username(username)
        
        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f"Welcome, {user['full_name']}!", "success")
            return redirect("/")
        else:
            flash("Invalid username or password", "error")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "info")
    return redirect("/login")

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session['user_id']
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get today's attendance
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT * FROM attendance 
            WHERE user_id = ? AND date = ?
            ORDER BY check_in DESC
        ''', (user_id, today))
        today_attendance = cursor.fetchone()
        
        # Get attendance stats
        cursor.execute('''
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present,
                   SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as absent,
                   SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late
            FROM attendance WHERE user_id = ?
        ''', (user_id,))
        stats = cursor.fetchone()
    
    user = get_user_by_id(user_id)
    return render_template("dashboard.html", user=user, today_attendance=today_attendance, stats=stats)

@app.route("/check-in", methods=["POST"])
@login_required
def check_in():
    user_id = session['user_id']
    today = datetime.now().strftime('%Y-%m-%d')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        
        # Check if already checked in today
        cursor.execute('''
            SELECT id FROM attendance 
            WHERE user_id = ? AND date = ?
        ''', (user_id, today))
        
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Already checked in today'}), 400
        
        cursor.execute('''
            INSERT INTO attendance (user_id, check_in, date, status)
            VALUES (?, ?, ?, 'present')
        ''', (user_id, now, today))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Check-in successful', 'time': now})

@app.route("/check-out", methods=["POST"])
@login_required
def check_out():
    user_id = session['user_id']
    today = datetime.now().strftime('%Y-%m-%d')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE attendance 
            SET check_out = ?
            WHERE user_id = ? AND date = ? AND check_out IS NULL
        ''', (now, user_id, today))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'No active check-in found'}), 400
    
    return jsonify({'success': True, 'message': 'Check-out successful', 'time': now})

@app.route("/reports")
@login_required
def reports():
    user_id = session['user_id']
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM attendance 
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 30
        ''', (user_id,))
        attendance_records = cursor.fetchall()
    
    user = get_user_by_id(user_id)
    return render_template("reports.html", user=user, records=attendance_records)

@app.route("/api/attendance-summary")
@login_required
def attendance_summary():
    user_id = session['user_id']
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM attendance 
            WHERE user_id = ?
            GROUP BY status
        ''', (user_id,))
        
        summary = {row[0]: row[1] for row in cursor.fetchall()}
    
    return jsonify(summary)

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template("500.html"), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True)