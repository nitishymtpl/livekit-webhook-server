import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException
from livekit.api import WebhookEvent, Room, ParticipantInfo, Codec # type: ignore[import-untyped]


# Mock environment variables before importing the module
@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "test_api_key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test_api_secret")
    # Import the router after env vars are set
    from routes.webhook import router as webhook_router
    global router
    router = webhook_router


# Mock Redis client
@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    client.hset = MagicMock()
    client.hgetall = MagicMock()
    client.set = MagicMock()
    client.get = MagicMock()
    return client

# Mock Request object
@pytest.fixture
def mock_request(mock_redis_client):
    request = AsyncMock()
    request.app = MagicMock()
    request.app.state = MagicMock()
    request.app.state.redis = mock_redis_client
    return request

# Sample Webhook Events
def create_sample_event(event_type, room_sid="RM_testroom", participant_sid="PA_testparticipant", participant_name="Test User"):
    room = Room(
        sid=room_sid,
        name="Test Room",
        empty_timeout=60,
        max_participants=10,
        creation_time=int(time.time()),
        turn_password="turn_password",
        enabled_codecs=[Codec(mime="video/h264", fmtp_line="")],
        metadata="test_metadata",
        num_participants=1,
        active_recording=False,
    )
    participant = None
    if event_type in ["participant_joined", "participant_left"]:
        participant = ParticipantInfo(
            sid=participant_sid,
            identity="test_identity",
            name=participant_name,
            joined_at=int(time.time())
        )

    return WebhookEvent(
        event=event_type,
        room=room,
        participant=participant,
        id="EV_testevent",
        created_at=int(time.time() * 1000) # milliseconds for created_at
    )

# Test for participant_joined event
@pytest.mark.asyncio
async def test_handle_webhook_participant_joined(mock_request, mock_redis_client):
    from routes.webhook import handle_webhook # Import here to use mocked env

    event_time = int(time.time() * 1000)
    event = create_sample_event("participant_joined")
    event.created_at = event_time # Ensure consistent time

    # Mock WebhookReceiver.receive to return our sample event
    with patch("routes.webhook.receiver.receive", return_value=event) as mock_receive:
        mock_request.body = AsyncMock(return_value=b'{"event": "participant_joined"}') # Dummy body
        response = await handle_webhook(mock_request, authorization="test_auth_token")

    mock_receive.assert_called_once_with(b'{"event": "participant_joined"}'.decode("utf-8"), "test_auth_token")
    mock_redis_client.hset.assert_called_once_with(
        f"room:{event.room.sid}:participant:{event.participant.sid}",
        mapping={
            "name": event.participant.name,
            "join_time": event.created_at,
            "status": "joined"
        }
    )
    assert response == {"status": "ok", "event_type": "participant_joined"}

# Test for participant_left event
@pytest.mark.asyncio
async def test_handle_webhook_participant_left(mock_request, mock_redis_client):
    from routes.webhook import handle_webhook

    room_sid = "RM_testroom_left"
    participant_sid = "PA_testparticipant_left"
    join_timestamp = int(time.time() * 1000) - 5000 # Joined 5 seconds ago
    leave_timestamp = int(time.time() * 1000)

    event = create_sample_event("participant_left", room_sid=room_sid, participant_sid=participant_sid)
    event.created_at = leave_timestamp # Set leave time

    # Mock existing data in Redis for the participant
    mock_redis_client.hgetall.return_value = {
        b"name": b"Test User Left",
        b"join_time": str(join_timestamp).encode('utf-8'), # Stored as string
        b"status": b"joined"
    }

    with patch("routes.webhook.receiver.receive", return_value=event) as mock_receive:
        mock_request.body = AsyncMock(return_value=b'{"event": "participant_left"}')
        response = await handle_webhook(mock_request, authorization="test_auth_token_left")

    mock_receive.assert_called_once_with(b'{"event": "participant_left"}'.decode("utf-8"), "test_auth_token_left")
    mock_redis_client.hgetall.assert_called_once_with(f"room:{room_sid}:participant:{participant_sid}")
    expected_duration = (leave_timestamp - join_timestamp)
    mock_redis_client.hset.assert_called_once_with(
        f"room:{room_sid}:participant:{participant_sid}",
        mapping={
            "leave_time": leave_timestamp,
            "duration": expected_duration,
            "status": "left"
        }
    )
    assert response == {"status": "ok", "event_type": "participant_left"}


@pytest.mark.asyncio
async def test_handle_webhook_participant_left_no_join_data(mock_request, mock_redis_client):
    from routes.webhook import handle_webhook

    room_sid = "RM_testroom_no_join"
    participant_sid = "PA_testparticipant_no_join"
    leave_timestamp = int(time.time() * 1000)

    event = create_sample_event("participant_left", room_sid=room_sid, participant_sid=participant_sid)
    event.created_at = leave_timestamp

    # Mock no data in Redis for the participant
    mock_redis_client.hgetall.return_value = {} # Empty dict means no data

    with patch("routes.webhook.receiver.receive", return_value=event) as mock_receive, \
         patch("logging.warning") as mock_logging_warning: # Also mock logging
        mock_request.body = AsyncMock(return_value=b'{"event": "participant_left_no_join"}')
        response = await handle_webhook(mock_request, authorization="test_auth_token_no_join")

    mock_receive.assert_called_once()
    mock_redis_client.hgetall.assert_called_once_with(f"room:{room_sid}:participant:{participant_sid}")
    mock_redis_client.hset.assert_not_called() # Should not attempt to set data if no join info
    mock_logging_warning.assert_any_call(f"Participant {participant_sid} left room {room_sid}, but no join data found.")
    assert response == {"status": "ok", "event_type": "participant_left"}


