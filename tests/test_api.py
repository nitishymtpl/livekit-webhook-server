import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from models import Call, Participant # Ensure your models are importable
from datetime import datetime, timezone, timedelta, date # Added date

# Test API Key is set in conftest.py via environment variable
# INTERNAL_API_KEY = "test_internal_api_key_12345"
# No longer needed here as conftest handles it.

def test_get_call_analytics_success(client: TestClient, db_session: Session, sample_call_data, sample_participant_data_1, sample_participant_data_2, test_api_key: str):
    # 1. Populate the database with test data
    call = Call(**sample_call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    participant1_data = sample_participant_data_1.copy()
    participant1_data["call_db_id"] = call.id
    participant1 = Participant(**participant1_data)
    db_session.add(participant1)

    participant2_data = sample_participant_data_2.copy()
    participant2_data["call_db_id"] = call.id
    participant2 = Participant(**participant2_data)
    db_session.add(participant2)

    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}

    # 2. Make the API request
    response = client.get(f"/api/calls/{sample_call_data['call_id']}/analytics", headers=headers)

    # 3. Assert the response
    assert response.status_code == 200
    data = response.json()

    assert data["call_id"] == sample_call_data["call_id"]
    assert data["room_name"] == sample_call_data["room_name"]
    assert datetime.fromisoformat(data["call_created_at"]) == sample_call_data["call_created_at"]
    assert datetime.fromisoformat(data["call_finished_at"]) == sample_call_data["call_finished_at"]

    expected_overall_duration = int((sample_call_data["call_finished_at"] - sample_call_data["call_created_at"]).total_seconds())
    assert data["overall_call_duration_seconds"] == expected_overall_duration

    assert len(data["participants"]) == 2

    p1_analytics = next(p for p in data["participants"] if p["participant_id"] == sample_participant_data_1["participant_id"])
    assert p1_analytics["participant_name"] == sample_participant_data_1["participant_name"]
    assert datetime.fromisoformat(p1_analytics["joined_at"]) == sample_participant_data_1["joined_at"]
    assert datetime.fromisoformat(p1_analytics["left_at"]) == sample_participant_data_1["left_at"]
    expected_p1_duration = int((sample_participant_data_1["left_at"] - sample_participant_data_1["joined_at"]).total_seconds())
    assert p1_analytics["duration_in_call_seconds"] == expected_p1_duration

    p2_analytics = next(p for p in data["participants"] if p["participant_id"] == sample_participant_data_2["participant_id"])
    assert p2_analytics["participant_name"] == sample_participant_data_2["participant_name"]
    assert datetime.fromisoformat(p2_analytics["joined_at"]) == sample_participant_data_2["joined_at"]
    assert p2_analytics["left_at"] is None # Bob did not explicitly leave

    # For Bob, duration should be calculated until call_finished_at
    expected_p2_duration = int((sample_call_data["call_finished_at"] - sample_participant_data_2["joined_at"]).total_seconds())
    assert p2_analytics["duration_in_call_seconds"] == expected_p2_duration


def test_get_call_analytics_call_not_found(client: TestClient, test_api_key: str):
    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/calls/non_existent_call_id/analytics", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Call not found"

def test_get_call_analytics_no_auth_header(client: TestClient):
    response = client.get("/api/calls/some_call_id/analytics")
    assert response.status_code == 401
    assert "Missing Authorization header" in response.json()["detail"]


def test_get_call_analytics_invalid_token_format(client: TestClient):
    headers = {"Authorization": "InvalidToken"}
    response = client.get("/api/calls/some_call_id/analytics", headers=headers)
    assert response.status_code == 401
    assert "Invalid token format" in response.json()["detail"]

def test_get_call_analytics_wrong_api_key(client: TestClient):
    headers = {"Authorization": "Bearer wrong_key"}
    response = client.get("/api/calls/some_call_id/analytics", headers=headers)
    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]

