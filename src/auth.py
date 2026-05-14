import os
import pickle
import logging

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

DATA_DIR = os.getenv("DATA_DIR", "/data")
TOKEN_PATH = os.path.join(DATA_DIR, "token.pickle")
CREDENTIALS_PATH = os.path.join(DATA_DIR, "credentials.json")


def authenticate():
    """Interactive first-time OAuth2 authentication. Run with 'python main.py auth'."""
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_PATH}\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_console()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TOKEN_PATH, "wb") as fh:
        pickle.dump(creds, fh)
    logger.info("Authentication successful — token saved to %s", TOKEN_PATH)


def _load_credentials():
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            "No token found. Run authentication first:\n"
            "  docker compose run --rm -it classroom-downloader python main.py auth"
        )
    with open(TOKEN_PATH, "rb") as fh:
        return pickle.load(fh)


def get_credentials():
    creds = _load_credentials()
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logger.info("Refreshing expired token...")
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as fh:
                pickle.dump(creds, fh)
        else:
            raise RuntimeError(
                "Token is invalid and cannot be refreshed. Re-run authentication:\n"
                "  docker compose run --rm -it classroom-downloader python main.py auth"
            )
    return creds


def build_services():
    creds = get_credentials()
    classroom = build("classroom", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return classroom, drive
