import uuid
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/mydatabase")

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String, unique=True, index=True, default=generate_uuid)
    room_name = Column(String, index=True)
    call_created_at = Column(DateTime(timezone=True), server_default=func.now())
    call_finished_at = Column(DateTime(timezone=True), nullable=True)
    transcript = Column(Text, nullable=True)
    recording_url = Column(String, nullable=True)

    participants = relationship("Participant", back_populates="call")

class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(String, unique=True, index=True, default=generate_uuid)
    participant_name = Column(String, index=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)

    call_db_id = Column(Integer, ForeignKey("calls.id"))
    call = relationship("Call", back_populates="participants")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_db_and_tables():
    Base.metadata.create_all(bind=engine, checkfirst=True)
