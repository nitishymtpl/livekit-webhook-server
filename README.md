# LiveKit Webhook Service

This service provides a FastAPI application to handle LiveKit webhooks and expose an API for room data.

## Features

-   **Webhook Handling (`/webhook`):**
    -   Receives and verifies LiveKit webhook events (`room_started`, `room_finished`).
    -   Authenticates webhooks using `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`.
    -   Persists room information to Redis:
        -   On `room_started`: Stores room details (SID, name, creation time, status as "started", etc.).
        -   On `room_finished`: Updates the room status to "finished" and records the finish time.
-   **API Endpoint (`/api/rooms`):**
    -   Returns a list of all rooms stored in Redis.
    -   Requires Bearer token authentication using a static `INTERNAL_API_KEY`.

## Prerequisites

-   Python 3.x
-   Redis server
-   LiveKit server (for sending webhooks)

## Setup

1.  **Clone the repository (if applicable).**
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment Variables:**
    Create a `.env` file in the root directory with the following variables:
    ```env
    LIVEKIT_API_KEY=your_livekit_api_key
    LIVEKIT_API_SECRET=your_livekit_api_secret
    INTERNAL_API_KEY=your_internal_api_key_for_api_access
    REDIS_HOST=localhost
    REDIS_PORT=6379
    ```
    - `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`: Your LiveKit server API key and secret for webhook verification.
    - `INTERNAL_API_KEY`: A secret key you define for authenticating requests to the `/api/rooms` endpoint.
    - `REDIS_HOST` and `REDIS_PORT`: Connection details for your Redis instance.

## Running the Application

Use Gunicorn with Uvicorn workers to run the application:

```bash
gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 4
```

This command will start the FastAPI application.

-   The webhook receiver will be available at `http://<your_host>:<port>/webhook`. Configure this URL in your LiveKit server settings.
-   The API endpoint for rooms will be available at `http://<your_host>:<port>/api/rooms`. Remember to include the `Authorization: Bearer <INTERNAL_API_KEY>` header when accessing this endpoint.
