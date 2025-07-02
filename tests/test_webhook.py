import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from models import Call, Participant # Your SQLAlchemy models
from livekit.api import WebhookEvent # This is what receiver returns
# No need to import RoomInfo/ParticipantInfo if we set fields on WebhookEvent attributes
from datetime import datetime, timezone
import json
import os # For API keys
from unittest.mock import patch # To mock WebhookReceiver if needed, or parts of it.

# Test LiveKit API Key and Secret are set in conftest.py via environment variables
# LIVEKIT_API_KEY = "test_lk_api_key"
# LIVEKIT_API_SECRET = "test_lk_api_secret"
# These are used by the WebhookReceiver instance in routes.webhook

# Helper to create a mock LiveKit WebhookEvent object
def create_mock_webhook_event(event_name, room_sid, room_name=None, participant_sid=None, participant_identity=None, timestamp_ns=None) -> WebhookEvent:
    if timestamp_ns is None:
        timestamp_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)

    # The WebhookEvent constructor or factory method would be used here.
    # Based on livekit.api.WebhookEvent structure (which is a protobuf message wrapper):
    # We need to populate event.event, event.room, event.participant, event.created_at

    # The local _room and _participant assignments using livekit_models_pb2 were incorrect and removed.
    # We directly populate the attributes of the mock_event object below.

    # Actual WebhookEvent fields might be e.g. event.room, event.participant
    # For simplicity, we'll assume direct attribute assignment works or it takes them in constructor.
    # The livekit.api.WebhookEvent is a class generated from protobuf.
    # It will have attributes like 'event', 'room', 'participant', 'created_at', 'id', etc.

    # Let's try to build it piece by piece, assuming direct attribute setting
    # This might need adjustment based on actual livekit.api.WebhookEvent structure
    # For `livekit.api.WebhookEvent`, it's typically built up from underlying protobuf messages.
    # However, the `WebhookReceiver.receive` method *returns* this object.
    # For mocking, we just need an object that quacks like a WebhookEvent.
    # A simple class or a MagicMock could also work if direct instantiation is too complex.
    # Let's assume direct instantiation for now, which is common for such SDK classes.

    # The WebhookEvent class in livekit.api.webhook is a protobuf message.
    # Instantiate it. Its 'room' and 'participant' attributes are themselves protobuf messages.
    mock_event = WebhookEvent(event=event_name, created_at=timestamp_ns, id='mock_event_id_' + str(timestamp_ns))

    # Populate the room information if room_sid is provided
    if room_sid:
        # mock_event.room is an instance of the RoomInfo (or similar) protobuf message
        mock_event.room.sid = room_sid
        mock_event.room.name = room_name or f"Room for {room_sid}"
        # Add other necessary room fields if your handler uses them

    # Populate the participant information if participant_sid is provided
    if participant_sid:
        # mock_event.participant is an instance of the ParticipantInfo protobuf message
        mock_event.participant.sid = participant_sid
        mock_event.participant.identity = participant_identity or f"Identity for {participant_sid}"
        # Add other necessary participant fields if your handler uses them

    return mock_event


# Fixture for LiveKit Webhook Auth - not strictly needed if we mock receiver.receive
@pytest.fixture
def livekit_webhook_auth_header():
    return "dummy-livekit-auth-token" # Placeholder


