from app.credentials import load_instagram_credentials
from app.logging_config import configure_logging
from app.services.instagram_auth import login_instaloader
from app.services.instaloader import download_reel
from app.utils import parser


def main(instagram_reel_url) -> None:
    configure_logging("download_reel", debug=True)

    credentials = load_instagram_credentials()
    shortcode = parser.parse_reel_shortcode(instagram_reel_url)

    client = login_instaloader(credentials)
    download_reel(client, shortcode)


if __name__ == "__main__":
    main("https://www.instagram.com/reel/DWa4EvEEU6D/?id=3862646246440259203_7046063475&is_sponsored=false&is_ineligible_for_clips_chaining=false")
