import os

# The app binds its database engine at import time, so the test database has to be chosen
# before `app` is imported. Tests must never touch the real flexfit.db (tearDown drops every table),
# so they use in-memory SQLite unless TEST_DATABASE_URL points at a throwaway database (CI uses MySQL).
os.environ['DATABASE_URL'] = os.environ.get('TEST_DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-only-secret-key')
