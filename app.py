import hmac
import os
import random
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlsplit
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import func
from gym_models import (
    db, User, TrainerProfile, MembershipPlan, UserMembership,
    GymClass, ClassBooking, TrainerAvailability, CoachingSession,
    ExerciseVideo, MealPlan, WorkoutLog, Feedback, Payment,
    local_now, local_today
)

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, instance_relative_config=True)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(basedir, 'flexfit.db')}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['WTF_CSRF_TIME_LIMIT'] = None  # token lives as long as the session

# Secrets never live in the repo. Set them as environment variables or in instance/config.py (git-ignored).
# Staff sign-up stays disabled until an invite code is configured; admins can still promote users.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['TRAINER_INVITE_CODE'] = os.environ.get('TRAINER_INVITE_CODE')
app.config['ADMIN_INVITE_CODE'] = os.environ.get('ADMIN_INVITE_CODE')
app.config.from_pyfile('config.py', silent=True)


def _load_or_create_secret_key():
    """Keep a random per-install key in instance/secret_key so sessions survive restarts."""
    key_file = os.path.join(app.instance_path, 'secret_key')
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    os.makedirs(app.instance_path, exist_ok=True)
    key = secrets.token_hex(32)
    with open(key_file, 'w') as f:
        f.write(key)
    return key


if not app.config['SECRET_KEY']:
    app.config['SECRET_KEY'] = _load_or_create_secret_key()

db.init_app(app)
csrf = CSRFProtect(app)

with app.app_context():
    db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash('Access denied: You do not have permission for this section.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    message = 'Your session expired or the page was out of date. Please reload and try again.'
    if request.is_json:
        return jsonify({'success': False, 'message': message}), 400
    flash(message, 'danger')
    return redirect(url_for('index'))


def safe_next_url(target):
    """Only follow ?next= to a path on this site, never to another host."""
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return None
    parts = urlsplit(target)
    return target if not parts.scheme and not parts.netloc else None


def is_http_url(value):
    parts = urlsplit(value or '')
    return parts.scheme in ('http', 'https') and bool(parts.netloc)


def staff_code_matches(role, submitted):
    expected = app.config.get('TRAINER_INVITE_CODE' if role == 'trainer' else 'ADMIN_INVITE_CODE')
    return bool(expected) and hmac.compare_digest(submitted.encode(), str(expected).encode())


def valid_macros(calories, *grams):
    return bool(calories) and calories >= 1 and all(g is not None and g >= 0 for g in grams)


def sandbox_revenue():
    return float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar())


def payment_count():
    return Payment.query.count()


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    staff_signup = {
        'trainer': bool(app.config.get('TRAINER_INVITE_CODE')),
        'admin': bool(app.config.get('ADMIN_INVITE_CODE')),
    }

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'member').lower()

        if not full_name or not email or not password or not phone:
            flash('All fields are required.', 'danger')
            return render_template('register.html', staff_signup=staff_signup)

        staff_passcode = request.form.get('staff_passcode', '').strip()

        if role not in ['member', 'trainer', 'admin']:
            role = 'member'

        if role == 'trainer' and not staff_code_matches('trainer', staff_passcode):
            flash('Invalid Staff Invite Passcode for Personal Trainer registration.', 'danger')
            return render_template('register.html', staff_signup=staff_signup)

        if role == 'admin' and not staff_code_matches('admin', staff_passcode):
            flash('Invalid Admin Passcode for System Administrator registration.', 'danger')
            return render_template('register.html', staff_signup=staff_signup)

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email address is already registered.', 'danger')
            return render_template('register.html', staff_signup=staff_signup)

        user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            role=role
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        if role == 'trainer':
            profile = TrainerProfile(
                user_id=user.id,
                bio="Certified Personal Trainer specialized in Strength & Functional Fitness.",
                specialization="General Fitness",
                hourly_rate=50.00,
                profile_image_url="https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=400"
            )
            db.session.add(profile)
            db.session.commit()

        if role == 'member':
            default_plan = MembershipPlan.query.filter_by(name='Monthly Access').first()
            if default_plan:
                user_membership = UserMembership(
                    user_id=user.id,
                    plan_id=default_plan.id,
                    start_date=local_today(),
                    end_date=local_today() + timedelta(days=30),
                    status='active'
                )
                db.session.add(user_membership)
                db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', staff_signup=staff_signup)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.full_name.split()[0]}!', 'success')
            next_page = safe_next_url(request.args.get('next'))
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    category_filter = request.args.get('category', 'ALL').upper()

    query = GymClass.query
    if category_filter != 'ALL':
        query = query.filter(GymClass.category.ilike(category_filter))
    
    classes = query.order_by(GymClass.start_time.asc()).all()

    active_membership = current_user.get_active_membership()
    membership_name = active_membership.plan.name if (active_membership and active_membership.plan) else "No Active Plan"
    membership_status = active_membership.status.capitalize() if active_membership else "Inactive"

    classes_attended = current_user.get_classes_attended_count()
    upcoming_bookings = current_user.get_upcoming_bookings_count()
    total_weight = current_user.get_total_weight_lifted()

    trainer_classes = []
    trainer_coaching = []
    trainer_rating = 5.0
    trainer_rev_count = 0
    trainer_students = 0

    if current_user.role == 'trainer' and current_user.trainer_profile:
        t_prof = current_user.trainer_profile
        trainer_classes = GymClass.query.filter_by(trainer_id=t_prof.id).order_by(GymClass.start_time.asc()).all()
        trainer_coaching = CoachingSession.query.filter_by(trainer_id=t_prof.id).order_by(CoachingSession.session_time.desc()).all()
        trainer_rating, trainer_rev_count = t_prof.get_average_rating()
        trainer_students = sum(c.booked_count for c in trainer_classes)

    total_users_count = 0
    total_classes_count = 0
    total_bookings_count = 0
    total_revenue = 0.0
    recent_bookings = []
    recent_users = []

    if current_user.role == 'admin':
        total_users_count = User.query.count()
        total_classes_count = GymClass.query.count()
        total_bookings_count = ClassBooking.query.count()
        total_revenue = sandbox_revenue()
        recent_bookings = ClassBooking.query.order_by(ClassBooking.id.desc()).limit(6).all()
        recent_users = User.query.order_by(User.id.desc()).limit(6).all()

    return render_template(
        'dashboard.html',
        classes=classes,
        current_category=category_filter,
        membership_name=membership_name,
        membership_status=membership_status,
        classes_attended=classes_attended,
        upcoming_bookings=upcoming_bookings,
        total_weight=total_weight,
        trainer_classes=trainer_classes,
        trainer_coaching=trainer_coaching,
        trainer_rating=trainer_rating,
        trainer_rev_count=trainer_rev_count,
        trainer_students=trainer_students,
        total_users_count=total_users_count,
        total_classes_count=total_classes_count,
        total_bookings_count=total_bookings_count,
        total_revenue=total_revenue,
        recent_bookings=recent_bookings,
        recent_users=recent_users
    )


