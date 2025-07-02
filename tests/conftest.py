import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from main import app, init_db as main_init_db # Import app and init_db from main
from models import Base, get_db, Call, Participant # Import Base and get_db from models
import os
from datetime import datetime, timezone

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency for testing
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    # Set a dummy DATABASE_URL for models.py if it's read at import time there for engine creation
    # However, our models.py engine is separate from the test engine here.
    # The critical part is that Base.metadata uses the test engine.
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(create_test_tables):
    """Fixture to create a new database session for each test function."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session): # Ensure db_session is used to setup client if client interacts with db
    """Fixture to create a TestClient instance."""
    # Ensure the app's dependency override is in place for this client
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)

@pytest.fixture(scope="session")
def test_api_key():
    # It's better to set this via environment variable for the test session
    # but for simplicity in this environment, we'll use a fixed key.
    # Ensure your actual INTERNAL_API_KEY is different and kept secret.
    return "test_internal_api_key_12345"

@pytest.fixture(scope="session", autouse=True)
def set_test_env_vars(test_api_key):
    original_api_key = os.environ.get("INTERNAL_API_KEY")
    os.environ["INTERNAL_API_KEY"] = test_api_key
    # For webhooks, if LIVEKIT_API_KEY and LIVEKIT_API_SECRET are needed for receiver setup
    original_lk_key = os.environ.get("LIVEKIT_API_KEY")
    original_lk_secret = os.environ.get("LIVEKIT_API_SECRET")
    os.environ["LIVEKIT_API_KEY"] = "test_lk_api_key"
    os.environ["LIVEKIT_API_SECRET"] = "test_lk_api_secret"

    # Reload modules that might have cached env vars at import time if necessary
    # For example, if routes.api directly reads os.getenv("INTERNAL_API_KEY") at module level
    import importlib
    import routes.api
    import routes.webhook
    importlib.reload(routes.api)
    importlib.reload(routes.webhook)


    yield
    # Restore original environment variables
    if original_api_key is None:
        del os.environ["INTERNAL_API_KEY"]
    else:
        os.environ["INTERNAL_API_KEY"] = original_api_key

    if original_lk_key is None:
        del os.environ["LIVEKIT_API_KEY"]
    else:
        os.environ["LIVEKIT_API_KEY"] = original_lk_key

    if original_lk_secret is None:
        del os.environ["LIVEKIT_API_SECRET"]
    else:
        os.environ["LIVEKIT_API_SECRET"] = original_lk_secret

    importlib.reload(routes.api) # Reload again to restore original state if necessary
    importlib.reload(routes.webhook)


# Sample data fixtures
@pytest.fixture
def sample_call_data():
    return {
        "call_id": "test_call_sid_1",
        "room_name": "Test Room 1",
        "call_created_at": datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        "call_finished_at": datetime(2023, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
    }

@pytest.fixture
def sample_participant_data_1(sample_call_data):
    return {
        "participant_id": "test_participant_sid_1",
        "participant_name": "Alice",
        "joined_at": datetime(2023, 1, 1, 10, 0, 5, tzinfo=timezone.utc),
        "left_at": datetime(2023, 1, 1, 10, 30, 0, tzinfo=timezone.utc),
    }

@pytest.fixture
def sample_participant_data_2(sample_call_data):
    return {
        "participant_id": "test_participant_sid_2",
        "participant_name": "Bob",
        "joined_at": datetime(2023, 1, 1, 10, 1, 0, tzinfo=timezone.utc),
        "left_at": None, # Bob didn't leave explicitly, or left when call ended
    }