def test_get_call_analytics_participant_left_at_null_call_not_finished(client: TestClient, db_session: Session, test_api_key: str):
    call_data = {
        "call_id": "active_call_sid",
        "room_name": "Active Room",
        "call_created_at": datetime(2023, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        "call_finished_at": None,
    }
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    participant_data = {
        "participant_id": "active_participant_sid",
        "participant_name": "Carol",
        "joined_at": datetime(2023, 1, 2, 10, 0, 5, tzinfo=timezone.utc),
        "left_at": None,
        "call_db_id": call.id
    }
    participant = Participant(**participant_data)
    db_session.add(participant)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call_data['call_id']}/analytics", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["call_finished_at"] is None
    assert data["overall_call_duration_seconds"] is None

    p_analytics = data["participants"][0]
    assert p_analytics["participant_id"] == participant_data["participant_id"]
    assert p_analytics["left_at"] is None
    assert p_analytics["duration_in_call_seconds"] is None

def test_get_call_analytics_no_participants(client: TestClient, db_session: Session, test_api_key: str):
    call_data = {
        "call_id": "empty_call_sid",
        "room_name": "Empty Room",
        "call_created_at": datetime(2023, 1, 3, 10, 0, 0, tzinfo=timezone.utc),
        "call_finished_at": datetime(2023, 1, 3, 10, 5, 0, tzinfo=timezone.utc),
    }
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call_data['call_id']}/analytics", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["call_id"] == call_data["call_id"]
    assert len(data["participants"]) == 0
    expected_duration = int((call_data["call_finished_at"] - call_data["call_created_at"]).total_seconds())
    assert data["overall_call_duration_seconds"] == expected_duration


# Tests for GET /api/calls
def test_list_calls_success(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call1_data = sample_call_data.copy()
    call1 = Call(**call1_data)
    db_session.add(call1)

    call2_data = sample_call_data.copy()
    call2_data["call_id"] = "test_call_sid_2"
    call2_data["room_name"] = "Test Room 2"
    call2_data["call_created_at"] = datetime(2023, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    call2_data["call_finished_at"] = datetime(2023, 1, 2, 11, 0, 0, tzinfo=timezone.utc)
    call2 = Call(**call2_data)
    db_session.add(call2)
    db_session.commit()
    db_session.refresh(call1)

    p_data = {
        "participant_id": "p_list_1", "participant_name": "P List",
        "joined_at": call1_data["call_created_at"] + timedelta(seconds=5),
        "call_db_id": call1.id
    }
    db_session.add(Participant(**p_data))
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/calls?limit=5", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["limit"] == 5
    assert data["skip"] == 0

    item1 = next(i for i in data["items"] if i["call_id"] == call2_data["call_id"])
    item2 = next(i for i in data["items"] if i["call_id"] == call1_data["call_id"])

    assert item1["room_name"] == call2_data["room_name"]
    assert item1["participant_count"] == 0
    assert item1["overall_call_duration_seconds"] == 3600

    assert item2["room_name"] == call1_data["room_name"]
    assert item2["participant_count"] == 1
    assert item2["overall_call_duration_seconds"] == 3600

def test_list_calls_pagination(client: TestClient, db_session: Session, test_api_key: str):
    for i in range(3):
        call_data = {
            "call_id": f"page_call_{i+1}",
            "room_name": f"Page Room {i+1}",
            "call_created_at": datetime(2023, 1, 1+i, 10, 0, 0, tzinfo=timezone.utc),
            "call_finished_at": datetime(2023, 1, 1+i, 11, 0, 0, tzinfo=timezone.utc)
        }
        db_session.add(Call(**call_data))
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}

    response1 = client.get("/api/calls?skip=0&limit=2", headers=headers)
    data1 = response1.json()
    assert response1.status_code == 200
    assert data1["total"] == 3
    assert len(data1["items"]) == 2
    assert data1["items"][0]["call_id"] == "page_call_3"
    assert data1["items"][1]["call_id"] == "page_call_2"

    response2 = client.get("/api/calls?skip=2&limit=2", headers=headers)
    data2 = response2.json()
    assert response2.status_code == 200
    assert data2["total"] == 3
    assert len(data2["items"]) == 1
    assert data2["items"][0]["call_id"] == "page_call_1"

def test_list_calls_date_filtering(client: TestClient, db_session: Session, test_api_key: str):
    db_session.add(Call(call_id="date_call_1", room_name="Date Room 1", call_created_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)))
    db_session.add(Call(call_id="date_call_2", room_name="Date Room 2", call_created_at=datetime(2023, 1, 15, 12, 0, 0, tzinfo=timezone.utc)))
    db_session.add(Call(call_id="date_call_3", room_name="Date Room 3", call_created_at=datetime(2023, 2, 1, 12, 0, 0, tzinfo=timezone.utc)))
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}

    response_start = client.get("/api/calls?start_date=2023-01-15", headers=headers)
    data_start = response_start.json()
    assert response_start.status_code == 200
    assert data_start["total"] == 2
    assert {item["call_id"] for item in data_start["items"]} == {"date_call_2", "date_call_3"}

    response_end = client.get("/api/calls?end_date=2023-01-15", headers=headers)
    data_end = response_end.json()
    assert response_end.status_code == 200
    assert data_end["total"] == 2
    assert {item["call_id"] for item in data_end["items"]} == {"date_call_1", "date_call_2"}

    response_both = client.get("/api/calls?start_date=2023-01-01&end_date=2023-01-31", headers=headers)
    data_both = response_both.json()
    assert response_both.status_code == 200
    assert data_both["total"] == 2
    assert {item["call_id"] for item in data_both["items"]} == {"date_call_1", "date_call_2"}

    response_none = client.get("/api/calls?start_date=2024-01-01", headers=headers)
    data_none = response_none.json()
    assert response_none.status_code == 200
    assert data_none["total"] == 0
    assert len(data_none["items"]) == 0

