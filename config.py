"""Runtime configuration for the MEDCO Diesel Price dashboard, loaded from
environment variables (see .env.example). Every value has a sane default so
the app runs out of the box with no .env present.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")

MEDCO_URL = os.environ.get("MEDCO_URL", "https://medco.com.lb/")
SCRAPER_TIME = os.environ.get("SCRAPER_TIME", "10:30")
SCRAPER_TIMEZONE = os.environ.get("SCRAPER_TIMEZONE", "Asia/Beirut")
SCRAPER_TIMEOUT_SECONDS = int(os.environ.get("SCRAPER_TIMEOUT_SECONDS", "30"))
SCRAPER_MAX_RETRIES = int(os.environ.get("SCRAPER_MAX_RETRIES", "3"))
SCRAPER_USER_AGENT = os.environ.get(
    "SCRAPER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)
DB_PATH = Path(os.environ.get("DIESEL_DB_PATH", APP_DIR / "diesel_price.db"))
SCHEMA_PATH = APP_DIR / "schema.sql"

FOCUS_FUEL_TYPE = "DIESEL"

# Display metadata for every fuel type MEDCO's marquee publishes - the
# scraper already extracts and stores all of these (see scraper.py), this
# just controls what the dashboard shows and in what order.
FUEL_LABELS = {
    "DIESEL": "Diesel",
    "95": "95 Octane",
    "98": "98 Octane",
    "LPG": "LPG",
}
FUEL_TYPE_ORDER = ["DIESEL", "95", "98", "LPG"]
