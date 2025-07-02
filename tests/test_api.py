import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

# Mock environment variables before importing the module
@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test_internal_api_key")
    # Import the router after env vars are set
    from routes.api import router as api_router
    global router # Make router available globally for tests
    router = api_router


# Mock Redis client
@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    client.keys = MagicMock()
    client.hgetall = MagicMock()
    client.exists = MagicMock()
    return client

# Mock Request object
@pytest.fixture
def mock_request(mock_redis_client):
    request = AsyncMock()
    request.app = MagicMock()
    request.app.state = MagicMock()
    request.app.state.redis = mock_redis_client
    return request


# Test /api/analytics/{room_sid} endpoint
@pytest.mark.asyncio
async def test_get_room_analytics_success(mock_request, mock_redis_client):
    from routes.api import get_room_analytics # Import here to use mocked env

    room_sid = "RM_testanalytics"
    auth_header = f"Bearer test_internal_api_key"

    mock_redis_client.exists.return_value = True # Room exists
    mock_redis_client.keys.return_value = [
        f"room:{room_sid}:participant:PA1".encode('utf-8'),
        f"room:{room_sid}:participant:PA2".encode('utf-8')
    ]
    mock_redis_client.hgetall.side_effect = [
        {
            b"name": b"User1", b"join_time": b"1678886400.0", b"leave_time": b"1678886460.0", b"duration": b"60.0", b"status": b"left"
        },
        {
            b"name": b"User2", b"join_time": b"1678886500.0", b"status": b"joined" # Still in call
        }
    ]

    response = await get_room_analytics(mock_request, room_sid, authorization=auth_header)

    mock_redis_client.exists.assert_called_once_with(f"room:{room_sid}")
    mock_redis_client.keys.assert_called_once_with(f"room:{room_sid}:participant:*")
    assert mock_redis_client.hgetall.call_count == 2
    mock_redis_client.hgetall.assert_any_call(f"room:{room_sid}:participant:PA1")
    mock_redis_client.hgetall.assert_any_call(f"room:{room_sid}:participant:PA2")

    expected_response = {
        "room_sid": room_sid,
        "participants": [
            {"name": "User1", "join_time": 1678886400.0, "leave_time": 1678886460.0, "duration": 60.0, "status": "left"},
            {"name": "User2", "join_time": 1678886500.0, "status": "joined"}
        ]
    }
    assert response == expected_response

@pytest.mark.asyncio
async def test_get_room_analytics_room_not_found(mock_request, mock_redis_client):
    from routes.api import get_room_analytics

    room_sid = "RM_nonexistent"
    auth_header = f"Bearer test_internal_api_key"
    mock_redis_client.exists.return_value = False # Room does not exist

    with pytest.raises(HTTPException) as exc_info:
        await get_room_analytics(mock_request, room_sid, authorization=auth_header)

    assert exc_info.value.status_code == 404
    assert f"Room with SID {room_sid} not found" in exc_info.value.detail
    mock_redis_client.exists.assert_called_once_with(f"room:{room_sid}")
    mock_redis_client.keys.assert_not_called()


@pytest.mark.asyncio
async def test_get_room_analytics_no_participants(mock_request, mock_redis_client):
    from routes.api import get_room_analytics

    room_sid = "RM_emptyroom"
    auth_header = f"Bearer test_internal_api_key"

    mock_redis_client.exists.return_value = True # Room exists
    mock_redis_client.keys.return_value = [] # No participant keys

    response = await get_room_analytics(mock_request, room_sid, authorization=auth_header)

    mock_redis_client.exists.assert_called_once_with(f"room:{room_sid}")
    mock_redis_client.keys.assert_called_once_with(f"room:{room_sid}:participant:*")
    mock_redis_client.hgetall.assert_not_called()
    assert response == {"room_sid": room_sid, "participants": []}


@pytest.mark.asyncio
async def test_get_room_analytics_auth_missing(mock_request):
    from routes.api import get_room_analytics
    with pytest.raises(HTTPException) as exc_info:
        await get_room_analytics(mock_request, "RM_test", authorization=None)
    assert exc_info.value.status_code == 401
    assert "Missing Authorization header" in exc_info.value.detail

@pytest.mark.asyncio
async def test_get_room_analytics_auth_invalid_format(mock_request):
    from routes.api import get_room_analytics
    with pytest.raises(HTTPException) as exc_info:
        await get_room_analytics(mock_request, "RM_test", authorization="InvalidKey")
    assert exc_info.value.status_code == 401
    assert "Invalid token format" in exc_info.value.detail

@pytest.mark.asyncio
async def test_get_room_analytics_auth_wrong_key(mock_request):
    from routes.api import get_room_analytics
    with pytest.raises(HTTPException) as exc_info:
        await get_room_analytics(mock_request, "RM_test", authorization="Bearer wrong_key")
    assert exc_info.value.status_code == 403
    assert "Invalid API key" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_room_analytics_redis_connection_error(mock_request, mock_redis_client):
    from routes.api import get_room_analytics
    room_sid = "RM_redis_error"
    auth_header = f"Bearer test_internal_api_key"

    mock_redis_client.exists.side_effect = Exception("Redis connection failed") # Simulate general Redis error

    with pytest.raises(HTTPException) as exc_info:
        await get_room_analytics(mock_request, room_sid, authorization=auth_header)

    assert exc_info.value.status_code == 500
    # Updated to reflect the actual error message from the specific catch block
    assert f"Error fetching analytics for room {room_sid}" in exc_info.value.detail

# Test for /api/rooms (existing endpoint, good to have basic coverage)
@pytest.mark.asyncio
async def test_get_rooms_success(mock_request, mock_redis_client):
    from routes.api import get_rooms

    auth_header = f"Bearer test_internal_api_key"
    mock_redis_client.keys.return_value = [b"room:RM1", b"room:RM2"]
    mock_redis_client.get.side_effect = [
        json.dumps({"sid": "RM1", "name": "Room 1"}).encode('utf-8'),
        json.dumps({"sid": "RM2", "name": "Room 2"}).encode('utf-8')
    ]

    response = await get_rooms(mock_request, authorization=auth_header)

    mock_redis_client.keys.assert_called_once_with("room:*")
    assert mock_redis_client.get.call_count == 2
    assert response == [{"sid": "RM1", "name": "Room 1"}, {"sid": "RM2", "name": "Room 2"}]

@pytest.mark.asyncio
async def test_get_rooms_auth_missing(mock_request):
    from routes.api import get_rooms
    with pytest.raises(HTTPException) as exc_info:
        await get_rooms(mock_request, authorization=None)
    assert exc_info.value.status_code == 401

# Ensure INTERNAL_API_KEY is checked at module level
def test_api_env_vars_missing(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with patch("logging.error") as mock_logging_error:
        # Need to reload the module to trigger the check
        import sys
        if "routes.api" in sys.modules:
            del sys.modules["routes.api"]
        import routes.api # This will re-evaluate the module-level code
        mock_logging_error.assert_any_call("INTERNAL_API_KEY must be set in environment for routes/api.py")


# To run these tests:
# 1. Ensure pytest and pytest-asyncio are installed: pip install pytest pytest-asyncio
# 2. Navigate to the root directory of the project.
# 3. Run: pytest
#
# These tests mock the Redis client and FastAPI request objects to isolate the logic
# within the API route handlers.
print("Created tests/test_api.py")
