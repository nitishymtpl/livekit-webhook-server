import logging
import os
from fastapi import APIRouter, Request, Header, HTTPException
from livekit.api import WebhookReceiver, TokenVerifier
from dotenv import load_dotenv
import json

load_dotenv()

router = APIRouter()

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
    logging.error("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in environment for routes/webhook.py")

token_verifier = TokenVerifier(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
receiver = WebhookReceiver(token_verifier)

@router.post("/webhook")
async def handle_webhook(request: Request, authorization: str = Header(None)):
    if not authorization:
        logging.warning("Missing Authorization header in webhook request")
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization header")

    auth_token = authorization

    body = await request.body()
    redis_client = request.app.state.redis

    try:
        event = receiver.receive(body.decode("utf-8"), auth_token)
        logging.info(f"Received and verified webhook event: {event.event}, data: {event}")

        if event.event == "room_started":
            if event.room:
                room_data = {
                    "sid": event.room.sid,
                    "name": event.room.name,
                    "empty_timeout": event.room.empty_timeout,
                    "creation_time": event.room.creation_time,
                    "turn_password": event.room.turn_password,
                    "enabled_codecs": [codec.mime for codec in event.room.enabled_codecs],
                    "status": "started",
                    "id": event.id,
                    "created_at": event.created_at
                }
                redis_client.set(f"room:{event.room.sid}", json.dumps(room_data))
                logging.info(f"Room {event.room.sid} created in Redis.")
        elif event.event == "room_finished":
            if event.room:
                room_sid = event.room.sid
                existing_room_data = redis_client.get(f"room:{room_sid}")
                if existing_room_data:
                    room_data = json.loads(existing_room_data)
                    room_data["status"] = "finished"
                    room_data["finished_at"] = event.created_at # Use event creation as finish time
                    redis_client.set(f"room:{room_sid}", json.dumps(room_data))
                    logging.info(f"Room {room_sid} marked as finished in Redis.")
                else:
                    logging.warning(f"Room {room_sid} not found in Redis for finishing.")

        return {"status": "ok", "event_type": event.event}
    except Exception as e:
        logging.error(f"Webhook verification or processing failed: {e}")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid signature or token")
