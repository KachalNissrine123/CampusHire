from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    school = db.Column(db.String(20), nullable=False)  
    level = db.Column(db.String(20), nullable=False)  
    student_type = db.Column(db.String(20), nullable=False)  
    gpa = db.Column(db.Float, nullable=True)
    credits = db.Column(db.Integer, nullable=True)
    cv_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    
    applications = db.relationship('Application', backref='student', lazy=True, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='student', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'email': self.email,
            'school': self.school,
            'level': self.level,
            'student_type': self.student_type,
            'gpa': self.gpa,
            'credits': self.credits,
            'cv_path': self.cv_path
        }


class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    logo_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    
    positions = db.relationship('Position', backref='department', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'description': self.description,
            'logo_path': self.logo_path
        }


class Position(db.Model):
    __tablename__ = 'positions'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    required_gpa = db.Column(db.Float, nullable=True)
    required_credits = db.Column(db.Integer, nullable=True)
    required_skills = db.Column(db.Text, nullable=True) 
    required_level = db.Column(db.String(50), nullable=True) 
    required_school = db.Column(db.String(50), nullable=True)  
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    
    applications = db.relationship('Application', backref='position', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'required_gpa': self.required_gpa,
            'required_credits': self.required_credits,
            'required_skills': self.required_skills,
            'required_level': self.required_level,
            'required_school': self.required_school,
            'department_id': self.department_id,
            'department_name': self.department.name if self.department else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Application(db.Model):
    __tablename__ = 'applications'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'), nullable=False)
    status = db.Column(db.String(20), default='pending') 
    ai_score = db.Column(db.Float, nullable=True)
    ai_feedback = db.Column(db.Text, nullable=True)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.full_name if self.student else None,
            'student_email': self.student.email if self.student else None,
            'student_gpa': self.student.gpa if self.student else None,
            'student_credits': self.student.credits if self.student else None,
            'student_level': self.student.level if self.student else None,
            'student_school': self.student.school if self.student else None,
            'position_id': self.position_id,
            'position_title': self.position.title if self.position else None,
            'status': self.status,
            'ai_score': self.ai_score,
            'ai_feedback': self.ai_feedback,
            'applied_at': self.applied_at.isoformat() if self.applied_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'message': self.message,
            'is_read': self.is_read,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }