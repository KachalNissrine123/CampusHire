from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
from functools import wraps
from models import db, Student, Department, Position, Application, Notification
from datetime import datetime

from config import Config
from pypdf import PdfReader
import docx  
from openai import OpenAI
import json
from datetime import datetime



app = Flask(__name__)
app.config.from_object(Config)
client = OpenAI(api_key=app.config['OPENAI_API_KEY'])


os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'cvs'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logos'), exist_ok=True)


db.init_app(app)

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.utcnow().year}


def student_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'student':
            flash('Please log in as a student to access this page.', 'warning')
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

def department_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'department':
            flash('Please log in as a department to access this page.', 'warning')
            return redirect(url_for('department_login'))
        return f(*args, **kwargs)
    return decorated_function


def analyze_application_with_ai(student, position):
    """Use Claude API to analyze if student matches position requirements"""
    try:
       
        student_profile = f"""
        Student Profile:
        - Name: {student.full_name}
        - School: {student.school}
        - Level: {student.level}
        - Type: {student.student_type}
        - GPA: {student.gpa if student.gpa else 'Not provided'}
        - Credits: {student.credits if student.credits else 'Not provided'}
        """
        
        
        position_reqs = f"""
        Position: {position.title}
        Department: {position.department.name}
        Requirements:
        - Required GPA: {position.required_gpa if position.required_gpa else 'Any'}
        - Required Credits: {position.required_credits if position.required_credits else 'Any'}
        - Required Level: {position.required_level if position.required_level else 'Any'}
        - Required School: {position.required_school if position.required_school else 'Any'}
        - Required Skills: {position.required_skills if position.required_skills else 'None specified'}
        
        Position Description:
        {position.description}
        """

        score = calculate_match_score(student, position)
        feedback = generate_feedback(student, position, score)
        
        return score, feedback
    except Exception as e:
        print(f"Error in AI analysis: {e}")
        return 0.5, "Unable to analyze application at this time."

def calculate_match_score(student, position):
    """Calculate a match score between 0 and 1"""
    score = 0.0
    factors = 0
    
   
    if position.required_gpa:
        factors += 1
        if student.gpa and student.gpa >= position.required_gpa:
            score += 0.3
        elif student.gpa:
          
            score += max(0, 0.3 * (student.gpa / position.required_gpa))
    
   
    if position.required_credits:
        factors += 1
        if student.credits and student.credits >= position.required_credits:
            score += 0.2
        elif student.credits:
            score += max(0, 0.2 * (student.credits / position.required_credits))
    
    
    if position.required_level:
        factors += 1
        if student.level == position.required_level:
            score += 0.2
        else:
            score += 0.1  
    
    
    if position.required_school:
        factors += 1
        if student.school == position.required_school:
            score += 0.3
    
    
    if factors == 0:
        return 0.7
    
   
    return min(1.0, score / max(1, factors * 0.25))

def generate_feedback(student, position, score):
    """Generate feedback based on the match score"""
    feedback_parts = []
    
    if score >= 0.8:
        feedback_parts.append("Excellent match for this position!")
    elif score >= 0.6:
        feedback_parts.append("Good candidate with strong qualifications.")
    elif score >= 0.4:
        feedback_parts.append("Meets some requirements, consider for interview.")
    else:
        feedback_parts.append("May not meet all requirements.")
    
   
    if position.required_gpa and student.gpa:
        if student.gpa >= position.required_gpa:
            feedback_parts.append(f"✓ GPA requirement met ({student.gpa} >= {position.required_gpa})")
        else:
            feedback_parts.append(f"✗ GPA below requirement ({student.gpa} < {position.required_gpa})")
    
    if position.required_credits and student.credits:
        if student.credits >= position.required_credits:
            feedback_parts.append(f"✓ Credit requirement met ({student.credits} >= {position.required_credits})")
        else:
            feedback_parts.append(f"✗ Credits below requirement ({student.credits} < {position.required_credits})")
    
    if position.required_level and student.level != position.required_level:
        feedback_parts.append(f"Note: Student is {student.level}, position prefers {position.required_level}")
    
    if position.required_school and student.school != position.required_school:
        feedback_parts.append(f"Note: Student from {student.school}, position prefers {position.required_school}")
    
    return " | ".join(feedback_parts)

