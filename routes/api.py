import logging
import json
import os
from fastapi import APIRouter, Request, HTTPException, Header
import redis

router = APIRouter()

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

if not INTERNAL_API_KEY:
    logging.error("INTERNAL_API_KEY must be set in environment for routes/api.py")

@router.get("/rooms")
async def get_rooms(request: Request, authorization: str = Header(None)):
    if not INTERNAL_API_KEY:
        logging.error("API endpoint disabled: INTERNAL_API_KEY not configured on server.")
        raise HTTPException(status_code=503, detail="Service unavailable: API key not configured")

    if not authorization:
        logging.warning("Missing Authorization header in API request")
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization header")

    # Expecting "Bearer <your_api_key>"
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        logging.warning("Invalid Authorization header format. Expected 'Bearer <token>'")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token format")

    if token != INTERNAL_API_KEY:
        logging.warning("Invalid API key provided.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API key")

    logging.info("API request authorized with static API key.")

    redis_client = request.app.state.redis
    try:
        room_keys = redis_client.keys("room:*")
        rooms = []
        for key in room_keys:
            room_data = redis_client.get(key)
            if room_data:
                rooms.append(json.loads(room_data.decode('utf-8')))
        return rooms
    except redis.exceptions.ConnectionError as e:
        logging.error(f"Redis connection error: {e}")
        raise HTTPException(status_code=500, detail="Could not connect to Redis")
    except Exception as e:
        logging.error(f"Error fetching rooms from Redis: {e}")
        raise HTTPException(status_code=500, detail="Error fetching rooms")


@router.get("/analytics/{room_sid}")
async def get_room_analytics(request: Request, room_sid: str, authorization: str = Header(None)):
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

    logging.info(f"Analytics API request authorized for room: {room_sid}")

    redis_client = request.app.state.redis
    try:
        # Check if the room itself exists to give a better error message
        room_key = f"room:{room_sid}"
        if not redis_client.exists(room_key):
            logging.warning(f"Analytics requested for non-existent room: {room_sid}")
            raise HTTPException(status_code=404, detail=f"Room with SID {room_sid} not found.")

        participant_keys = redis_client.keys(f"room:{room_sid}:participant:*")
        analytics_data = []
        for p_key_bytes in participant_keys:
            p_key = p_key_bytes.decode('utf-8')
            participant_data_raw = redis_client.hgetall(p_key)
            if participant_data_raw:
                participant_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in participant_data_raw.items()}
                # Convert numeric fields appropriately
                if 'join_time' in participant_data:
                    participant_data['join_time'] = float(participant_data['join_time'])
                if 'leave_time' in participant_data:
                    participant_data['leave_time'] = float(participant_data['leave_time'])
                if 'duration' in participant_data:
                    participant_data['duration'] = float(participant_data['duration'])
                analytics_data.append(participant_data)

        if not analytics_data:
            # Room exists but no participants, or participants haven't left yet / no duration data
            logging.info(f"No participant analytics data found for room {room_sid}, though room exists.")
            # Return empty list instead of 404 if room exists but no participant data
            # This distinguishes from "room not found"

        return {"room_sid": room_sid, "participants": analytics_data}

    except redis.exceptions.ConnectionError as e:
        logging.error(f"Redis connection error: {e}")
        raise HTTPException(status_code=500, detail="Could not connect to Redis")
    except HTTPException as e: # Re-raise HTTPExceptions to preserve status code and detail
        raise e
    except Exception as e:
        logging.error(f"Error fetching analytics for room {room_sid} from Redis: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching analytics for room {room_sid}")
