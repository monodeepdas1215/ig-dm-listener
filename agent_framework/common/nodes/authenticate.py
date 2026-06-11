import logging
from typing import Any

from agent_framework.nodes.base import BaseNode
from agent_framework.schemas.state import AgentState
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import get_instagrapi_client

logger = logging.getLogger(__name__)


class AuthenticateClientsNode(BaseNode):
    """Shared node to authenticate Instagram clients before downstream processing."""
    
    async def run(self, state: AgentState) -> dict[str, Any]:
        logger.info("Authenticating Instagram clients...")
        
        credentials = load_instagram_credentials()
        get_instagrapi_client(credentials)
        
        logger.info("Instagram clients authenticated successfully.")
        
        return {}
