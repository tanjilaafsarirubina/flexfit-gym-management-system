"""Browser smoke test: every page for every role in a real Chromium, plus the main buttons.

It fails on any uncaught JavaScript error, which the Flask test client can't see.
The run uses a throwaway seeded database, never flexfit.db.

    pip install -r requirements.txt playwright
    playwright install chromium          # or set PLAYWRIGHT_CHANNEL=msedge / chrome
    python tests/e2e_smoke.py
"""
import os
import sys
import tempfile
import threading
from datetime import datetime

DB_FILE = os.path.join(tempfile.mkdtemp(), 'e2e.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB_FILE.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'e2e-only-secret-key')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright, expect  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import seed_db  # noqa: E402
from app import app, db  # noqa: E402
from gym_models import GymClass, ClassBooking, User  # noqa: E402

HTML_TITLE = '<img src=x onerror="window.__xss=1">'
QUOTE_TITLE = "Women's Mobility"
PAGES = {
    'tanjila@flexfit.com': ['/', '/schedule', '/tracker', '/videos', '/nutrition', '/trainers', '/membership'],
    'sarah@flexfit.com': ['/', '/schedule', '/trainers', '/videos', '/nutrition'],
    'admin@flexfit.com': ['/', '/admin', '/schedule', '/trainers', '/videos', '/nutrition', '/membership'],
}
PASSWORDS = {'admin@flexfit.com': 'admin123'}
failures = []


def check(label, condition):
    print(('PASS ' if condition else 'FAIL ') + label)
    if not condition:
        failures.append(label)


def seed():
    seed_db.seed_database()
    with app.app_context():
        sarah = User.query.filter_by(email='sarah@flexfit.com').first().trainer_profile
        tanjila = User.query.filter_by(email='tanjila@flexfit.com').first()
        html_class = GymClass(trainer_id=sarah.id, title=HTML_TITLE, category='Yoga',
                              start_time=datetime(2030, 1, 1, 10), max_capacity=5)
        quote_class = GymClass(trainer_id=sarah.id, title=QUOTE_TITLE, category='Yoga',
                               start_time=datetime(2030, 1, 2, 10), max_capacity=5)
        db.session.add_all([html_class, quote_class])
        db.session.commit()
        db.session.add(ClassBooking(user_id=tanjila.id, class_id=quote_class.id, status='completed', attended=True))
        db.session.commit()


def main():
    seed()
    server = make_server('127.0.0.1', 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get('PLAYWRIGHT_CHANNEL') or None)
        page = browser.new_page()
        js_errors = []
        page.on('pageerror', lambda e: js_errors.append(str(e)))
        page.on('dialog', lambda d: d.accept())

        def login(email):
            page.goto(base + '/logout')
            page.goto(base + '/login')
            page.fill('#email', email)
            page.fill('#password', PASSWORDS.get(email, 'password123'))
            page.click('button[type=submit]')
            page.wait_for_url(base + '/')

        def no_js_errors(label):
            check(f'{label}: no JavaScript errors {js_errors or ""}', not js_errors)
            js_errors.clear()

        for email, paths in PAGES.items():
            login(email)
            for path in paths:
                response = page.goto(base + path)
                check(f'{email} {path} -> {response.status}', response.status == 200)
                no_js_errors(f'{email} {path}')

        # Member flows
        login('tanjila@flexfit.com')
        page.goto(base + '/schedule')
        page.locator('tr', has_text='window.__xss').get_by_role('button', name='BOOK CLASS').click()
        expect(page.locator('.toast-body').last).to_contain_text('<img src=x')
        check('HTML in a class title is shown as text, not executed', not page.evaluate('window.__xss'))

        page.goto(base + '/schedule')
        page.locator('tr', has_text=QUOTE_TITLE).get_by_role('button', name='Review').click()
        expect(page.locator('#classReviewModal')).to_be_visible()
        check('review modal opens for a title with an apostrophe', page.locator('#modal-class-name').inner_text() == QUOTE_TITLE)
        page.fill('#class-review-text', 'Great mobility work.')
        page.click('#btn-class-review-submit')
        expect(page.locator('.toast-body').last).to_contain_text('verified review')
        no_js_errors('member schedule actions')

        page.goto(base + '/membership')
        page.get_by_role('button', name='Pay with bKash / Nagad / Card').first.click()
        page.click('#btn-gw-submit')
        expect(page.locator('#receiptModal')).to_be_visible(timeout=10000)
        check('sandbox checkout shows a receipt', page.locator('#receipt-trx-id').inner_text().startswith('BKASH'))
        page.goto(base + '/membership')
        page.get_by_role('button', name='Freeze Account').click()
        page.wait_for_load_state('load')
        expect(page.get_by_role('button', name='Unfreeze & Reactivate')).to_be_visible(timeout=10000)
        page.get_by_role('button', name='Unfreeze & Reactivate').click()
        expect(page.get_by_role('button', name='Freeze Account')).to_be_visible(timeout=10000)
        no_js_errors('member membership actions')

        page.goto(base + '/videos')
        page.get_by_role('button', name='Stream Tutorial').first.click()
        expect(page.locator('#videoModal')).to_be_visible()
        check('video player loads an https embed', page.locator('#video-modal-iframe').get_attribute('src').startswith('https://'))
        page.goto(base + '/trainers')
        page.get_by_role('button', name='Book 1-on-1').first.click()
        page.click('#btn-coach-submit')
        expect(page.locator('.toast-body').last).to_contain_text('scheduled')
        no_js_errors('member videos and coaching')

        # Trainer flows
        login('sarah@flexfit.com')
        page.goto(base + '/trainers')
        page.get_by_role('button', name='Edit My Profile & Rates').click()
        page.fill('#edit-profile-bio', "Line one.\nIt's line two.")
        page.click('#btn-edit-profile-submit')
        expect(page.locator('.toast-body').last).to_contain_text('updated')
        page.wait_for_timeout(1500)
        page.goto(base + '/trainers')
        page.get_by_role('button', name='Edit My Profile & Rates').click()
        check('multi-line bio round-trips into the edit modal',
              page.input_value('#edit-profile-bio') == "Line one.\nIt's line two.")
        page.goto(base + '/schedule')
        page.get_by_role('link', name='Attendance Roster').first.click()
        page.get_by_role('button', name='Confirm Attendance').first.click()
        expect(page.locator('.toast-body').last).to_contain_text('Present')
        no_js_errors('trainer actions')

        # Admin flows
        login('admin@flexfit.com')
        page.goto(base + '/admin')
        page.click('#videos-tab')
        page.locator('#videos-content button.btn-outline-info').first.click()
        expect(page.locator('#editVideoModal')).to_be_visible()
        page.fill('#edit-video-title', 'Renamed By Admin')
        page.locator('#edit-video-form button[type=submit]').click()
        check('admin can edit a video', 'Renamed By Admin' in page.content())
        page.click('#plans-tab')
        page.locator('#plans-content button.btn-outline-info').first.click()
        expect(page.locator('#editPlanModal')).to_be_visible()
        page.fill('#edit-plan-price', '31.50')
        page.locator('#edit-plan-form button[type=submit]').click()
        check('admin can edit plan pricing', '$31.50' in page.content())
        page.locator('#classes-content button.btn-outline-info').first.click()
        expect(page.locator('#editClassModal')).to_be_visible()
        page.goto(base + '/trainers')
        page.get_by_role('button', name='Edit Profile & Rate').first.click()
        expect(page.locator('#adminEditCoachModal')).to_be_visible()
        no_js_errors('admin actions')

        browser.close()
    server.shutdown()

    print(f'\n{len(failures)} failure(s)' if failures else '\nAll browser checks passed.')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