# Test for room_started and room_finished (existing functionality, good to have coverage)
@pytest.mark.asyncio
async def test_handle_webhook_room_started(mock_request, mock_redis_client):
    from routes.webhook import handle_webhook

    event = create_sample_event("room_started")
    with patch("routes.webhook.receiver.receive", return_value=event) as mock_receive:
        mock_request.body = AsyncMock(return_value=b'{"event": "room_started"}')
        response = await handle_webhook(mock_request, authorization="test_auth_token_rs")

    mock_receive.assert_called_once()
    # Basic check, detailed structure is less critical for this test vs participant events
    mock_redis_client.set.assert_called_once()
    args, kwargs = mock_redis_client.set.call_args
    assert args[0] == f"room:{event.room.sid}"
    assert json.loads(args[1])["status"] == "started"
    assert response == {"status": "ok", "event_type": "room_started"}

@pytest.mark.asyncio
async def test_handle_webhook_room_finished(mock_request, mock_redis_client):
    from routes.webhook import handle_webhook

    room_sid = "RM_testroom_finished"
    event = create_sample_event("room_finished", room_sid=room_sid)

    # Mock existing room data
    mock_redis_client.get.return_value = json.dumps({
        "sid": room_sid, "name": "Test Room Finished", "status": "started"
    }).encode('utf-8')

    with patch("routes.webhook.receiver.receive", return_value=event) as mock_receive:
        mock_request.body = AsyncMock(return_value=b'{"event": "room_finished"}')
        response = await handle_webhook(mock_request, authorization="test_auth_token_rf")

    mock_receive.assert_called_once()
    mock_redis_client.get.assert_called_once_with(f"room:{room_sid}")
    mock_redis_client.set.assert_called_once()
    args, kwargs = mock_redis_client.set.call_args
    assert args[0] == f"room:{room_sid}"
    assert json.loads(args[1])["status"] == "finished"
    assert response == {"status": "ok", "event_type": "room_finished"}

# Test webhook auth failure
@pytest.mark.asyncio
async def test_handle_webhook_auth_failure(mock_request):
    from routes.webhook import handle_webhook

    with patch("routes.webhook.receiver.receive", side_effect=Exception("Invalid signature")) as mock_receive:
        mock_request.body = AsyncMock(return_value=b'{"event": "participant_joined"}')
        with pytest.raises(HTTPException) as exc_info:
            await handle_webhook(mock_request, authorization="invalid_auth_token")

    mock_receive.assert_called_once()
    assert exc_info.value.status_code == 403
    assert "Invalid signature or token" in exc_info.value.detail

@pytest.mark.asyncio
async def test_handle_webhook_missing_auth_header(mock_request):
    from routes.webhook import handle_webhook
    with pytest.raises(HTTPException) as exc_info:
        await handle_webhook(mock_request, authorization=None) # No auth header
    assert exc_info.value.status_code == 401
    assert "Missing Authorization header" in exc_info.value.detail

# Ensure LIVEKIT_API_KEY and LIVEKIT_API_SECRET are checked
def test_webhook_env_vars_missing(monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

    # Patch the original TokenVerifier class in the livekit.api module
    with patch("logging.error") as mock_logging_error, \
         patch("livekit.api.TokenVerifier", return_value=MagicMock()) as mock_livekit_token_verifier:
        import sys
        # Ensure routes.webhook is reloaded to trigger its module-level code under the patch
        if "routes.webhook" in sys.modules:
            del sys.modules["routes.webhook"]
        import routes.webhook

        mock_logging_error.assert_any_call("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in environment for routes/webhook.py")
        # We expect TokenVerifier to be called (or attempted) even if env vars are missing,
        # because the logging check happens before the TokenVerifier instantiation in the original code flow.
        # The critical part is that our mock_livekit_token_verifier prevents the ValueError.
        # Depending on precise execution, it might be called with None, None if os.getenv is used by TokenVerifier *after* our check.
        # The livekit.api.TokenVerifier itself uses os.getenv if api_key/api_secret are not passed,
        # so it would pick up the deleted env vars.
        # The patch ensures it doesn't raise an error.

# To run these tests:
# 1. Ensure pytest and pytest-asyncio are installed: pip install pytest pytest-asyncio
# 2. Navigate to the root directory of the project.
# 3. Run: pytest
#
# Note: livekit.api.WebhookEvent and related classes might need actual instantiation or more detailed mocking
# if their internal attributes are heavily used beyond what's shown in the webhook handler.
# For now, basic MagicMock for event objects passed to `receiver.receive` should suffice.
# The `create_sample_event` helper provides more realistic event objects.
# The `livekit.api` package is marked with `# type: ignore[import-untyped]` due to potential missing type hints.
# If `livekit` sdk is not installed, these tests will fail on import.
# `pip install livekit-api` might be needed in the test environment.
print("Created tests/test_webhook.py")
