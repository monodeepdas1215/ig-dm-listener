import sys
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import login_instagrapi
import instaloader
import logging

logging.basicConfig(level=logging.DEBUG)

credentials = load_instagram_credentials()
client_api = login_instagrapi(credentials)

cookies = client_api.get_settings().get("cookies", {})
print("Cookies from instagrapi:", cookies)

loader = instaloader.Instaloader()
loader.context._session.cookies.update(cookies)
loader.context.username = credentials.username

try:
    profile = instaloader.Profile.from_username(loader.context, credentials.username)
    print("Successfully fetched profile info using instagrapi cookies!", profile.followers)
except Exception as e:
    print("Failed:", e)

