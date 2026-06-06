import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agent_framework.common.video_message_strategy import (
    get_video_strategy, 
    LangChainVideoStrategy, 
    GlmMapReduceVideoStrategy
)
from agent_framework.common.video_chunker import ChunkManifest, VideoChunk

def test_get_video_strategy():
    assert isinstance(get_video_strategy("google-genai"), LangChainVideoStrategy)
    assert isinstance(get_video_strategy("zhipuai"), GlmMapReduceVideoStrategy)
    
    with pytest.raises(ValueError):
        get_video_strategy("unknown-provider")

@pytest.mark.asyncio
async def test_langchain_strategy():
    strategy = LangChainVideoStrategy("google-genai")
    
    with patch("builtins.open"), patch("base64.b64encode") as mock_b64:
        mock_b64.return_value = b"encoded_video"
        
        messages = strategy.build_messages("sys prompt", "usr prompt", "path.mp4")
        
        assert len(messages) == 2
        assert messages[0].content == "sys prompt"
        assert messages[1].content[1]["data"] == "encoded_video"
        assert messages[1].content[1]["mime_type"] == "video/mp4"

@pytest.mark.asyncio
async def test_glm_map_reduce_strategy_single_chunk():
    strategy = GlmMapReduceVideoStrategy()
    caller = MagicMock()
    
    manifest = ChunkManifest(
        source_path="video.mp4",
        source_size_bytes=1000000,
        source_duration_sec=10.0,
        target_chunk_size_mb=2.0,
        chunk_dir="chunks",
        chunks=[
            VideoChunk("video.mp4", 0, 0.0, 10.0, 1000000)
        ]
    )
    
    with patch("agent_framework.common.video_message_strategy.split_video") as mock_split, \
         patch.object(strategy, "_analyze_single_chunk", new_callable=AsyncMock) as mock_analyze:
         
        mock_split.return_value = manifest
        mock_analyze.return_value = "single chunk analysis"
        
        result = await strategy.analyze(
            caller, "sys", "usr", "video.mp4", "red_sys", "red_usr"
        )
        
        assert result == "single chunk analysis"
        mock_analyze.assert_called_once()
        # Ensure it didn't call reduce (which requires multiple chunks and calls _reduce)
        caller.invoke_sync.assert_not_called() # Not called directly here because mocked

@pytest.mark.asyncio
async def test_glm_map_reduce_strategy_multi_chunk():
    strategy = GlmMapReduceVideoStrategy()
    caller = MagicMock()
    
    manifest = ChunkManifest(
        source_path="video.mp4",
        source_size_bytes=4000000,
        source_duration_sec=20.0,
        target_chunk_size_mb=2.0,
        chunk_dir="chunks",
        chunks=[
            VideoChunk("chunk0.mp4", 0, 0.0, 10.0, 2000000),
            VideoChunk("chunk1.mp4", 1, 10.0, 10.0, 2000000)
        ]
    )
    
    with patch("agent_framework.common.video_message_strategy.split_video") as mock_split, \
         patch.object(strategy, "_analyze_single_chunk", new_callable=AsyncMock) as mock_analyze_chunk, \
         patch.object(strategy, "_reduce", new_callable=AsyncMock) as mock_reduce:
         
        mock_split.return_value = manifest
        mock_analyze_chunk.side_effect = ["analysis 1", "analysis 2"]
        mock_reduce.return_value = "final synthesis"
        
        result = await strategy.analyze(
            caller, "sys", "usr", "video.mp4", "red_sys", "red_usr"
        )
        
        assert result == "final synthesis"
        assert mock_analyze_chunk.call_count == 2
        mock_reduce.assert_called_once()
        
        # Verify inputs to reduce
        reduce_args = mock_reduce.call_args[0]
        chunk_analyses = reduce_args[3]
        assert len(chunk_analyses) == 2
        assert chunk_analyses[0]["status"] == "success"
        assert chunk_analyses[0]["analysis"] == "analysis 1"
