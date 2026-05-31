import argparse
import json
import logging

from app.config import settings
from app.logging_config import configure_logging
from app.services.instagram_dm_reader import DirectThreadLookupError, read_dm_metadata_for_sender


logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read Instagram DM metadata for configured sender.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum messages to read from the thread.")
    parser.add_argument("--debug", action="store_true", default=None, help="Enable debug logging for this run.")
    args = parser.parse_args()

    configure_logging("read_instagram_inbox", debug=args.debug)
    logger.info(
        "Script started sender_username=%s limit=%s debug=%s",
        settings.ig_dm_sender_username,
        args.limit,
        bool(args.debug or settings.log_debug),
    )

    try:
        metadata = read_dm_metadata_for_sender(message_limit=args.limit)
        json_output = json.dumps(metadata, indent=2, default=str)
        print(json_output)
        logger.info("DM metadata JSON output emitted")
        logger.debug("DM metadata JSON:\n%s", json_output)
        logger.info("Script completed successfully")
    except (DirectThreadLookupError, ValueError) as exc:
        logger.error("Script failed: %s", exc)
        raise SystemExit(1) from exc
    except Exception as exc:
        logger.exception("Unexpected script failure")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
