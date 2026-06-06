import pytest
import asyncio
from app.services.resilient_caller import (
    is_rate_limit_error,
    is_connection_error,
    is_server_error,
    ResilientCaller,
    RetryConfig,
    RESILIENT_CLASSIFIERS
)
from agent_framework.exceptions import RetryExhaustedError

class MockResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.status = status_code
        self.headers = headers or {}

class MockHTTPError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response

def test_is_rate_limit_error():
    assert is_rate_limit_error(Exception("Rate limit exceeded"))
    assert is_rate_limit_error(Exception("Too many requests"))
    assert is_rate_limit_error(MockHTTPError("error", MockResponse(429)))
    assert not is_rate_limit_error(Exception("Connection reset"))

def test_is_connection_error():
    assert is_connection_error(Exception("connection error"))
    assert is_connection_error(Exception("timed out"))
    class APIConnectionError(Exception): pass
    assert is_connection_error(APIConnectionError())
    assert not is_connection_error(Exception("Rate limit"))

def test_is_server_error():
    assert is_server_error(MockHTTPError("error", MockResponse(500)))
    assert is_server_error(MockHTTPError("error", MockResponse(503)))
    assert is_server_error(Exception("Internal Server Error"))
    assert not is_server_error(MockHTTPError("error", MockResponse(400)))

@pytest.mark.asyncio
async def test_resilient_caller_success():
    caller = ResilientCaller()
    
    async def success_fn():
        return "success"
        
    result = await caller.call(success_fn)
    assert result == "success"

@pytest.mark.asyncio
async def test_resilient_caller_retry_429():
    caller = ResilientCaller(RetryConfig(max_retries=2, base_delay=0.01))
    
    attempts = 0
    async def fail_then_succeed():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise MockHTTPError("Too many requests", MockResponse(429))
        return "success"
        
    result = await caller.call(fail_then_succeed)
    assert result == "success"
    assert attempts == 2

@pytest.mark.asyncio
async def test_resilient_caller_exhausted():
    caller = ResilientCaller(RetryConfig(max_retries=1, base_delay=0.01))
    
    async def always_fail():
        raise MockHTTPError("Too many requests", MockResponse(429))
        
    with pytest.raises(RetryExhaustedError):
        await caller.call(always_fail)

@pytest.mark.asyncio
async def test_resilient_caller_non_retryable():
    caller = ResilientCaller(RetryConfig(max_retries=2, base_delay=0.01))
    
    async def bad_request():
        raise MockHTTPError("Bad Request", MockResponse(400))
        
    # Default config only retries 429
    with pytest.raises(MockHTTPError):
        await caller.call(bad_request)

@pytest.mark.asyncio
async def test_resilient_caller_resilient_classifiers():
    caller = ResilientCaller(RetryConfig(
        max_retries=2, 
        base_delay=0.01,
        retryable_classifiers=RESILIENT_CLASSIFIERS
    ))
    
    attempts = 0
    async def connection_error_fn():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise Exception("connection error")
        return "success"
        
    result = await caller.call(connection_error_fn)
    assert result == "success"
    assert attempts == 2
