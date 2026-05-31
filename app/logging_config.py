import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(execution_name: str, debug: bool | None = None) -> Path:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_execution_name = _safe_execution_name(execution_name)
    log_path = log_dir / f"{safe_execution_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    level = _log_level(debug)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
        force=True,
    )
    _configure_third_party_loggers()

    logger = logging.getLogger(__name__)
    logger.info("Logging configured for %s", safe_execution_name)
    logger.debug("Debug logging enabled")
    logger.debug("Log file path: %s", log_path)

    return log_path


def _log_level(debug: bool | None) -> int:
    if settings.log_debug if debug is None else debug:
        return logging.DEBUG

    configured_level = getattr(logging, settings.log_level.upper(), None)
    if isinstance(configured_level, int):
        return configured_level

    return logging.INFO


def _safe_execution_name(execution_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", execution_name.strip())
    return cleaned or "execution"


def _configure_third_party_loggers() -> None:
    for logger_name in ("instagrapi", "public_request", "private_request"):
        logging.getLogger(logger_name).setLevel(logging.INFO)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
