import os
import io
import pandas as pd
from functools import wraps
from flask import Flask, render_template, request, redirect, session, send_file
from db_config import create_connection
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
app = Flask(__name__, template_folder='templates')
app.secret_key = "my-dev-secret-key"

# Role-based access decorator
def role_required(role):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != role:
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def create_default_admin():
    conn = create_connection()
    if conn is None:
        print("❌ DB connection failed while creating default admin.")
        return
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", ('admin@site.com',))
    if not cursor.fetchone():
        hashed_pw = pwd_context.hash('admin123')
        cursor.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                       ('Admin', 'admin@site.com', hashed_pw, 'admin'))
        conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        conn = create_connection()
        if conn is None:
            return "❌ Database connection failed."
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user and pwd_context.verify(password, user['password']):
            session.update({'user_id': user['id'], 'role': user['role'], 'name': user['name'], 'email': user['email']})
            return redirect('/dashboard')
        else:
            error = 'Invalid email or password'
        cursor.close()
        conn.close()
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    message = error = None
    if request.method == 'POST':
        name, email, password, role = (request.form[k] for k in ('name', 'email', 'password', 'role'))
        email = email.strip().lower()
        conn = create_connection()
        if conn is None:
            return "❌ Database connection failed."
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            error = "Email already registered."
        else:
            hashed_password = pwd_context.hash(password)
            cursor.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                           (name, email, hashed_password, role))
            if role == 'student':
                cursor.execute("INSERT INTO students (name, email) VALUES (%s, %s)", (name, email))
            conn.commit()
            message = "✅ Registration successful! You can now log in."
        cursor.close()
        conn.close()
    return render_template("register.html", message=message, error=error)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    role = session['role']
    if role == 'student':
        return render_template('dashboard.html', name=session['name'])
    elif role == 'teacher':
        return render_template('teacher_dashboard.html', name=session['name'])
    elif role == 'admin':
        return render_template('admin_dashboard.html', name=session['name'])
    return redirect('/login')

@app.route('/admin')
@role_required('admin')
def admin():
    return render_template('admin_dashboard.html', name=session['name'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    create_default_admin()
    app.run(debug=True)
