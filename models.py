from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    department = db.Column(db.String(100))
    year = db.Column(db.String(20))
    class_name = db.Column(db.String(50))
    role = db.Column(db.String(20), default='student')
    points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    preference = db.relationship('Preference', backref='user', uselist=False)
    swipes = db.relationship('Swipe', backref='user', lazy=True)
    reservations = db.relationship('Reservation', backref='user', lazy=True)
    achievements = db.relationship('UserAchievement', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Preference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    front_back = db.Column(db.Float, default=5)   # 1=front, 10=back
    window = db.Column(db.Float, default=5)
    visibility = db.Column(db.Float, default=5)   # 1=visible to board, 10=invisible
    charging = db.Column(db.Float, default=5)
    comfort = db.Column(db.Float, default=5)

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rows = db.Column(db.Integer, default=6)
    columns = db.Column(db.Integer, default=5)
    chairs = db.relationship('Chair', backref='classroom', lazy=True, cascade='all, delete-orphan')

class Chair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    chair_code = db.Column(db.String(20), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    window_score = db.Column(db.Float, default=5)
    ac_score = db.Column(db.Float, default=5)
    visibility_score = db.Column(db.Float, default=5)  # 1=visible, 10=invisible
    noise_score = db.Column(db.Float, default=5)
    comfort_score = db.Column(db.Float, default=5)
    charging = db.Column(db.Boolean, default=False)
    qr_token = db.Column(db.String(64), unique=True, default=lambda: str(uuid.uuid4()))
    swipes = db.relationship('Swipe', backref='chair', lazy=True, cascade='all, delete-orphan')
    reservations = db.relationship('Reservation', backref='chair', lazy=True, cascade='all, delete-orphan')

    @property
    def front_back_score(self):
        # row 1=front(1), row 6=back(10)
        return ((self.row - 1) / 5) * 9 + 1

    @property
    def like_count(self):
        return sum(1 for s in self.swipes if s.action == 'like')

    @property
    def dislike_count(self):
        return sum(1 for s in self.swipes if s.action == 'dislike')

class Swipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chair_id = db.Column(db.Integer, db.ForeignKey('chair.id'), nullable=False)
    action = db.Column(db.String(10), nullable=False)  # like / dislike
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chair_id = db.Column(db.Integer, db.ForeignKey('chair.id'), nullable=False)
    date = db.Column(db.String(20))
    status = db.Column(db.String(20), default='active')  # active / cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(200))
    icon = db.Column(db.String(10))
    points = db.Column(db.Integer, default=10)

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    achievement = db.relationship('Achievement')
