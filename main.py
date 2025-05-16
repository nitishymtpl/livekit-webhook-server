from fastapi import FastAPI
import logging
import os
from dotenv import load_dotenv
from routes.webhook import router as webhook_router
from routes.api import router as api_router
import redis

load_dotenv()

app = FastAPI()

# Initialize Redis client
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=os.getenv("REDIS_PORT", 6379), db=0)
app.state.redis = redis_client

logging.basicConfig(level=logging.INFO)

app.include_router(webhook_router)
app.include_router(api_router, prefix="/api")