@app.route('/schedule')
@login_required
def schedule():
    category_filter = request.args.get('category', 'ALL').upper()
    query = GymClass.query
    if category_filter != 'ALL':
        query = query.filter(GymClass.category.ilike(category_filter))
    
    classes = query.order_by(GymClass.start_time.asc()).all()
    trainers = TrainerProfile.query.all()
    return render_template('schedule.html', classes=classes, trainers=trainers, current_category=category_filter)


@app.route('/api/book_class', methods=['POST'])
@login_required
def book_class_api():
    data = request.get_json() or {}
    class_id = data.get('class_id')

    if not class_id:
        return jsonify({'success': False, 'message': 'Class ID missing.'}), 400

    gym_class = db.session.get(GymClass, class_id)
    if not gym_class:
        return jsonify({'success': False, 'message': 'Class not found.'}), 404

    active_mem = current_user.get_active_membership()
    if not active_mem or active_mem.status == 'frozen':
        return jsonify({'success': False, 'message': 'Active membership required to book classes. Your account may be frozen or expired.'}), 403

    existing_booking = ClassBooking.query.filter_by(
        user_id=current_user.id,
        class_id=gym_class.id,
        status='booked'
    ).first()

    if existing_booking:
        return jsonify({'success': False, 'message': 'You have already booked this class.'}), 400

    if gym_class.booked_count >= gym_class.max_capacity:
        return jsonify({'success': False, 'message': 'Class is at full capacity.'}), 400

    booking = ClassBooking(
        user_id=current_user.id,
        class_id=gym_class.id,
        status='booked',
        attended=False
    )
    db.session.add(booking)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Successfully booked "{gym_class.title}"!',
        'booked': True,
        'booked_count': gym_class.booked_count,
        'max_capacity': gym_class.max_capacity,
        'user_total_classes': current_user.get_classes_attended_count(),
        'user_upcoming_bookings': current_user.get_upcoming_bookings_count()
    })


@app.route('/api/cancel_booking', methods=['POST'])
@login_required
def cancel_booking_api():
    data = request.get_json() or {}
    class_id = data.get('class_id')

    if not class_id:
        return jsonify({'success': False, 'message': 'Class ID missing.'}), 400

    booking = ClassBooking.query.filter_by(
        user_id=current_user.id,
        class_id=class_id,
        status='booked'
    ).first()

    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found.'}), 400

    booking.status = 'cancelled'
    db.session.commit()

    gym_class = db.session.get(GymClass, class_id)

    return jsonify({
        'success': True,
        'message': f'Booking for "{gym_class.title}" cancelled.',
        'booked': False,
        'booked_count': gym_class.booked_count,
        'max_capacity': gym_class.max_capacity,
        'user_total_classes': current_user.get_classes_attended_count(),
        'user_upcoming_bookings': current_user.get_upcoming_bookings_count()
    })


@app.route('/tracker', methods=['GET', 'POST'])
@login_required
def tracker():
    if request.method == 'POST':
        exercise_name = request.form.get('exercise_name', '').strip()
        sets = request.form.get('sets', type=int)
        reps = request.form.get('reps', type=int)
        weight_kg = request.form.get('weight_kg', type=float)

        if not exercise_name or not sets or not reps or weight_kg is None or sets < 1 or reps < 1 or weight_kg < 0:
            flash('Please fill in all workout log fields correctly.', 'danger')
        else:
            workout_log = WorkoutLog(
                user_id=current_user.id,
                exercise_name=exercise_name,
                sets=sets,
                reps=reps,
                weight_kg=weight_kg,
                log_date=local_today()
            )
            db.session.add(workout_log)
            db.session.commit()
            flash(f'Logged exercise: {exercise_name} ({sets} sets x {reps} reps @ {weight_kg}kg)', 'success')
            return redirect(url_for('tracker'))

    logs = WorkoutLog.query.filter_by(user_id=current_user.id).order_by(WorkoutLog.log_date.desc(), WorkoutLog.id.desc()).all()
    total_weight = current_user.get_total_weight_lifted()
    total_entries = len(logs)

    return render_template(
        'tracker.html',
        logs=logs,
        total_weight=total_weight,
        total_entries=total_entries
    )