def test_list_calls_empty(client: TestClient, test_api_key: str):
    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/calls", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0
    assert data["limit"] == 10
    assert data["skip"] == 0

# Tests for GET /api/calls/{call_id}/summary
def test_get_call_summary_success(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    p1_data = {"participant_id": "p_summary_1", "participant_name": "P Sum1", "joined_at": call_data["call_created_at"], "call_db_id": call.id}
    db_session.add(Participant(**p1_data))
    p2_data = {"participant_id": "p_summary_2", "participant_name": "P Sum2", "joined_at": call_data["call_created_at"], "call_db_id": call.id}
    db_session.add(Participant(**p2_data))
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call_data['call_id']}/summary", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["call_id"] == call_data["call_id"]
    assert data["room_name"] == call_data["room_name"]
    assert datetime.fromisoformat(data["call_created_at"]) == call_data["call_created_at"]
    assert datetime.fromisoformat(data["call_finished_at"]) == call_data["call_finished_at"]
    expected_duration = int((call_data["call_finished_at"] - call_data["call_created_at"]).total_seconds())
    assert data["overall_call_duration_seconds"] == expected_duration
    assert data["participant_count"] == 2

def test_get_call_summary_no_participants(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call_data["call_id"] = "summary_no_participants_call"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call_data['call_id']}/summary", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["call_id"] == call_data["call_id"]
    assert data["participant_count"] == 0

def test_get_call_summary_not_found(client: TestClient, test_api_key: str):
    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/calls/non_existent_call_id/summary", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Call not found"

# Tests for GET /api/calls/{call_id}/participants
def test_list_call_participants_success(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call_data["call_id"] = "call_with_participants"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    p1_join = call_data["call_created_at"] + timedelta(seconds=10)
    p1_left = call_data["call_created_at"] + timedelta(minutes=10)
    p1 = Participant(participant_id="cp_1", participant_name="CP One", joined_at=p1_join, left_at=p1_left, call_db_id=call.id)
    db_session.add(p1)

    p2_join = call_data["call_created_at"] + timedelta(seconds=20)
    p2 = Participant(participant_id="cp_2", participant_name="CP Two", joined_at=p2_join, call_db_id=call.id)
    db_session.add(p2)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call.call_id}/participants?limit=5", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["limit"] == 5
    assert data["skip"] == 0

    item1_data = next(item for item in data["items"] if item["participant_id"] == "cp_1")
    assert datetime.fromisoformat(item1_data["joined_at"]) == p1_join
    assert datetime.fromisoformat(item1_data["left_at"]) == p1_left
    assert item1_data["duration_in_call_seconds"] == int((p1_left - p1_join).total_seconds())

    item2_data = next(item for item in data["items"] if item["participant_id"] == "cp_2")
    assert datetime.fromisoformat(item2_data["joined_at"]) == p2_join
    assert item2_data["left_at"] is None
    expected_p2_duration = int((call_data["call_finished_at"] - p2_join).total_seconds())
    assert item2_data["duration_in_call_seconds"] == expected_p2_duration

