"""Gunicorn configuration file."""

import logging
from main import init_db

# Get the same logger instance that Gunicorn uses
logger = logging.getLogger("gunicorn.error")

def on_starting(server):
    """
    Gunicorn server hook called when the master process is starting.
    This is where we initialize the database.
    """
    logger.info("Master Gunicorn process is starting. Initializing database...")
    try:
        init_db()
        logger.info("Database initialization complete.")
    except Exception as e:
        logger.error(f"Error during database initialization: {e}")
        # Optionally, re-raise the exception if you want Gunicorn to fail starting
        # raise

# You can add other Gunicorn settings here if needed, for example:
# workers = 4
# worker_class = "uvicorn.workers.UvicornWorker"
# bind = "0.0.0.0:8000"
# loglevel = "info"
