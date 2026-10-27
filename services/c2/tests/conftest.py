import os
import pathlib

# Throwaway sqlite DB and test secrets, set before the app is imported.
_DB = pathlib.Path(__file__).parent / "test_c2.db"
if _DB.exists():
    _DB.unlink()

# Forced rather than setdefault so a deployment's environment cannot leak in
# (e.g. DATABASE_URL pointing at the live Postgres).
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "Admin1Admin1"
os.environ["SEED_DEMO_USERS"] = "true"
os.environ["OPERATOR_USERNAME"] = "operator"
os.environ["OPERATOR_PASSWORD"] = "Admin1Admin1"
os.environ["OBSERVER_USERNAME"] = "observer"
os.environ["OBSERVER_PASSWORD"] = "Admin1Admin1"
os.environ["DRONE_BACKEND"] = "mock"
os.environ["DRONE_COUNT"] = "1"
