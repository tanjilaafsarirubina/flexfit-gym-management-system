from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    trainer_profile = db.relationship('TrainerProfile', backref='user', uselist=False)
    memberships = db.relationship('UserMembership', backref='user', lazy=True)
    bookings = db.relationship('ClassBooking', backref='user', lazy=True)
    workout_logs = db.relationship('WorkoutLog', backref='user', lazy=True)
    reviews_written = db.relationship('Feedback', foreign_keys='Feedback.user_id', backref='author', lazy=True)
    coaching_sessions_as_client = db.relationship('CoachingSession', foreign_keys='CoachingSession.client_id', backref='client', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_active_membership(self):
        return UserMembership.query.filter(UserMembership.user_id == self.id, UserMembership.status.in_(['active', 'frozen'])).order_by(UserMembership.end_date.desc()).first()

    def get_classes_attended_count(self):
        return ClassBooking.query.filter_by(user_id=self.id, attended=True).count()

    def get_upcoming_bookings_count(self):
        return ClassBooking.query.filter_by(user_id=self.id, status='booked', attended=False).count()

    def get_total_weight_lifted(self):
        logs = WorkoutLog.query.filter_by(user_id=self.id).all()
        return sum(log.weight_kg * log.sets * log.reps for log in logs)


class TrainerProfile(db.Model):
    __tablename__ = 'trainer_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    specialization = db.Column(db.String(100), nullable=False)
    hourly_rate = db.Column(db.Numeric(10, 2), nullable=False)
    profile_image_url = db.Column(db.String(255), nullable=True)

    classes = db.relationship('GymClass', backref='trainer', lazy=True)
    availability_slots = db.relationship('TrainerAvailability', backref='trainer', lazy=True)
    coaching_sessions = db.relationship('CoachingSession', backref='trainer', lazy=True)
    reviews_received = db.relationship('Feedback', foreign_keys='Feedback.trainer_id', backref='trainer', lazy=True)

    def get_average_rating(self):
        revs = [r.rating for r in self.reviews_received]
        if not revs:
            return 5.0, 0
        return round(sum(revs) / len(revs), 1), len(revs)

    def user_has_attended(self, user_id):
        if not user_id:
            return False
        has_class = ClassBooking.query.join(GymClass).filter(
            ClassBooking.user_id == user_id,
            ClassBooking.attended == True,
            GymClass.trainer_id == self.id
        ).first() is not None
        if has_class:
            return True
        has_coaching = CoachingSession.query.filter_by(
            client_id=user_id,
            trainer_id=self.id,
            status='completed'
        ).first() is not None
        return has_coaching

    def user_has_reviewed(self, user_id):
        if not user_id:
            return False
        return Feedback.query.filter_by(trainer_id=self.id, user_id=user_id).first() is not None


class MembershipPlan(db.Model):
    __tablename__ = 'membership_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    features = db.Column(db.Text, nullable=True)


class UserMembership(db.Model):
    __tablename__ = 'user_memberships'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('membership_plans.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='active')

    plan = db.relationship('MembershipPlan', backref='user_memberships', lazy=True)

    @property
    def days_remaining(self):
        today = datetime.utcnow().date()
        rem = (self.end_date - today).days
        return max(0, rem)

    @property
    def is_expired(self):
        return datetime.utcnow().date() > self.end_date


class GymClass(db.Model):
    __tablename__ = 'gym_classes'
    
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey('trainer_profiles.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    duration_mins = db.Column(db.Integer, default=60)
    max_capacity = db.Column(db.Integer, nullable=False)

    bookings = db.relationship('ClassBooking', backref='gym_class', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Feedback', foreign_keys='Feedback.class_id', backref='gym_class', lazy=True, cascade="all, delete-orphan")

    @property
    def booked_count(self):
        return ClassBooking.query.filter_by(class_id=self.id, status='booked').count()

    def is_booked_by_user(self, user_id):
        if not user_id:
            return False
        return ClassBooking.query.filter_by(class_id=self.id, user_id=user_id, status='booked').first() is not None

    def user_has_attended(self, user_id):
        if not user_id:
            return False
        return ClassBooking.query.filter_by(class_id=self.id, user_id=user_id, attended=True).first() is not None

    def user_has_reviewed(self, user_id):
        if not user_id:
            return False
        return Feedback.query.filter_by(class_id=self.id, user_id=user_id).first() is not None

    def get_average_rating(self):
        revs = [r.rating for r in self.reviews]
        if not revs:
            return 5.0, 0
        return round(sum(revs) / len(revs), 1), len(revs)


class ClassBooking(db.Model):
    __tablename__ = 'class_bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=False)
    status = db.Column(db.String(20), default='booked')
    attended = db.Column(db.Boolean, default=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrainerAvailability(db.Model):
    __tablename__ = 'trainer_availabilities'
    
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey('trainer_profiles.id'), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_booked = db.Column(db.Boolean, default=False)


class CoachingSession(db.Model):
    __tablename__ = 'coaching_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    trainer_id = db.Column(db.Integer, db.ForeignKey('trainer_profiles.id'), nullable=False)
    session_time = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='scheduled')


class ExerciseVideo(db.Model):
    __tablename__ = 'exercise_videos'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    video_url = db.Column(db.String(255), nullable=False)
    thumbnail_url = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MealPlan(db.Model):
    __tablename__ = 'meal_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    goal = db.Column(db.String(50), nullable=False)
    calories_per_day = db.Column(db.Integer, nullable=False)
    protein_g = db.Column(db.Integer, default=150)
    carbs_g = db.Column(db.Integer, default=200)
    fat_g = db.Column(db.Integer, default=60)
    pdf_url = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    meal_breakdown = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkoutLog(db.Model):
    __tablename__ = 'workout_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    exercise_name = db.Column(db.String(100), nullable=False)
    sets = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    log_date = db.Column(db.Date, default=datetime.utcnow)


class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    trainer_id = db.Column(db.Integer, db.ForeignKey('trainer_profiles.id'), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=True)
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)