@app.route('/api/delete_workout/<int:log_id>', methods=['POST'])
@login_required
def delete_workout(log_id):
    log = db.session.get(WorkoutLog, log_id)
    if log and log.user_id == current_user.id:
        db.session.delete(log)
        db.session.commit()
        flash('Workout entry deleted.', 'info')
    else:
        flash('Workout log not found or permission denied.', 'danger')
    return redirect(url_for('tracker'))


@app.route('/membership')
@login_required
def membership():
    plans = MembershipPlan.query.all()
    user_membership = current_user.get_active_membership()
    return render_template('membership.html', plans=plans, user_membership=user_membership)


@app.route('/membership/checkout/<int:plan_id>', methods=['POST'])
@login_required
def membership_checkout(plan_id):
    plan = db.session.get(MembershipPlan, plan_id)
    if not plan:
        return jsonify({'success': False, 'message': 'Membership plan not found.'}), 404

    data = request.get_json() or {}
    payment_method = str(data.get('payment_method', 'bkash')).lower()
    account_number = str(data.get('account_number', '')).strip().replace(' ', '').replace('-', '')
    card_number = str(data.get('card_number', '')).strip().replace(' ', '').replace('-', '')
    pin = str(data.get('pin', '')).strip()

    if payment_method == 'bkash':
        if len(account_number) != 11 or not account_number.isdigit() or not account_number.startswith('01'):
            return jsonify({'success': False, 'message': 'Please enter a valid 11-digit bKash number (e.g. 017XXXXXXXX).'}), 400
        if len(pin) < 4:
            return jsonify({'success': False, 'message': 'Please enter your 5-digit bKash PIN.'}), 400
        trx_id = f"BKASH{random.randint(10000000, 99999999)}"
        channel_name = "bKash Merchant Gateway"

    elif payment_method == 'nagad':
        if len(account_number) != 11 or not account_number.isdigit() or not account_number.startswith('01'):
            return jsonify({'success': False, 'message': 'Please enter a valid 11-digit Nagad number (e.g. 018XXXXXXXX).'}), 400
        if len(pin) < 4:
            return jsonify({'success': False, 'message': 'Please enter your 4-digit Nagad PIN.'}), 400
        trx_id = f"NAGAD{random.randint(10000000, 99999999)}"
        channel_name = "Nagad Direct Pay Gateway"

    elif payment_method == 'rocket':
        if len(account_number) < 11 or not account_number.isdigit():
            return jsonify({'success': False, 'message': 'Please enter a valid 12-digit DBBL Rocket number.'}), 400
        if len(pin) < 4:
            return jsonify({'success': False, 'message': 'Please enter your 4-digit Rocket PIN.'}), 400
        trx_id = f"ROCKET{random.randint(10000000, 99999999)}"
        channel_name = "DBBL Rocket Gateway"

    else:
        payment_method = 'card'
        raw_card = card_number or account_number
        if len(raw_card) < 12 or not raw_card.isdigit():
            return jsonify({'success': False, 'message': 'Please enter a valid 16-digit card number for sandbox payment.'}), 400
        trx_id = f"VISA{random.randint(10000000, 99999999)}"
        channel_name = "Visa / Mastercard 3D Secure"

    today = local_today()
    current_mem = current_user.get_active_membership()

    if current_mem and not current_mem.is_expired:
        new_start = current_mem.start_date
        new_end = current_mem.end_date + timedelta(days=plan.duration_days)
        current_mem.plan_id = plan.id
        current_mem.end_date = new_end
        current_mem.status = 'active'
    else:
        new_mem = UserMembership(
            user_id=current_user.id,
            plan_id=plan.id,
            start_date=today,
            end_date=today + timedelta(days=plan.duration_days),
            status='active'
        )
        db.session.add(new_mem)
        new_end = today + timedelta(days=plan.duration_days)

    db.session.add(Payment(
        user_id=current_user.id,
        plan_name=plan.name,
        amount=plan.price,
        method=payment_method,
        transaction_id=trx_id
    ))
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Sandbox payment approved! {plan.name} is now active.',
        'transaction_id': trx_id,
        'payment_method': payment_method.upper(),
        'channel_name': channel_name,
        'amount': float(plan.price),
        'amount_bdt': round(float(plan.price) * 110, 2),
        'plan_name': plan.name,
        'duration_days': plan.duration_days,
        'end_date': new_end.strftime('%b %d, %Y')
    })


@app.route('/membership/toggle_freeze', methods=['POST'])
@login_required
def toggle_membership_freeze():
    current_mem = current_user.get_active_membership()
    if not current_mem:
        return jsonify({'success': False, 'message': 'No active membership found to freeze.'}), 404

    new_status = 'frozen' if current_mem.status == 'active' else 'active'
    current_mem.status = new_status
    db.session.commit()

    action_label = 'frozen' if new_status == 'frozen' else 'unfrozen and activated'
    return jsonify({
        'success': True,
        'message': f'Your membership has been {action_label}.',
        'status': new_status
    })


@app.route('/trainers')
@login_required
def trainers():
    trainers_list = TrainerProfile.query.all()
    user_coaching_sessions = CoachingSession.query.filter_by(client_id=current_user.id).order_by(CoachingSession.session_time.desc()).all()
    
    trainer_appointments = []
    if current_user.role == 'trainer' and current_user.trainer_profile:
        trainer_appointments = CoachingSession.query.filter_by(trainer_id=current_user.trainer_profile.id).order_by(CoachingSession.session_time.desc()).all()
    elif current_user.role == 'admin':
        trainer_appointments = CoachingSession.query.order_by(CoachingSession.session_time.desc()).all()

    return render_template(
        'trainers.html',
        trainers=trainers_list,
        user_coaching_sessions=user_coaching_sessions,
        trainer_appointments=trainer_appointments
    )


