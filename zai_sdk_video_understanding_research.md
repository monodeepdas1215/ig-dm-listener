# ZAI Python SDK — Video Understanding Research

> **Source**: [zai-org/z-ai-sdk-python](https://github.com/zai-org/z-ai-sdk-python) (official SDK)
> **Package**: `pip install zai-sdk`
> **Models investigated**: `glm-5.1` (text), `glm-5v-turbo` (multimodal/video)

---

## 1. SDK Architecture Overview

From the [_client.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/src/zai/_client.py) source, the `ZaiClient` exposes these API resources:

```python
from zai import ZaiClient

client = ZaiClient(api_key="...", base_url="https://api.z.ai/api/paas/v4/")

# Available resources:
client.chat          # Chat completions (text + multimodal)
client.files         # File upload/management
client.videos        # Video GENERATION (cogvideox-3) ← NOT video understanding
client.images        # Image generation
client.audio         # Audio / TTS
client.embeddings    # Text embeddings
client.agents        # Agent API
client.tools         # Web search etc.
```

> [!IMPORTANT]
> **`client.videos` is for video GENERATION**, not video understanding. Video understanding goes through **`client.chat.completions.create()`** with the `glm-5v-turbo` model.

---

## 2. Video Understanding via Chat Completions

### The `create()` method signature from [completions.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/src/zai/api_resource/chat/completions.py):

```python
class Completions(BaseAPI):
    def create(
        self,
        *,
        model: str,                    # ← "glm-5v-turbo"
        messages: Union[str, List[str], List[int], object, None],  # ← accepts dict/object
        stream: Optional[Literal[False]] | Literal[True] = NOT_GIVEN,
        temperature: Optional[float] = NOT_GIVEN,
        max_tokens: int = NOT_GIVEN,
        tools: Optional[object] = NOT_GIVEN,
        # ... other params
    ) -> Completion:
```

The `messages` parameter accepts `object` — meaning you pass standard OpenAI-format message dicts with multimodal content arrays.

---

## 3. Content Type Reference for GLM-5V-Turbo Messages

Within the `content` array of a message, these `type` values are supported:

| `type` value | Structure | Use Case |
|-------------|-----------|----------|
| `"text"` | `{"type": "text", "text": "..."}` | Text prompt |
| `"image_url"` | `{"type": "image_url", "image_url": {"url": "..."}}` | Image input (URL or base64 data URI) |
| `"video_url"` | `{"type": "video_url", "video_url": {"url": "..."}}` | **Video input** (URL or base64 data URI) |

### Video URL variations:

```python
# Option A: Public URL
{"type": "video_url", "video_url": {"url": "https://example.com/video.mp4"}}

# Option B: Base64 data URI (for local files)
{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AAAAIGZ0eXBpc29t..."}}
```

---

## 4. Concrete Code: Video Understanding with ZAI SDK

### 4a. Using `zai-sdk` directly

```python
import base64
from zai import ZaiClient

client = ZaiClient(
    api_key="your-zai-api-key",
    base_url="https://api.z.ai/api/paas/v4/"  # or https://open.bigmodel.cn/api/paas/v4/
)

# --- Option A: Video from URL ---
response = client.chat.completions.create(
    model="glm-5v-turbo",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Analyze this video and describe what happens"},
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://example.com/reel.mp4"
                }
            }
        ]
    }],
    temperature=0.25,
    max_tokens=4096
)
print(response.choices[0].message.content)


# --- Option B: Local video file as base64 ---
with open("downloaded_reel/video.mp4", "rb") as f:
    video_b64 = base64.b64encode(f.read()).decode("utf-8")

response = client.chat.completions.create(
    model="glm-5v-turbo",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Analyze this video and describe what happens"},
            {
                "type": "video_url",
                "video_url": {
                    "url": f"data:video/mp4;base64,{video_b64}"
                }
            }
        ]
    }],
    temperature=0.25,
    max_tokens=4096
)
print(response.choices[0].message.content)
```

### 4b. Using via raw `curl` (API reference)

```bash
curl -X POST \
    https://api.z.ai/api/paas/v4/chat/completions \
    -H "Authorization: Bearer your-api-key" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "glm-5v-turbo",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": "https://example.com/reel.mp4"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Summarize this video content"
                    }
                ]
            }
        ],
        "thinking": {
            "type": "enabled"
        }
    }'
```

---

## 5. Files API — NOT for Video Understanding

From [files.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/src/zai/api_resource/files/files.py), the `create()` method only supports these `purpose` values:

```python
def create(
    self,
    *,
    file: FileTypes = None,
    purpose: Literal['fine-tune', 'retrieval', 'batch', 'voice-clone-input'],
    # ...
) -> FileObject:
```

> [!WARNING]
> There is **no `'recognize'`** or `'vision'` purpose in the SDK's `files.create()`. The file upload API is for fine-tuning, retrieval, batch processing, and voice cloning — **not** for uploading videos for vision understanding.
>
> This means for video understanding, you **must** use either:
> 1. A publicly accessible video URL
> 2. Base64-encoded video inline as a data URI

---

## 6. Comparison: Gemini vs GLM-5V-Turbo for Your Reel Analysis Pipeline

### Current Gemini approach (in `analyze_reels.py`):

```python
# Gemini uses LangChain's "media" type with base64
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=[
        {"type": "text", "text": user_prompt},
        {
            "type": "media",           # ← Gemini-specific
            "mime_type": "video/mp4",   # ← Gemini-specific
            "data": video_b64           # ← raw base64 string
        }
    ])
]
response = await llm.ainvoke(messages)
```

### Required GLM-5V-Turbo approach (via LangChain + ChatOpenAI):

```python
# GLM uses OpenAI-compatible "video_url" type with data URI
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=[
        {"type": "text", "text": user_prompt},
        {
            "type": "video_url",        # ← GLM format
            "video_url": {              # ← nested object
                "url": f"data:video/mp4;base64,{video_b64}"  # ← data URI format
            }
        }
    ])
]
response = await llm.ainvoke(messages)
```

### Key Differences Table

| Aspect | Gemini (current) | GLM-5V-Turbo |
|--------|-----------------|--------------|
| **Content type** | `"media"` | `"video_url"` |
| **Data format** | Raw base64 string in `"data"` field | Data URI (`data:video/mp4;base64,...`) in nested `"url"` field |
| **Structure** | Flat: `{"type", "mime_type", "data"}` | Nested: `{"type", "video_url": {"url": ...}}` |
| **MIME type** | Explicit `"mime_type"` field | Embedded in data URI prefix |
| **URL support** | Via Google's File API | Direct URL in `"url"` field |
| **LangChain class** | `ChatGoogleGenerativeAI` | `ChatOpenAI` with custom `base_url` |

---

## 7. SDK Examples That Exist (and Don't Exist)

### ✅ Examples in the repo:

| File | What it covers |
|------|---------------|
| [basic_usage.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/examples/basic_usage.py) | Text chat, streaming, web search, MCP |
| [glm_example.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/examples/glm_example.py) | GLM-5.1 with web search streaming |
| [glm_thinking.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/examples/glm_thinking.py) | Deep thinking mode |
| [video_models_examples.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/examples/video_models_examples.py) | Video GENERATION (cogvideox-3) |
| [function_call_example.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/examples/function_call_example.py) | Tool/function calling |

### ❌ Missing from the repo:

- **No video understanding example** (sending video to `glm-5v-turbo` for analysis)
- **No image understanding example** (despite `test_multi_modal.jpeg` being present in examples/)
- No file upload → vision example

> [!NOTE]
> The SDK repository doesn't have a dedicated example for video understanding. The approach documented above (using `video_url` content type in chat completions) is derived from the API documentation and the SDK's passthrough `messages: object` type that accepts any valid OpenAI-format payload.

---

## 8. ZaiClient Initialization

From [_client.py](https://github.com/zai-org/z-ai-sdk-python/blob/main/src/zai/_client.py):

```python
from zai import ZaiClient

# Uses ZAI_API_KEY env var by default
client = ZaiClient()

# Or explicit configuration
client = ZaiClient(
    api_key="your-key",
    base_url="https://api.z.ai/api/paas/v4/",  # overseas
    # base_url="https://open.bigmodel.cn/api/paas/v4/",  # mainland China
    disable_token_cache=True,
)
```

The client reads `ZAI_API_KEY` from the environment by default if `api_key` is not provided.
