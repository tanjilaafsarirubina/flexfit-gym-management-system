import unittest
from datetime import datetime, timedelta
from app import app, db
from gym_models import (
    User, TrainerProfile, MembershipPlan, UserMembership,
    GymClass, ClassBooking, WorkoutLog, ExerciseVideo, MealPlan,
    Feedback, CoachingSession
)

class FlexFitTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            plan_m = MembershipPlan(name="Monthly Access", price=29.99, duration_days=30)
            plan_a = MembershipPlan(name="Annual Gold", price=249.99, duration_days=365)
            db.session.add_all([plan_m, plan_a])
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_user_registration_and_login(self):
        response = self.client.post('/register', data={
            'full_name': 'Test User',
            'email': 'testuser@flexfit.com',
            'phone': '+1234567890',
            'password': 'password123',
            'role': 'member'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with app.app_context():
            user = User.query.filter_by(email='testuser@flexfit.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.full_name, 'Test User')
            self.assertEqual(user.role, 'member')
            self.assertTrue(user.check_password('password123'))

        response = self.client.post('/login', data={
            'email': 'testuser@flexfit.com',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'WELCOME BACK', response.data.upper())

    def test_staff_passcode_protection(self):
        res_fail = self.client.post('/register', data={
            'full_name': 'Fake Trainer',
            'email': 'fake@flexfit.com',
            'phone': '123456',
            'password': 'pass',
            'role': 'trainer',
            'staff_passcode': 'WRONGPASS'
        }, follow_redirects=True)
        self.assertIn(b'Invalid Staff Invite Passcode', res_fail.data)

        res_success = self.client.post('/register', data={
            'full_name': 'Valid Trainer',
            'email': 'validtrainer@flexfit.com',
            'phone': '123456',
            'password': 'pass',
            'role': 'trainer',
            'staff_passcode': 'TRAINER2026'
        }, follow_redirects=True)
        self.assertIn(b'Registration successful', res_success.data)

        with app.app_context():
            trainer = User.query.filter_by(email='validtrainer@flexfit.com').first()
            self.assertIsNotNone(trainer)
            self.assertEqual(trainer.role, 'trainer')

    def test_class_booking_and_cancellation_ajax(self):
        with app.app_context():
            user = User(full_name='Booking Tester', email='booker@flexfit.com', phone='12345', role='member')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()

            plan = MembershipPlan.query.first()
            um = UserMembership(user_id=user.id, plan_id=plan.id, start_date=datetime.utcnow().date(), end_date=datetime.utcnow().date() + timedelta(days=30), status='active')
            db.session.add(um)

            trainer_user = User(full_name='Coach', email='coach@flexfit.com', phone='12345', role='trainer')
            trainer_user.set_password('password123')
            db.session.add(trainer_user)
            db.session.commit()

            profile = TrainerProfile(user_id=trainer_user.id, specialization='Yoga', hourly_rate=40)
            db.session.add(profile)
            db.session.commit()

            gym_class = GymClass(
                trainer_id=profile.id,
                title='Test Power Yoga',
                category='Yoga',
                start_time=db.func.now(),
                duration_mins=60,
                max_capacity=5
            )
            db.session.add(gym_class)
            db.session.commit()
            class_id = gym_class.id

        self.client.post('/login', data={'email': 'booker@flexfit.com', 'password': 'password123'})

        res_book = self.client.post('/api/book_class', json={'class_id': class_id})
        self.assertEqual(res_book.status_code, 200)
        json_book = res_book.get_json()
        self.assertTrue(json_book['success'])
        self.assertTrue(json_book['booked'])
        self.assertEqual(json_book['booked_count'], 1)

        res_cancel = self.client.post('/api/cancel_booking', json={'class_id': class_id})
        self.assertEqual(res_cancel.status_code, 200)
        json_cancel = res_cancel.get_json()
        self.assertTrue(json_cancel['success'])
        self.assertFalse(json_cancel['booked'])
        self.assertEqual(json_cancel['booked_count'], 0)

    def test_trainer_attendance_ownership_permission(self):
        with app.app_context():
            member = User(full_name='Member A', email='memA@flexfit.com', phone='123', role='member')
            member.set_password('pass')
            trainer1 = User(full_name='Assigned Trainer', email='trainer1@flexfit.com', phone='123', role='trainer')
            trainer1.set_password('pass')
            trainer2 = User(full_name='Unassigned Trainer', email='trainer2@flexfit.com', phone='123', role='trainer')
            trainer2.set_password('pass')

            db.session.add_all([member, trainer1, trainer2])
            db.session.commit()

            prof1 = TrainerProfile(user_id=trainer1.id, specialization='Yoga', hourly_rate=50)
            prof2 = TrainerProfile(user_id=trainer2.id, specialization='Cardio', hourly_rate=50)
            db.session.add_all([prof1, prof2])
            db.session.commit()

            gym_class = GymClass(trainer_id=prof1.id, title='Yoga Session', category='Yoga', start_time=db.func.now(), max_capacity=10)
            db.session.add(gym_class)
            db.session.commit()

            booking = ClassBooking(user_id=member.id, class_id=gym_class.id, status='booked', attended=False)
            db.session.add(booking)
            db.session.commit()

            booking_id = booking.id

        self.client.post('/login', data={'email': 'trainer2@flexfit.com', 'password': 'pass'})
        res_denied = self.client.post('/api/mark_attendance', json={'booking_id': booking_id, 'attended': True})
        self.assertEqual(res_denied.status_code, 403)
        self.assertIn(b'Only the assigned trainer', res_denied.data)

        self.client.get('/logout')

        self.client.post('/login', data={'email': 'trainer1@flexfit.com', 'password': 'pass'})
        res_success = self.client.post('/api/mark_attendance', json={'booking_id': booking_id, 'attended': True})
        self.assertEqual(res_success.status_code, 200)
        self.assertTrue(res_success.get_json()['success'])
        self.assertTrue(res_success.get_json()['attended'])

    def test_membership_checkout_and_freeze(self):
        with app.app_context():
            user = User(full_name='Member Mem', email='mem@flexfit.com', phone='123', role='member')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            plan = MembershipPlan.query.filter_by(name='Annual Gold').first()
            plan_id = plan.id

        self.client.post('/login', data={'email': 'mem@flexfit.com', 'password': 'pass'})

        res_checkout_card = self.client.post(f'/membership/checkout/{plan_id}', json={
            'payment_method': 'card',
            'card_number': '4000123456789010'
        })
        self.assertEqual(res_checkout_card.status_code, 200)
        self.assertTrue(res_checkout_card.get_json()['success'])
        self.assertIn('transaction_id', res_checkout_card.get_json())

        res_checkout_bkash = self.client.post(f'/membership/checkout/{plan_id}', json={
            'payment_method': 'bkash',
            'account_number': '01711000001',
            'otp': '123456',
            'pin': '12345'
        })
        self.assertEqual(res_checkout_bkash.status_code, 200)
        self.assertTrue(res_checkout_bkash.get_json()['success'])
        self.assertEqual(res_checkout_bkash.get_json()['payment_method'], 'BKASH')

        res_checkout_nagad = self.client.post(f'/membership/checkout/{plan_id}', json={
            'payment_method': 'nagad',
            'account_number': '01811000002',
            'otp': '123456',
            'pin': '1234'
        })
        self.assertEqual(res_checkout_nagad.status_code, 200)
        self.assertTrue(res_checkout_nagad.get_json()['success'])
        self.assertEqual(res_checkout_nagad.get_json()['payment_method'], 'NAGAD')

        res_freeze = self.client.post('/membership/toggle_freeze')
        self.assertEqual(res_freeze.status_code, 200)
        self.assertEqual(res_freeze.get_json()['status'], 'frozen')

        res_unfreeze = self.client.post('/membership/toggle_freeze')
        self.assertEqual(res_unfreeze.status_code, 200)
        self.assertEqual(res_unfreeze.get_json()['status'], 'active')

    def test_coaching_and_reviews_api(self):
        with app.app_context():
            user = User(full_name='Client User', email='client@flexfit.com', phone='123', role='member')
            user.set_password('pass')
            trainer_user = User(full_name='Coach Rob', email='rob@flexfit.com', phone='123', role='trainer')
            trainer_user.set_password('pass')
            db.session.add_all([user, trainer_user])
            db.session.commit()

            prof = TrainerProfile(user_id=trainer_user.id, specialization='Cardio', hourly_rate=50)
            db.session.add(prof)
            db.session.commit()
            trainer_id = prof.id

        self.client.post('/login', data={'email': 'client@flexfit.com', 'password': 'pass'})

        future_time = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%dT10:00')
        res_coach = self.client.post('/api/book_coaching', json={
            'trainer_id': trainer_id,
            'session_time': future_time,
            'notes': 'Stamina assessment'
        })
        self.assertEqual(res_coach.status_code, 200)
        self.assertTrue(res_coach.get_json()['success'])
        session_id = res_coach.get_json()['session_id']

        res_review_unattended = self.client.post('/api/submit_feedback', json={
            'trainer_id': trainer_id,
            'rating': 5,
            'review_text': 'Trying to review before session attended'
        })
        self.assertEqual(res_review_unattended.status_code, 403)
        self.assertFalse(res_review_unattended.get_json()['success'])

        self.client.get('/logout')
        self.client.post('/login', data={'email': 'rob@flexfit.com', 'password': 'pass'})

        res_update_status = self.client.post(f'/api/update_coaching_status/{session_id}', json={
            'status': 'completed',
            'notes': 'Great form on deadlifts today.'
        })
        self.assertEqual(res_update_status.status_code, 200)
        self.assertTrue(res_update_status.get_json()['success'])

        res_update_prof = self.client.post('/api/update_trainer_profile', json={
            'specialization': 'Advanced Cardio & Core',
            'hourly_rate': 65.0,
            'bio': 'Updated professional biography.'
        })
        self.assertEqual(res_update_prof.status_code, 200)
        self.assertTrue(res_update_prof.get_json()['success'])

        self.client.get('/logout')
        self.client.post('/login', data={'email': 'client@flexfit.com', 'password': 'pass'})

        res_review_attended = self.client.post('/api/submit_feedback', json={
            'trainer_id': trainer_id,
            'rating': 5,
            'review_text': 'Rob is an outstanding coach!'
        })
        self.assertEqual(res_review_attended.status_code, 200)
        self.assertTrue(res_review_attended.get_json()['success'])

    def test_admin_crud_endpoints(self):
        with app.app_context():
            admin = User(full_name='Admin Ops', email='adminops@flexfit.com', phone='123', role='admin')
            admin.set_password('adminpass')
            trainer = User(full_name='Coach Sam', email='sam@flexfit.com', phone='123', role='trainer')
            trainer.set_password('pass')
            db.session.add_all([admin, trainer])
            db.session.commit()

            prof = TrainerProfile(user_id=trainer.id, specialization='HIIT', hourly_rate=45)
            db.session.add(prof)
            db.session.commit()
            trainer_id = prof.id

        self.client.post('/login', data={'email': 'adminops@flexfit.com', 'password': 'adminpass'})

        future_time = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT10:00')
        res_class = self.client.post('/admin/class/create', data={
            'title': 'Admin Test Bootcamp',
            'category': 'Cardio',
            'trainer_id': trainer_id,
            'start_time': future_time,
            'duration_mins': 50,
            'max_capacity': 15
        }, follow_redirects=True)
        self.assertEqual(res_class.status_code, 200)
        self.assertIn(b'Admin Test Bootcamp', res_class.data)

        res_vid = self.client.post('/admin/video/create', data={
            'title': 'Admin Test Video',
            'category': 'Strength',
            'difficulty': 'Beginner',
            'video_url': 'https://www.youtube.com/embed/test',
            'thumbnail_url': 'https://example.com/thumb.jpg',
            'description': 'Test video description'
        }, follow_redirects=True)
        self.assertEqual(res_vid.status_code, 200)
        self.assertIn(b'Admin Test Video', res_vid.data)

        res_meal = self.client.post('/admin/meal_plan/create', data={
            'title': 'Admin Keto Blueprint',
            'goal': 'Weight Loss',
            'calories_per_day': 1800,
            'protein_g': 140,
            'carbs_g': 30,
            'fat_g': 120,
            'description': 'Strict keto regimen',
            'meal_breakdown': 'Breakfast: Eggs, Lunch: Salad'
        }, follow_redirects=True)
        self.assertEqual(res_meal.status_code, 200)
        self.assertIn(b'Admin Keto Blueprint', res_meal.data)

        self.client.get('/logout')
        self.client.post('/login', data={'email': 'sam@flexfit.com', 'password': 'pass'})

        future_trainer_time = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%dT15:00')
        res_tr_class = self.client.post('/trainer/class/create', data={
            'title': 'Trainer HIIT Blast',
            'category': 'Cardio',
            'start_time': future_trainer_time,
            'duration_mins': 45,
            'max_capacity': 10
        }, follow_redirects=True)
        self.assertEqual(res_tr_class.status_code, 200)
        self.assertIn(b'Trainer HIIT Blast', res_tr_class.data)

        res_tr_vid = self.client.post('/trainer/video/create', data={
            'title': 'Trainer Kettlebell Flow',
            'category': 'Strength',
            'difficulty': 'Intermediate',
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'description': 'Internet video tutorial posted by coach'
        }, follow_redirects=True)
        self.assertEqual(res_tr_vid.status_code, 200)
        self.assertIn(b'Trainer Kettlebell Flow', res_tr_vid.data)

        res_tr_meal = self.client.post('/trainer/meal_plan/create', data={
            'title': 'Trainer Shred Diet',
            'goal': 'Weight Loss',
            'calories_per_day': 1900,
            'protein_g': 160,
            'carbs_g': 120,
            'fat_g': 55,
            'description': 'Coach custom shred protocol',
            'meal_breakdown': 'Breakfast: Oats & Whey'
        }, follow_redirects=True)
        self.assertEqual(res_tr_meal.status_code, 200)
        self.assertIn(b'Trainer Shred Diet', res_tr_meal.data)

        with app.app_context():
            created_plan = MealPlan.query.filter_by(title='Trainer Shred Diet').first()
            self.assertIsNotNone(created_plan)
            plan_id = created_plan.id

        res_download = self.client.get(f'/nutrition/download/{plan_id}')
        self.assertEqual(res_download.status_code, 200)
        self.assertIn(b'FLEXFIT PERFORMANCE LAB', res_download.data)
        self.assertIn(b'Trainer Shred Diet', res_download.data)

        self.client.get('/logout')
        self.client.post('/login', data={'email': 'adminops@flexfit.com', 'password': 'adminpass'})

        res_tier = self.client.post('/admin/membership_plan/create', data={
            'name': 'Admin Executive VIP',
            'price': 199.99,
            'duration_days': 180,
            'features': 'Full gym & personal trainer access'
        }, follow_redirects=True)
        self.assertEqual(res_tier.status_code, 200)
        self.assertIn(b'Admin Executive VIP', res_tier.data)

if __name__ == '__main__':
    unittest.main()
