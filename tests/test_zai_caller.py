import pytest
from unittest.mock import patch, MagicMock
from agent_framework.core.zai_caller import ZaiCaller

@pytest.fixture
def mock_zai_client():
    with patch("agent_framework.core.zai_caller.ZaiClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "mocked response content"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        yield mock_client

@pytest.mark.asyncio
async def test_zai_caller_invoke(mock_zai_client):
    caller = ZaiCaller(
        model="glm-4",
        api_key="test-key",
        base_url="https://test.com",
    )
    
    messages = [{"role": "user", "content": "hello"}]
    response = await caller.invoke(messages)
    
    assert response == "mocked response content"
    mock_zai_client.chat.completions.create.assert_called_once_with(
        model="glm-4",
        messages=messages,
        temperature=0.1
    )

@pytest.mark.asyncio
async def test_zai_caller_invoke_list_content(mock_zai_client):
    # Mock GLM returning content as a list of dicts/strings
    mock_zai_client.chat.completions.create.return_value.choices[0].message.content = [
        {"type": "text", "text": "part 1 "},
        "part 2",
        {"type": "image", "url": "ignored"}
    ]
    
    caller = ZaiCaller(model="glm-4", api_key="test", base_url="test")
    response = await caller.invoke([{"role": "user", "content": "hi"}])
    
    assert response == "part 1 \npart 2"

@pytest.mark.asyncio
async def test_zai_caller_model_override(mock_zai_client):
    caller = ZaiCaller(model="glm-4", api_key="test", base_url="test")
    
    await caller.invoke([{"role": "user", "content": "hi"}], model_override="glm-4v")
    
    mock_zai_client.chat.completions.create.assert_called_once()
    args, kwargs = mock_zai_client.chat.completions.create.call_args
    assert kwargs["model"] == "glm-4v"