@app.route('/api/book_coaching', methods=['POST'])
@login_required
def book_coaching_api():
    data = request.get_json() or {}
    trainer_id = data.get('trainer_id')
    session_time_str = data.get('session_time')
    notes = data.get('notes', '').strip()

    if not trainer_id or not session_time_str:
        return jsonify({'success': False, 'message': 'Trainer ID and Session Time are required.'}), 400

    trainer = db.session.get(TrainerProfile, trainer_id)
    if not trainer:
        return jsonify({'success': False, 'message': 'Trainer profile not found.'}), 404

    try:
        session_time = datetime.strptime(session_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DDTHH:MM.'}), 400

    if session_time < local_now():
        return jsonify({'success': False, 'message': 'Cannot schedule appointments in the past.'}), 400

    coaching_session = CoachingSession(
        client_id=current_user.id,
        trainer_id=trainer.id,
        session_time=session_time,
        notes=notes,
        status='scheduled'
    )
    db.session.add(coaching_session)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'1-on-1 Coaching session scheduled with {trainer.user.full_name} for {session_time.strftime("%b %d, %Y @ %I:%M %p")}!',
        'session_id': coaching_session.id
    })


@app.route('/api/cancel_coaching/<int:session_id>', methods=['POST'])
@login_required
def cancel_coaching_api(session_id):
    session = db.session.get(CoachingSession, session_id)
    if not session:
        return jsonify({'success': False, 'message': 'Session not found.'}), 404

    is_client = session.client_id == current_user.id
    is_trainer = current_user.role == 'trainer' and session.trainer.user_id == current_user.id
    is_admin = current_user.role == 'admin'

    if not (is_client or is_trainer or is_admin):
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    session.status = 'cancelled'
    db.session.commit()

    return jsonify({'success': True, 'message': 'Coaching appointment cancelled.'})


@app.route('/api/update_coaching_status/<int:session_id>', methods=['POST'])
@login_required
def update_coaching_status_api(session_id):
    session = db.session.get(CoachingSession, session_id)
    if not session:
        return jsonify({'success': False, 'message': 'Session not found.'}), 404

    is_trainer = current_user.role == 'trainer' and session.trainer.user_id == current_user.id
    is_admin = current_user.role == 'admin'

    if not (is_trainer or is_admin):
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    data = request.get_json() or {}
    new_status = data.get('status')
    trainer_notes = data.get('notes')

    if new_status in ['scheduled', 'completed', 'cancelled']:
        session.status = new_status
    if trainer_notes is not None:
        session.notes = str(trainer_notes).strip()

    db.session.commit()
    return jsonify({'success': True, 'message': f'Coaching session updated to {session.status}.'})


@app.route('/api/update_trainer_profile', methods=['POST'])
@login_required
def update_trainer_profile_api():
    data = request.get_json() or {}
    trainer_id = data.get('trainer_id')

    if current_user.role == 'trainer':
        if not current_user.trainer_profile:
            return jsonify({'success': False, 'message': 'Trainer profile not found.'}), 404
        profile = current_user.trainer_profile
    elif current_user.role == 'admin':
        if not trainer_id:
            return jsonify({'success': False, 'message': 'Trainer ID required.'}), 400
        profile = db.session.get(TrainerProfile, trainer_id)
        if not profile:
            return jsonify({'success': False, 'message': 'Trainer profile not found.'}), 404
    else:
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    bio = str(data.get('bio', '')).strip()
    specialization = str(data.get('specialization', '')).strip()
    hourly_rate = data.get('hourly_rate')

    if hourly_rate:
        try:
            hourly_rate = float(hourly_rate)
        except (TypeError, ValueError):
            hourly_rate = 0
        if hourly_rate <= 0:
            return jsonify({'success': False, 'message': 'Hourly rate must be a positive number.'}), 400
        profile.hourly_rate = hourly_rate
    if bio:
        profile.bio = bio
    if specialization:
        profile.specialization = specialization

    db.session.commit()
    return jsonify({'success': True, 'message': 'Trainer profile updated successfully.'})


@app.route('/videos')
@login_required
def videos():
    search_query = request.args.get('q', '').strip()
    category_filter = request.args.get('category', 'ALL').upper()
    difficulty_filter = request.args.get('difficulty', 'ALL').capitalize()

    query = ExerciseVideo.query

    if search_query:
        query = query.filter(
            db.or_(
                ExerciseVideo.title.ilike(f'%{search_query}%'),
                ExerciseVideo.description.ilike(f'%{search_query}%')
            )
        )

    if category_filter != 'ALL':
        query = query.filter(ExerciseVideo.category.ilike(category_filter))

    if difficulty_filter != 'All':
        query = query.filter(ExerciseVideo.difficulty.ilike(difficulty_filter))

    videos_list = query.order_by(ExerciseVideo.id.desc()).all()

    return render_template(
        'videos.html',
        videos=videos_list,
        current_category=category_filter,
        current_difficulty=difficulty_filter,
        search_query=search_query
    )


@app.route('/nutrition')
@login_required
def nutrition():
    goal_filter = request.args.get('goal', 'ALL').strip()
    query = MealPlan.query

    if goal_filter != 'ALL' and goal_filter != '':
        query = query.filter(MealPlan.goal.ilike(goal_filter))

    meal_plans = query.order_by(MealPlan.id.asc()).all()
    return render_template('nutrition.html', meal_plans=meal_plans, current_goal=goal_filter)


