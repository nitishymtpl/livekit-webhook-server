import logging
import json
import os
from fastapi import APIRouter, Request, HTTPException, Header, Depends, Path
from sqlalchemy.orm import Session
from models import get_db, Call, Participant
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter()

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

if not INTERNAL_API_KEY:
    logging.error("INTERNAL_API_KEY must be set in environment for routes/api.py. Analytics endpoint will be unavailable.")

# Pydantic models for response structure
class ParticipantAnalytics(BaseModel):
    participant_id: str
    participant_name: str
    joined_at: datetime
    left_at: Optional[datetime]
    duration_in_call_seconds: Optional[int]

class CallAnalyticsResponse(BaseModel):
    call_id: str
    room_name: str
    call_created_at: datetime
    call_finished_at: Optional[datetime]
    overall_call_duration_seconds: Optional[int]
    participants: List[ParticipantAnalytics]
    transcript: Optional[str] = None
    recording_url: Optional[str] = None

# Models for new endpoints
class CallSummary(BaseModel):
    call_id: str
    room_name: str
    call_created_at: datetime
    call_finished_at: Optional[datetime]
    overall_call_duration_seconds: Optional[int]
    participant_count: int
    transcript: Optional[str] = None
    recording_url: Optional[str] = None

class PaginatedCallSummaryResponse(BaseModel):
    items: List[CallSummary]
    total: int
    limit: int
    skip: int

class ParticipantSummary(BaseModel):
    participant_id: str
    participant_name: str
    joined_at: datetime
    left_at: Optional[datetime]
    duration_in_call_seconds: Optional[int]

class PaginatedParticipantSummaryResponse(BaseModel):
    items: List[ParticipantSummary]
    total: int
    limit: int
    skip: int

class StatsSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    total_calls: int
    total_duration_seconds: int
    total_participants: int # Consider if this is total unique participants or total participant sessions
    average_duration_seconds: Optional[float]
    average_participants_per_call: Optional[float]

class CallDataUpdateRequest(BaseModel):
    call_id: str # Room SID
    user_id: Optional[str] = None # Added user_id
    transcript: Optional[str] = None
    recording_url: Optional[str] = None

# Utility for date parsing if needed, or rely on FastAPI's default
from datetime import date # For date type hint

# FastAPI's Query for default values and validation
from fastapi import Query

# Helper function to get a call record or raise 404
def _get_call_or_404(call_id: str, db: Session = Depends(get_db)) -> Call:
    call_record = db.query(Call).filter(Call.call_id == call_id).first()
    if not call_record:
        raise HTTPException(status_code=404, detail="Call not found")
    return call_record

# Helper function to calculate participant duration
def _calculate_participant_duration(participant_record: Participant, call_record: Call) -> Optional[int]:
    duration_in_call_seconds = None
    effective_left_at = participant_record.left_at

    if participant_record.joined_at:
        # If participant hasn't left but call is finished, cap duration at call_finished_at
        if not effective_left_at and call_record.call_finished_at:
            effective_left_at = call_record.call_finished_at

        if effective_left_at: # Now calculate duration if effective_left_at is set
            joined_at_aware = participant_record.joined_at.replace(tzinfo=timezone.utc) if participant_record.joined_at.tzinfo is None else participant_record.joined_at
            effective_left_at_aware = effective_left_at.replace(tzinfo=timezone.utc) if effective_left_at.tzinfo is None else effective_left_at
            if joined_at_aware and effective_left_at_aware: # Ensure both are valid
                 duration_in_call_seconds = int((effective_left_at_aware - joined_at_aware).total_seconds())
    return duration_in_call_seconds

def verify_api_key(authorization: str = Header(None)):
    if not INTERNAL_API_KEY:
        logging.error("API endpoint disabled: INTERNAL_API_KEY not configured on server.")
        raise HTTPException(status_code=503, detail="Service unavailable: API key not configured")

    if not authorization:
        logging.warning("Missing Authorization header in API request")
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization header")

    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        logging.warning("Invalid Authorization header format. Expected 'Bearer <token>'")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token format")

    if token != INTERNAL_API_KEY:
        logging.warning("Invalid API key provided.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API key")
    logging.info("API request authorized with static API key.")


