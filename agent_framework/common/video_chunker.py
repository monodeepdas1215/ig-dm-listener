import asyncio
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VideoChunk:
    """A single chunk of a split video."""
    path: str              # Absolute path to the chunk MP4 file
    index: int             # 0-based chunk index
    start_sec: float       # Start time in the original video (seconds)
    duration_sec: float    # Duration of this chunk (seconds)
    size_bytes: int = 0    # Actual file size after splitting


@dataclass
class ChunkManifest:
    """Manifest tracking all chunks produced from a single video file."""
    source_path: str                    # Original video file path
    source_size_bytes: int              # Original video file size
    source_duration_sec: float          # Original video total duration
    target_chunk_size_mb: float         # Requested chunk size
    chunk_dir: str                      # Directory containing chunks
    chunks: list[VideoChunk] = field(default_factory=list)
    manifest_path: str = ""             # Path to the manifest.json file itself
    
    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "source_size_bytes": self.source_size_bytes,
            "source_duration_sec": self.source_duration_sec,
            "target_chunk_size_mb": self.target_chunk_size_mb,
            "chunk_dir": self.chunk_dir,
            "manifest_path": self.manifest_path,
            "chunks": [asdict(c) for c in self.chunks],
        }
    
    def save(self) -> str:
        """Write manifest.json to chunk_dir and return its path."""
        self.manifest_path = os.path.join(self.chunk_dir, "manifest.json")
        with open(self.manifest_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Chunk manifest saved: {self.manifest_path}")
        return self.manifest_path
    
    @staticmethod
    def load(manifest_path: str) -> "ChunkManifest":
        """Load a manifest from disk."""
        with open(manifest_path, "r") as f:
            data = json.load(f)
        chunks = [VideoChunk(**c) for c in data.pop("chunks", [])]
        return ChunkManifest(**data, chunks=chunks)


async def _probe_video(input_path: str) -> tuple[float, int]:
    """Use ffprobe to get video duration (seconds) and bitrate (bps).
    
    Returns:
        (duration_sec, bitrate_bps)
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,bit_rate",
        "-of", "json",
        input_path,
    ]
    logger.debug(f"Running ffprobe: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed (rc={proc.returncode}): {stderr.decode()}")
    
    data = json.loads(stdout.decode())
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0))
    bitrate = int(fmt.get("bit_rate", 0))
    
    # Fallback: estimate bitrate from file size and duration
    if bitrate == 0 and duration > 0:
        file_size = os.path.getsize(input_path)
        bitrate = int((file_size * 8) / duration)
    
    logger.info(f"Video probe: duration={duration:.2f}s, bitrate={bitrate}bps, "
                f"file_size={os.path.getsize(input_path)} bytes")
    return duration, bitrate


async def _split_segment(
    input_path: str, output_path: str, start_sec: float, duration_sec: float
) -> int:
    """Extract a single segment using ffmpeg stream-copy (no re-encoding).
    
    Returns the output file size in bytes.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", input_path,
        "-c", "copy",         # stream copy — fast, no re-encoding
        "-movflags", "+faststart",  # optimize for streaming/playback
        output_path,
    ]
    logger.debug(f"Splitting segment: start={start_sec:.2f}s, duration={duration_sec:.2f}s -> {output_path}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg split failed (rc={proc.returncode}): {stderr.decode()}")
    
    size = os.path.getsize(output_path)
    logger.debug(f"Segment written: {output_path} ({size} bytes)")
    return size


