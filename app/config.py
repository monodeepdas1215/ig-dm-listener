import os
from dataclasses import dataclass
from pathlib import Path
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

DEFAULT_INSTAGRAM_SESSION_FILE = ".instagrapi-session.json"
DEFAULT_SESSION_FILE = "DEFAULT_SESSION_FILE"
IG_DM_SENDER_USERNAME = "IG_DM_SENDER_USERNAME"
IG_PASSWORD = "IG_PASSWORD"
IG_SESSION_FILE = "IG_SESSION_FILE"
IG_USERNAME = "IG_USERNAME"
LOG_DEBUG = "LOG_DEBUG"
LOG_DIR = "LOG_DIR"
LOG_LEVEL = "LOG_LEVEL"
META_VERIFY_TOKEN = "META_VERIFY_TOKEN"
DATABASE_URL = "DATABASE_URL"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "ig-dm-listener"
    meta_verify_token: str = os.getenv(META_VERIFY_TOKEN, "")
    ig_username: str = os.getenv(IG_USERNAME, "")
    ig_password: str = os.getenv(IG_PASSWORD, "")
    ig_dm_sender_username: str = os.getenv(IG_DM_SENDER_USERNAME, "")
    log_level: str = os.getenv(LOG_LEVEL, "INFO")
    log_debug: bool = _env_bool(LOG_DEBUG, False)
    log_dir: str = os.getenv(LOG_DIR, "logs")
    default_session_file: Path = Path(
        os.getenv(DEFAULT_SESSION_FILE, DEFAULT_INSTAGRAM_SESSION_FILE)
    )
    
    # Retry
    retry_max_retries: int = int(os.getenv("RETRY_MAX_RETRIES", "3"))
    retry_base_delay: float = float(os.getenv("RETRY_BASE_DELAY", "5.0"))
    retry_max_delay: float = float(os.getenv("RETRY_MAX_DELAY", "120.0"))
    
    # LLM throttle
    llm_max_concurrent: int = int(os.getenv("LLM_MAX_CONCURRENT", "2"))
    llm_inter_call_delay_max: float = float(os.getenv("LLM_INTER_CALL_DELAY_MAX", "120.0"))
    
    # Download throttle
    download_max_concurrent: int = int(os.getenv("DOWNLOAD_MAX_CONCURRENT", "3"))
    download_inter_call_delay_max: float = float(os.getenv("DOWNLOAD_INTER_CALL_DELAY_MAX", "30.0"))

    # Backfill
    backfill_batch_size: int = int(os.getenv("BACKFILL_BATCH_SIZE", "5"))
    backfill_stale_threshold_minutes: int = int(os.getenv("BACKFILL_STALE_THRESHOLD_MINUTES", "15"))
    
    # Database
    drop_db_on_start: bool = os.getenv("DROP_DB_ON_START", "false").lower() == "true"

    # Paths
    download_dir: str = os.getenv("DOWNLOAD_DIR", "downloaded_reel")
    database_url: str = os.getenv(
        DATABASE_URL,
        "postgresql://igapp:igapp_secret@localhost:5432/ig_dm_listener"
    )
    db_pool_min: int = int(os.getenv("DB_POOL_MIN", "2"))
    db_pool_max: int = int(os.getenv("DB_POOL_MAX", "10"))


settings = Settings()
