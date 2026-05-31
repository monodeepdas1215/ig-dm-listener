import logging

import instaloader

from app.config import settings

logger = logging.getLogger(__name__)


class InstagramLoader:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

        _client_obj = instaloader.Instaloader()
        self._client = _client_obj.login(username, password)


def download_reel(client: instaloader.Instaloader, shortcode: str) -> None:
    post = instaloader.Post.from_shortcode(client.context, shortcode)
    client.download_post(post, target=settings.download_dir)
