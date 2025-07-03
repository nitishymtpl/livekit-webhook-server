from fastapi import FastAPI, Depends
import logging
import os
from dotenv import load_dotenv
from routes.webhook import router as webhook_router
from routes.api import router as api_router
from models import create_db_and_tables, SessionLocal, get_db # New imports
from sqlalchemy.orm import Session # New import

load_dotenv()

app = FastAPI()

# Database setup
def init_db():
    create_db_and_tables()

# Dependency to get DB session
app.dependency_overrides[get_db] = get_db


logging.basicConfig(level=logging.INFO)

app.include_router(webhook_router)
app.include_router(api_router, prefix="/api")