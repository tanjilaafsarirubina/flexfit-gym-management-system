# FlexFit: Gym & Fitness Management Platform

[![CI](https://github.com/tanjilaafsarirubina/flexfit-gym-management-system/actions/workflows/ci.yml/badge.svg)](https://github.com/tanjilaafsarirubina/flexfit-gym-management-system/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python 3.11–3.14](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)
![Flask 3.1](https://img.shields.io/badge/flask-3.1-lightgrey.svg)

A full-stack Flask web app for running a gym, with three roles:

- **Members** book group classes, pay for memberships through a simulated bKash / Nagad / Rocket / card checkout, log workouts, book 1-on-1 coaching and review classes and trainers they have actually attended.
- **Trainers** take attendance for their own classes, run their 1-on-1 appointments and publish classes, videos and meal plans.
- **Admins** manage classes, videos, meal plans, membership pricing, user roles and review moderation from one control panel.

![Member dashboard](docs/screenshots/member-dashboard.png)

> Course project by **Tanjila Afsari Rubina** for CSE391 (Programming for the Internet), BRAC University, Summer 2026. The graded submission is commit [`9eb55c2`](https://github.com/tanjilaafsarirubina/flexfit-gym-management-system/tree/9eb55c227299f769092b6facde7bb593949c4c94). The fixes listed under [Changes after grading](#changes-after-grading) came later.

## Features

| Area | What it does |
|---|---|
| Accounts and roles | Registration and login with hashed passwords (Werkzeug, scrypt). Trainer and admin sign-up need an invite code set by the server. Admins can change anyone's role. |
| Class timetable | Filter by Cardio / Strength / Yoga and book or cancel with AJAX; capacity bars update in place. Booking needs an active, unfrozen, unexpired membership. |
| Attendance | Trainers see a roster for their own classes and mark members present. They can't mark attendance for another trainer's class. |
| Verified reviews | A member can review a class only after being marked present, and a trainer only after attending one of their classes or finishing a 1-on-1 with them. One review each. |
| Memberships | Monthly / Quarterly / Annual tiers. Renewing extends the current plan, and members can freeze and unfreeze. Checkout goes through a **simulated** bKash, Nagad, Rocket or card gateway and issues a receipt with a transaction ID. |
| 1-on-1 coaching | Members book a trainer for any future time. Trainers complete sessions with notes, and either side can cancel. |
| Workout tracker | Log sets × reps × weight; the dashboard totals lifetime volume. |
| Video library | Search and filter by category and difficulty. YouTube `watch?v=` and `youtu.be` links are turned into embeds. |
| Nutrition | Meal plans with macro splits and a printable blueprint page. Trainers get a TDEE / macro calculator (Mifflin–St Jeor). |
| Admin panel | CRUD for classes, videos, meal plans and membership tiers, plus user roles, review moderation and revenue from recorded sandbox payments. |

## Screenshots

| | |
|---|---|
| ![Class timetable](docs/screenshots/class-schedule.png) | ![Sandbox checkout](docs/screenshots/sandbox-checkout.png) |
| Class timetable (member) | Simulated bKash checkout |
| ![Trainer hub](docs/screenshots/trainer-hub.png) | ![Admin panel](docs/screenshots/admin-panel.png) |
| Trainer 1-on-1 hub | Admin control center |
| ![Nutrition](docs/screenshots/nutrition.png) | <img src="docs/screenshots/mobile-dashboard.png" alt="Mobile dashboard" width="260"> |
| Meal plans | Mobile (390 px) |

The original wireframe and schema diagram are in [`docs/`](docs).

## Run it locally

Needs Python 3.11 or newer.

```bash
git clone https://github.com/tanjilaafsarirubina/flexfit-gym-management-system.git
cd flexfit-gym-management-system
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_db.py                # creates flexfit.db with demo data (wipes it if it exists)
python app.py                    # http://127.0.0.1:5000
```

Demo accounts created by `seed_db.py`:

| Role | Email | Password |
|---|---|---|
| Member | `tanjila@flexfit.com`, `rahim@flexfit.com`, `nusrat@flexfit.com` | `password123` |
| Trainer | `sarah@flexfit.com` (Yoga), `tanvir@flexfit.com` (Strength), `farhan@flexfit.com` (HIIT) | `password123` |
| Admin | `admin@flexfit.com` | `admin123` |

The checkout is a simulation. It only checks the format of what you type, never contacts a payment provider and doesn't store card numbers or PINs. The form comes pre-filled with test values, so don't enter real details.

### Configuration

Set these as environment variables, or put them in `instance/config.py` (git-ignored) as `SECRET_KEY = "..."` and so on.

| Setting | Default | Notes |
|---|---|---|
| `SECRET_KEY` | random, saved to `instance/secret_key` | Signs session cookies. Set it explicitly when you run more than one worker. |
| `DATABASE_URL` | `sqlite:///flexfit.db` | Any SQLAlchemy URL. MySQL works via PyMySQL: `mysql+pymysql://user:pass@host/db` (CI tests it on MySQL 8). |
| `TRAINER_INVITE_CODE` | unset | If unset, the register page doesn't offer trainer sign-up. |
| `ADMIN_INVITE_CODE` | unset | Same, for admin sign-up. |
| `PORT` / `FLASK_DEBUG` | `5000` / `1` | Only used by `python app.py`. |

To deploy on PythonAnywhere or any other WSGI host, point it at `wsgi.py`, set the variables above and run `python seed_db.py` once if you want the demo data.

## Tests

```bash
python -m unittest discover -s tests -t .      # 21 tests, in-memory SQLite

pip install playwright
python -m playwright install chromium          # or: set PLAYWRIGHT_CHANNEL=msedge / chrome
python tests/e2e_smoke.py                      # real browser, throwaway database
```

- `tests/test_app.py` holds the original suite: registration, booking, attendance permissions, checkout, coaching, reviews and admin CRUD.
- `tests/test_regressions.py` holds regression tests for the fixes in the next section, plus CSRF enforcement.
- `tests/e2e_smoke.py` logs in as each role in Chromium and opens every page, failing on any uncaught JavaScript error. It then clicks through booking, reviewing, checkout, freeze/unfreeze, the video player, coaching, attendance and the admin edit dialogs. Run against the graded version, it fails on every page.

[CI](.github/workflows/ci.yml) runs the unit tests on Python 3.11–3.14 with SQLite, again on MySQL 8, and runs the browser smoke test.

## Changes after grading

These changes were made after the course was graded. Each item under **Security** and **Bugs** was checked against the graded code before it was fixed and is covered by a test in [`tests/`](tests).

**Security**
- The trainer and admin invite codes (and the session `SECRET_KEY`) were hard-coded in this public repo, so anyone could register as an admin. They now come from configuration, and staff sign-up is off until a code is set.
- No CSRF protection: any website could, for example, freeze a logged-in member's plan with a plain form post. Every form and `fetch()` call now sends a Flask-WTF token.
- Stored XSS: toast messages were inserted as HTML, so a trainer who put `<img src=x onerror=…>` in a class title ran script in the browser of any member who booked it. Toasts now render text.
- Inline `onclick` handlers built JavaScript strings from titles and bios by hand. An apostrophe (`Women's Mobility`) or a line break in a bio broke the button, and crafted text could inject script. The handlers now use `|tojson`.
- `/login?next=https://evil.example` redirected off-site after sign-in. Video and thumbnail links now have to be `http(s)`.

**Bugs**
- `base.html` loaded `style.css` through a `<script>` tag, which threw a JavaScript error on every page.
- The admin "edit video" button called a function that didn't exist. The route was there but the dialog wasn't, so the dialog has been added. Membership pricing can now be edited too; the original feature list promised it but the panel only offered create and delete.
- Deleting a membership tier that anyone was on crashed with a 500. It's now refused with a message.
- Memberships past their end date still counted as active and could book classes.
- Admin "revenue" was minutes-attended × 0.5 plus the list price of every tier. Checkouts are now recorded in a `payments` table, and revenue is their sum.
- The test suite set its in-memory database after the engine was already bound, so it ran against `flexfit.db` and dropped every table on teardown. Running the tests wiped the demo data.
- A zero-calorie meal plan crashed the printable blueprint page with a division by zero.

Smaller fixes, not covered by tests: the Rocket field was capped at 11 characters although Rocket numbers have 12; the coaching form's default time was in UTC; unstyled table text was nearly black on the dark theme; deprecated `datetime.utcnow()` calls were replaced.

These post-submission changes were made with help from an AI coding assistant (Claude Code). The original [AI usage declaration](docs/AI_DECLARATION.txt) covers the graded submission only.

## Limitations

- Payments are simulated (see above). There's no real gateway, no refunds and no invoices.
- The `trainer_availabilities` table exists but isn't used. 1-on-1 bookings accept any future time and don't check for clashes.
- "Adopt nutrition plan" and "Mark video as completed" only show a confirmation; nothing is saved.
- Meal plans don't record who created them, so any trainer can delete any plan.
- The capacity check and the booking insert aren't one locked transaction, so two requests racing for the last spot could both get in.
- Freezing a membership doesn't pause its end date.
- Times are stored as the server's local time, without a timezone.
- There's no password reset or email verification.
- The PythonAnywhere deployment that was live during the course is no longer running.

## How it's built

- **Backend**: Flask 3.1 with 44 routes in [`app.py`](app.py), SQLAlchemy models in [`gym_models.py`](gym_models.py), Flask-Login sessions and Flask-WTF CSRF. Role checks use a `role_required` decorator plus per-record ownership checks (for example, trainers can only take attendance for their own classes).
- **Frontend**: Jinja templates, Bootstrap 5 and vanilla JavaScript. Booking, reviews, checkout, attendance and coaching go through JSON endpoints under `/api/` with `fetch()`; the rest are regular form posts.
- **Data**: SQLite by default, MySQL in production. 13 tables:

```mermaid
erDiagram
    users ||--o| trainer_profiles : "is a trainer"
    users ||--o{ user_memberships : holds
    membership_plans ||--o{ user_memberships : "priced by"
    users ||--o{ payments : makes
    trainer_profiles ||--o{ gym_classes : teaches
    gym_classes ||--o{ class_bookings : has
    users ||--o{ class_bookings : books
    users ||--o{ coaching_sessions : "books 1-on-1"
    trainer_profiles ||--o{ coaching_sessions : coaches
    users ||--o{ feedbacks : writes
    trainer_profiles ||--o{ feedbacks : "reviewed in"
    gym_classes ||--o{ feedbacks : "reviewed in"
    users ||--o{ workout_logs : logs
    trainer_profiles ||--o{ trainer_availabilities : "(unused)"

    users {
        int id PK
        string email UK
        string password_hash
        string role "member, trainer or admin"
    }
    user_memberships {
        int id PK
        int user_id FK
        int plan_id FK
        date end_date
        string status "active, frozen or expired"
    }
    class_bookings {
        int id PK
        int user_id FK
        int class_id FK
        string status "booked, cancelled or completed"
        bool attended
    }
    payments {
        int id PK
        int user_id FK
        string plan_name
        decimal amount
        string method
        string transaction_id
    }
```

`exercise_videos` and `meal_plans` stand alone.

```
app.py              routes, config, CSRF
gym_models.py       SQLAlchemy models
seed_db.py          demo data (drops and recreates all tables)
wsgi.py             WSGI entry point
templates/          Jinja pages, one per section
static/             style.css, main.js (toasts, booking, CSRF header)
tests/              unit, regression and browser tests
docs/               original report, AI declaration, feature list, wireframe, schema, screenshots
```

## Author and license

Designed and built by **Tanjila Afsari Rubina**. Released under the [MIT License](LICENSE).
