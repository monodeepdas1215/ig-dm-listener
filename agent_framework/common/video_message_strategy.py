import asyncio
import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from agent_framework.common.video_chunker import (
    split_video, cleanup_chunks, ChunkManifest, VideoChunk,
)
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.services.resilient_caller import RetryConfig, RESILIENT_CLASSIFIERS
from app.config import settings

logger = logging.getLogger(__name__)

def _load_prompt(filename: str) -> str:
    path = os.path.join(
        os.path.dirname(__file__), "..", "graphs", "shared", "prompts", filename
    )
    with open(path, "r") as f:
        return f.read()

class VideoMessageStrategy(ABC):
    """Abstract strategy for building and executing video analysis."""
    
    @abstractmethod
    async def chunk(self, local_path: str, chunk_size_mb: float = 2.0) -> ChunkManifest | None:
        """Optional pre-processing step. Returns manifest if chunking occurred."""
        ...

    @abstractmethod
    async def analyze(self, local_path: str, llm: Any, manifest: ChunkManifest | None = None) -> str:
        """Executes the analysis and returns the final JSON string."""
        ...


class LangChainVideoStrategy(VideoMessageStrategy):
    """Strategy for providers using LangChain's ChatModel (Gemini/OpenAI)."""
    
    def __init__(self, provider: str):
        self.provider = provider
        
    async def chunk(self, local_path: str, chunk_size_mb: float = 2.0) -> ChunkManifest | None:
        # Gemini handles large files natively, no ffmpeg splitting needed
        return None
    
    async def analyze(self, local_path: str, llm: BaseChatModel, manifest: ChunkManifest | None = None) -> str:
        system_prompt = _load_prompt("system_prompt.md")
        user_prompt = _load_prompt("user_prompt.md")
        
        with open(local_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=[
                {"type": "text", "text": user_prompt},
                {
                    "type": "media",
                    "mime_type": "video/mp4",
                    "data": video_b64,
                }
            ])
        ]
        
        response = await llm.ainvoke(messages)
        content = response.content
        if isinstance(content, list):
            content = " ".join([str(c) for c in content if isinstance(c, str)])
        return str(content)


