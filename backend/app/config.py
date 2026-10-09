import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./servicecheck.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
REPORT_COMPANY = os.getenv("REPORT_COMPANY", "PCO")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "0") == "1"
FRONTEND_DIR = os.getenv("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))

# --- Dokumentablage: "db" (in der Datenbank) oder "azure" (Azure Blob Storage) ---
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "db")
AZURE_STORAGE_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")  # https://<konto>.blob.core.windows.net
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")  # nur Entwicklung/Azurite
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "documents")

# --- Anmeldung ---
AUTH_LOCAL_ENABLED = os.getenv("AUTH_LOCAL_ENABLED", "1") == "1"  # lokale Benutzer/Passwörter
OIDC_TENANT_ID = os.getenv("OIDC_TENANT_ID", "")  # Verzeichnis-ID (GUID) des Entra-Mandanten
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "")  # https://<host>/api/auth/oidc/callback
OIDC_ADMIN_ROLE = os.getenv("OIDC_ADMIN_ROLE", "ServiceCheck.Admin")
OIDC_USER_ROLE = os.getenv("OIDC_USER_ROLE", "ServiceCheck.Consultant")


def oidc_enabled() -> bool:
    return bool(OIDC_TENANT_ID and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_REDIRECT_URI)
