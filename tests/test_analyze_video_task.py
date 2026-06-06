import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
from agent_framework.graphs.insta_dm_automation.nodes.analyze_reels import analyze_video_task
from agent_framework.common.video_message_strategy import LangChainVideoStrategy, GlmMapReduceVideoStrategy

@pytest.mark.asyncio
async def test_analyze_video_task_langchain():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value.content = '```json\n{"visual_text": "hello"}\n```'
    
    with patch("agent_framework.graphs.insta_dm_automation.nodes.analyze_reels.get_video_strategy") as mock_get_strategy:
        mock_strategy = MagicMock(spec=LangChainVideoStrategy)
        mock_strategy.build_messages.return_value = ["mocked", "messages"]
        mock_get_strategy.return_value = mock_strategy
        
        result = await analyze_video_task(
            mock_llm, "sys", "user", "msg123", "video.mp4", provider="google-genai"
        )
        
        assert result["message_id"] == "msg123"
        assert result["summary"]["visual_text"] == "hello"
        mock_llm.ainvoke.assert_called_once_with(["mocked", "messages"])

@pytest.mark.asyncio
async def test_analyze_video_task_glm():
    mock_llm = MagicMock() # ZaiCaller
    
    with patch("agent_framework.graphs.insta_dm_automation.nodes.analyze_reels.get_video_strategy") as mock_get_strategy:
        mock_strategy = AsyncMock(spec=GlmMapReduceVideoStrategy)
        mock_strategy.analyze.return_value = '{"visual_text": "hello zhipu"}'
        mock_get_strategy.return_value = mock_strategy
        
        result = await analyze_video_task(
            mock_llm, "sys", "user", "msg123", "video.mp4", provider="zhipuai",
            reduce_system_prompt="red_sys", reduce_user_prompt="red_usr"
        )
        
        assert result["message_id"] == "msg123"
        assert result["summary"]["visual_text"] == "hello zhipu"
        mock_strategy.analyze.assert_called_once()
        
@pytest.mark.asyncio
async def test_analyze_video_task_glm_missing_prompts():
    mock_llm = MagicMock()
    
    with patch("agent_framework.graphs.insta_dm_automation.nodes.analyze_reels.get_video_strategy") as mock_get_strategy:
        mock_strategy = AsyncMock(spec=GlmMapReduceVideoStrategy)
        mock_get_strategy.return_value = mock_strategy
        
        with pytest.raises(ValueError):
            await analyze_video_task(
                mock_llm, "sys", "user", "msg123", "video.mp4", provider="zhipuai"
            )
