import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./servicecheck.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
REPORT_COMPANY = os.getenv("REPORT_COMPANY", "Managed Service Provider")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "1") == "1"
FRONTEND_DIR = os.getenv("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))
