from pathlib import Path
import pickle

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from langchain_community.tools.gmail.send_message import GmailSendMessage


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

_SERVICE = None
_GMAIL_AVAILABLE = False


def get_gmail_service():
    """Authenticate with Gmail and return the Gmail API service."""

    root = Path(__file__).resolve().parents[2]

    credentials_path = root / "credentials.json"
    token_path = root / "token.pickle"

    credentials = None

    # Load previously saved OAuth token.
    if token_path.exists():
        with token_path.open("rb") as file:
            credentials = pickle.load(file)

    # Refresh expired credentials if possible.
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    # If no valid credentials exist, start OAuth flow.
    if not credentials or not credentials.valid:
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Gmail credentials not found: {credentials_path}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_path,
            SCOPES,
        )

        credentials = flow.run_local_server(port=0)

        # Save credentials for future runs.
        with token_path.open("wb") as file:
            pickle.dump(credentials, file)

    # Build Gmail API resource.
    return build(
        "gmail",
        "v1",
        credentials=credentials,
    )


def initialize_gmail() -> bool:
    """Initialize Gmail once and return whether it is available."""

    global _SERVICE, _GMAIL_AVAILABLE

    if _SERVICE is not None:
        return True

    try:
        _SERVICE = get_gmail_service()
        _GMAIL_AVAILABLE = True
        return True

    except Exception as exc:
        print(f"Gmail initialization skipped: {exc}")
        _SERVICE = None
        _GMAIL_AVAILABLE = False
        return False


def get_gmail_tools():
    """Return Gmail tools when Gmail is available."""

    if not _GMAIL_AVAILABLE or _SERVICE is None:
        return []

    return [
        GmailSendMessage(api_resource=_SERVICE)
    ]


def is_gmail_available() -> bool:
    """Return whether Gmail is currently available."""

    return _GMAIL_AVAILABLE