def extract_cv_text(student):
    """Read the student's CV file and return plain text (PDF/DOCX)."""
    if not student.cv_path:
        return ""

    cv_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'cvs')
    cv_full_path = os.path.join(cv_dir, student.cv_path)

    if not os.path.exists(cv_full_path):
        return ""

    ext = os.path.splitext(cv_full_path)[1].lower()

  
    if ext == '.pdf':
        try:
            reader = PdfReader(cv_full_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
            return text.strip()
        except Exception as e:
            print(f"Error reading PDF CV: {e}")
            return ""

    
    if ext == '.docx':
        try:
            doc = docx.Document(cv_full_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            return text.strip()
        except Exception as e:
            print(f"Error reading DOCX CV: {e}")
            return ""

   
    return ""

def analyze_cv_with_openai(cv_text, student, position):
    """
    Use OpenAI to evaluate a student's CV for a given position.
    Returns: (decision, score, reason)
    """
   
    if not app.config['OPENAI_API_KEY']:
        score = calculate_match_score(student, position)
        feedback = generate_feedback(student, position, score)
        decision = "pass" if score >= 0.6 else "fail"
        return decision, score, feedback

    
    if not cv_text:
        score = calculate_match_score(student, position)
        feedback = "Could not read CV; using profile-based match only. " + generate_feedback(student, position, score)
        decision = "pass" if score >= 0.6 else "fail"
        return decision, score, feedback

    prompt = f"""
You are an assistant evaluating a student's CV for a campus job position.

Job Position:
- Title: {position.title}
- Description: {position.description}
- Required GPA: {position.required_gpa or "Any"}
- Required Credits: {position.required_credits or "Any"}
- Required Level: {position.required_level or "Any"}
- Required School: {position.required_school or "Any"}
- Required Skills: {position.required_skills or "Not specified"}

Student Profile:
- Name: {student.full_name}
- School: {student.school}
- Level: {student.level}
- Type: {student.student_type}
- GPA: {student.gpa if student.gpa is not None else "Not provided"}
- Credits: {student.credits if student.credits is not None else "Not provided"}

CV Content:
{cv_text[:8000]}
(Only the first ~8000 characters are shown if the CV is long.)

Please evaluate how well this CV matches the position, considering skills, experience, and requirements.

Respond ONLY with valid JSON in this exact format:
{{
  "decision": "pass" or "fail",
  "score": number between 0 and 1,
  "reason": "short explanation (1-3 sentences)"
}}
"""

    try:
        response = client.chat.completions.create(
            model=app.config['OPENAI_MODEL'],   
            messages=[
                {"role": "system", "content": "You evaluate student CVs for campus jobs and respond in strict JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        decision = data.get("decision", "fail")
        score = float(data.get("score", 0.0))
        reason = data.get("reason", "No reason provided.")

        
        score = max(0.0, min(1.0, score))
        if decision not in ("pass", "fail"):
            decision = "fail"

        return decision, score, reason

    except Exception as e:
        print(f"Error calling OpenAI: {e}")
       
        score = calculate_match_score(student, position)
        feedback = "AI evaluation failed; using profile-based match only. " + generate_feedback(student, position, score)
        decision = "pass" if score >= 0.6 else "fail"
        return decision, score, feedback


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        try:
            student = Student(
                full_name=request.form['full_name'],
                email=request.form['email'],
                school=request.form['school'],
                level=request.form['level'],
                student_type=request.form['student_type'],
                gpa=float(request.form['gpa']) if request.form.get('gpa') else None,
                credits=int(request.form['credits']) if request.form.get('credits') else None
            )
            student.set_password(request.form['password'])
            
            db.session.add(student)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('student_login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error during registration: {str(e)}', 'danger')
    
    return render_template('student_register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        student = Student.query.filter_by(email=email).first()
        
        if student and student.check_password(password):
            session['user_id'] = student.id
            session['user_type'] = 'student'
            session['user_name'] = student.full_name
            flash('Welcome back!', 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('student_login.html')

@app.route('/student/dashboard')
@student_login_required
def student_dashboard():
    student = Student.query.get(session['user_id'])
    applications = Application.query.filter_by(student_id=student.id).order_by(Application.applied_at.desc()).all()
    notifications = Notification.query.filter_by(student_id=student.id).order_by(Notification.timestamp.desc()).limit(5).all()
    
    return render_template('student_dashboard.html', student=student, applications=applications, notifications=notifications)
@app.route('/student/profile', methods=['GET', 'POST'])
@student_login_required
def student_profile():
    student = Student.query.get(session['user_id'])

    if request.method == 'POST':
        try:
            
            student.full_name = request.form['full_name']
            student.school = request.form['school']
            student.level = request.form['level']
            student.student_type = request.form['student_type']
            student.gpa = float(request.form['gpa']) if request.form.get('gpa') else None
            student.credits = int(request.form['credits']) if request.form.get('credits') else None

            
            if request.form.get('remove_cv') == "1" and student.cv_path:
                cv_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'cvs', student.cv_path)
                if os.path.exists(cv_full_path):
                    try:
                        os.remove(cv_full_path)
                    except Exception as e:
                        print(f"Error removing CV file: {e}")
                student.cv_path = None

           
            if 'cv' in request.files:
                file = request.files['cv']
                if file and file.filename:
                  
                    if student.cv_path:
                        old_cv = os.path.join(app.config['UPLOAD_FOLDER'], 'cvs', student.cv_path)
                        if os.path.exists(old_cv):
                            try:
                                os.remove(old_cv)
                            except Exception as e:
                                print(f"Error removing old CV file: {e}")

                    
                    filename = secure_filename(f"{student.id}_{file.filename}")
                    cv_path = os.path.join(app.config['UPLOAD_FOLDER'], 'cvs', filename)
                    file.save(cv_path)
                    student.cv_path = filename

            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('student_profile'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating profile: {str(e)}", "danger")

    return render_template('student_profile.html', student=student)


@app.route('/student/positions')
@student_login_required
def student_positions():
    student = Student.query.get(session['user_id'])
    positions = Position.query.filter_by(is_active=True).order_by(Position.created_at.desc()).all()
    
   
    applied_ids = [app.position_id for app in Application.query.filter_by(student_id=student.id).all()]
    
    return render_template('student_positions.html', positions=positions, applied_ids=applied_ids)

@app.route('/student/apply/<int:position_id>', methods=['POST'])
@student_login_required
def apply_position(position_id):
    student = Student.query.get(session['user_id'])
    position = Position.query.get_or_404(position_id)
    
    
    if not student.cv_path:
        flash('Please upload your CV in your profile before applying.', 'warning')
        return redirect(url_for('student_profile'))
    
   
    existing = Application.query.filter_by(student_id=student.id, position_id=position_id).first()
    if existing:
        flash('You have already applied to this position.', 'warning')
        return redirect(url_for('student_positions'))
    
       
    existing = Application.query.filter_by(student_id=student.id, position_id=position_id).first()
    if existing:
        flash('You have already applied to this position.', 'warning')
        return redirect(url_for('student_positions'))

   
    cv_text = extract_cv_text(student)

    
    application = Application(student_id=student.id, position_id=position_id)

    
    decision, score, reason = analyze_cv_with_openai(cv_text, student, position)
    application.ai_score = score
    application.ai_feedback = reason

    
    if decision == "pass":
        
        application.status = 'under_review'
    else:
        application.status = 'rejected'

    db.session.add(application)
    db.session.commit()

    if decision == "pass":
        flash('Application submitted and passed the AI filter! Status: Under Review.', 'success')
    else:
        flash('Application submitted but did not pass the AI filter. Status: Rejected.', 'warning')

    return redirect(url_for('student_dashboard'))

    
    db.session.add(application)
    db.session.commit()
    
    flash('Application submitted successfully!', 'success')
    return redirect(url_for('student_dashboard'))


@app.route('/department/register', methods=['GET', 'POST'])
def department_register():
    if request.method == 'POST':
        try:
            department = Department(
                name=request.form['name'],
                email=request.form['email'],
                description=request.form.get('description', '')
            )
            department.set_password(request.form['password'])
            
            
            if 'logo' in request.files:
                file = request.files['logo']
                if file and file.filename:
                    filename = secure_filename(f"{request.form['name']}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'logos', filename))
                    department.logo_path = filename
            
            db.session.add(department)
            db.session.commit()
            
            flash('Department registered successfully! Please log in.', 'success')
            return redirect(url_for('department_login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error during registration: {str(e)}', 'danger')
    
    return render_template('department_register.html')

@app.route('/department/login', methods=['GET', 'POST'])
def department_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        department = Department.query.filter_by(email=email).first()
        
        if department and department.check_password(password):
            session['user_id'] = department.id
            session['user_type'] = 'department'
            session['user_name'] = department.name
            flash('Welcome back!', 'success')
            return redirect(url_for('department_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('department_login.html')

@app.route('/department/position/<int:position_id>/delete', methods=['POST'])
@department_login_required
def delete_position(position_id):
    position = Position.query.get_or_404(position_id)

    
    if position.department_id != session['user_id']:
        flash('You do not have permission to delete this position.', 'danger')
        return redirect(url_for('department_dashboard'))

    
    db.session.delete(position)
    db.session.commit()

    flash('Position deleted successfully.', 'info')
    return redirect(url_for('department_dashboard'))

@app.route('/department/dashboard')
@department_login_required
def department_dashboard():
    department = Department.query.get(session['user_id'])
    positions = Position.query.filter_by(department_id=department.id).order_by(Position.created_at.desc()).all()
    
   
    total_applications = 0
    pending_applications = 0
    for position in positions:
        apps = Application.query.filter_by(position_id=position.id).all()
        total_applications += len(apps)
        pending_applications += len([a for a in apps if a.status == 'pending'])
    
    return render_template('department_dashboard.html', 
                         department=department, 
                         positions=positions,
                         total_applications=total_applications,
                         pending_applications=pending_applications)

@app.route('/department/position/create', methods=['GET', 'POST'])
@department_login_required
def create_position():
    if request.method == 'POST':
        try:
            position = Position(
                title=request.form['title'],
                description=request.form['description'],
                required_gpa=float(request.form['required_gpa']) if request.form.get('required_gpa') else None,
                required_credits=int(request.form['required_credits']) if request.form.get('required_credits') else None,
                required_skills=request.form.get('required_skills', ''),
                required_level=request.form.get('required_level', ''),
                required_school=request.form.get('required_school', ''),
                department_id=session['user_id']
            )
            
            db.session.add(position)
            db.session.commit()
            
            flash('Position created successfully!', 'success')
            return redirect(url_for('department_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating position: {str(e)}', 'danger')
    
    return render_template('create_position.html')

@app.route('/department/position/<int:position_id>/applicants')
@department_login_required
def view_applicants(position_id):
    position = Position.query.get_or_404(position_id)
    
    
    if position.department_id != session['user_id']:
        flash('You do not have access to this position.', 'danger')
        return redirect(url_for('department_dashboard'))
    
    applications = Application.query.filter_by(position_id=position_id).order_by(Application.ai_score.desc()).all()
    
    return render_template('view_applicants.html', position=position, applications=applications)

@app.route('/department/application/<int:app_id>/update', methods=['POST'])
@department_login_required
def update_application(app_id):
    application = Application.query.get_or_404(app_id)
    
   
    if application.position.department_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    new_status = request.form['status']
    application.status = new_status
    
    if new_status == 'accepted':
        message = f"Congratulations! Your application for {application.position.title} has been accepted. You will receive an interview invitation soon."
    elif new_status == 'rejected':
        message = f"Thank you for your interest in {application.position.title}. Unfortunately, we have decided to move forward with other candidates."
    elif new_status == 'under_review':
        message = f"Your application for {application.position.title} is now under review."
    else:
        message = f"Your application status for {application.position.title} has been updated to {new_status}."
    
    notification = Notification(student_id=application.student_id, message=message)
    db.session.add(notification)
    db.session.commit()
    
    flash('Application status updated!', 'success')
    return redirect(url_for('view_applicants', position_id=application.position_id))

@app.route('/department/profile', methods=['GET', 'POST'])
@department_login_required
def department_profile():
    department = Department.query.get(session['user_id'])

    if request.method == 'POST':
        try:
            department.name = request.form['name']
            department.description = request.form.get('description', '')

         
            if request.form.get('remove_logo') and department.logo_path:
                try:
                    logo_full = os.path.join(app.config['UPLOAD_FOLDER'], 'logos', department.logo_path)
                    if os.path.exists(logo_full):
                        os.remove(logo_full)
                except Exception as e:
                    print(f"Error removing logo file: {e}")
                department.logo_path = None

           
            if 'logo' in request.files:
                file = request.files['logo']
                if file and file.filename:
                    
                    if department.logo_path:
                        try:
                            old_logo = os.path.join(app.config['UPLOAD_FOLDER'], 'logos', department.logo_path)
                            if os.path.exists(old_logo):
                                os.remove(old_logo)
                        except Exception as e:
                            print(f"Error removing old logo file: {e}")
                    filename = secure_filename(f"{department.name}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'logos', filename))
                    department.logo_path = filename

            db.session.commit()
            flash('Department profile updated.', 'success')
            return redirect(url_for('department_profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating department profile: {e}', 'danger')

    return render_template('department_profile.html', department=department)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)