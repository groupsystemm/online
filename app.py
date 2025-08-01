import os
import io
import pandas as pd
from flask import Flask, render_template, request, redirect, session, send_file, url_for
from db_config import create_connection
from passlib.context import CryptContext
from werkzeug.utils import secure_filename

# --- Flask Setup ---
app = Flask(__name__, template_folder='templates')
app.secret_key = "my-dev-secret-key"

# --- Upload Config ---
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# --- Default Admin Setup ---
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


# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    # ✅ Clear session when visiting login (especially for GET)
    if request.method == 'GET':
        session.clear()

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        conn = create_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user and pwd_context.verify(password, user['password']):
            session.update({
                'user_id': user['id'],
                'role': user['role'],
                'name': user['name'],
                'email': user['email']
            })
            return redirect('/dashboard')
        else:
            error = 'Invalid email or password'
        cursor.close()
        conn.close()

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch departments for dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    # Add academic years: 2014 up to 2022
    years = [str(y) for y in range(2014, 2023)]

    error = None
    message = None
    selected_role = ''

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email'].strip().lower()
        password = request.form['password']
        role = request.form['role']
        selected_role = role
        department = request.form.get('department') if role in ['student', 'teacher'] else None
        year = request.form.get('year') if role == 'student' else None

        # Validation
        if role in ['student', 'teacher'] and (not department or department.strip() == ''):
            error = "Please select a department."
        elif role == 'student' and (not year or year.strip() == ''):
            error = "Please select a year."
        else:
            try:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    error = "Email already exists."
                else:
                    hashed_pw = pwd_context.hash(password)
                    cursor.execute(
                        "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                        (name, email, hashed_pw, role)
                    )

                    if role == 'student':
                        cursor.execute(
                            "INSERT INTO students (name, email, department, year) VALUES (%s, %s, %s, %s)",
                            (name, email, department, year)
                        )
                    elif role == 'teacher':
                        cursor.execute(
                            "INSERT INTO teachers (name, email, department) VALUES (%s, %s, %s)",
                            (name, email, department)
                        )

                    conn.commit()
                    message = "✅ Registered successfully!"
            except Exception as e:
                conn.rollback()
                error = f"An error occurred: {str(e)}"

    cursor.close()
    conn.close()
    return render_template(
        'register.html',
        error=error,
        message=message,
        departments=departments,
        selected_role=selected_role,
        years=years  # pass year list to template
    )

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

    # Fetch departments for dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    if request.method == 'POST':
        course_name = request.form['course_name']
        department = request.form.get('department')
        course_code = request.form.get('course_code') or None
        credit_hours = request.form.get('credit_hours')
        credit_hours = int(credit_hours) if credit_hours else None
        entering_year = request.form.get('entering_year') or None
        section = request.form.get('section') or None
        semester = request.form.get('semester') or None

        try:
            cursor.execute("""
                INSERT INTO courses (course_name, course_code, credit_hours, entering_year, section, semester, teacher_id, department)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (course_name, course_code, credit_hours, entering_year, section, semester, session['user_id'], department))
            conn.commit()
            message = "✅ Course added successfully!"
        except Exception as e:
            error = f"❌ Error: {str(e)}"

    cursor.close()
    conn.close()
    return render_template('add_course.html', message=message, error=error, departments=departments)
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/login')
    return render_template('admin_dashboard.html')

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

    # Get all departments
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    students = []
    if selected_dept and selected_dept != "All":
        cursor.execute("SELECT id, name, department FROM students WHERE department = %s", (selected_dept,))
        students = cursor.fetchall()
    elif selected_dept == "All":
        cursor.execute("SELECT id, name, department FROM students")
        students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "students_by_department.html",
        all_departments=departments,
        students=students,
        selected_dept=selected_dept
    )


@app.route('/add-grade', methods=['GET', 'POST'])
def add_grade():
    if session.get('role') != 'teacher':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Get all departments
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    selected_department = request.args.get('department')

    # Get teacher's courses filtered by department if selected
    if selected_department:
        cursor.execute(
            "SELECT id, course_name, department FROM courses WHERE teacher_id = %s AND department = %s",
            (session['user_id'], selected_department)
        )
    else:
        cursor.execute(
            "SELECT id, course_name, department FROM courses WHERE teacher_id = %s",
            (session['user_id'],)
        )
    courses = cursor.fetchall()

    # Determine which department's students to show
    dept_for_students = selected_department or (courses[0]['department'] if courses else None)

    if dept_for_students:
        cursor.execute("SELECT id, name FROM students WHERE department = %s", (dept_for_students,))
        students = cursor.fetchall()
    else:
        students = []

    message = error = None

    if request.method == 'POST':
        try:
            student_id = int(request.form['student_id'])
            course_id = int(request.form['course_id'])
            semester = request.form['semester']
            mid_exam = float(request.form['mid_exam'])
            final_exam = float(request.form['final_exam'])
            assignment = float(request.form['assignment'])
            quiz = float(request.form['quiz'])

            # 🔁 Total = Simple Sum (not percentage)
            total_grade = round(mid_exam + final_exam + assignment + quiz, 2)

            # Insert the grade record
            cursor.execute("""
                INSERT INTO grades (student_id, course_id, semester, mid_exam, final_exam, assignment, quiz, grade)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (student_id, course_id, semester, mid_exam, final_exam, assignment, quiz, total_grade))
            conn.commit()

            message = f"✅ Grade submitted successfully! Total: {total_grade}"
        except Exception as e:
            error = f"❌ Error: {str(e)}"

    cursor.close()
    conn.close()

    return render_template(
        'add_grade.html',
        departments=departments,
        selected_dept=selected_department,
        students=students,
        courses=courses,
        message=message,
        error=error
    )


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
    message = request.args.get('message')
    error = request.args.get('error')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Get all departments for filter dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    # Build query for grades with optional department filter
    query = """
        SELECT s.id AS student_id, c.id AS course_id,
               s.name AS student_name, s.email, s.department, 
               c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz, g.grade,
               cm.comment
        FROM grades g
        JOIN students s ON g.student_id = s.id
        JOIN courses c ON g.course_id = c.id
        LEFT JOIN comments cm ON cm.student_id = g.student_id AND cm.course_id = g.course_id
    """
    params = []

    if selected_dept and selected_dept != "All":
        query += " WHERE s.department = %s"
        params.append(selected_dept)

    cursor.execute(query, params)
    grades = cursor.fetchall()

    cursor.close()
    conn.close()

    # Add total and letter grade
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

    return render_template(
        "admin_all_grades.html",
        grades=grades,
        departments=departments,
        selected_dept=selected_dept,
        message=message,
        error=error
    )


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
    selected_year = request.args.get('year')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Prepare base query and params
    query = "SELECT u.id, u.name, u.email, u.role, s.year FROM users u LEFT JOIN students s ON u.email = s.email WHERE u.role = 'student'"
    params = []

    if selected_year and selected_year != "All":
        query += " AND s.year = %s"
        params.append(selected_year)

    cursor.execute(query, params)
    students = cursor.fetchall()

    # Also pass years for dropdown (2014-2023 + 'All')
    years = ['All'] + [str(y) for y in range(2014, 2024)]

    cursor.close()
    conn.close()
    return render_template("admin_students.html", students=students, years=years, selected_year=selected_year)

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
        dept_name = request.form.get('department_name', '').strip()
        if dept_name:
            try:
                cursor.execute("INSERT INTO departments (name) VALUES (%s)", (dept_name,))
                conn.commit()
                message = "✅ Department added successfully!"
            except Exception as e:
                error = f"❌ {str(e)}"
        else:
            error = "❌ Department name cannot be empty."

    cursor.execute("SELECT * FROM departments ORDER BY id")
    departments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_departments.html", departments=departments, message=message, error=error)


