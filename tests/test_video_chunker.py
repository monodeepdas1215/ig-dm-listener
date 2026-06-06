import asyncio
import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from agent_framework.common.video_chunker import (
    VideoChunk, ChunkManifest, split_video, cleanup_chunks, _probe_video
)


@pytest.fixture
def temp_video_file(tmp_path):
    video_path = tmp_path / "test_video.mp4"
    video_path.write_text("dummy content")
    return str(video_path)


@pytest.mark.asyncio
async def test_probe_video(temp_video_file):
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(
            json.dumps({"format": {"duration": "10.5", "bit_rate": "1000000"}}).encode(),
            b""
        ))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc
        
        duration, bitrate = await _probe_video(temp_video_file)
        assert duration == 10.5
        assert bitrate == 1000000


@pytest.mark.asyncio
async def test_split_video_single_chunk(temp_video_file, tmp_path):
    with patch("agent_framework.common.video_chunker._probe_video") as mock_probe:
        mock_probe.return_value = (10.0, 1000000)
        # File is small, should bypass split
        manifest = await split_video(temp_video_file, chunk_size_mb=2.0)
        
        assert len(manifest.chunks) == 1
    assert manifest.chunks[0].path == temp_video_file
    assert manifest.chunks[0].start_sec == 0.0
    
    # Cleanup should not delete the source file
    cleanup_chunks(manifest)
    assert os.path.exists(temp_video_file)


@pytest.mark.asyncio
async def test_split_video_multiple_chunks(temp_video_file, tmp_path):
    with patch("agent_framework.common.video_chunker._probe_video") as mock_probe, \
         patch("agent_framework.common.video_chunker._split_segment") as mock_split, \
         patch("os.path.getsize") as mock_getsize:
        
        mock_probe.return_value = (30.0, 8000000) # 30 seconds, ~1MB/s
        mock_getsize.side_effect = [30000000, 2000000, 2000000, 2000000] # Source size, then chunk sizes
        mock_split.return_value = 2000000
        
        # Target chunk size is 2MB, but mock file is 30MB
        manifest = await split_video(temp_video_file, chunk_size_mb=2.0)
        
        # Total duration is 30s. Target size is 2MB = 16Mbit. 
        # seconds_per_chunk = 16Mbit / 8Mbps = 2.0s
        # 30s / 2.0s = 15 chunks
        assert len(manifest.chunks) == 15
        assert manifest.chunks[0].duration_sec == 2.0
        assert manifest.chunks[1].start_sec == 2.0
        
        assert os.path.exists(manifest.manifest_path)