async def split_video(
    input_path: str,
    chunk_size_mb: float = 2.0,
    output_dir: str | None = None,
) -> ChunkManifest:
    """Split a video into time-based chunks of approximately `chunk_size_mb` each.
    
    Strategy:
    1. Probe video duration and bitrate with ffprobe
    2. Calculate seconds_per_chunk = (chunk_size_mb * 8_000_000) / bitrate_bps
    3. Use ffmpeg -c copy to split without re-encoding
    4. Write manifest.json tracking all chunks
    5. If file is already <= chunk_size_mb, return single-chunk manifest
    
    Args:
        input_path: Absolute path to the source video file.
        chunk_size_mb: Target size per chunk in megabytes.
        output_dir: Directory for chunks. Defaults to a subdir next to input file.
    
    Returns:
        ChunkManifest with paths to all chunk files and the manifest.json.
    """
    file_size = os.path.getsize(input_path)
    file_size_mb = file_size / (1024 * 1024)
    
    logger.info(f"split_video: input={input_path}, size={file_size_mb:.2f}MB, "
                f"target_chunk={chunk_size_mb}MB")
    
    # Determine output directory
    if output_dir is None:
        base_name = Path(input_path).stem
        output_dir = os.path.join(os.path.dirname(input_path), f"{base_name}_chunks")
    os.makedirs(output_dir, exist_ok=True)
    
    duration, bitrate = await _probe_video(input_path)
    
    # If file is small enough, single chunk — no splitting needed
    if file_size_mb <= chunk_size_mb:
        logger.info(f"Video ({file_size_mb:.2f}MB) <= chunk_size ({chunk_size_mb}MB), "
                    f"skipping split — single chunk")
        chunk = VideoChunk(
            path=input_path,
            index=0,
            start_sec=0.0,
            duration_sec=duration,
            size_bytes=file_size,
        )
        manifest = ChunkManifest(
            source_path=input_path,
            source_size_bytes=file_size,
            source_duration_sec=duration,
            target_chunk_size_mb=chunk_size_mb,
            chunk_dir=output_dir,
            chunks=[chunk],
        )
        manifest.save()
        return manifest
    
    # Calculate seconds per chunk
    if bitrate <= 0:
        raise RuntimeError(f"Cannot determine bitrate for {input_path}")
    
    seconds_per_chunk = (chunk_size_mb * 8 * 1_000_000) / bitrate
    num_chunks = math.ceil(duration / seconds_per_chunk)
    
    logger.info(f"Splitting into ~{num_chunks} chunks "
                f"(~{seconds_per_chunk:.1f}s each, bitrate={bitrate}bps)")
    
    chunks: list[VideoChunk] = []
    for i in range(num_chunks):
        start = i * seconds_per_chunk
        chunk_duration = min(seconds_per_chunk, duration - start)
        
        if chunk_duration <= 0:
            break
        
        chunk_path = os.path.join(output_dir, f"chunk_{i:03d}.mp4")
        size = await _split_segment(input_path, chunk_path, start, chunk_duration)
        
        chunks.append(VideoChunk(
            path=chunk_path,
            index=i,
            start_sec=round(start, 2),
            duration_sec=round(chunk_duration, 2),
            size_bytes=size,
        ))
    
    manifest = ChunkManifest(
        source_path=input_path,
        source_size_bytes=file_size,
        source_duration_sec=duration,
        target_chunk_size_mb=chunk_size_mb,
        chunk_dir=output_dir,
        chunks=chunks,
    )
    manifest.save()
    
    logger.info(f"Split complete: {len(chunks)} chunks in {output_dir}")
    return manifest


def cleanup_chunks(manifest: ChunkManifest) -> None:
    """Remove all chunk files and the chunk directory.
    
    Does NOT remove the original source video.
    """
    for chunk in manifest.chunks:
        # Don't delete the original file if single-chunk (path == source_path)
        if chunk.path != manifest.source_path and os.path.exists(chunk.path):
            os.remove(chunk.path)
            logger.debug(f"Removed chunk: {chunk.path}")
    
    if os.path.exists(manifest.manifest_path):
        os.remove(manifest.manifest_path)
    
    if os.path.isdir(manifest.chunk_dir):
        try:
            os.rmdir(manifest.chunk_dir)  # Only removes if empty
        except OSError:
            pass
    
    logger.info(f"Cleaned up chunks for {manifest.source_path}")
