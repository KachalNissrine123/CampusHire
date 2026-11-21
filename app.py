import json
import os
from datetime import datetime
from functools import wraps

import docx
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from openai import OpenAI
from pypdf import PdfReader
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from config import Config
from models import Application, Department, Notification, Position, Student, db

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# OpenAI() raises if there's no key, so only build the client when one is set.
# Without it, screening falls back to the profile score.
ai_client = OpenAI(api_key=app.config["OPENAI_API_KEY"]) if app.config["OPENAI_API_KEY"] else None

CV_DIR = os.path.join(app.config["UPLOAD_FOLDER"], "cvs")
LOGO_DIR = os.path.join(app.config["UPLOAD_FOLDER"], "logos")
os.makedirs(CV_DIR, exist_ok=True)
os.makedirs(LOGO_DIR, exist_ok=True)

APPLICATION_STATUSES = ("pending", "under_review", "accepted", "rejected")

# A CV the screener scores at or above this goes to the department as
# "under_review"; anything lower is auto-rejected.
SCREENING_PASS_MARK = 0.6

# How much each requirement a department can set is worth. A position only
# gets scored on the requirements it actually sets (see profile_match_score).
REQUIREMENT_WEIGHTS = {"gpa": 0.3, "credits": 0.2, "level": 0.2, "school": 0.3}


@app.context_processor
def inject_current_year():
    return {"current_year": datetime.utcnow().year}


def login_required_as(user_type, login_endpoint):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("user_type") != user_type or "user_id" not in session:
                flash(f"Please log in as a {user_type} to access this page.", "warning")
                return redirect(url_for(login_endpoint))
            return view(*args, **kwargs)
        return wrapped
    return decorator


student_login_required = login_required_as("student", "student_login")
department_login_required = login_required_as("department", "department_login")


def save_upload(file, folder, prefix, allowed_exts):
    """Save an uploaded file as '<prefix>_<original name>' and return the stored name.

    Returns None when the extension isn't allowed so callers can flash a message.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        return None
    filename = secure_filename(f"{prefix}_{file.filename}")
    file.save(os.path.join(folder, filename))
    return filename


def delete_upload(folder, filename):
    if not filename:
        return
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

def profile_match_score(student, position):
    """Score 0..1 from GPA, credits, level and school only (no CV).

    Used when there's no API key, the CV can't be read, or the API call fails.
    Being short on GPA or credits earns partial credit in proportion; a level
    mismatch earns half, since a Sophomore can still do a Junior's job.
    """
    earned = possible = 0.0
    w = REQUIREMENT_WEIGHTS

    if position.required_gpa:
        possible += w["gpa"]
        if student.gpa:
            earned += w["gpa"] * min(1.0, student.gpa / position.required_gpa)

    if position.required_credits:
        possible += w["credits"]
        if student.credits:
            earned += w["credits"] * min(1.0, student.credits / position.required_credits)

    if position.required_level:
        possible += w["level"]
        earned += w["level"] if student.level == position.required_level else w["level"] / 2

    if position.required_school:
        possible += w["school"]
        if student.school == position.required_school:
            earned += w["school"]

    # Position with no hard requirements: everyone is a reasonable fit.
    if possible == 0:
        return 0.7
    return round(earned / possible, 2)


def profile_feedback(student, position, score):
    if score >= 0.8:
        parts = ["Strong match on the posted requirements."]
    elif score >= 0.6:
        parts = ["Meets most of the posted requirements."]
    elif score >= 0.4:
        parts = ["Meets some requirements; worth a look."]
    else:
        parts = ["Falls short of several requirements."]

    if position.required_gpa and student.gpa:
        mark = "✓" if student.gpa >= position.required_gpa else "✗"
        parts.append(f"{mark} GPA {student.gpa} (needs {position.required_gpa})")
    if position.required_credits and student.credits:
        mark = "✓" if student.credits >= position.required_credits else "✗"
        parts.append(f"{mark} {student.credits} credits (needs {position.required_credits})")
    if position.required_level and student.level != position.required_level:
        parts.append(f"{student.level}, position asks for {position.required_level}")
    if position.required_school and student.school != position.required_school:
        parts.append(f"{student.school} student, position asks for {position.required_school}")

    return " | ".join(parts)


def profile_only_result(student, position, note=""):
    score = profile_match_score(student, position)
    decision = "pass" if score >= SCREENING_PASS_MARK else "fail"
    return decision, score, note + profile_feedback(student, position, score)


def extract_cv_text(student):
    """Plain text from the student's CV (PDF or DOCX), or '' if unreadable."""
    if not student.cv_path:
        return ""
    path = os.path.join(CV_DIR, student.cv_path)
    if not os.path.exists(path):
        return ""

    try:
        if path.lower().endswith(".pdf"):
            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages).strip()
        if path.lower().endswith(".docx"):
            return "\n".join(p.text for p in docx.Document(path).paragraphs).strip()
    except Exception as exc:  # corrupt or scanned files: fall back to the profile score
        app.logger.warning("Could not read CV %s: %s", student.cv_path, exc)
    return ""