def test_webhook_room_started(client: TestClient, db_session: Session, livekit_webhook_auth_header):
    room_sid = "test_room_started_sid"
    room_name = "My Test Room Started"
    event_time = datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc)
    event_ts_ns = int(event_time.timestamp() * 1_000_000_000)

    mock_event_obj = create_mock_webhook_event(
        event_name="room_started",
        room_sid=room_sid,
        room_name=room_name,
        timestamp_ns=event_ts_ns
    )

    # The body sent to the endpoint can be a simple JSON string.
    # The actual parsing is bypassed by mocking receiver.receive.
    event_body_str = json.dumps({"event": "room_started", "room": {"sid": room_sid, "name": room_name}})

    with patch('routes.webhook.receiver.receive', return_value=mock_event_obj) as mock_receive:
        response = client.post("/webhook", content=event_body_str, headers={"Authorization": livekit_webhook_auth_header})

    assert response.status_code == 200
    assert response.json()["event_type"] == "room_started"
    mock_receive.assert_called_once_with(event_body_str, livekit_webhook_auth_header)

    call_record = db_session.query(Call).filter(Call.call_id == room_sid).first() # Corrected this line from previous output, was `assert call_record = ...`
    assert call_record is not None
    assert call_record.room_name == room_name
    assert call_record.call_created_at.replace(tzinfo=timezone.utc) == event_time
    assert call_record.call_finished_at is None

