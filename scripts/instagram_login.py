import argparse
import logging
from app.credentials import load_instagram_credentials
from app.logging_config import configure_logging
from app.services.instagram_auth import login_instagrapi

logger = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser(description="Log in to Instagram and save session.")
    parser.add_argument("--debug", action="store_true", default=None, help="Enable debug logging for this run.")
    args = parser.parse_args()

    configure_logging("instagram_login", debug=args.debug)
    logger.info("Instagram login script started")

    try:
        credentials = load_instagram_credentials()
        # This will either load the session file or log in with credentials and save the session
        client = login_instagrapi(credentials)
        logger.info("Successfully logged in as %s. Session saved to %s", credentials.username, credentials.session_file)
    except Exception as exc:
        logger.exception("Login failed")
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()
