import logging
from instagrapi import Client as InstagrapiClient
import instaloader

from app.credentials import InstagramCredentials
from app.config import settings

logger = logging.getLogger(__name__)


_instagrapi_client_cache: InstagrapiClient | None = None

def get_instagrapi_client(credentials: InstagramCredentials) -> InstagrapiClient:
    global _instagrapi_client_cache
    if _instagrapi_client_cache:
        return _instagrapi_client_cache
    _instagrapi_client_cache = login_instagrapi(credentials)
    return _instagrapi_client_cache

def login_instagrapi(credentials: InstagramCredentials) -> InstagrapiClient:
    client = InstagrapiClient()

    if credentials.session_file.exists():
        logger.info("Instagram session file found")
        logger.debug("Loading Instagram session settings from %s", credentials.session_file)
        client.load_settings(credentials.session_file)
    else:
        logger.info("Instagram session file not found; logging in with credentials")

    logger.info("Instagram login started for username=%s", credentials.username)
    client.login(credentials.username, credentials.password)
    logger.info("Instagram login succeeded for username=%s", credentials.username)
    client.dump_settings(credentials.session_file)
    logger.debug("Instagram session settings saved to %s", credentials.session_file)

    return client


def login_instaloader(credentials: InstagramCredentials) -> instaloader.Instaloader:
    client = instaloader.Instaloader(
        iphone_support=False,
        save_metadata=True,
        download_video_thumbnails=True,
        dirname_pattern=settings.download_dir,
        filename_pattern="{shortcode}_{date_utc}",
    )

    session_file_instaloader = credentials.session_file.with_suffix('.instaloader')

    if session_file_instaloader.exists():
        logger.info("Instaloader session file found")
        try:
            client.load_session_from_file(credentials.username, filename=str(session_file_instaloader))
            logger.info("Instaloader session loaded successfully for username=%s", credentials.username)
            return client
        except Exception as e:
            logger.warning("Failed to load instaloader session: %s", e)

    logger.info("Instaloader login started for username=%s", credentials.username)
    client.login(credentials.username, credentials.password)
    logger.info("Instaloader login succeeded for username=%s", credentials.username)
    
    client.save_session_to_file(str(session_file_instaloader))
    logger.debug("Instaloader session saved to %s", session_file_instaloader)
    
    return client
