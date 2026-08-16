import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SERPAPI_KEY = os.getenv("SERPAPI_KEY") or os.getenv("SEARCH_API_KEY", "")
SEARCH_ENGINE = os.getenv("SEARCH_ENGINE", "google_maps")
SEARCH_ENRICH_WEBSITES = os.getenv("SEARCH_ENRICH_WEBSITES", "true").lower() == "true"

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SEND_DELAY = float(os.getenv("SEND_DELAY", "5"))

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "")
UNSUBSCRIBE_BASE_URL = os.getenv(
    "UNSUBSCRIBE_BASE_URL", "http://localhost:5000/unsubscribe"
)

LEADS_CSV_PATH = os.getenv(
    "LEADS_CSV_PATH", os.path.join(BASE_DIR, "data", "leads.csv")
)
SETTINGS_PATH = os.getenv(
    "SETTINGS_PATH", os.path.join(BASE_DIR, "data", "settings.json")
)
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
SECRET_KEY = os.getenv("SECRET_KEY", "lead-report-dev-secret")


def search_api_configured() -> bool:
    return bool(SERPAPI_KEY)


def smtp_configured() -> bool:
    return bool(SMTP_EMAIL and SMTP_PASSWORD)


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return value[0] + "*" * (len(value) - 1)
    return f"{value[:4]}{'*' * 6}{value[-4:]}"