def screen_application(student, position):
    """Return (decision, score, reason) for a new application.

    With an API key the CV text goes to the model along with the posting.
    Without one, or if anything goes wrong, the profile score decides.
    """
    if ai_client is None:
        return profile_only_result(student, position)

    cv_text = extract_cv_text(student)
    if not cv_text:
        return profile_only_result(student, position, "CV text unreadable; scored on profile. ")

    prompt = f"""You are screening applications for on-campus student jobs at Al Akhawayn University.

Position: {position.title} ({position.department.name})
Description: {position.description}
Required GPA: {position.required_gpa or "any"}
Required credits: {position.required_credits or "any"}
Required level: {position.required_level or "any"}
Required school: {position.required_school or "any"}
Skills wanted: {position.required_skills or "not specified"}

Applicant: {student.level} {student.student_type} in {student.school}, GPA {student.gpa or "not given"}, {student.credits or "unknown"} credits.

CV (truncated to 8000 characters):
{cv_text[:8000]}

Reply with JSON only: {{"decision": "pass" or "fail", "score": 0 to 1, "reason": "1-3 sentences a hiring manager can act on"}}"""

    try:
        response = ai_client.chat.completions.create(
            model=app.config["OPENAI_MODEL"],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(response.choices[0].message.content)
        score = max(0.0, min(1.0, float(data.get("score", 0))))
        decision = data.get("decision") if data.get("decision") in ("pass", "fail") else "fail"
        return decision, score, data.get("reason", "")
    except Exception as exc:
        app.logger.error("CV screening call failed: %s", exc)
        return profile_only_result(student, position, "AI screening unavailable; scored on profile. ")


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """Logos are public. A CV is visible to its owner and to departments it was sent to."""
    folder, _, name = filename.partition("/")
    if folder == "logos":
        return send_from_directory(LOGO_DIR, name)
    if folder != "cvs":
        abort(404)

    owner = Student.query.filter_by(cv_path=name).first_or_404()
    user_type, user_id = session.get("user_type"), session.get("user_id")

    if user_type == "student" and user_id == owner.id:
        return send_from_directory(CV_DIR, name)
    if user_type == "department":
        applied_here = (
            Application.query.join(Position)
            .filter(Application.student_id == owner.id, Position.department_id == user_id)
            .first()
        )
        if applied_here:
            return send_from_directory(CV_DIR, name)
    abort(403)


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        form = request.form
        try:
            student = Student(
                full_name=form["full_name"].strip(),
                email=form["email"].strip().lower(),
                school=form["school"],
                level=form["level"],
                student_type=form["student_type"],
                gpa=float(form["gpa"]) if form.get("gpa") else None,
                credits=int(form["credits"]) if form.get("credits") else None,
            )
            student.set_password(form["password"])
            db.session.add(student)
            db.session.commit()
            flash("Account created. You can log in now.", "success")
            return redirect(url_for("student_login"))
        except IntegrityError:
            db.session.rollback()
            flash("An account with that email already exists.", "danger")
        except ValueError:
            flash("GPA and credits must be numbers.", "danger")

    return render_template("student_register.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        student = Student.query.filter_by(email=request.form["email"].strip().lower()).first()
        if student and student.check_password(request.form["password"]):
            session.clear()
            session.update(user_id=student.id, user_type="student", user_name=student.full_name)
            return redirect(url_for("student_dashboard"))
        flash("Invalid email or password.", "danger")

    return render_template("student_login.html")


@app.route("/student/dashboard")
@student_login_required
def student_dashboard():
    student = db.session.get(Student, session["user_id"])
    applications = (
        Application.query.filter_by(student_id=student.id)
        .order_by(Application.applied_at.desc()).all()
    )
    notifications = (
        Notification.query.filter_by(student_id=student.id)
        .order_by(Notification.timestamp.desc()).limit(5).all()
    )
    return render_template("student_dashboard.html", student=student,
                           applications=applications, notifications=notifications)


@app.route("/student/profile", methods=["GET", "POST"])
@student_login_required
def student_profile():
    student = db.session.get(Student, session["user_id"])

    if request.method == "POST":
        form = request.form
        try:
            student.full_name = form["full_name"].strip()
            student.school = form["school"]
            student.level = form["level"]
            student.student_type = form["student_type"]
            student.gpa = float(form["gpa"]) if form.get("gpa") else None
            student.credits = int(form["credits"]) if form.get("credits") else None
        except ValueError:
            flash("GPA and credits must be numbers.", "danger")
            return redirect(url_for("student_profile"))

        if form.get("remove_cv") == "1":
            delete_upload(CV_DIR, student.cv_path)
            student.cv_path = None

        file = request.files.get("cv")
        if file and file.filename:
            saved = save_upload(file, CV_DIR, student.id, app.config["CV_EXTENSIONS"])
            if saved is None:
                flash("CV must be a PDF or DOCX file.", "danger")
                return redirect(url_for("student_profile"))
            if student.cv_path != saved:
                delete_upload(CV_DIR, student.cv_path)
            student.cv_path = saved

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("student_profile"))

    return render_template("student_profile.html", student=student)


@app.route("/student/positions")
@student_login_required
def student_positions():
    positions = Position.query.filter_by(is_active=True).order_by(Position.created_at.desc()).all()
    applied_ids = {
        a.position_id for a in Application.query.filter_by(student_id=session["user_id"])
    }
    return render_template("student_positions.html", positions=positions, applied_ids=applied_ids)


@app.route("/student/apply/<int:position_id>", methods=["POST"])
@student_login_required
def apply_position(position_id):
    student = db.session.get(Student, session["user_id"])
    position = Position.query.get_or_404(position_id)

    if not student.cv_path:
        flash("Upload your CV on your profile before applying.", "warning")
        return redirect(url_for("student_profile"))

    if Application.query.filter_by(student_id=student.id, position_id=position_id).first():
        flash("You have already applied to this position.", "warning")
        return redirect(url_for("student_positions"))

    decision, score, reason = screen_application(student, position)
    db.session.add(Application(
        student_id=student.id,
        position_id=position_id,
        ai_score=score,
        ai_feedback=reason,
        status="under_review" if decision == "pass" else "rejected",
    ))
    db.session.commit()

    if decision == "pass":
        flash("Application sent. It passed screening and is now with the department.", "success")
    else:
        flash("Application sent, but it didn't pass the screening step.", "warning")
    return redirect(url_for("student_dashboard"))


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

@app.route("/department/register", methods=["GET", "POST"])
def department_register():
    if request.method == "POST":
        form = request.form
        department = Department(
            name=form["name"].strip(),
            email=form["email"].strip().lower(),
            description=form.get("description", ""),
        )
        department.set_password(form["password"])

        logo = request.files.get("logo")
        if logo and logo.filename:
            department.logo_path = save_upload(logo, LOGO_DIR, department.name, app.config["LOGO_EXTENSIONS"])
            if department.logo_path is None:
                flash("Logo must be a PNG, JPG or WEBP image.", "danger")
                return render_template("department_register.html")

        try:
            db.session.add(department)
            db.session.commit()
            flash("Department registered. You can log in now.", "success")
            return redirect(url_for("department_login"))
        except IntegrityError:
            db.session.rollback()
            delete_upload(LOGO_DIR, department.logo_path)
            flash("A department with that name or email already exists.", "danger")

    return render_template("department_register.html")


@app.route("/department/login", methods=["GET", "POST"])
def department_login():
    if request.method == "POST":
        department = Department.query.filter_by(email=request.form["email"].strip().lower()).first()
        if department and department.check_password(request.form["password"]):
            session.clear()
            session.update(user_id=department.id, user_type="department", user_name=department.name)
            return redirect(url_for("department_dashboard"))
        flash("Invalid email or password.", "danger")

    return render_template("department_login.html")


@app.route("/department/dashboard")
@department_login_required
def department_dashboard():
    department = db.session.get(Department, session["user_id"])
    positions = (
        Position.query.filter_by(department_id=department.id)
        .order_by(Position.created_at.desc()).all()
    )
    applications = [a for p in positions for a in p.applications]
    # Screening moves passing CVs straight to "under_review", so that bucket
    # is what's actually waiting on the department.
    awaiting = sum(a.status in ("pending", "under_review") for a in applications)

    return render_template("department_dashboard.html", department=department, positions=positions,
                           total_applications=len(applications), pending_applications=awaiting)


@app.route("/department/position/create", methods=["GET", "POST"])
@department_login_required
def create_position():
    if request.method == "POST":
        form = request.form
        try:
            position = Position(
                title=form["title"].strip(),
                description=form["description"].strip(),
                required_gpa=float(form["required_gpa"]) if form.get("required_gpa") else None,
                required_credits=int(form["required_credits"]) if form.get("required_credits") else None,
                required_skills=form.get("required_skills", ""),
                required_level=form.get("required_level", ""),
                required_school=form.get("required_school", ""),
                department_id=session["user_id"],
            )
        except ValueError:
            flash("Required GPA and credits must be numbers.", "danger")
            return render_template("create_position.html")

        db.session.add(position)
        db.session.commit()
        flash("Position posted.", "success")
        return redirect(url_for("department_dashboard"))

    return render_template("create_position.html")


def own_position_or_redirect(position_id):
    position = Position.query.get_or_404(position_id)
    if position.department_id != session["user_id"]:
        flash("That position belongs to another department.", "danger")
        return None
    return position


@app.route("/department/position/<int:position_id>/delete", methods=["POST"])
@department_login_required
def delete_position(position_id):
    position = own_position_or_redirect(position_id)
    if position:
        db.session.delete(position)
        db.session.commit()
        flash("Position deleted.", "info")
    return redirect(url_for("department_dashboard"))


@app.route("/department/position/<int:position_id>/applicants")
@department_login_required
def view_applicants(position_id):
    position = own_position_or_redirect(position_id)
    if position is None:
        return redirect(url_for("department_dashboard"))

    applications = (
        Application.query.filter_by(position_id=position_id)
        .order_by(Application.ai_score.desc()).all()
    )
    return render_template("view_applicants.html", position=position, applications=applications)


STATUS_MESSAGES = {
    "accepted": "Good news: your application for {title} was accepted. Expect an interview invitation soon.",
    "rejected": "Thanks for applying to {title}. The department has decided to go with other candidates.",
    "under_review": "Your application for {title} is now under review.",
    "pending": "Your application for {title} was moved back to pending.",
}


@app.route("/department/application/<int:app_id>/update", methods=["POST"])
@department_login_required
def update_application(app_id):
    application = Application.query.get_or_404(app_id)
    if application.position.department_id != session["user_id"]:
        abort(403)

    new_status = request.form.get("status")
    if new_status not in APPLICATION_STATUSES:
        flash("Unknown status.", "danger")
        return redirect(url_for("view_applicants", position_id=application.position_id))

    if new_status != application.status:
        application.status = new_status
        db.session.add(Notification(
            student_id=application.student_id,
            message=STATUS_MESSAGES[new_status].format(title=application.position.title),
        ))
        db.session.commit()
        flash("Status updated and the student was notified.", "success")

    return redirect(url_for("view_applicants", position_id=application.position_id))


@app.route("/department/profile", methods=["GET", "POST"])
@department_login_required
def department_profile():
    department = db.session.get(Department, session["user_id"])

    if request.method == "POST":
        department.name = request.form["name"].strip()
        department.description = request.form.get("description", "")

        if request.form.get("remove_logo"):
            delete_upload(LOGO_DIR, department.logo_path)
            department.logo_path = None

        logo = request.files.get("logo")
        if logo and logo.filename:
            saved = save_upload(logo, LOGO_DIR, department.name, app.config["LOGO_EXTENSIONS"])
            if saved is None:
                flash("Logo must be a PNG, JPG or WEBP image.", "danger")
                return redirect(url_for("department_profile"))
            if department.logo_path != saved:
                delete_upload(LOGO_DIR, department.logo_path)
            department.logo_path = saved

        try:
            db.session.commit()
            session["user_name"] = department.name
            flash("Department profile updated.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Another department already uses that name.", "danger")
        return redirect(url_for("department_profile"))

    return render_template("department_profile.html", department=department)


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", "5000")))