@app.route('/admin/delete-department/<int:dept_id>')
def delete_department(dept_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM departments WHERE id = %s", (dept_id,))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return redirect('/admin/departments')


@app.route('/admin/edit-department/<int:dept_id>', methods=['GET', 'POST'])
def edit_department(dept_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM departments WHERE id = %s", (dept_id,))
    department = cursor.fetchone()

    if not department:
        cursor.close()
        conn.close()
        return "❌ Department not found"

    message = error = None

    if request.method == 'POST':
        new_name = request.form['department_name'].strip()
        try:
            cursor.execute("UPDATE departments SET name = %s WHERE id = %s", (new_name, dept_id))
            conn.commit()
            message = "✅ Department updated successfully!"
            department['name'] = new_name
        except Exception as e:
            conn.rollback()
            error = f"❌ {str(e)}"

    cursor.close()
    conn.close()
    return render_template("edit_department.html", department=department, message=message, error=error)



@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect('/login')
    return render_template('admin_dashboard.html', name=session['name'])
@app.route('/admin/delete-student/<int:user_id>', methods=['GET'])
def delete_student(user_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM students WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s AND role = 'student'", (user_id,))
        conn.commit()
        message = "✅ Student deleted successfully!"
    except Exception as e:
        conn.rollback()
        message = f"❌ Error deleting student: {str(e)}"
    finally:
        cursor.close()
        conn.close()

    return redirect(f"/admin/students?message={message}")


@app.route('/admin/edit-student/<int:user_id>', methods=['GET', 'POST'])
def edit_student(user_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    # Get departments for dropdown
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    # Get student info joining by email, linking users and students
    cursor.execute("""
        SELECT u.id, u.name, u.email, s.year, s.department
        FROM users u
        LEFT JOIN students s ON u.email = s.email
        WHERE u.id = %s AND u.role = 'student'
    """, (user_id,))
    student = cursor.fetchone()

    # Redirect to students list if student not found (instead of showing error)
    if not student:
        cursor.close()
        conn.close()
        return redirect('/admin/students?error=Student+not+found')

    message = error = None
    years = [str(y) for y in range(2014, 2025)]

    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            email = request.form['email'].strip().lower()
            year = request.form.get('year')
            department = request.form.get('department')

            # Update users table (name and email)
            cursor.execute("UPDATE users SET name=%s, email=%s WHERE id=%s", (name, email, user_id))

            # Update students table (name, email, year, department) by old email
            cursor.execute("""
                UPDATE students
                SET name=%s, email=%s, year=%s, department=%s
                WHERE email=%s
            """, (name, email, year, department, student['email']))

            conn.commit()

            student.update({'name': name, 'email': email, 'year': year, 'department': department})
            message = "✅ Student updated successfully!"
        except Exception as e:
            conn.rollback()
            error = f"❌ {str(e)}"

    cursor.close()
    conn.close()

    return render_template(
        "edit_student.html",
        student=student,
        years=years,
        departments=departments,
        message=message,
        error=error
    )


@app.route('/add-comment/<int:student_id>/<int:course_id>', methods=['GET', 'POST'])
@app.route('/edit-comment/<int:student_id>/<int:course_id>', methods=['GET', 'POST'])
def comment_form(student_id, course_id):
    if session.get('role') not in ['teacher', 'admin']:
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    message = error = None

    cursor.execute("""
        SELECT * FROM comments WHERE student_id=%s AND course_id=%s
    """, (student_id, course_id))
    existing = cursor.fetchone()

    if request.method == 'POST':
        comment = request.form['comment'].strip()
        try:
            if existing:
                cursor.execute("""
                    UPDATE comments SET comment=%s WHERE student_id=%s AND course_id=%s
                """, (comment, student_id, course_id))
            else:
                cursor.execute("""
                    INSERT INTO comments (student_id, course_id, comment)
                    VALUES (%s, %s, %s)
                """, (student_id, course_id, comment))
            conn.commit()
            message = "✅ Comment saved successfully."
        except Exception as e:
            conn.rollback()
            error = f"❌ Error: {str(e)}"

    cursor.close()
    conn.close()
    return render_template("comment_form.html", message=message, error=error, student_id=student_id, course_id=course_id, existing=existing)
@app.route('/admin/edit-teacher/<int:user_id>', methods=['GET', 'POST'])
def edit_teacher(user_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE id=%s AND role='teacher'", (user_id,))
    teacher = cursor.fetchone()

    message = error = None
    if not teacher:
        return "❌ Teacher not found"

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email'].strip().lower()
        try:
            cursor.execute("UPDATE users SET name=%s, email=%s WHERE id=%s", (name, email, user_id))
            cursor.execute("UPDATE teachers SET name=%s, email=%s WHERE email=%s", (name, email, teacher['email']))
            conn.commit()
            message = "✅ Teacher updated successfully!"
        except Exception as e:
            conn.rollback()
            error = f"❌ {str(e)}"

    cursor.close()
    conn.close()
    return render_template("edit_teacher.html", teacher=teacher, message=message, error=error)
@app.route('/admin/delete-teacher/<int:user_id>')
def delete_teacher(user_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM teachers WHERE email=(SELECT email FROM users WHERE id=%s)", (user_id,))
        cursor.execute("DELETE FROM users WHERE id=%s AND role='teacher'", (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
    cursor.close()
    conn.close()
    return redirect('/admin/teachers')

@app.route('/admin/export-grades')
def export_all_grades():
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.name AS student_name, s.email, s.department,
               c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz, g.grade
        FROM grades g
        JOIN students s ON g.student_id = s.id
        JOIN courses c ON g.course_id = c.id
    """)
    rows = cursor.fetchall()
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='All Grades')
    output.seek(0)
    return send_file(output, download_name='all_grades.xlsx', as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/delete-grade/<int:student_id>/<int:course_id>', methods=['POST', 'GET'])
def delete_grade(student_id, course_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM grades WHERE student_id = %s AND course_id = %s",
            (student_id, course_id)
        )
        conn.commit()
        message = "✅ Grade deleted successfully!"
        return redirect(f"/admin/view-all-grades?message={message}")
    except Exception as e:
        conn.rollback()
        error = f"❌ Error deleting grade: {str(e)}"
        return redirect(f"/admin/view-all-grades?error={error}")
    finally:
        cursor.close()
        conn.close()

# EDIT GRADE
@app.route('/edit-grade/<int:student_id>/<int:course_id>', methods=['GET', 'POST'])
def edit_grade(student_id, course_id):
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            mid = request.form['mid']
            final = request.form['final']
            assignment = request.form['assignment']
            quiz = request.form['quiz']
            cursor.execute("""
                UPDATE grades SET mid_exam=%s, final_exam=%s, assignment=%s, quiz=%s
                WHERE student_id=%s AND course_id=%s
            """, (mid, final, assignment, quiz, student_id, course_id))
            conn.commit()
            return redirect('/admin/view-all-grades')

        cursor.execute("""
            SELECT s.name AS student_name, c.course_name, g.mid_exam, g.final_exam, g.assignment, g.quiz
            FROM grades g
            JOIN students s ON g.student_id = s.id
            JOIN courses c ON g.course_id = c.id
            WHERE g.student_id = %s AND g.course_id = %s
        """, (student_id, course_id))
        grade = cursor.fetchone()
        if grade:
            return render_template('edit_grade.html', grade=grade)
        else:
            return "Grade not found", 404
    finally:
        cursor.close()
        conn.close()
# 📝 Edit Course
@app.route('/admin/edit-course/<int:course_id>', methods=['GET', 'POST'])
def edit_course(course_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        course_name = request.form['course_name']
        teacher_id = request.form['teacher_id']
        cursor.execute("UPDATE courses SET course_name = %s, teacher_id = %s WHERE id = %s",
                       (course_name, teacher_id, course_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect('/admin/courses')

    cursor.execute("SELECT * FROM courses WHERE id = %s", (course_id,))
    course = cursor.fetchone()

    cursor.execute("SELECT id, name FROM users WHERE role = 'teacher'")
    teachers = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('edit_course.html', course=course, teachers=teachers)
# 🗑️ Delete Course
@app.route('/admin/delete-course/<int:course_id>')
def delete_course(course_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/admin/courses')
# Profile page route
@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    message = error = None

    if request.method == 'POST':
        file = request.files.get('profile_pic')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                cursor.execute("UPDATE users SET profile_pic = %s WHERE id = %s", (filename, session['user_id']))
                conn.commit()
                message = "✅ Profile photo updated successfully."
            except Exception as e:
                error = f"❌ Error updating photo: {e}"
        else:
            error = "❌ Invalid file format."

    # Fetch admin details
    cursor.execute("SELECT name, email, profile_pic FROM users WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('admin_profile.html', user=user, message=message, error=error)
# Settings page route
@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if session.get('role') != 'admin':
        return redirect('/login')

    message = error = None

    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            error = "❌ Passwords do not match."
        elif len(new_password) < 6:
            error = "❌ Password must be at least 6 characters."
        else:
            hashed_pw = pwd_context.hash(new_password)
            try:
                conn = create_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, session['user_id']))
                conn.commit()
                message = "✅ Password updated successfully!"
            except Exception as e:
                error = f"❌ {str(e)}"
            finally:
                cursor.close()
                conn.close()

    return render_template('admin_settings.html', message=message, error=error)
@app.route('/teacher/submit-grade-with-course', methods=['GET', 'POST'])
def submit_grade_with_course():
    if session.get('role') != 'teacher':
        return redirect('/login')

    message = error = None
    conn = create_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            # Course Info
            course_name = request.form['course_name']
            course_code = request.form['course_code']
            department_id = request.form['department_id']

            # Grade Info
            student_id = request.form['student_id']
            grade = request.form['grade']

            # 1. Insert course
            cursor.execute("INSERT INTO courses (name, code, department_id) VALUES (%s, %s, %s)",
                           (course_name, course_code, department_id))
            conn.commit()

            # 2. Get course_id
            cursor.execute("SELECT id FROM courses WHERE code = %s ORDER BY id DESC LIMIT 1", (course_code,))
            course_id = cursor.fetchone()[0]

            # 3. Insert grade
            cursor.execute("INSERT INTO grades (student_id, course_id, grade) VALUES (%s, %s, %s)",
                           (student_id, course_id, grade))
            conn.commit()

            message = "✅ Course and Grade submitted successfully!"

        except Exception as e:
            conn.rollback()
            error = f"❌ Error: {str(e)}"

        finally:
            cursor.close()
            conn.close()

    # Load departments and students for dropdown
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM departments")
    departments = cursor.fetchall()
    cursor.execute("SELECT id, name FROM users WHERE role='student'")
    students = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("submit_grade_with_course.html", departments=departments, students=students, message=message, error=error)
@app.route('/teacher/view-grades', methods=['GET'])
def teacher_view_grades():
    if session.get('role') != 'teacher':
        return redirect('/login')

    teacher_id = session.get('user_id')
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get teacher's courses
        cursor.execute("SELECT id, course_name FROM courses WHERE teacher_id = %s", (teacher_id,))
        teacher_courses = cursor.fetchall()
        course_ids = [course['id'] for course in teacher_courses]

        if not course_ids:
            return render_template('teacher_view_grades.html', grades=[], message="You have no courses assigned.")

        format_strings = ','.join(['%s'] * len(course_ids))
        cursor.execute(f"""
            SELECT 
                g.student_id, g.course_id, g.grade, g.comment,
                s.name AS student_name, c.course_name
            FROM grades g
            JOIN students s ON g.student_id = s.id
            JOIN courses c ON g.course_id = c.id
            WHERE g.course_id IN ({format_strings})
        """, tuple(course_ids))

        grades = cursor.fetchall()

    except Exception as e:
        grades = []
        print("Error:", str(e))
    finally:
        cursor.close()
        conn.close()

    return render_template('teacher_view_grades.html', grades=grades)


@app.route('/teacher/add-comment/<int:student_id>/<int:course_id>', methods=['POST'])
def add_teacher_comment(student_id, course_id):
    if session.get('role') != 'teacher':
        return redirect('/login')

    teacher_id = session.get('user_id')
    comment_text = request.form.get('comment', '').strip()

    if not comment_text:
        flash("Comment cannot be empty.", "danger")
        return redirect(url_for('teacher_view_grades'))

    conn = create_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO comments (teacher_id, student_id, course_id, comment, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (teacher_id, student_id, course_id, comment_text, datetime.now()))

        conn.commit()
        flash("Comment added successfully.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Failed to add comment: {str(e)}", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('teacher_view_grades'))

@app.route('/teacher/delete-grade/<int:student_id>/<int:course_id>')
def teacher_delete_grade(student_id, course_id):
    if session.get('role') != 'teacher':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM grades WHERE student_id = %s AND course_id = %s", (student_id, course_id))
        conn.commit()
    except:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    return redirect('/teacher/view-grades')
@app.route('/teacher/edit-grade/<int:student_id>/<int:course_id>', methods=['GET', 'POST'])
def teacher_edit_grade(student_id, course_id):
    if session.get('role') != 'teacher':
        return redirect('/login')

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        new_grade = request.form['grade']
        try:
            cursor.execute("UPDATE grades SET grade = %s WHERE student_id = %s AND course_id = %s",
                           (new_grade, student_id, course_id))
            conn.commit()
        except:
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
        return redirect('/teacher/view-grades')

    cursor.execute("""
        SELECT g.*, u.name AS student_name, c.name AS course_name
        FROM grades g
        JOIN users u ON g.student_id = u.id
        JOIN courses c ON g.course_id = c.id
        WHERE g.student_id = %s AND g.course_id = %s
    """, (student_id, course_id))
    grade = cursor.fetchone()

    return render_template("teacher_edit_grade.html", grade=grade)
@app.route('/api/comments/<int:student_id>/<int:course_id>')
def api_get_comments(student_id, course_id):
    if session.get('role') != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.comment, DATE_FORMAT(c.created_at, '%Y-%m-%d %H:%i') AS created_at, u.name AS teacher_name
        FROM comments c
        JOIN users u ON c.teacher_id = u.id
        WHERE c.student_id = %s AND c.course_id = %s
        ORDER BY c.created_at DESC
    """, (student_id, course_id))

    comments = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'comments': comments})

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect('/login')
    
    # Get teacher name from session or fallback to 'Teacher'
    name = session.get('name') or 'Teacher'
    
    return render_template('teacher_dashboard.html', name=name)
@app.route('/add-course-grade', methods=['GET', 'POST'])
def add_course_grade():
    if session.get('role') != 'teacher':
        return redirect('/login')
    
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    message = error = None

    # Fetch departments for dropdowns
    cursor.execute("SELECT name FROM departments")
    departments = cursor.fetchall()

    # Handle form submissions (determine which form was submitted)
    if request.method == 'POST':
        if 'add_course' in request.form:
            # Add Course form submitted
            course_name = request.form['course_name']
            department = request.form['department']
            teacher_id = session['user_id']
            try:
                cursor.execute(
                    "INSERT INTO courses (course_name, department, teacher_id) VALUES (%s, %s, %s)",
                    (course_name, department, teacher_id)
                )
                conn.commit()
                message = f"✅ Course '{course_name}' added successfully!"
            except Exception as e:
                error = f"❌ Error adding course: {e}"

        elif 'add_grade' in request.form:
            # Add Grade form submitted
            try:
                student_id = int(request.form['student_id'])
                course_id = int(request.form['course_id'])
                semester = request.form['semester']
                mid_exam = float(request.form['mid_exam'])
                final_exam = float(request.form['final_exam'])
                assignment = float(request.form['assignment'])
                quiz = float(request.form['quiz'])

                total_grade = round(mid_exam * 0.3 + final_exam * 0.4 + assignment * 0.2 + quiz * 0.1, 2)

                cursor.execute("""
                    INSERT INTO grades (student_id, course_id, semester, mid_exam, final_exam, assignment, quiz, grade)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (student_id, course_id, semester, mid_exam, final_exam, assignment, quiz, total_grade))
                conn.commit()
                message = f"✅ Grade added successfully! Total: {total_grade}"
            except Exception as e:
                error = f"❌ Error adding grade: {e}"

    # For the Grade form dropdowns, get students and courses
    cursor.execute("SELECT id, name FROM students")
    students = cursor.fetchall()

    cursor.execute("SELECT id, course_name FROM courses WHERE teacher_id = %s", (session['user_id'],))
    courses = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'add_course_grade.html',
        departments=departments,
        students=students,
        courses=courses,
        message=message,
        error=error
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    create_default_admin()
    app.run(debug=True)