@app.route('/nutrition/download/<int:plan_id>')
@login_required
def download_nutrition_plan(plan_id):
    plan = db.session.get(MealPlan, plan_id)
    if not plan:
        flash('Nutrition blueprint not found.', 'danger')
        return redirect(url_for('nutrition'))
    return render_template('nutrition_pdf.html', plan=plan)


@app.route('/api/submit_feedback', methods=['POST'])
@login_required
def submit_feedback_api():
    if current_user.role != 'member':
        return jsonify({'success': False, 'message': 'Only registered gym members can submit reviews.'}), 403

    data = request.get_json() or {}
    rating = data.get('rating')
    try:
        rating = int(rating)
    except (ValueError, TypeError):
        rating = 0
    review_text = str(data.get('review_text', '')).strip()
    trainer_id = data.get('trainer_id')
    class_id = data.get('class_id')

    if not rating or rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Please provide a star rating between 1 and 5.'}), 400

    if not review_text:
        return jsonify({'success': False, 'message': 'Review feedback comment cannot be empty.'}), 400

    if not trainer_id and not class_id:
        return jsonify({'success': False, 'message': 'Review must be assigned to either a trainer or a class.'}), 400

    if class_id:
        gym_class = db.session.get(GymClass, int(class_id))
        if not gym_class:
            return jsonify({'success': False, 'message': 'Gym class not found.'}), 404
        if not gym_class.user_has_attended(current_user.id):
            return jsonify({'success': False, 'message': 'Attendance required: You can only review a class once an instructor or admin has marked your attendance for that class.'}), 403
        if gym_class.user_has_reviewed(current_user.id):
            return jsonify({'success': False, 'message': 'You have already submitted a review for this class.'}), 400

    if trainer_id:
        trainer = db.session.get(TrainerProfile, int(trainer_id))
        if not trainer:
            return jsonify({'success': False, 'message': 'Trainer profile not found.'}), 404
        if not trainer.user_has_attended(current_user.id):
            return jsonify({'success': False, 'message': 'Attendance required: You can only review an instructor once you have attended at least one of their classes or completed a 1-on-1 coaching session with them.'}), 403
        if trainer.user_has_reviewed(current_user.id):
            return jsonify({'success': False, 'message': 'You have already submitted a review for this instructor.'}), 400

    feedback = Feedback(
        user_id=current_user.id,
        trainer_id=int(trainer_id) if trainer_id else None,
        class_id=int(class_id) if class_id else None,
        rating=rating,
        review_text=review_text,
        created_at=local_now()
    )
    db.session.add(feedback)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Thank you! Your verified review has been submitted.',
        'rating': rating
    })


@app.route('/api/delete_feedback/<int:feedback_id>', methods=['POST'])
@login_required
def delete_feedback_api(feedback_id):
    fb = db.session.get(Feedback, feedback_id)
    if not fb:
        return jsonify({'success': False, 'message': 'Feedback record not found.'}), 404

    if fb.user_id != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    db.session.delete(fb)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Review removed.'})


@app.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    all_users = User.query.order_by(User.id.asc()).all()
    all_classes = GymClass.query.order_by(GymClass.start_time.asc()).all()
    all_bookings = ClassBooking.query.order_by(ClassBooking.id.desc()).all()
    all_videos = ExerciseVideo.query.order_by(ExerciseVideo.id.desc()).all()
    all_meal_plans = MealPlan.query.order_by(MealPlan.id.asc()).all()
    all_trainers = TrainerProfile.query.all()
    all_plans = MembershipPlan.query.all()
    all_feedbacks = Feedback.query.order_by(Feedback.id.desc()).all()
    all_coaching = CoachingSession.query.order_by(CoachingSession.session_time.desc()).all()

    return render_template(
        'admin.html',
        users=all_users,
        classes=all_classes,
        bookings=all_bookings,
        videos=all_videos,
        meal_plans=all_meal_plans,
        trainers=all_trainers,
        plans=all_plans,
        feedbacks=all_feedbacks,
        coaching_sessions=all_coaching,
        total_revenue=sandbox_revenue(),
        payment_count=payment_count()
    )


