import os 
import io
import pandas as pd
from flask import Flask, render_template, request, redirect, session, send_file
from db_config import create_connection
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
app = Flask(__name__, template_folder='templates')
app.secret_key = "my-dev-secret-key"

def create_default_admin():
    conn = create_connection()
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
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # fetch departments for dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    if request.method == 'POST':
        name, email, password, role = (request.form[k] for k in ('name', 'email', 'password', 'role'))
        email = email.strip().lower()
        department = request.form.get('department', 'Unknown')
        
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            error = "Email already registered."
        else:
            hashed_password = pwd_context.hash(password)
            cursor.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                           (name, email, hashed_password, role))
            if role == 'student':
                cursor.execute("INSERT INTO students (name, email, department) VALUES (%s, %s, %s)", (name, email, department))
            conn.commit()
            message = "✅ Registration successful! You can now log in."

    cursor.close()
    conn.close()
    return render_template("register.html", message=message, error=error, departments=departments)

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

@app.route('/add-course', methods=['GET', 'POST'])
def add_course():
    if session.get('role') != 'teacher':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    message = error = None
    if request.method == 'POST':
        course_name = request.form['course_name']
        department = request.form.get('department', 'Unknown')
        try:
            cursor.execute("INSERT INTO courses (course_name, teacher_id, department) VALUES (%s, %s, %s)",
                           (course_name, session['user_id'], department))
            conn.commit()
            message = "✅ Course added successfully!"
        except Exception as e:
            error = f"❌ Error: {str(e)}"
    cursor.close()
    conn.close()
    return render_template('add_course.html', message=message, error=error)

@app.route('/admin/courses')
def manage_courses():
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT c.id, c.course_name, c.department, u.name AS teacher_name FROM courses c JOIN users u ON c.teacher_id = u.id")
    courses = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_courses.html", courses=courses)

@app.route('/admin/students-by-department')
def students_by_department():
    if session.get('role') != 'admin':
        return redirect('/login')

    selected_dept = request.args.get('department')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Get departments for dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    students = []
    if selected_dept and selected_dept != "All":
        cursor.execute("SELECT name, department FROM students WHERE department = %s", (selected_dept,))
        students = cursor.fetchall()
    elif selected_dept == "All":
        cursor.execute("SELECT name, department FROM students")
        students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "students_by_department.html",
        departments=departments,
        students=students,
        selected_dept=selected_dept
    )

