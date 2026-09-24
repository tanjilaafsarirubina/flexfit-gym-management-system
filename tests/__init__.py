import os

# The app binds its database engine at import time, so the test database has to be chosen
# before `app` is imported. Tests must never touch the real flexfit.db (tearDown drops every table).
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ.setdefault('SECRET_KEY', 'test-only-secret-key')
