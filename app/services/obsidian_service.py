import logging
import os
from datetime import datetime
from typing import Any, List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# Path to the highlight prompt template
_HIGHLIGHT_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "agent_framework", "graphs", "shared", "prompts", "highlight_prompt.md",
)


def build_vault_path(shortcode: str, message_id: str) -> str:
    """Build the vault path raw/instaKB/{shortcode}.md (or fallback to message_id)."""
    identifier = shortcode or message_id
    # Clean identifier to avoid directory traversal
    identifier = identifier.replace("/", "_").replace("\\", "_")
    return f"raw/instaKB/{identifier}.md"


def format_reel_note(reel_record: dict, summary_data: dict, creator_username: str, highlight: str = "") -> str:
    """Format the reel details and LLM analysis into an Obsidian Markdown note."""
    shortcode = reel_record.get("shortcode", "")
    message_id = reel_record.get("message_id", "")
    reel_url = reel_record.get("reel_url", "")
    media_pk = reel_record.get("media_pk", "")
    
    # Fallback to the parsed/provided location or database location
    location = summary_data.get("location") or reel_record.get("location") or "Unknown"
    
    # Get tags, prefixing with 'instagram-reel'
    tags = ["instagram-reel"]
    raw_tags = summary_data.get("tags", [])
    if isinstance(raw_tags, list):
        for t in raw_tags:
            # Clean tag
            t_clean = str(t).strip().lstrip("#")
            if t_clean and t_clean not in tags:
                tags.append(t_clean)
                
    summary = summary_data.get("summary", "No summary available.")
    
    visual_text = summary_data.get("visual_text", "")
    transcript = summary_data.get("transcript", "")
    extracted_text_parts = []
    if visual_text:
        extracted_text_parts.append(f"**Visual Text:**\n{visual_text}")
    if transcript:
        extracted_text_parts.append(f"**Transcript:**\n{transcript}")
    
    extracted_text = "\n\n".join(extracted_text_parts) if extracted_text_parts else "No extracted text available."
    
    synced_at = datetime.now().isoformat()
    
    # Construct YAML frontmatter
    yaml_tags = "\n".join(f"  - {t}" for t in tags)
    
    note_content = f"""---
tags:
{yaml_tags}
reel_url: {reel_url}
shortcode: {shortcode}
media_pk: "{media_pk}"
message_id: "{message_id}"
location: "{location}"
creator: "{creator_username}"
synced_at: {synced_at}
---

# Reel: {shortcode or message_id}
{f"{chr(10)}## Highlight{chr(10)}{highlight}{chr(10)}" if highlight else ""}
#### Creator: {creator_username}

## Summary
{summary}

## Extracted Text
{extracted_text}

## Metadata
- **Reel URL**: [Open in Instagram]({reel_url})
- **Location**: {location}
"""
    return note_content


async def sync_reel_to_obsidian(tools: List[BaseTool], vault_path: str, content: str) -> bool:
    """Find the vault_write tool and write the note to the Obsidian vault."""
    vault_write_tool = next((t for t in tools if t.name == "vault_write"), None)
    if not vault_write_tool:
        logger.error("vault_write tool not found in loaded MCP tools.")
        return False
        
    try:
        logger.info(f"Writing note to Obsidian vault at {vault_path}...")
        result = await vault_write_tool.ainvoke({
            "path": vault_path,
            "content": content
        })
        logger.info(f"Successfully wrote note to Obsidian: {result}")
        return True
    except Exception as e:
        logger.error(f"Failed to write note to Obsidian at {vault_path}: {e}")
        return False


async def generate_highlight(llm: BaseChatModel, summary_data: dict) -> str:
    """Generate a catchy one-liner highlight for the reel note via LLM."""
    try:
        with open(_HIGHLIGHT_PROMPT_PATH, "r") as f:
            template = f.read()

        tags = summary_data.get("tags", [])
        visual_text = summary_data.get("visual_text", "")
        transcript = summary_data.get("transcript", "")
        extracted_text = f"Visual Text: {visual_text}\nTranscript: {transcript}" if visual_text or transcript else ""

        rendered = template.format(
            summary=summary_data.get("summary", ""),
            extracted_text=extracted_text,
            tags=", ".join(tags) if isinstance(tags, list) else str(tags),
            location=summary_data.get("location") or "Unknown",
        )

        response = await llm.ainvoke([HumanMessage(content=rendered)])
        highlight = response.content.strip().strip('"').strip("'")
        logger.info(f"Generated highlight: {highlight}")
        return highlight
    except Exception as e:
        logger.warning(f"Failed to generate highlight, note will be written without one: {e}")
        return ""