def test_list_call_participants_pagination(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call_data["call_id"] = "call_participants_pagination"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    for i in range(3):
        p_join = call_data["call_created_at"] + timedelta(seconds=i*10)
        p = Participant(participant_id=f"cpp_{i+1}", participant_name=f"CPP {i+1}", joined_at=p_join, call_db_id=call.id)
        db_session.add(p)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}

    response1 = client.get(f"/api/calls/{call.call_id}/participants?skip=0&limit=2", headers=headers)
    data1 = response1.json()
    assert response1.status_code == 200
    assert data1["total"] == 3
    assert len(data1["items"]) == 2
    assert data1["items"][0]["participant_id"] == "cpp_1"
    assert data1["items"][1]["participant_id"] == "cpp_2"

    response2 = client.get(f"/api/calls/{call.call_id}/participants?skip=2&limit=2", headers=headers)
    data2 = response2.json()
    assert response2.status_code == 200
    assert data2["total"] == 3
    assert len(data2["items"]) == 1
    assert data2["items"][0]["participant_id"] == "cpp_3"

def test_list_call_participants_call_not_found(client: TestClient, test_api_key: str):
    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/calls/non_existent_call_id/participants", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Call not found"

def test_list_call_participants_no_participants(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call_data["call_id"] = "call_no_participants_for_list"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call.call_id}/participants", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0