@router.get("/users/{user_id}/calls", response_model=PaginatedCallSummaryResponse, dependencies=[Depends(verify_api_key)])
async def list_user_calls(
    user_id: str = Path(..., description="The ID of the user whose calls are to be listed"),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    start_date: Optional[date] = Query(None, description="Filter calls created on or after this date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter calls created on or before this date (YYYY-MM-DD)")
):
    query = db.query(Call).filter(Call.user_id == user_id)

    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        query = query.filter(Call.call_created_at >= start_datetime)

    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        query = query.filter(Call.call_created_at <= end_datetime)

    total_calls = query.count()
    calls_records = query.order_by(Call.call_created_at.desc()).offset(skip).limit(limit).all()

    call_summaries: List[CallSummary] = []
    for call_record in calls_records:
        participant_count = db.query(Participant).filter(Participant.call_db_id == call_record.id).count()

        overall_call_duration_seconds = None
        if call_record.call_created_at and call_record.call_finished_at:
            overall_call_duration_seconds = int((call_record.call_finished_at - call_record.call_created_at).total_seconds())

        call_created_at_utc = call_record.call_created_at.replace(tzinfo=timezone.utc) if call_record.call_created_at.tzinfo is None else call_record.call_created_at
        call_finished_at_utc = call_record.call_finished_at.replace(tzinfo=timezone.utc) if call_record.call_finished_at and call_record.call_finished_at.tzinfo is None else call_record.call_finished_at

        call_summaries.append(
            CallSummary(
                call_id=call_record.call_id,
                room_name=call_record.room_name,
                call_created_at=call_created_at_utc,
                call_finished_at=call_finished_at_utc,
                overall_call_duration_seconds=overall_call_duration_seconds,
                participant_count=participant_count,
                transcript=call_record.transcript,
                recording_url=call_record.recording_url
            )
        )

    return PaginatedCallSummaryResponse(
        items=call_summaries,
        total=total_calls,
        limit=limit,
        skip=skip
    )

@router.get("/calls/{call_id}/summary", response_model=CallSummary, dependencies=[Depends(verify_api_key)])
async def get_call_summary(
    call_id: str = Path(..., description="The SID of the call/room"),
    db: Session = Depends(get_db) # Keep db session for other queries
):
    call_record = _get_call_or_404(call_id=call_id, db=db) # Use helper

    participant_count = db.query(Participant).filter(Participant.call_db_id == call_record.id).count()

    overall_call_duration_seconds = None
    if call_record.call_created_at and call_record.call_finished_at:
        overall_call_duration_seconds = int((call_record.call_finished_at - call_record.call_created_at).total_seconds())

    call_created_at_utc = call_record.call_created_at.replace(tzinfo=timezone.utc) if call_record.call_created_at.tzinfo is None else call_record.call_created_at
    call_finished_at_utc = call_record.call_finished_at.replace(tzinfo=timezone.utc) if call_record.call_finished_at and call_record.call_finished_at.tzinfo is None else call_record.call_finished_at

    return CallSummary(
        call_id=call_record.call_id,
        room_name=call_record.room_name,
        call_created_at=call_created_at_utc,
        call_finished_at=call_finished_at_utc,
        overall_call_duration_seconds=overall_call_duration_seconds,
        participant_count=participant_count,
        transcript=call_record.transcript,
        recording_url=call_record.recording_url
    )


@router.get("/calls/{call_id}/participants", response_model=PaginatedParticipantSummaryResponse, dependencies=[Depends(verify_api_key)])
async def list_call_participants(
    call_id: str = Path(..., description="The SID of the call/room"),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return")
):
    call_record = _get_call_or_404(call_id=call_id, db=db) # Use helper

    participant_query = db.query(Participant).filter(Participant.call_db_id == call_record.id)
    total_participants = participant_query.count()

    participants_records = participant_query.order_by(Participant.joined_at).offset(skip).limit(limit).all()

    participant_summaries: List[ParticipantSummary] = []
    for p_record in participants_records:
        duration_in_call_seconds = _calculate_participant_duration(p_record, call_record)

        joined_at_utc = p_record.joined_at.replace(tzinfo=timezone.utc) if p_record.joined_at.tzinfo is None else p_record.joined_at
        left_at_utc = p_record.left_at.replace(tzinfo=timezone.utc) if p_record.left_at and p_record.left_at.tzinfo is None else p_record.left_at

        participant_summaries.append(
            ParticipantSummary(
                participant_id=p_record.participant_id,
                participant_name=p_record.participant_name,
                joined_at=joined_at_utc,
                left_at=left_at_utc,
                duration_in_call_seconds=duration_in_call_seconds
            )
        )

    return PaginatedParticipantSummaryResponse(
        items=participant_summaries,
        total=total_participants,
        limit=limit,
        skip=skip
    )

