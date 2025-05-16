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
