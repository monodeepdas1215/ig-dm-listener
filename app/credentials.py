from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.config import IG_USERNAME, IG_PASSWORD, IG_SESSION_FILE, DEFAULT_INSTAGRAM_SESSION_FILE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstagramCredentials:
    username: str
    password: str
    session_file: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "InstagramCredentials":
        return load_instagram_credentials(env=env)


def load_instagram_credentials(env: Mapping[str, str] | None = None) -> InstagramCredentials:
    env = env or os.environ
    username = env.get(IG_USERNAME, "").strip()
    password = env.get(IG_PASSWORD, "")
    session_file = Path(env.get(IG_SESSION_FILE, DEFAULT_INSTAGRAM_SESSION_FILE))

    if not username or not password:
        raise ValueError(
            f"Set {IG_USERNAME} and {IG_PASSWORD} before reading Instagram DMs."
        )

    logger.info("Instagram credentials loaded for username=%s", username)
    logger.debug("Instagram session file configured at %s", session_file)
    return InstagramCredentials(username=username, password=password, session_file=session_file)
