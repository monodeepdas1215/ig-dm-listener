import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app import env_keys
from app.config import settings
from app.utils.parser import parse_webhook_payload


logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhook"])

HUB_MODE_QUERY_PARAM = "hub.mode"
HUB_VERIFY_TOKEN_QUERY_PARAM = "hub.verify_token"
HUB_CHALLENGE_QUERY_PARAM = "hub.challenge"


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias=HUB_MODE_QUERY_PARAM),
    hub_verify_token: str | None = Query(default=None, alias=HUB_VERIFY_TOKEN_QUERY_PARAM),
    hub_challenge: str | None = Query(default=None, alias=HUB_CHALLENGE_QUERY_PARAM),
) -> str:
    if not settings.meta_verify_token:
        logger.error("%s is not configured", env_keys.META_VERIFY_TOKEN)
        raise HTTPException(status_code=500, detail="Webhook verify token is not configured")

    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token and hub_challenge:
        logger.info("Meta webhook verification succeeded")
        return hub_challenge

    logger.warning("Meta webhook verification failed")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    entries = payload.get("entry", [])
    logger.info(
        "Incoming Meta webhook payload received object=%s entry_count=%s",
        payload.get("object"),
        len(entries) if isinstance(entries, list) else 0,
    )

    parsed_payload = parse_webhook_payload(payload)
    logger.info(
        "Parsed Meta webhook payload object=%s entry_count=%s",
        parsed_payload.get("object"),
        len(parsed_payload.get("entries", [])),
    )
    logger.debug("Meta webhook payload parsed successfully")

    return {"status": "received"}