@app.route('/admin/membership_plan/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_membership_plan():
    name = request.form.get('name', '').strip()
    price = request.form.get('price', 0.0, type=float)
    duration_days = request.form.get('duration_days', 30, type=int)
    features = request.form.get('features', '').strip()

    if not name or price is None or price <= 0 or not duration_days or duration_days < 1:
        flash('Plan name, a positive price and a duration of at least 1 day are required.', 'danger')
        return redirect(url_for('admin_panel'))

    plan = MembershipPlan(
        name=name,
        price=price,
        duration_days=duration_days,
        features=features
    )
    db.session.add(plan)
    db.session.commit()
    flash(f'New Membership Tier "{name}" added successfully!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/membership_plan/edit/<int:plan_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_membership_plan(plan_id):
    plan = db.session.get(MembershipPlan, plan_id)
    if not plan:
        flash('Plan not found.', 'danger')
        return redirect(url_for('admin_panel'))

    name = request.form.get('name', plan.name).strip()
    price = request.form.get('price', plan.price, type=float)
    duration_days = request.form.get('duration_days', plan.duration_days, type=int)
    if not name or price is None or price <= 0 or not duration_days or duration_days < 1:
        flash('Plan name, a positive price and a duration of at least 1 day are required.', 'danger')
        return redirect(url_for('admin_panel'))

    plan.name = name
    plan.price = price
    plan.duration_days = duration_days
    plan.features = request.form.get('features', plan.features or '').strip()

    db.session.commit()
    flash(f'Membership Tier "{plan.name}" updated successfully!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/membership_plan/delete/<int:plan_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_membership_plan(plan_id):
    plan = db.session.get(MembershipPlan, plan_id)
    if plan:
        members_on_plan = UserMembership.query.filter_by(plan_id=plan.id).count()
        if members_on_plan:
            flash(f'"{plan.name}" cannot be deleted: {members_on_plan} membership record(s) use it. Edit its price or features instead.', 'danger')
            return redirect(url_for('admin_panel'))
        db.session.delete(plan)
        db.session.commit()
        flash('Membership tier deleted.', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/admin/feedback/delete/<int:feedback_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_feedback(feedback_id):
    fb = db.session.get(Feedback, feedback_id)
    if fb:
        db.session.delete(fb)
        db.session.commit()
        flash('Review removed from platform moderation.', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/admin/class/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_class():
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Strength').strip()
    trainer_id = request.form.get('trainer_id', type=int)
    start_time_str = request.form.get('start_time')
    duration_mins = request.form.get('duration_mins', 60, type=int)
    max_capacity = request.form.get('max_capacity', 12, type=int)

    if not title or not trainer_id or not start_time_str:
        flash('All class fields are required.', 'danger')
        return redirect(url_for('admin_panel'))

    if not duration_mins or duration_mins < 1 or not max_capacity or max_capacity < 1:
        flash('Duration and capacity must be at least 1.', 'danger')
        return redirect(url_for('admin_panel'))

    try:
        start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Invalid datetime format.', 'danger')
        return redirect(url_for('admin_panel'))

    new_class = GymClass(
        trainer_id=trainer_id,
        title=title,
        category=category,
        start_time=start_time,
        duration_mins=duration_mins,
        max_capacity=max_capacity
    )
    db.session.add(new_class)
    db.session.commit()
    flash(f'New Gym Class "{title}" created successfully!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/class/edit/<int:class_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_class(class_id):
    gym_class = db.session.get(GymClass, class_id)
    if not gym_class:
        flash('Class not found.', 'danger')
        return redirect(url_for('admin_panel'))

    gym_class.title = request.form.get('title', gym_class.title).strip()
    gym_class.category = request.form.get('category', gym_class.category).strip()
    gym_class.trainer_id = request.form.get('trainer_id', gym_class.trainer_id, type=int)
    start_time_str = request.form.get('start_time')
    if start_time_str:
        try:
            gym_class.start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            pass
    duration_mins = request.form.get('duration_mins', gym_class.duration_mins, type=int)
    max_capacity = request.form.get('max_capacity', gym_class.max_capacity, type=int)
    if not duration_mins or duration_mins < 1 or not max_capacity or max_capacity < 1:
        db.session.rollback()
        flash('Duration and capacity must be at least 1.', 'danger')
        return redirect(url_for('admin_panel'))
    gym_class.duration_mins = duration_mins
    gym_class.max_capacity = max_capacity

    db.session.commit()
    flash(f'Class "{gym_class.title}" updated successfully!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/class/delete/<int:class_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_class(class_id):
    gym_class = db.session.get(GymClass, class_id)
    if gym_class:
        db.session.delete(gym_class)
        db.session.commit()
        flash('Class deleted successfully.', 'info')
    else:
        flash('Class not found.', 'danger')
    return redirect(url_for('admin_panel'))


@app.route('/admin/video/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_video():
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Cardio').strip()
    difficulty = request.form.get('difficulty', 'Intermediate').strip()
    video_url = request.form.get('video_url', '').strip()
    thumbnail_url = request.form.get('thumbnail_url', '').strip()
    description = request.form.get('description', '').strip()

    if not title or not video_url:
        flash('Title and Video URL are required.', 'danger')
        return redirect(url_for('admin_panel'))

    if not is_http_url(video_url) or (thumbnail_url and not is_http_url(thumbnail_url)):
        flash('Video and thumbnail links must be full http:// or https:// URLs.', 'danger')
        return redirect(url_for('admin_panel'))

    video = ExerciseVideo(
        title=title,
        category=category,
        difficulty=difficulty,
        video_url=video_url,
        thumbnail_url=thumbnail_url or "https://images.unsplash.com/photo-1518611012118-696072aa579a?w=500",
        description=description,
        created_at=local_now()
    )
    db.session.add(video)
    db.session.commit()
    flash(f'Exercise Video "{title}" uploaded successfully!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/video/edit/<int:video_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_video(video_id):
    video = db.session.get(ExerciseVideo, video_id)
    if not video:
        flash('Video not found.', 'danger')
        return redirect(url_for('admin_panel'))

    video_url = request.form.get('video_url', video.video_url).strip()
    thumbnail_url = request.form.get('thumbnail_url', video.thumbnail_url or '').strip()
    if not is_http_url(video_url) or (thumbnail_url and not is_http_url(thumbnail_url)):
        flash('Video and thumbnail links must be full http:// or https:// URLs.', 'danger')
        return redirect(url_for('admin_panel'))

    video.title = request.form.get('title', video.title).strip()
    video.category = request.form.get('category', video.category).strip()
    video.difficulty = request.form.get('difficulty', video.difficulty).strip()
    video.video_url = video_url
    video.thumbnail_url = thumbnail_url or video.thumbnail_url
    video.description = request.form.get('description', video.description or '').strip()

    db.session.commit()
    flash(f'Video "{video.title}" updated!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/video/delete/<int:video_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_video(video_id):
    video = db.session.get(ExerciseVideo, video_id)
    if video:
        db.session.delete(video)
        db.session.commit()
        flash('Video removed from library.', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/trainer/class/create', methods=['POST'])
@login_required
def trainer_create_class():
    if current_user.role not in ['trainer', 'admin']:
        flash('Only trainers or administrators can schedule new classes.', 'danger')
        return redirect(url_for('schedule'))

    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Strength').strip()
    start_time_str = request.form.get('start_time')
    duration_mins = request.form.get('duration_mins', 60, type=int)
    max_capacity = request.form.get('max_capacity', 12, type=int)

    if current_user.role == 'trainer' and current_user.trainer_profile:
        trainer_id = current_user.trainer_profile.id
    else:
        trainer_id = request.form.get('trainer_id', type=int)

    if not title or not start_time_str or not trainer_id:
        flash('Class Title, Start Time, and Trainer are required.', 'danger')
        return redirect(url_for('schedule'))

    if not duration_mins or duration_mins < 1 or not max_capacity or max_capacity < 1:
        flash('Duration and capacity must be at least 1.', 'danger')
        return redirect(url_for('schedule'))

    try:
        start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('schedule'))

    new_class = GymClass(
        trainer_id=trainer_id,
        title=title,
        category=category,
        start_time=start_time,
        duration_mins=duration_mins,
        max_capacity=max_capacity
    )
    db.session.add(new_class)
    db.session.commit()
    flash(f'New class "{title}" published to the schedule successfully!', 'success')
    return redirect(url_for('schedule'))


@app.route('/trainer/video/create', methods=['POST'])
@login_required
def trainer_create_video():
    if current_user.role not in ['trainer', 'admin']:
        flash('Only trainers or administrators can post new video tutorials.', 'danger')
        return redirect(url_for('videos'))

    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Cardio').strip()
    difficulty = request.form.get('difficulty', 'Intermediate').strip()
    video_url = request.form.get('video_url', '').strip()
    thumbnail_url = request.form.get('thumbnail_url', '').strip()
    description = request.form.get('description', '').strip()

    if not title or not video_url:
        flash('Tutorial title and video link from the internet are required.', 'danger')
        return redirect(url_for('videos'))

    if not is_http_url(video_url) or (thumbnail_url and not is_http_url(thumbnail_url)):
        flash('Video and thumbnail links must be full http:// or https:// URLs.', 'danger')
        return redirect(url_for('videos'))

    v_id = None
    if 'watch?v=' in video_url:
        v_id = video_url.split('watch?v=')[1].split('&')[0]
        video_url = f"https://www.youtube.com/embed/{v_id}"
    elif 'youtu.be/' in video_url:
        v_id = video_url.split('youtu.be/')[1].split('?')[0]
        video_url = f"https://www.youtube.com/embed/{v_id}"

    if not thumbnail_url:
        if v_id:
            thumbnail_url = f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"
        elif category.lower() == 'cardio':
            thumbnail_url = "https://images.unsplash.com/photo-1518611012118-696072aa579a?w=500"
        elif category.lower() == 'yoga':
            thumbnail_url = "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=500"
        else:
            thumbnail_url = "https://images.unsplash.com/photo-1581009146145-b5ef050c2e1e?w=500"

    video = ExerciseVideo(
        title=title,
        category=category,
        difficulty=difficulty,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        description=description,
        created_at=local_now()
    )
    db.session.add(video)
    db.session.commit()
    flash(f'Exercise tutorial "{title}" posted and embedded into the video library!', 'success')
    return redirect(url_for('videos'))


@app.route('/admin/meal_plan/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_meal_plan():
    title = request.form.get('title', '').strip()
    goal = request.form.get('goal', 'Weight Loss').strip()
    calories_per_day = request.form.get('calories_per_day', 2000, type=int)
    protein_g = request.form.get('protein_g', 150, type=int)
    carbs_g = request.form.get('carbs_g', 200, type=int)
    fat_g = request.form.get('fat_g', 60, type=int)
    description = request.form.get('description', '').strip()
    meal_breakdown = request.form.get('meal_breakdown', '').strip()

    if not title:
        flash('Meal Plan Title is required.', 'danger')
        return redirect(url_for('admin_panel'))

    if not valid_macros(calories_per_day, protein_g, carbs_g, fat_g):
        flash('Calories must be at least 1 and macros cannot be negative.', 'danger')
        return redirect(url_for('admin_panel'))

    mp = MealPlan(
        title=title,
        goal=goal,
        calories_per_day=calories_per_day,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        description=description,
        meal_breakdown=meal_breakdown,
        pdf_url="#",
        created_at=local_now()
    )
    db.session.add(mp)
    db.session.commit()
    flash(f'Meal Plan "{title}" published!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/meal_plan/edit/<int:plan_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_meal_plan(plan_id):
    mp = db.session.get(MealPlan, plan_id)
    if not mp:
        flash('Meal plan not found.', 'danger')
        return redirect(url_for('admin_panel'))

    calories_per_day = request.form.get('calories_per_day', mp.calories_per_day, type=int)
    protein_g = request.form.get('protein_g', mp.protein_g, type=int)
    carbs_g = request.form.get('carbs_g', mp.carbs_g, type=int)
    fat_g = request.form.get('fat_g', mp.fat_g, type=int)
    if not valid_macros(calories_per_day, protein_g, carbs_g, fat_g):
        flash('Calories must be at least 1 and macros cannot be negative.', 'danger')
        return redirect(url_for('admin_panel'))

    mp.title = request.form.get('title', mp.title).strip()
    mp.goal = request.form.get('goal', mp.goal).strip()
    mp.calories_per_day = calories_per_day
    mp.protein_g = protein_g
    mp.carbs_g = carbs_g
    mp.fat_g = fat_g
    mp.description = request.form.get('description', mp.description).strip()
    mp.meal_breakdown = request.form.get('meal_breakdown', mp.meal_breakdown).strip()

    db.session.commit()
    flash(f'Meal Plan "{mp.title}" updated!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/meal_plan/delete/<int:plan_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_meal_plan(plan_id):
    mp = db.session.get(MealPlan, plan_id)
    if mp:
        db.session.delete(mp)
        db.session.commit()
        flash('Meal plan deleted.', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/trainer/meal_plan/create', methods=['POST'])
@login_required
def trainer_create_meal_plan():
    if current_user.role not in ['trainer', 'admin']:
        flash('Only trainers or administrators can publish nutrition blueprints.', 'danger')
        return redirect(url_for('nutrition'))

    title = request.form.get('title', '').strip()
    goal = request.form.get('goal', 'Weight Loss').strip()
    calories_per_day = request.form.get('calories_per_day', 2000, type=int)
    protein_g = request.form.get('protein_g', 150, type=int)
    carbs_g = request.form.get('carbs_g', 200, type=int)
    fat_g = request.form.get('fat_g', 60, type=int)
    description = request.form.get('description', '').strip()
    meal_breakdown = request.form.get('meal_breakdown', '').strip()

    if not title:
        flash('Nutrition Blueprint Title is required.', 'danger')
        return redirect(url_for('nutrition'))

    if not valid_macros(calories_per_day, protein_g, carbs_g, fat_g):
        flash('Calories must be at least 1 and macros cannot be negative.', 'danger')
        return redirect(url_for('nutrition'))

    mp = MealPlan(
        title=title,
        goal=goal,
        calories_per_day=calories_per_day,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        description=description,
        meal_breakdown=meal_breakdown,
        pdf_url="#",
        created_at=local_now()
    )
    db.session.add(mp)
    db.session.commit()
    flash(f'Nutrition Blueprint "{title}" published successfully!', 'success')
    return redirect(url_for('nutrition'))


@app.route('/trainer/meal_plan/delete/<int:plan_id>', methods=['POST'])
@login_required
def trainer_delete_meal_plan(plan_id):
    if current_user.role not in ['trainer', 'admin']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('nutrition'))

    mp = db.session.get(MealPlan, plan_id)
    if mp:
        db.session.delete(mp)
        db.session.commit()
        flash('Nutrition blueprint deleted.', 'info')
    return redirect(url_for('nutrition'))


@app.route('/admin/user/update_role/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_user_role(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_panel'))

    new_role = request.form.get('role', 'member').lower()
    if new_role in ['member', 'trainer', 'admin']:
        user.role = new_role
        if new_role == 'trainer' and not user.trainer_profile:
            profile = TrainerProfile(
                user_id=user.id,
                bio="Certified Fitness Instructor",
                specialization="General Conditioning",
                hourly_rate=45.00,
                profile_image_url="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
            )
            db.session.add(profile)
        db.session.commit()
        flash(f'Role for {user.full_name} updated to {new_role.upper()}.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/membership/toggle_status/<int:membership_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_toggle_membership_status(membership_id):
    mem = db.session.get(UserMembership, membership_id)
    if not mem:
        flash('Membership not found.', 'danger')
        return redirect(url_for('admin_panel'))

    new_status = request.form.get('status', 'active').lower()
    if new_status in ['active', 'frozen', 'expired']:
        mem.status = new_status
        db.session.commit()
        flash(f'Membership #{mem.id} status updated to {new_status.upper()}.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/class/<int:class_id>/roster')
@login_required
@role_required('trainer', 'admin')
def class_roster(class_id):
    gym_class = db.session.get(GymClass, class_id)
    if not gym_class:
        flash('Class not found.', 'danger')
        return redirect(url_for('schedule'))

    if current_user.role == 'trainer' and gym_class.trainer and gym_class.trainer.user_id != current_user.id:
        flash('You can only manage attendance for your own assigned classes.', 'danger')
        return redirect(url_for('schedule'))

    bookings = ClassBooking.query.filter_by(class_id=gym_class.id).filter(ClassBooking.status != 'cancelled').all()
    return render_template('class_roster.html', gym_class=gym_class, bookings=bookings)


@app.route('/api/mark_attendance', methods=['POST'])
@login_required
@role_required('trainer', 'admin')
def mark_attendance():
    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    attended = data.get('attended', True)

    booking = db.session.get(ClassBooking, booking_id)
    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found.'}), 404

    gym_class = booking.gym_class
    if current_user.role == 'trainer' and gym_class.trainer and gym_class.trainer.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Access denied: Only the assigned trainer for this class can confirm member attendance.'}), 403

    booking.attended = attended
    booking.status = 'completed' if attended else 'booked'
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"Updated attendance for {booking.user.full_name}: {'Present' if attended else 'Absent'}.",
        'attended': booking.attended,
        'status': booking.status
    })


if __name__ == '__main__':
    with app.app_context():
        if not User.query.first():
            print("The database is empty. Run `python seed_db.py` to load the demo accounts and data.")
    port = int(os.environ.get('PORT', 5000))
    print(f"\nFlexFit App is running at: http://127.0.0.1:{port}\n")
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1', host='127.0.0.1', port=port)
