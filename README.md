# LiveKit Webhook Service

LiveKit has an API call limit of 1000 requests per minute, but for some applications you may need to make more requests than that.

This service provides a FastAPI app to handle LiveKit webhooks and expose an API for room data.

If you want to expose more resources, just listen for the webhook, put it in Redis, then serve it with the API! Instead of 1k requests per minute, make as many as you want.

## Features

-   **Webhook Handling (`/webhook`):**
    -   Receives and verifies LiveKit webhook events (`room_started`, `room_finished`, `participant_joined`, `participant_left`).
    -   Authenticates webhooks using `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`.
    -   Persists call and participant information to a PostgreSQL database.
-   **API Endpoints (under `/api` prefix, require Bearer token authentication using `INTERNAL_API_KEY`):**
    -   `GET /calls/{call_id}/analytics`: Returns detailed analytics for a specific call, including overall duration and a list of participants with their individual durations and join/leave times.
    -   `GET /calls`: Lists all calls with pagination and optional date filtering. Provides a summary for each call (ID, name, creation/finish times, duration, participant count).
    -   `GET /calls/{call_id}/summary`: Returns a summary for a specific call (ID, name, creation/finish times, duration, participant count).
    -   `GET /calls/{call_id}/participants`: Lists all participants for a specific call with pagination. Includes join/leave times and duration in call for each participant.
    -   `GET /calls/{call_id}/participants/{participant_id}`: Returns detailed information for a specific participant within a specific call.
    -   `GET /stats`: Provides aggregate statistics (e.g., total calls, total duration, total participants) for a given day (defaults to today).

## Prerequisites

-   Python 3.x
-   PostgreSQL server
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
    LIVEKIT_API_KEY="your_livekit_api_key"
    LIVEKIT_API_SECRET="your_livekit_api_secret"
    INTERNAL_API_KEY="your_internal_api_key_for_api_access"
    DATABASE_URL="postgresql://username:password@host:port/database_name"
    ```
    - `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`: Your LiveKit server API key and secret for webhook verification.
    - `INTERNAL_API_KEY`: A secret key you define for authenticating requests to the API endpoints.
    - `DATABASE_URL`: Connection string for your PostgreSQL database.

## Running the Application

Use Gunicorn with Uvicorn workers to run the application:

```bash
gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 4
```

This command will start the FastAPI application.

-   The webhook receiver will be available at `http://<your_host>:<port>/webhook`. Configure this URL in your LiveKit server settings.
-   The API endpoints will be available under `http://<your_host>:<port>/api/`. Remember to include the `Authorization: Bearer <INTERNAL_API_KEY>` header when accessing these endpoints.
