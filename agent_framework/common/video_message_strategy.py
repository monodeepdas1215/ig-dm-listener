import asyncio
import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_framework.common.video_chunker import (
    split_video, cleanup_chunks, ChunkManifest, VideoChunk,
)
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.services.resilient_caller import RetryConfig, RESILIENT_CLASSIFIERS

logger = logging.getLogger(__name__)


class VideoMessageStrategy(ABC):
    """Abstract strategy for building video analysis messages."""
    
    @abstractmethod
    def build_messages(self, system_prompt: str, user_prompt: str, local_path: str) -> list:
        """Build provider-specific messages with video content."""
        ...


class LangChainVideoStrategy(VideoMessageStrategy):
    """Unified strategy for providers using LangChain's ChatModel.
    
    Builds SystemMessage + HumanMessage with the appropriate
    content block format for the given provider.
    
    Supported providers:
    - google-genai: {type: "media", mime_type: ..., data: ...}
    - openai/anthropic/ollama: {type: "media", mime_type: ..., data: ...}
    """
    
    def __init__(self, provider: str):
        self.provider = provider
    
    def build_messages(self, system_prompt: str, user_prompt: str, local_path: str) -> list:
        with open(local_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        return [
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


class GlmMapReduceVideoStrategy(VideoMessageStrategy):
    """Map-reduce video strategy for ZhipuAI GLM models.
    
    Pipeline:
    1. SPLIT: Break video into ~2MB time-based chunks via ffmpeg
    2. MAP:   Send each chunk to GLM concurrently (via ThrottledPool)
              Each chunk gets the original system_prompt + user_prompt
    3. REDUCE: Feed all chunk responses as text to GLM for final synthesis
               Uses dedicated reduce_system_prompt + reduce_user_prompt
    
    This strategy owns the full LLM invocation lifecycle — it calls
    ZaiCaller.invoke() directly rather than just building messages.
    """
    
    def build_messages(self, system_prompt: str, user_prompt: str, local_path: str) -> list:
        raise NotImplementedError(
            "GlmMapReduceVideoStrategy uses analyze() instead of build_messages(). "
            "Call analyze() directly with the ZaiCaller instance."
        )
    
    async def analyze(
        self,
        caller: Any,  # ZaiCaller
        system_prompt: str,
        user_prompt: str,
        local_path: str,
        reduce_system_prompt: str,
        reduce_user_prompt: str,
        chunk_size_mb: float = 2.0,
        map_max_concurrent: int = 3,
        vision_model: str | None = None,
    ) -> str:
        """Full map-reduce video analysis. Returns final synthesized text.
        
        Args:
            caller: ZaiCaller instance for GLM API calls.
            system_prompt: System prompt for the MAP step (per-chunk analysis).
            user_prompt: User prompt for the MAP step (per-chunk analysis).
            local_path: Path to the source video file.
            reduce_system_prompt: System prompt for the REDUCE step.
            reduce_user_prompt: User prompt template for the REDUCE step.
                                Must contain {chunk_analyses} placeholder.
            chunk_size_mb: Target chunk size in MB for splitting.
            map_max_concurrent: Max concurrent MAP workers.
            vision_model: The GLM vision model to use for map step.
        
        Returns:
            The final synthesized analysis text from the REDUCE step.
        """
        logger.info(
            f"GlmMapReduceVideoStrategy.analyze: "
            f"file={local_path}, chunk_size={chunk_size_mb}MB, "
            f"map_concurrency={map_max_concurrent}"
        )
        
        # ── 1. SPLIT ──────────────────────────────────────
        manifest = await split_video(local_path, chunk_size_mb)
        logger.info(
            f"SPLIT complete: {len(manifest.chunks)} chunks from "
            f"{manifest.source_duration_sec:.1f}s video "
            f"({manifest.source_size_bytes / 1024 / 1024:.2f}MB). "
            f"Manifest: {manifest.manifest_path}"
        )
        
        try:
            if len(manifest.chunks) == 1:
                # Small video — single call, no map-reduce overhead
                logger.info("Single chunk — bypassing map-reduce, direct analysis")
                return await self._analyze_single_chunk(
                    caller, system_prompt, user_prompt,
                    manifest.chunks[0],
                    chunk_label="(full video, 1/1)",
                    vision_model=vision_model,
                )
            
            # ── 2. MAP ────────────────────────────────────
            logger.info(
                f"MAP phase: dispatching {len(manifest.chunks)} chunks "
                f"to {map_max_concurrent} concurrent workers"
            )
            
            pool = ThrottledPool(ThrottleConfig(
                max_concurrent=map_max_concurrent,
                inter_call_delay_max=0,  # no throttle between map calls
                retry_config=RetryConfig(
                    max_retries=3,
                    base_delay=5.0,
                    max_delay=60.0,
                    retryable_classifiers=RESILIENT_CLASSIFIERS,
                ),
            ))
            
            total = len(manifest.chunks)
            task_fns = [
                lambda c=chunk, i=chunk.index: self._analyze_single_chunk(
                    caller, system_prompt, user_prompt, c,
                    chunk_label=f"(chunk {i+1}/{total}, "
                                f"{c.start_sec:.1f}s-{c.start_sec + c.duration_sec:.1f}s)",
                    vision_model=vision_model,
                )
                for chunk in manifest.chunks
            ]
            
            chunk_results = await pool.run(task_fns)
            
            # Collect results, logging failures
            chunk_analyses: list[dict[str, Any]] = []
            for i, result in enumerate(chunk_results):
                chunk = manifest.chunks[i]
                if isinstance(result, Exception):
                    logger.error(
                        f"MAP chunk {i} FAILED "
                        f"({chunk.start_sec:.1f}s-{chunk.start_sec + chunk.duration_sec:.1f}s): "
                        f"{result}"
                    )
                    chunk_analyses.append({
                        "chunk_index": i,
                        "start_sec": chunk.start_sec,
                        "duration_sec": chunk.duration_sec,
                        "status": "failed",
                        "error": str(result),
                        "analysis": None,
                    })
                else:
                    logger.info(
                        f"MAP chunk {i} SUCCESS "
                        f"({chunk.start_sec:.1f}s-{chunk.start_sec + chunk.duration_sec:.1f}s): "
                        f"response_len={len(str(result))} chars"
                    )
                    chunk_analyses.append({
                        "chunk_index": i,
                        "start_sec": chunk.start_sec,
                        "duration_sec": chunk.duration_sec,
                        "status": "success",
                        "error": None,
                        "analysis": result,
                    })
            
            successful = [ca for ca in chunk_analyses if ca["status"] == "success"]
            failed = [ca for ca in chunk_analyses if ca["status"] == "failed"]
            logger.info(
                f"MAP phase complete: {len(successful)} succeeded, "
                f"{len(failed)} failed out of {total} chunks"
            )
            
            if not successful:
                raise RuntimeError(
                    f"All {total} MAP chunks failed. "
                    f"Errors: {[ca['error'] for ca in failed]}"
                )
            
            # ── 3. REDUCE ─────────────────────────────────
            return await self._reduce(
                caller,
                reduce_system_prompt,
                reduce_user_prompt,
                chunk_analyses,
                manifest,
            )
        
        finally:
            # We don't cleanup chunks per user request
            logger.info("Skipping chunk cleanup per user request.")
            pass
    
    async def _analyze_single_chunk(
        self,
        caller: Any,
        system_prompt: str,
        user_prompt: str,
        chunk: VideoChunk,
        chunk_label: str = "",
        vision_model: str | None = None,
    ) -> str:
        """Analyze a single video chunk via ZaiCaller.
        
        Reads the chunk file, base64-encodes it, builds ZhipuAI-compatible
        messages with video_url content block, and invokes the caller.
        
        Args:
            caller: ZaiCaller instance.
            system_prompt: System prompt text.
            user_prompt: User prompt text.
            chunk: The VideoChunk to analyze.
            chunk_label: Human-readable label for logging.
        
        Returns:
            Raw text response from GLM.
        """
        logger.info(
            f"_analyze_single_chunk {chunk_label}: "
            f"path={chunk.path}, size={chunk.size_bytes} bytes, "
            f"start={chunk.start_sec}s, duration={chunk.duration_sec}s"
        )
        
        with open(chunk.path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        logger.debug(
            f"_analyze_single_chunk {chunk_label}: "
            f"base64 payload size={len(video_b64)} chars"
        )
        
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": f"data:video/mp4;base64,{video_b64}"
                        },
                    },
                ],
            },
        ]
        
        # ZaiCaller is synchronous — run in thread
        import asyncio
        result = await asyncio.to_thread(caller.invoke_sync, messages, vision_model)
        
        logger.info(
            f"_analyze_single_chunk {chunk_label}: "
            f"response received, length={len(result)} chars"
        )
        return result
    
    async def _reduce(
        self,
        caller: Any,
        reduce_system_prompt: str,
        reduce_user_prompt: str,
        chunk_analyses: list[dict],
        manifest: ChunkManifest,
    ) -> str:
        """Synthesize chunk analyses into a final coherent analysis.
        
        Takes all successful chunk analyses and feeds them as structured
        text to GLM with a dedicated reduce prompt that instructs it to
        merge partial analyses into a single output.
        
        Args:
            caller: ZaiCaller instance.
            reduce_system_prompt: System prompt for the reduce step.
            reduce_user_prompt: User prompt template with {chunk_analyses}
                                and {video_metadata} placeholders.
            chunk_analyses: List of chunk analysis dicts from the MAP phase.
            manifest: The ChunkManifest with source video metadata.
        
        Returns:
            The final synthesized analysis text.
        """
        successful = [ca for ca in chunk_analyses if ca["status"] == "success"]
        failed = [ca for ca in chunk_analyses if ca["status"] == "failed"]
        
        logger.info(
            f"REDUCE phase: synthesizing {len(successful)} chunk analyses "
            f"({len(failed)} failed chunks will be noted). "
            f"Source: {manifest.source_path}, "
            f"duration: {manifest.source_duration_sec:.1f}s"
        )
        
        # Format chunk analyses for the reduce prompt
        formatted_chunks = []
        for ca in chunk_analyses:
            if ca["status"] == "success":
                formatted_chunks.append(
                    f"--- SEGMENT {ca['chunk_index'] + 1} "
                    f"({ca['start_sec']:.1f}s to {ca['start_sec'] + ca['duration_sec']:.1f}s) ---\n"
                    f"{ca['analysis']}"
                )
            else:
                formatted_chunks.append(
                    f"--- SEGMENT {ca['chunk_index'] + 1} "
                    f"({ca['start_sec']:.1f}s to {ca['start_sec'] + ca['duration_sec']:.1f}s) ---\n"
                    f"[ANALYSIS UNAVAILABLE: This segment could not be analyzed. Error: {ca['error']}]"
                )
        
        chunk_analyses_text = "\n\n".join(formatted_chunks)
        logger.debug(f"Chunk analyses text prepared for reduce:\n{chunk_analyses_text}")
        
        video_metadata = (
            f"Total video duration: {manifest.source_duration_sec:.1f} seconds\n"
            f"Total segments: {len(chunk_analyses)}\n"
            f"Successfully analyzed segments: {len(successful)}\n"
            f"Failed segments: {len(failed)}"
        )
        
        # Substitute placeholders in the reduce user prompt
        filled_user_prompt = reduce_user_prompt.replace(
            "{chunk_analyses}", chunk_analyses_text
        ).replace(
            "{video_metadata}", video_metadata
        )
        
        messages = [
            {"role": "system", "content": reduce_system_prompt},
            {"role": "user", "content": filled_user_prompt},
        ]
        
        logger.debug(
            f"REDUCE: sending {len(filled_user_prompt)} chars of assembled input "
            f"to ZaiCaller"
        )
        
        import asyncio
        result = await asyncio.to_thread(caller.invoke_sync, messages)
        
        logger.info(
            f"REDUCE phase complete: final response length={len(result)} chars"
        )
        return result


# ── Factory ──────────────────────────────────────────
_STRATEGY_MAP: dict[str, Any] = {
    "google-genai": lambda: LangChainVideoStrategy("google-genai"),
    "openai":       lambda: LangChainVideoStrategy("openai"),
    "anthropic":    lambda: LangChainVideoStrategy("anthropic"),
    "ollama":       lambda: LangChainVideoStrategy("ollama"),
    "zhipuai":      lambda: GlmMapReduceVideoStrategy(),
}


def get_video_strategy(provider: str) -> VideoMessageStrategy:
    """Resolve the correct video message strategy for a provider."""
    factory = _STRATEGY_MAP.get(provider)
    if not factory:
        raise ValueError(
            f"No video message strategy for provider '{provider}'. "
            f"Supported: {list(_STRATEGY_MAP.keys())}"
        )
    return factory()