class ZhipuVideoStrategy(VideoMessageStrategy):
    """Map-reduce strategy for ZhipuAI GLM models."""
    
    async def chunk(self, local_path: str, chunk_size_mb: float = 2.0) -> ChunkManifest | None:
        # GLM requires <5MB chunks, so we split via ffmpeg and return the manifest
        manifest = await split_video(local_path, chunk_size_mb)
        return manifest
    
    async def analyze(self, local_path: str, llm: Any, manifest: ChunkManifest | None = None) -> str:
        if not manifest:
            raise ValueError("ZhipuVideoStrategy requires a ChunkManifest")
            
        system_prompt = _load_prompt("system_prompt.md")
        user_prompt = _load_prompt("user_prompt.md")
        reduce_system_prompt = _load_prompt("reduce_system_prompt.md")
        reduce_user_prompt = _load_prompt("reduce_user_prompt.md")

        if len(manifest.chunks) == 1:
            return await self._analyze_single_chunk(
                llm, system_prompt, user_prompt,
                manifest.chunks[0],
                chunk_label="(full video, 1/1)"
            )
            
        # MAP phase
        pool = ThrottledPool(ThrottleConfig(
            max_concurrent=settings.zai_video_map_max_concurrent,
            inter_call_delay_max=0,
            retry_config=RetryConfig(
                max_retries=settings.zai_max_retries,
                base_delay=5.0,
                max_delay=60.0,
                retryable_classifiers=RESILIENT_CLASSIFIERS,
            ),
        ))
        
        total = len(manifest.chunks)
        task_fns = [
            lambda c=chunk, i=chunk.index: self._analyze_single_chunk(
                llm, system_prompt, user_prompt, c,
                chunk_label=f"(chunk {i+1}/{total}, {c.start_sec:.1f}s-{c.start_sec + c.duration_sec:.1f}s)"
            )
            for chunk in manifest.chunks
        ]
        
        chunk_results = await pool.run(task_fns)
        
        chunk_analyses: list[dict[str, Any]] = []
        for i, result in enumerate(chunk_results):
            chunk = manifest.chunks[i]
            if isinstance(result, Exception):
                logger.error(f"MAP chunk {i} FAILED: {result}")
                chunk_analyses.append({
                    "chunk_index": i, "start_sec": chunk.start_sec, "duration_sec": chunk.duration_sec,
                    "status": "failed", "error": str(result), "analysis": None,
                })
            else:
                chunk_analyses.append({
                    "chunk_index": i, "start_sec": chunk.start_sec, "duration_sec": chunk.duration_sec,
                    "status": "success", "error": None, "analysis": result,
                })
                
        successful = [ca for ca in chunk_analyses if ca["status"] == "success"]
        if not successful:
            raise RuntimeError("All MAP chunks failed.")
            
        # REDUCE phase
        return await self._reduce(
            llm, reduce_system_prompt, reduce_user_prompt, chunk_analyses, manifest
        )
        
    async def _analyze_single_chunk(
        self, caller: Any, system_prompt: str, user_prompt: str,
        chunk: VideoChunk, chunk_label: str = ""
    ) -> str:
        with open(chunk.path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": user_prompt},
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
            ]},
        ]
        
        import asyncio
        result = await asyncio.to_thread(caller.invoke_sync, messages, settings.zai_vision_model)
        return result
        
    async def _reduce(
        self, caller: Any, reduce_system_prompt: str, reduce_user_prompt: str,
        chunk_analyses: list[dict], manifest: ChunkManifest
    ) -> str:
        formatted_chunks = []
        for ca in chunk_analyses:
            status_text = ca['analysis'] if ca['status'] == "success" else f"[ANALYSIS UNAVAILABLE: {ca['error']}]"
            formatted_chunks.append(
                f"--- SEGMENT {ca['chunk_index'] + 1} "
                f"({ca['start_sec']:.1f}s to {ca['start_sec'] + ca['duration_sec']:.1f}s) ---\n"
                f"{status_text}"
            )
            
        chunk_analyses_text = "\n\n".join(formatted_chunks)
        video_metadata = (
            f"Total video duration: {manifest.source_duration_sec:.1f} seconds\n"
            f"Total segments: {len(chunk_analyses)}\n"
            f"Successfully analyzed segments: {len([ca for ca in chunk_analyses if ca['status'] == 'success'])}\n"
            f"Failed segments: {len([ca for ca in chunk_analyses if ca['status'] == 'failed'])}"
        )
        
        filled_user_prompt = reduce_user_prompt.replace("{chunk_analyses}", chunk_analyses_text).replace("{video_metadata}", video_metadata)
        
        messages = [
            {"role": "system", "content": reduce_system_prompt},
            {"role": "user", "content": filled_user_prompt},
        ]
        
        import asyncio
        result = await asyncio.to_thread(caller.invoke_sync, messages)
        return result


# ── Factory ──────────────────────────────────────────
_STRATEGY_MAP: dict[str, Any] = {
    "google-genai": lambda: LangChainVideoStrategy("google-genai"),
    "openai":       lambda: LangChainVideoStrategy("openai"),
    "anthropic":    lambda: LangChainVideoStrategy("anthropic"),
    "ollama":       lambda: LangChainVideoStrategy("ollama"),
    "zhipuai":      lambda: ZhipuVideoStrategy(),
}

def get_video_strategy(provider: str) -> VideoMessageStrategy:
    """Resolve the correct video message strategy for a provider."""
    factory = _STRATEGY_MAP.get(provider)
    if not factory:
        raise ValueError(f"No video message strategy for provider '{provider}'. Supported: {list(_STRATEGY_MAP.keys())}")
    return factory()