@router.get("/calls/{call_id}/participants/{participant_id}", response_model=ParticipantAnalytics, dependencies=[Depends(verify_api_key)])
async def get_call_participant_details(
    call_id: str = Path(..., description="The SID of the call/room"),
    participant_id: str = Path(..., description="The SID of the participant"),
    db: Session = Depends(get_db)
):
    call_record = _get_call_or_404(call_id=call_id, db=db) # Use helper

    participant_record = db.query(Participant).filter(
        Participant.call_db_id == call_record.id,
        Participant.participant_id == participant_id
    ).first()

    if not participant_record:
        raise HTTPException(status_code=404, detail="Participant not found in this call")

    duration_in_call_seconds = _calculate_participant_duration(participant_record, call_record)

    joined_at_utc = participant_record.joined_at.replace(tzinfo=timezone.utc) if participant_record.joined_at.tzinfo is None else participant_record.joined_at
    left_at_utc = participant_record.left_at.replace(tzinfo=timezone.utc) if participant_record.left_at and participant_record.left_at.tzinfo is None else participant_record.left_at

    return ParticipantAnalytics(
        participant_id=participant_record.participant_id,
        participant_name=participant_record.participant_name,
        joined_at=joined_at_utc,
        left_at=left_at_utc,
        duration_in_call_seconds=duration_in_call_seconds
    )


@router.get("/calls/{call_id}/analytics", response_model=CallAnalyticsResponse, dependencies=[Depends(verify_api_key)])
async def get_call_analytics(
    call_id: str = Path(..., description="The SID of the call/room"),
    db: Session = Depends(get_db)
):
    call_record = _get_call_or_404(call_id=call_id, db=db) # Use helper

    participants_records = db.query(Participant).filter(Participant.call_db_id == call_record.id).all()

    overall_call_duration_seconds = None
    if call_record.call_created_at and call_record.call_finished_at:
        overall_call_duration_seconds = int((call_record.call_finished_at - call_record.call_created_at).total_seconds())

    # Ensure datetimes are timezone-aware (UTC) for consistent ISO formatting
    # For fields that are already aware (due to how they are stored/retrieved from PG or set in code)
    # .replace(tzinfo=timezone.utc) might be redundant if tzinfo is already UTC, but safe.
    # If they are naive from DB (e.g. SQLite in tests), this makes them aware.
    call_created_at_utc = call_record.call_created_at.replace(tzinfo=timezone.utc) if call_record.call_created_at.tzinfo is None else call_record.call_created_at
    call_finished_at_utc = call_record.call_finished_at.replace(tzinfo=timezone.utc) if call_record.call_finished_at and call_record.call_finished_at.tzinfo is None else call_record.call_finished_at


    participants_analytics = []
    for p_record in participants_records:
        duration_in_call_seconds = _calculate_participant_duration(p_record, call_record)

        joined_at_utc = p_record.joined_at.replace(tzinfo=timezone.utc) if p_record.joined_at.tzinfo is None else p_record.joined_at
        left_at_utc = p_record.left_at.replace(tzinfo=timezone.utc) if p_record.left_at and p_record.left_at.tzinfo is None else p_record.left_at


        participants_analytics.append(
            ParticipantAnalytics(
                participant_id=p_record.participant_id,
                participant_name=p_record.participant_name,
                joined_at=joined_at_utc,
                left_at=left_at_utc,
                duration_in_call_seconds=duration_in_call_seconds
            )
        )

    return CallAnalyticsResponse(
        call_id=call_record.call_id,
        room_name=call_record.room_name,
        call_created_at=call_created_at_utc,
        call_finished_at=call_finished_at_utc,
        overall_call_duration_seconds=overall_call_duration_seconds,
        participants=participants_analytics,
        transcript=call_record.transcript,
        recording_url=call_record.recording_url
    )

