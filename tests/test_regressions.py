"""Regression tests for bugs fixed after the CSE391 submission (see README "Changes after grading")."""
import html
import json
import re
import unittest
from datetime import datetime, timedelta

from app import app, db
from gym_models import (
    User, TrainerProfile, MembershipPlan, UserMembership, GymClass, ExerciseVideo, MealPlan, Payment
)


class AppTestCase(unittest.TestCase):
    """One admin, one member on the Monthly plan, one trainer with one class."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['TRAINER_INVITE_CODE'] = None
        app.config['ADMIN_INVITE_CODE'] = None
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            self.monthly = self._add(MembershipPlan(name='Monthly Access', price=29.99, duration_days=30))
            self.unused = self._add(MembershipPlan(name='Unused Tier', price=5, duration_days=7))
            self._user('admin@test.io', 'admin')
            member = self._user('member@test.io', 'member')
            self._add(UserMembership(user_id=member, plan_id=self.monthly, status='active',
                                     start_date=datetime.now().date(),
                                     end_date=datetime.now().date() + timedelta(days=30)))
            trainer = self._user('coach@test.io', 'trainer')
            self.profile = self._add(TrainerProfile(user_id=trainer, specialization='Yoga', hourly_rate=40))
            self.gym_class = self._add(GymClass(trainer_id=self.profile, title='Morning Flow', category='Yoga',
                                                start_time=datetime.now() + timedelta(days=1), max_capacity=5))

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        app.config['WTF_CSRF_ENABLED'] = False

    def _add(self, obj):
        db.session.add(obj)
        db.session.commit()
        return obj.id

    def _user(self, email, role):
        user = User(full_name=email.split('@')[0].title(), email=email, phone='01700000000', role=role)
        user.set_password('pass')
        return self._add(user)

    def login(self, email):
        return self.client.post('/login', data={'email': email, 'password': 'pass'})


class RegressionTests(AppTestCase):
    def test_suite_uses_in_memory_database(self):
        # Before the fix the tests ran against flexfit.db and dropped every table in tearDown.
        self.assertEqual(app.config['SQLALCHEMY_DATABASE_URI'], 'sqlite://')

    def test_staff_signup_disabled_without_invite_codes(self):
        # The old codes were hard-coded in this public repo, so anyone could register as admin.
        self.client.post('/register', data={'full_name': 'Stranger', 'email': 'x@evil.test', 'phone': '1',
                                            'password': 'pw', 'role': 'admin', 'staff_passcode': 'ADMIN2026'})
        with app.app_context():
            self.assertIsNone(User.query.filter_by(email='x@evil.test').first())
        page = self.client.get('/register').get_data(as_text=True)
        self.assertNotIn('value="admin"', page)
        self.assertNotIn('value="trainer"', page)

    def test_staff_signup_uses_configured_code(self):
        app.config['ADMIN_INVITE_CODE'] = 'from-env'
        self.client.post('/register', data={'full_name': 'New Admin', 'email': 'new@test.io', 'phone': '1',
                                            'password': 'pw', 'role': 'admin', 'staff_passcode': 'from-env'})
        with app.app_context():
            self.assertEqual(User.query.filter_by(email='new@test.io').first().role, 'admin')

    def test_login_next_only_redirects_within_site(self):
        for target, expected in [('https://evil.example/phish', '/'), ('//evil.example', '/'),
                                 ('/\\evil.example', '/'), ('/schedule', '/schedule')]:
            client = app.test_client()
            res = client.post('/login?next=' + target, data={'email': 'member@test.io', 'password': 'pass'})
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers['Location'], expected, target)

    def test_expired_membership_cannot_book(self):
        with app.app_context():
            membership = UserMembership.query.first()
            membership.end_date = datetime.now().date() - timedelta(days=10)
            db.session.commit()
        self.login('member@test.io')
        res = self.client.post('/api/book_class', json={'class_id': self.gym_class})
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'No Active Plan', self.client.get('/').data)

    def test_deleting_plan_in_use_is_refused_instead_of_500(self):
        self.login('admin@test.io')
        res = self.client.post(f'/admin/membership_plan/delete/{self.monthly}', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"cannot be deleted", res.data)
        self.client.post(f'/admin/membership_plan/delete/{self.unused}')
        with app.app_context():
            self.assertIsNotNone(db.session.get(MembershipPlan, self.monthly))
            self.assertIsNone(db.session.get(MembershipPlan, self.unused))

    def test_admin_can_edit_plan_pricing(self):
        self.login('admin@test.io')
        self.client.post(f'/admin/membership_plan/edit/{self.monthly}',
                         data={'name': 'Monthly Access', 'price': '34.50', 'duration_days': '30', 'features': 'x'})
        with app.app_context():
            self.assertEqual(float(db.session.get(MembershipPlan, self.monthly).price), 34.5)

    def test_onclick_arguments_survive_quotes_and_newlines(self):
        # An apostrophe or a line break in a bio used to break the button's inline JavaScript.
        bio = 'Line one.\nIt\'s "line two" </script>'
        self.login('coach@test.io')
        self.client.post('/api/update_trainer_profile', json={'bio': bio, 'specialization': "Women's Yoga"})
        page = self.client.get('/trainers').get_data(as_text=True)
        attr = re.search(r"onclick='openEditProfileModal\((.*?)\)'", page).group(1)
        self.assertNotIn('\n', attr)
        self.assertNotIn('</script>', attr)
        self.assertEqual(json.loads('[' + html.unescape(attr) + ']'), ["Women's Yoga", 40, bio])

    def test_video_links_must_be_http(self):
        self.login('coach@test.io')
        self.client.post('/trainer/video/create', data={'title': 'Bad', 'category': 'Yoga', 'difficulty': 'Beginner',
                                                        'video_url': 'javascript:alert(1)'})
        with app.app_context():
            self.assertIsNone(ExerciseVideo.query.filter_by(title='Bad').first())

    def test_zero_calorie_meal_plan_rejected(self):
        # calories_per_day=0 made the printable blueprint divide by zero.
        self.login('coach@test.io')
        self.client.post('/trainer/meal_plan/create', data={'title': 'Zero', 'goal': 'Maintenance',
                                                            'calories_per_day': 0, 'protein_g': 0,
                                                            'carbs_g': 0, 'fat_g': 0})
        with app.app_context():
            self.assertIsNone(MealPlan.query.filter_by(title='Zero').first())

    def test_checkout_records_payment_and_admin_revenue_uses_it(self):
        self.login('member@test.io')
        res = self.client.post(f'/membership/checkout/{self.unused}',
                               json={'payment_method': 'card', 'card_number': '4000123456789010'})
        self.assertTrue(res.get_json()['success'])
        with app.app_context():
            payment = Payment.query.one()
            self.assertEqual(float(payment.amount), 5.0)
            self.assertEqual(payment.transaction_id, res.get_json()['transaction_id'])
        self.client.get('/logout')
        self.login('admin@test.io')
        self.assertIn(b'$5', self.client.get('/admin').data)

    def test_non_numeric_wallet_number_rejected(self):
        self.login('member@test.io')
        res = self.client.post(f'/membership/checkout/{self.unused}',
                               json={'payment_method': 'bkash', 'account_number': '01abcdefghi', 'pin': '12345'})
        self.assertEqual(res.status_code, 400)


class CsrfTests(AppTestCase):
    def setUp(self):
        super().setUp()
        app.config['WTF_CSRF_ENABLED'] = True

    def csrf_token(self):
        page = self.client.get('/').get_data(as_text=True)
        return re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)

    def login(self, email):
        token = re.search(r'name="csrf_token" value="([^"]+)"',
                          self.client.get('/login').get_data(as_text=True)).group(1)
        return self.client.post('/login', data={'email': email, 'password': 'pass', 'csrf_token': token})

    def test_cross_site_form_post_is_rejected(self):
        # Before the fix a plain HTML form on any site could freeze a logged-in member's account.
        self.login('member@test.io')
        res = self.client.post('/membership/toggle_freeze', data={})
        self.assertEqual(res.status_code, 302)
        with app.app_context():
            self.assertEqual(UserMembership.query.first().status, 'active')

    def test_json_api_requires_header_token(self):
        self.login('member@test.io')
        res = self.client.post('/api/book_class', json={'class_id': self.gym_class})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()['success'])
        res = self.client.post('/api/book_class', json={'class_id': self.gym_class},
                               headers={'X-CSRFToken': self.csrf_token()})
        self.assertEqual(res.status_code, 200)


if __name__ == '__main__':
    unittest.main()