@app.route('/add-grade', methods=['GET', 'POST'])
def add_grade():
    if session.get('role') != 'teacher':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Get teacher's courses and department
    cursor.execute("SELECT id, course_name, department FROM courses WHERE teacher_id = %s", (session['user_id'],))
    courses = cursor.fetchall()

    department = courses[0]['department'] if courses else None

    # Fetch students in same department
    cursor.execute("SELECT id, name FROM students WHERE department = %s", (department,))
    students = cursor.fetchall()

    message = error = None
    if request.method == 'POST':
        try:
            student_id = int(request.form['student_id'])
            course_id = int(request.form['course_id'])
            mid = float(request.form['mid_exam'])
            final = float(request.form['final_exam'])
            assignment = float(request.form['assignment'])
            quiz = float(request.form['quiz'])
            total = round(mid * 0.3 + final * 0.4 + assignment * 0.2 + quiz * 0.1, 2)

            cursor.execute("""
                INSERT INTO grades (student_id, course_id, mid_exam, final_exam, assignment, quiz, grade)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (student_id, course_id, mid, final, assignment, quiz, total))
            conn.commit()
            message = f"✅ Grade submitted successfully! Total: {total}"
        except Exception as e:
            error = f"❌ Error: {str(e)}"

    cursor.close()
    conn.close()
    return render_template('add_grade.html', students=students, courses=courses, message=message, error=error)

@app.route('/view-grades')
def view_grades():
    if session.get('role') != 'student':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM students WHERE email = %s", (session['email'],))
    student = cursor.fetchone()
    if not student:
        cursor.close()
        conn.close()
        return "Student not found."
    cursor.execute("""
        SELECT c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz, g.grade
        FROM grades g 
        JOIN courses c ON g.course_id = c.id 
        WHERE g.student_id = %s
    """, (student['id'],))
    grades = cursor.fetchall()

    def grade_to_letter(g):
        if g is None:
            return "-"
        g = float(g)
        if g >= 90: return "A+"
        elif g >= 80: return "A"
        elif g >= 70: return "B+"
        elif g >= 60: return "B"
        elif g >= 50: return "C"
        else: return "F"

    cleaned_grades = []
    for g in grades:
        mid = g.get('mid_exam') or 0
        final = g.get('final_exam') or 0
        assignment = g.get('assignment') or 0
        quiz = g.get('quiz') or 0
        total = mid + final + assignment + quiz
        cleaned_grades.append({
            'course_name': g['course_name'],
            'mid_exam': mid,
            'final_exam': final,
            'assignment': assignment,
            'quiz': quiz,
            'total_grade': total,
            'letter': grade_to_letter(total)
        })
    average = round(sum(g['total_grade'] for g in cleaned_grades) / len(cleaned_grades), 2) if cleaned_grades else None
    cursor.close()
    conn.close()
    return render_template('view_grades.html', grades=cleaned_grades, name=session['name'], average=average)

@app.route('/admin/view-all-grades')
def view_all_grades():
    if session.get('role') != 'admin':
        return redirect('/login')

    selected_dept = request.args.get('department')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Load all departments for filter dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    # Query grades filtered by department
    if selected_dept and selected_dept != "All":
        cursor.execute("""
            SELECT s.name AS student_name, s.email, s.department, 
                   c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz, g.grade
            FROM grades g
            JOIN students s ON g.student_id = s.id
            JOIN courses c ON g.course_id = c.id
            WHERE s.department = %s
        """, (selected_dept,))
    else:
        cursor.execute("""
            SELECT s.name AS student_name, s.email, s.department, 
                   c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz, g.grade
            FROM grades g
            JOIN students s ON g.student_id = s.id
            JOIN courses c ON g.course_id = c.id
        """)

    grades = cursor.fetchall()
    cursor.close()
    conn.close()

    def letter(g):
        if g is None:
            return "-"
        g = float(g)
        if g >= 90: return "A+"
        elif g >= 80: return "A"
        elif g >= 70: return "B+"
        elif g >= 60: return "B"
        elif g >= 50: return "C"
        else: return "F"

    for row in grades:
        total = round((row['mid_exam'] or 0) + (row['final_exam'] or 0) +
                      (row['assignment'] or 0) + (row['quiz'] or 0), 2)
        row['total'] = total
        row['letter'] = letter(total)

    return render_template("admin_all_grades.html", grades=grades, departments=departments, selected_dept=selected_dept)

@app.route('/download-grades')
def download_grades():
    if session.get('role') != 'student':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM students WHERE email = %s", (session['email'],))
    student = cursor.fetchone()
    cursor.execute("""
        SELECT c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz, g.grade
        FROM grades g
        JOIN courses c ON g.course_id = c.id
        WHERE g.student_id = %s
    """, (student['id'],))
    grades = cursor.fetchall()
    cursor.close()
    conn.close()
    df = pd.DataFrame(grades)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"{session['name']}_grades.xlsx", as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/students')
def admin_students():
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_students.html", students=students)

@app.route('/admin/teachers')
def admin_teachers():
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE role = 'teacher'")
    teachers = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_teachers.html", teachers=teachers)

@app.route('/admin/departments', methods=['GET', 'POST'])
def manage_departments():
    if session.get('role') != 'admin':
        return redirect('/login')
    
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    message = error = None

    if request.method == 'POST':
        dept_name = request.form['department_name'].strip()
        try:
            cursor.execute("INSERT INTO departments (name) VALUES (%s)", (dept_name,))
            conn.commit()
            message = "✅ Department added successfully!"
        except Exception as e:
            error = f"❌ {str(e)}"

    cursor.execute("SELECT * FROM departments")
    departments = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_departments.html", departments=departments, message=message, error=error)

@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect('/login')
    return render_template('admin_dashboard.html', name=session['name'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    create_default_admin()
    app.run(debug=True)
