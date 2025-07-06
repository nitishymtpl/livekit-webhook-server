# LiveKit Webhook Service

LiveKit has an API call limit of 1000 requests per minute, but for some applications you may need to make more requests than that.

This service provides a FastAPI app to handle LiveKit webhooks and expose an API for room data.

If you want to expose more resources, just listen for the webhook, put it in Redis, then serve it with the API! Instead of 1k requests per minute, make as many as you want.

## Features

-   **Webhook Handling (`/webhook`):**
    -   Receives and verifies LiveKit webhook events (`room_started`, `room_finished`, `participant_joined`, `participant_left`).
    -   Authenticates webhooks using `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`.
    -   Persists call and participant information to a PostgreSQL database.
    -   Associates a `user_id` (derived from `participant.identity` of the first participant joining or from agent data) with each call.
-   **API Endpoints (under `/api` prefix, require Bearer token authentication using `INTERNAL_API_KEY`):**
    -   `GET /users/{user_id}/calls`: Lists calls for a specific user with pagination and optional date filtering. Provides a summary for each call (ID, name, creation/finish times, duration, participant count). This replaces the previous generic `/calls` endpoint.
    -   `GET /calls/{call_id}/analytics`: Returns detailed analytics for a specific call, including overall duration and a list of participants with their individual durations and join/leave times.
    -   `GET /calls/{call_id}/summary`: Returns a summary for a specific call (ID, name, creation/finish times, duration, participant count).
    -   `GET /calls/{call_id}/participants`: Lists all participants for a specific call with pagination. Includes join/leave times and duration in call for each participant.
    -   `GET /calls/{call_id}/participants/{participant_id}`: Returns detailed information for a specific participant within a specific call.
    -   `GET /stats`: Provides aggregate statistics (e.g., total calls, total duration, total participants) for a given day (defaults to today).
    -   `POST /calls/data`: Receives transcript, recording URL, and `user_id` for a specific call (room SID) from an agent (e.g., the agent in `test.py`) and updates the database.

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

## Example API Responses

This section provides examples of the JSON responses you can expect from the API endpoints.

**1. Get Call Analytics (`GET /api/calls/{call_id}/analytics`)**
```json
{
  "call_id": "your_call_id",
  "name": "example_room_name",
  "created_at": "2023-10-26T10:00:00Z",
  "finished_at": "2023-10-26T11:00:00Z",
  "total_duration_seconds": 3600,
  "participants": [
    {
      "participant_id": "participant_sid_1",
      "identity": "user_identity_1",
      "joined_at": "2023-10-26T10:00:00Z",
      "left_at": "2023-10-26T11:00:00Z",
      "duration_seconds": 3600
    },
    {
      "participant_id": "participant_sid_2",
      "identity": "user_identity_2",
      "joined_at": "2023-10-26T10:05:00Z",
      "left_at": "2023-10-26T10:55:00Z",
      "duration_seconds": 3000
    }
  ],
  "participant_count": 2
}
```

**2. List Calls for a User (`GET /api/users/{user_id}/calls`)**
```json
{
  "items": [
    {
      "call_id": "call_id_1",
      "name": "Room Alpha",
      "created_at": "2023-10-26T10:00:00Z",
      "finished_at": "2023-10-26T11:00:00Z",
      "duration_seconds": 3600,
      "participant_count": 5
    },
    {
      "call_id": "call_id_2",
      "name": "Room Beta",
      "created_at": "2023-10-26T12:00:00Z",
      "finished_at": null,
      "duration_seconds": null,
      "participant_count": 3
    }
  ],
  "total": 2,
  "page": 1,
  "size": 50,
  "pages": 1
}
```
*If filtered by `date_filter`, only calls created on that date would appear.*
*Pagination fields (`total`, `page`, `size`, `pages`) would reflect the current view.*

**3. Get Call Summary (`GET /api/calls/{call_id}/summary`)**
```json
{
  "call_id": "your_call_id",
  "name": "example_room_name",
  "created_at": "2023-10-26T10:00:00Z",
  "finished_at": "2023-10-26T11:00:00Z",
  "duration_seconds": 3600,
  "participant_count": 2
}
```

**4. List Call Participants (`GET /api/calls/{call_id}/participants`)**
```json
{
  "items": [
    {
      "participant_id": "participant_sid_1",
      "identity": "user_identity_1",
      "name": "Participant One",
      "joined_at": "2023-10-26T10:00:00Z",
      "left_at": "2023-10-26T11:00:00Z",
      "duration_seconds": 3600
    },
    {
      "participant_id": "participant_sid_2",
      "identity": "user_identity_2",
      "name": "Participant Two",
      "joined_at": "2023-10-26T10:05:00Z",
      "left_at": "2023-10-26T10:55:00Z",
      "duration_seconds": 3000
    }
  ],
  "total": 2,
  "page": 1,
  "size": 50,
  "pages": 1
}
```
*Pagination fields would adjust based on query parameters and total number of participants.*

**5. Get Participant Details (`GET /api/calls/{call_id}/participants/{participant_id}`)**
```json
{
  "participant_id": "your_participant_id",
  "call_id": "your_call_id",
  "identity": "user_identity_example",
  "name": "Participant Example",
  "joined_at": "2023-10-26T10:00:00Z",
  "left_at": "2023-10-26T11:00:00Z",
  "duration_seconds": 3600,
  "metadata": "Optional participant metadata if stored",
  "permissions": {
    "can_publish": true,
    "can_subscribe": true
  }
}
```
*The exact fields here are more speculative as "detailed information" can vary.*

**6. Get Aggregate Statistics (`GET /api/stats`)**
```json
{
  "date": "2023-10-26",
  "total_calls": 15,
  "total_duration_seconds": 54000,
  "total_participants": 75,
  "average_call_duration_seconds": 3600,
  "average_participants_per_call": 5
}
```

**Important Considerations for Responses:**
*   **Error Responses:** If the `Authorization` header is missing or incorrect, you'd likely get a `401 Unauthorized` or `403 Forbidden` error. If a `call_id` or `participant_id` is not found, you'd get a `404 Not Found`.
    ```json
    // Example 401
    { "detail": "Not authenticated" }
    // Example 404
    { "detail": "Call not found" }
    ```
*   **Timestamps:** These are likely ISO 8601 formatted strings.
*   **`null` values:** Fields like `finished_at` or `duration_seconds` might be `null` if a call is ongoing or if data is incomplete.
*   **Customization:** The actual JSON structure and field names will depend on the exact implementation in `main.py` and the database schema. The examples above are based on common practices and the information in the README.