def test_webhook_room_finished(client: TestClient, db_session: Session, livekit_webhook_auth_header):
    room_sid = "test_room_finished_sid"
    initial_create_time = datetime(2023, 10, 27, 11, 0, 0, tzinfo=timezone.utc)

    existing_call = Call(call_id=room_sid, room_name="My Test Room To Finish", call_created_at=initial_create_time)
    db_session.add(existing_call)
    db_session.commit()

    event_time = datetime(2023, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    event_ts_ns = int(event_time.timestamp() * 1_000_000_000)
    mock_event_obj = create_mock_webhook_event(
        event_name="room_finished",
        room_sid=room_sid,
        timestamp_ns=event_ts_ns
    )
    event_body_str = json.dumps({"event": "room_finished", "room": {"sid": room_sid}})

    with patch('routes.webhook.receiver.receive', return_value=mock_event_obj) as mock_receive:
        response = client.post("/webhook", content=event_body_str, headers={"Authorization": livekit_webhook_auth_header})

    assert response.status_code == 200
    assert response.json()["event_type"] == "room_finished"

    call_record = db_session.query(Call).filter(Call.call_id == room_sid).first()
    assert call_record is not None
    assert call_record.call_finished_at.replace(tzinfo=timezone.utc) == event_time

def test_webhook_participant_joined(client: TestClient, db_session: Session, livekit_webhook_auth_header):
    room_sid = "test_room_for_participant_join_sid"
    participant_sid = "test_participant_joined_sid"
    participant_identity = "John Doe"
    call_create_time = datetime(2023, 10, 27, 13, 0, 0, tzinfo=timezone.utc)

    call = Call(call_id=room_sid, room_name="RoomForJoin", call_created_at=call_create_time)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    event_time = datetime(2023, 10, 27, 13, 5, 0, tzinfo=timezone.utc)
    event_ts_ns = int(event_time.timestamp() * 1_000_000_000)
    mock_event_obj = create_mock_webhook_event(
        event_name="participant_joined",
        room_sid=room_sid,
        room_name="RoomForJoin", # good to include if handler might use it
        participant_sid=participant_sid,
        participant_identity=participant_identity,
        timestamp_ns=event_ts_ns
    )
    event_body_str = json.dumps({"event": "participant_joined", "room": {"sid": room_sid}, "participant": {"sid": participant_sid, "identity": participant_identity}})

    with patch('routes.webhook.receiver.receive', return_value=mock_event_obj) as mock_receive:
        response = client.post("/webhook", content=event_body_str, headers={"Authorization": livekit_webhook_auth_header})

    assert response.status_code == 200
    assert response.json()["event_type"] == "participant_joined"

    participant_record = db_session.query(Participant).filter(Participant.participant_id == participant_sid).first()
    assert participant_record is not None
    assert participant_record.participant_name == participant_identity
    assert participant_record.joined_at.replace(tzinfo=timezone.utc) == event_time
    assert participant_record.left_at is None
    assert participant_record.call_db_id == call.id

def test_webhook_participant_left(client: TestClient, db_session: Session, livekit_webhook_auth_header):
    room_sid = "test_room_for_participant_leave_sid"
    participant_sid = "test_participant_left_sid"
    call_create_time = datetime(2023, 10, 27, 14, 0, 0, tzinfo=timezone.utc)
    participant_join_time = datetime(2023, 10, 27, 14, 5, 0, tzinfo=timezone.utc)

    call = Call(call_id=room_sid, room_name="RoomForLeave", call_created_at=call_create_time)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    participant = Participant(participant_id=participant_sid, participant_name="Jane Doe", joined_at=participant_join_time, call_db_id=call.id)
    db_session.add(participant)
    db_session.commit()

    event_time = datetime(2023, 10, 27, 14, 30, 0, tzinfo=timezone.utc)
    event_ts_ns = int(event_time.timestamp() * 1_000_000_000)
    mock_event_obj = create_mock_webhook_event(
        event_name="participant_left",
        room_sid=room_sid,
        participant_sid=participant_sid,
        timestamp_ns=event_ts_ns
    )
    event_body_str = json.dumps({"event": "participant_left", "room": {"sid": room_sid}, "participant": {"sid": participant_sid}})

    with patch('routes.webhook.receiver.receive', return_value=mock_event_obj) as mock_receive:
        response = client.post("/webhook", content=event_body_str, headers={"Authorization": livekit_webhook_auth_header})

    assert response.status_code == 200
    assert response.json()["event_type"] == "participant_left"

    participant_record = db_session.query(Participant).filter(Participant.participant_id == participant_sid).first()
    assert participant_record is not None
    assert participant_record.left_at.replace(tzinfo=timezone.utc) == event_time

def test_webhook_invalid_auth(client: TestClient):
    # This test assumes that if `receiver.receive` is not mocked, it will perform auth.
    # If LIVEKIT_API_KEY and LIVEKIT_API_SECRET are not set or receiver is None, it should fail early.
    # If they are set (as per conftest), then `receive` will try to validate the token.
    # An invalid token should lead to an error.

    # To make this test robust without complex token generation, we can check the case
    # where the Authorization header is missing or malformed, if not already covered.
    # Or, we can explicitly make `receiver.receive` raise an exception.

    with patch('routes.webhook.receiver.receive', side_effect=Exception("Invalid signature")) as mock_receive:
        response = client.post("/webhook", content="{}", headers={"Authorization": "bad-token"})

    # The exception from `receiver.receive` is caught in the webhook handler
    # and turned into an HTTPException. The status code depends on the exception type.
    # Livekit's `WebhookReceiver` raises `WebhookError` which might translate to 401 or 403.
    # Our handler currently raises 500 for general exceptions after receive.
    # For an "Invalid signature" type error from receiver.receive(), it would be 500 based on current handler.
    # Let's refine the handler to return 403 for specific auth errors from receiver if possible.
    # For now, expecting 500 as per the generic catch-all.
    assert response.status_code == 500
    assert "Webhook processing error: Invalid signature" in response.json()["detail"]


def test_webhook_receiver_not_initialized(client: TestClient):
    # Temporarily unset LIVEKIT_API_KEY to simulate receiver not being initialized
    original_key = os.environ.pop("LIVEKIT_API_KEY", None)
    original_secret = os.environ.pop("LIVEKIT_API_SECRET", None)

    import importlib
    import routes.webhook
    # Critical: reload routes.webhook so it sees the changed env vars
    importlib.reload(routes.webhook)

    response = client.post("/webhook", content="{}", headers={"Authorization": "any-token"})
    assert response.status_code == 503 # Service Unavailable
    assert "Webhook receiver not configured" in response.json()["detail"]

    # Restore env vars and reload module again to not affect other tests
    if original_key:
        os.environ["LIVEKIT_API_KEY"] = original_key
    if original_secret:
        os.environ["LIVEKIT_API_SECRET"] = original_secret
    importlib.reload(routes.webhook)