@router.get("/stats", response_model=StatsSummary, dependencies=[Depends(verify_api_key)])
async def get_aggregate_stats(
    db: Session = Depends(get_db),
    # For simplicity, let's start with a specific day. Generalizing to period (daily, weekly, monthly) can be an enhancement.
    target_date: Optional[date] = Query(None, description="Target date for daily stats (YYYY-MM-DD). If not provided, defaults to today.")
):
    if target_date is None:
        target_date = date.today()

    period_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    period_end = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc)

    # Query calls within the period
    calls_in_period = db.query(Call).filter(
        Call.call_created_at >= period_start,
        Call.call_created_at <= period_end
    ).all()

    total_calls = len(calls_in_period)
    total_duration_seconds = 0
    total_participants_in_period = 0

    if not calls_in_period:
        return StatsSummary(
            period_start=period_start,
            period_end=period_end,
            total_calls=0,
            total_duration_seconds=0,
            total_participants=0,
            average_duration_seconds=0,
            average_participants_per_call=0
        )

    for call_record in calls_in_period:
        if call_record.call_created_at and call_record.call_finished_at:
            duration = call_record.call_finished_at - call_record.call_created_at
            total_duration_seconds += int(duration.total_seconds())

        # Count participants for this call.
        # This counts participant records (sessions). If unique participants are needed, query would be different.
        participants_in_call_count = db.query(Participant).filter(Participant.call_db_id == call_record.id).count()
        total_participants_in_period += participants_in_call_count

    average_duration_seconds = total_duration_seconds / total_calls if total_calls > 0 else 0
    average_participants_per_call = total_participants_in_period / total_calls if total_calls > 0 else 0

    return StatsSummary(
        period_start=period_start,
        period_end=period_end,
        total_calls=total_calls,
        total_duration_seconds=total_duration_seconds,
        total_participants=total_participants_in_period,
        average_duration_seconds=average_duration_seconds,
        average_participants_per_call=average_participants_per_call
    )


# The old /rooms endpoint is removed as it was Redis specific and not part of the current task.
# If it needs to be re-implemented using PostgreSQL, that would be a separate requirement.

@router.post("/calls/data", status_code=202, dependencies=[Depends(verify_api_key)])
async def update_call_data(
    update_request: CallDataUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Receives transcript and recording URL for a specific call (room)
    and updates the database. Intended to be called by the LiveKit Agent
    after a call has finished and data is processed.
    """
    call_record = db.query(Call).filter(Call.call_id == update_request.call_id).first()

    if not call_record:
        # If webhook for room_started hasn't been processed yet, or invalid call_id
        # We could choose to create a new Call record here if needed,
        # but for now, let's assume room_started webhook creates it.
        # However, if it's not found, we could also consider creating it here if user_id is provided.
        # For now, sticking to the plan of requiring room_started webhook first.
        logging.warning(f"Call data update received for non-existent call_id: {update_request.call_id}")
        raise HTTPException(status_code=404, detail=f"Call with ID {update_request.call_id} not found. Ensure room_started webhook has been processed.")

    updated = False
    # Handle user_id update
    if update_request.user_id:
        if call_record.user_id is None:
            call_record.user_id = update_request.user_id
            updated = True
            logging.info(f"User ID '{update_request.user_id}' set for call_id: {update_request.call_id}")
        elif call_record.user_id != update_request.user_id:
            logging.warning(f"User ID mismatch for call_id: {update_request.call_id}. "
                            f"Existing: '{call_record.user_id}', Received: '{update_request.user_id}'. "
                            f"Existing user_id will be kept.")
            # Not setting updated = True here as we are not changing the user_id in this case.

    if update_request.transcript is not None:
        call_record.transcript = update_request.transcript
        updated = True
        logging.info(f"Transcript updated for call_id: {update_request.call_id}")

    if update_request.recording_url is not None:
        call_record.recording_url = update_request.recording_url
        updated = True
        logging.info(f"Recording URL updated for call_id: {update_request.call_id}")

    if updated:
        try:
            db.commit()
            db.refresh(call_record)
            logging.info(f"Call data for {update_request.call_id} committed to database.")
        except Exception as e:
            db.rollback()
            logging.error(f"Database error updating call data for {update_request.call_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to update call data in database.")
        return {"message": "Call data update accepted."}
    else:
        logging.info(f"No new data provided to update for call_id: {update_request.call_id}")
        return {"message": "No new data provided for update."}
