import logging
from typing import Any

from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import get_instagrapi_client

logger = logging.getLogger(__name__)


class AuthenticateClientsNode(InstaDMBaseNode):
    async def run(self, state: InstaDMState) -> dict[str, Any]:
        logger.info("Authenticating Instagram clients...")
        
        credentials = load_instagram_credentials()
        get_instagrapi_client(credentials)
        
        logger.info("Instagram clients authenticated successfully.")
        
        return {}
