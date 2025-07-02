import logging
import os
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from livekit.api import WebhookReceiver, TokenVerifier, WebhookEvent # Corrected import
from dotenv import load_dotenv
import json
from sqlalchemy.orm import Session
from models import get_db, Call, Participant # Import Call and Participant models
from datetime import datetime, timezone # Added timezone

load_dotenv()

router = APIRouter()

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
    logging.error("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in environment for routes/webhook.py")
    # Consider raising an exception or exiting if these are critical for startup
    token_verifier = None # Ensure verifier is None if keys are missing
    receiver = None
else:
    token_verifier = TokenVerifier(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    receiver = WebhookReceiver(token_verifier)

@router.post("/webhook")
async def handle_webhook(request: Request, authorization: str = Header(None), db: Session = Depends(get_db)):
    if not receiver:
        logging.error("Webhook receiver not initialized due to missing API keys.")
        raise HTTPException(status_code=503, detail="Service unavailable: Webhook receiver not configured")

    if not authorization:
        logging.warning("Missing Authorization header in webhook request")
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization header")

    auth_token = authorization
    body = await request.body()

    try:
        event = receiver.receive(body.decode("utf-8"), auth_token)
        logging.info(f"Received webhook event: {event.event}, Room SID: {event.room.sid if event.room else 'N/A'}, Participant SID: {event.participant.sid if event.participant else 'N/A'}")

        if event.event == "room_started":
            if event.room:
                # Convert LiveKit timestamp (nanoseconds) to datetime
                created_at_dt = datetime.fromtimestamp(event.created_at / 1_000_000_000, timezone.utc)

                new_call = Call(
                    call_id=event.room.sid,
                    room_name=event.room.name,
                    call_created_at=created_at_dt
                )
                db.add(new_call)
                db.commit()
                logging.info(f"Room {event.room.sid} started and saved to DB.")

        elif event.event == "room_finished":
            if event.room:
                finished_at_dt = datetime.fromtimestamp(event.created_at / 1_000_000_000, timezone.utc)
                call_record = db.query(Call).filter(Call.call_id == event.room.sid).first()
                if call_record:
                    call_record.call_finished_at = finished_at_dt
                    db.commit()
                    logging.info(f"Room {event.room.sid} finished and updated in DB.")
                else:
                    logging.warning(f"Room {event.room.sid} not found in DB for finishing.")

        elif event.event == "participant_joined":
            if event.room and event.participant:
                joined_at_dt = datetime.fromtimestamp(event.created_at / 1_000_000_000, timezone.utc)
                # Find the call record by room_sid
                call_record = db.query(Call).filter(Call.call_id == event.room.sid).first()
                if call_record:
                    new_participant = Participant(
                        participant_id=event.participant.sid,
                        participant_name=event.participant.identity, # Assuming identity is the name
                        joined_at=joined_at_dt,
                        call_db_id=call_record.id # Link to the Call's primary key
                    )
                    db.add(new_participant)
                    db.commit()
                    logging.info(f"Participant {event.participant.sid} ({event.participant.identity}) joined room {event.room.sid} and saved to DB.")
                else:
                    logging.warning(f"Call with SID {event.room.sid} not found for participant {event.participant.sid} to join.")

        elif event.event == "participant_left":
            if event.room and event.participant:
                left_at_dt = datetime.fromtimestamp(event.created_at / 1_000_000_000, timezone.utc)
                participant_record = db.query(Participant).filter(Participant.participant_id == event.participant.sid).first()
                if participant_record:
                    # Ensure the participant belongs to the correct call if necessary, though participant_id should be unique
                    call_record = db.query(Call).filter(Call.id == participant_record.call_db_id, Call.call_id == event.room.sid).first()
                    if call_record:
                        participant_record.left_at = left_at_dt
                        db.commit()
                        logging.info(f"Participant {event.participant.sid} left room {event.room.sid} and updated in DB.")
                    else:
                        logging.warning(f"Participant {event.participant.sid} found, but not associated with active call SID {event.room.sid}.")
                else:
                    logging.warning(f"Participant {event.participant.sid} not found in DB for leaving.")

        return {"status": "ok", "event_type": event.event}
    except Exception as e:
        logging.error(f"Webhook verification or processing failed: {e}", exc_info=True)
        # Rollback in case of error during DB operations for this event
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")
