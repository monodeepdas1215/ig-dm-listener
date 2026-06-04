# Video Understanding via `langchain-openai` ChatOpenAI + ZAI GLM-5V-Turbo

> Evidence-based research from actual LangChain source code

---

## TL;DR — Does it work?

**Yes — `video_url` content blocks pass through `ChatOpenAI` untouched** to the underlying ZAI API. This is because LangChain's message formatter has a **catch-all passthrough** for any content block type it doesn't explicitly handle.

---

## Evidence 1: The `_format_message_content()` passthrough

**Source**: [langchain_openai/chat_models/base.py](https://github.com/langchain-ai/langchain/blob/master/libs/partners/openai/langchain_openai/chat_models/base.py) — lines 293-351

```python
def _format_message_content(
    content: Any,
    api: Literal["chat/completions", "responses"] = "chat/completions",
    role: str | None = None,
) -> Any:
    """Format message content."""
    if content and isinstance(content, list):
        formatted_content = []
        for block in content:
            # ① Skip these known types (strip them out)
            if (
                isinstance(block, dict)
                and "type" in block
                and (
                    block["type"] in ("tool_use", "thinking", "reasoning_content")
                    or (
                        block["type"] in ("function_call", "code_interpreter_call")
                        and api == "chat/completions"
                    )
                )
            ):
                continue  # ← SKIPPED

            # ② Convert standard data blocks (image_url, input_audio, file)
            if (
                isinstance(block, dict)
                and is_data_content_block(block)
                ...
            ):
                formatted_content.append(convert_to_openai_data_block(block, api=api))

            # ③ Convert Anthropic-style image blocks
            elif (
                isinstance(block, dict)
                and block.get("type") == "image"
                and (source := block.get("source"))
                ...
            ):
                # converts to image_url format
                ...

            # ④ ★ CATCH-ALL: Everything else passes through AS-IS ★
            else:
                formatted_content.append(block)  # ← LINE 347
```

> [!IMPORTANT]
> **Line 347 is the key evidence.** Any block with a `type` value not in the explicit skip/convert list (steps ①②③) falls through to the `else` branch and is appended to `formatted_content` **unchanged**. Since `"video_url"` is not `"tool_use"`, `"thinking"`, `"image"`, etc., it passes through directly.

### What gets stripped (step ①):
- `"tool_use"`, `"thinking"`, `"reasoning_content"`, `"function_call"`, `"code_interpreter_call"`

### What gets converted (steps ②③):
- `"image_url"` (OpenAI standard data block) → passes through as-is
- `"input_audio"` (OpenAI standard data block) → passes through as-is
- `"file"` (OpenAI standard data block) → passes through as-is
- `"image"` (Anthropic format) → converted to `"image_url"` format

### What passes through untouched (step ④):
- **`"video_url"` ✅** — falls to the `else` catch-all
- **`"text"` ✅** — falls to the `else` catch-all
- Any other unknown type → falls to the `else` catch-all

---

## Evidence 2: `is_data_content_block` does NOT match `video_url`

**Source**: [langchain_core/language_models/_utils.py](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/_utils.py) — `is_openai_data_block()`

```python
def is_openai_data_block(
    block: dict, filter_: Literal["image", "audio", "file"] | None = None
) -> bool:
    """Check whether a block contains multimodal data in OpenAI format."""
    
    if block.get("type") == "image_url":    # ← Only matches image_url
        ...
    elif block.get("type") == "input_audio": # ← Only matches input_audio
        ...
    elif block.get("type") == "file":        # ← Only matches file
        ...
    else:
        return False                          # ← video_url → returns False
```

**`video_url` is NOT recognized as an OpenAI data block**, so `is_data_content_block()` returns `False` for it. This means step ② in `_format_message_content()` is skipped, and the block falls through to step ④ (the passthrough).

---

## Evidence 3: `convert_to_openai_data_block` only handles image/file/audio

**Source**: [langchain_core/messages/block_translators/openai.py](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/messages/block_translators/openai.py) — lines 66-160

```python
def convert_to_openai_data_block(block, api="chat/completions"):
    if block["type"] == "image":     # handles image → image_url
        ...
    elif block["type"] == "file":    # handles file → file object  
        ...
    elif block["type"] == "audio":   # handles audio → input_audio
        ...
    else:
        raise ValueError(f"Block of type {block['type']} is not supported.")
```

**No video handler exists.** But this function is never called for `video_url` blocks (because `is_data_content_block` returns `False` first), so no error is raised.

---

## Evidence 4: `_convert_message_to_dict` wraps content via `_format_message_content`

**Source**: [base.py](https://github.com/langchain-ai/langchain/blob/master/libs/partners/openai/langchain_openai/chat_models/base.py) — lines 354-361

```python
def _convert_message_to_dict(message, api="chat/completions"):
    message_dict = {
        "content": _format_message_content(message.content, api=api, role=message.type)
        # ↑ This is where the content goes through _format_message_content
    }
    ...
    if isinstance(message, HumanMessage):
        message_dict["role"] = "user"
    ...
    return message_dict
```

The final dict sent to the OpenAI SDK is just `{"role": "user", "content": [...]}` with whatever `_format_message_content` returned. Since `video_url` passes through, the API request body will contain it verbatim.

---

## Concrete Code: Video Understanding with `langchain-openai`

### Working approach — `video_url` with URL:

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Initialize ChatOpenAI pointing to ZAI
llm = ChatOpenAI(
    model="glm-5v-turbo",
    api_key="your-zai-api-key",
    base_url="https://api.z.ai/api/paas/v4",  # or https://open.bigmodel.cn/api/paas/v4
    temperature=0.25,
)

# Send video via URL
messages = [
    SystemMessage(content="You are a video analyst."),
    HumanMessage(content=[
        {"type": "text", "text": "Describe what happens in this video"},
        {
            "type": "video_url",           # ← passes through untouched
            "video_url": {
                "url": "https://example.com/reel.mp4"
            }
        }
    ])
]

response = await llm.ainvoke(messages)
print(response.content)
```

### Working approach — `video_url` with base64 data URI (for local files):

```python
import base64
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

llm = ChatOpenAI(
    model="glm-5v-turbo",
    api_key="your-zai-api-key",
    base_url="https://api.z.ai/api/paas/v4",
    temperature=0.25,
)

# Read local video file
with open("downloaded_reel/video.mp4", "rb") as f:
    video_b64 = base64.b64encode(f.read()).decode("utf-8")

messages = [
    SystemMessage(content="You are a video analyst."),
    HumanMessage(content=[
        {"type": "text", "text": "Describe what happens in this video"},
        {
            "type": "video_url",           # ← passes through untouched
            "video_url": {
                "url": f"data:video/mp4;base64,{video_b64}"  # data URI format
            }
        }
    ])
]

response = await llm.ainvoke(messages)
print(response.content)
```

---

## ⚠️ What does NOT work: the current Gemini `media` type

Your current `analyze_reels.py` uses this format for Gemini:

```python
# ❌ This format would FAIL with ChatOpenAI + GLM-5V-Turbo
HumanMessage(content=[
    {"type": "text", "text": user_prompt},
    {
        "type": "media",              # ← "media" is NOT stripped, NOT converted
        "mime_type": "video/mp4",     #    It passes through to the API...
        "data": video_b64             #    ...but ZAI doesn't recognize this format
    }
])
```

**Why it fails:** The `"media"` type passes through the `else` catch-all just like `"video_url"`, BUT the ZAI API doesn't recognize `{"type": "media", ...}` as a valid content block. It's a Gemini-specific format that `ChatGoogleGenerativeAI` understands but no OpenAI-compatible API does.

---

## Summary: The Content Block Pipeline

```
Your code                    LangChain                        ZAI API
─────────                    ────────                         ───────
HumanMessage(content=[       _format_message_content()        POST /chat/completions
  {"type": "text", ...},     ├─ "text" → pass through ✅     {"messages": [{
  {"type": "video_url",      ├─ "video_url" → not in          "role": "user",
    "video_url": {           │    skip list, not a data        "content": [
      "url": "..."           │    block → pass through ✅       {"type": "text",...},
    }                        └─ result: unchanged array         {"type": "video_url",
  }                                                              "video_url":{"url":"..."}}
])                                                             ]
                                                              }]}
```

### Key decision table for your refactor:

| Provider | LangChain Class | Video Content Type | Data Format |
|----------|----------------|-------------------|-------------|
| **Gemini** | `ChatGoogleGenerativeAI` | `"media"` | `{"mime_type": "video/mp4", "data": "<raw_b64>"}` |
| **ZAI GLM-5V-Turbo** | `ChatOpenAI` (custom base_url) | `"video_url"` | `{"video_url": {"url": "data:video/mp4;base64,<b64>"}}` |

> [!NOTE]
> Both approaches use base64-encoded video, but the **envelope format** is completely different. Gemini expects a flat `media` block with separate `mime_type` and `data` fields. ZAI expects a nested `video_url` block with a data URI string.