# Tests for GET /api/calls/{call_id}/participants/{participant_id}
def test_get_call_participant_details_success(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call_data["call_id"] = "call_for_specific_participant"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    p_join = call_data["call_created_at"] + timedelta(minutes=1)
    p_left = call_data["call_created_at"] + timedelta(minutes=30)
    participant_data = {
        "participant_id": "csp_1",
        "participant_name": "CSP One",
        "joined_at": p_join,
        "left_at": p_left,
        "call_db_id": call.id
    }
    participant = Participant(**participant_data)
    db_session.add(participant)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call.call_id}/participants/{participant.participant_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["participant_id"] == participant.participant_id
    assert data["participant_name"] == participant.participant_name
    assert datetime.fromisoformat(data["joined_at"]) == p_join
    assert datetime.fromisoformat(data["left_at"]) == p_left
    expected_duration = int((p_left - p_join).total_seconds())
    assert data["duration_in_call_seconds"] == expected_duration

def test_get_call_participant_details_participant_not_in_call(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    call_data = sample_call_data.copy()
    call_data["call_id"] = "call_for_missing_participant"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call.call_id}/participants/non_existent_participant_sid", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Participant not found in this call"

def test_get_call_participant_details_call_not_found(client: TestClient, test_api_key: str):
    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/calls/non_existent_call_id/participants/any_participant_sid", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Call not found"

def test_get_call_participant_details_active_participant(client: TestClient, db_session: Session, test_api_key: str, sample_call_data):
    # sample_call_data has call_finished_at, so this participant's duration will be capped by it
    call_data = sample_call_data.copy()
    call_data["call_id"] = "call_for_active_specific_participant"
    call = Call(**call_data)
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)

    p_join = call_data["call_created_at"] + timedelta(minutes=5)
    # Participant is still in the call (left_at is None)
    participant_data = {
        "participant_id": "csp_active_1",
        "participant_name": "CSP Active One",
        "joined_at": p_join,
        "left_at": None,
        "call_db_id": call.id
    }
    participant = Participant(**participant_data)
    db_session.add(participant)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/calls/{call.call_id}/participants/{participant.participant_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["participant_id"] == participant.participant_id
    assert data["left_at"] is None
    # Duration should be calculated until call_finished_at
    expected_duration = int((call_data["call_finished_at"] - p_join).total_seconds())
    assert data["duration_in_call_seconds"] == expected_duration

# Tests for GET /api/stats
def test_get_aggregate_stats_success(client: TestClient, db_session: Session, test_api_key: str):
    # Call 1: Today
    today = date.today()
    call1_created = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
    call1_finished = call1_created + timedelta(minutes=30) # 30 min duration
    call1 = Call(call_id="stats_call_1", room_name="Stats Room 1", call_created_at=call1_created, call_finished_at=call1_finished)
    db_session.add(call1)
    db_session.commit()
    db_session.refresh(call1)
    # Add 2 participants to call1
    db_session.add(Participant(participant_id="stat_p1_c1", call_db_id=call1.id, joined_at=call1_created))
    db_session.add(Participant(participant_id="stat_p2_c1", call_db_id=call1.id, joined_at=call1_created))

    # Call 2: Today
    call2_created = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
    call2_finished = call2_created + timedelta(hours=1) # 1 hour duration
    call2 = Call(call_id="stats_call_2", room_name="Stats Room 2", call_created_at=call2_created, call_finished_at=call2_finished)
    db_session.add(call2)
    db_session.commit()
    db_session.refresh(call2)
    # Add 1 participant to call2
    db_session.add(Participant(participant_id="stat_p1_c2", call_db_id=call2.id, joined_at=call2_created))

    # Call 3: Yesterday (should not be included if target_date is today)
    yesterday = today - timedelta(days=1)
    call3_created = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
    call3 = Call(call_id="stats_call_3_yesterday", room_name="Stats Room 3", call_created_at=call3_created, call_finished_at=call3_created + timedelta(minutes=15))
    db_session.add(call3)
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/stats?target_date={today.isoformat()}", headers=headers)

    assert response.status_code == 200
    data = response.json()

    expected_period_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    expected_period_end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

    assert datetime.fromisoformat(data["period_start"]) == expected_period_start
    assert datetime.fromisoformat(data["period_end"]) == expected_period_end
    assert data["total_calls"] == 2
    assert data["total_duration_seconds"] == (30 * 60) + (60 * 60) # 1800 + 3600 = 5400
    assert data["total_participants"] == 3 # 2 from call1, 1 from call2
    assert data["average_duration_seconds"] == 5400 / 2
    assert data["average_participants_per_call"] == 3 / 2

def test_get_aggregate_stats_no_calls_on_date(client: TestClient, db_session: Session, test_api_key: str):
    # Add a call for a different date
    yesterday = date.today() - timedelta(days=1)
    call_created = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
    db_session.add(Call(call_id="some_other_call", room_name="Other Room", call_created_at=call_created, call_finished_at=call_created + timedelta(minutes=10)))
    db_session.commit()

    today = date.today()
    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get(f"/api/stats?target_date={today.isoformat()}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    expected_period_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    expected_period_end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

    assert datetime.fromisoformat(data["period_start"]) == expected_period_start
    assert datetime.fromisoformat(data["period_end"]) == expected_period_end
    assert data["total_calls"] == 0
    assert data["total_duration_seconds"] == 0
    assert data["total_participants"] == 0
    assert data["average_duration_seconds"] == 0
    assert data["average_participants_per_call"] == 0

def test_get_aggregate_stats_default_to_today(client: TestClient, db_session: Session, test_api_key: str):
    # Add one call for today
    today = date.today()
    call_created = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
    call_finished = call_created + timedelta(minutes=60)
    c = Call(call_id="default_today_call", room_name="Default Today", call_created_at=call_created, call_finished_at=call_finished)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    db_session.add(Participant(participant_id="p_def", call_db_id=c.id, joined_at=call_created))
    db_session.commit()

    headers = {"Authorization": f"Bearer {test_api_key}"}
    response = client.get("/api/stats", headers=headers) # No target_date, should default to today

    assert response.status_code == 200
    data = response.json()

    assert data["total_calls"] == 1
    assert data["total_duration_seconds"] == 3600
    assert data["total_participants"] == 1
    assert data["average_duration_seconds"] == 3600
    assert data["average_participants_per_call"] == 1
    # Check if period_start and period_end correspond to today
    assert datetime.fromisoformat(data["period_start"]).date() == today
    assert datetime.fromisoformat(data["period_end"]).date() == today
