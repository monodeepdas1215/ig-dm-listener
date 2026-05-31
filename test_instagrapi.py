import sys
import logging
import asyncio
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import login_instagrapi
from app.utils import parser

logging.basicConfig(level=logging.DEBUG)

credentials = load_instagram_credentials()
client = login_instagrapi(credentials)

url = "https://www.instagram.com/reel/DYl2VM1MGRr/?id=3901763603584279659_4060964118&is_sponsored=false&is_ineligible_for_clips_chaining=false"
shortcode = parser.parse_reel_shortcode(url)
print("Shortcode:", shortcode)

try:
    media_pk = client.media_pk_from_code(shortcode)
    print("Media PK:", media_pk)
    
    path = client.clip_download(media_pk, folder="downloaded_reel")
    print("Downloaded to:", path)
except Exception as e:
    print("Failed to download:", e)

