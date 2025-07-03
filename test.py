import os
import json
import logging
import httpx # Or any other HTTP client library
from datetime import datetime

from dotenv import load_dotenv

from livekit import agents, rtc # rtc is needed for JobContext if not already imported via agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    noise_cancellation,
)
from livekit import api # For Egress and LiveKitAPI client

load_dotenv()

# --- Configuration (ideally from environment variables or a config file) ---
LIVEKIT_API_URL = os.getenv("LIVEKIT_URL", "http://localhost:7880") # Your LiveKit server URL
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Azure Blob Storage Configuration
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING") # Added, though account key might be more direct for Egress

# URL for your FastAPI analytics backend (where we'll send the data)
ANALYTICS_BACKEND_URL = os.getenv("ANALYTICS_BACKEND_URL", "http://localhost:8000/api/calls/data") 
ANALYTICS_INTERNAL_API_KEY = os.getenv("ANALYTICS_INTERNAL_API_KEY", "your_internal_api_key_for_analytics_backend")

# Prompt Management API Configuration
PROMPT_API_URL = os.getenv("PROMPT_API_URL") # e.g., http://localhost:8001/api/internal/user-prompts
PROMPT_API_KEY = os.getenv("PROMPT_API_KEY")

# Configure logging
logging.basicConfig(level=logging.INFO)


class Assistant(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)


async def entrypoint(ctx: agents.JobContext):
    logging.info(f"Agent started for room: {ctx.room.name} (SID: {ctx.room.sid})")

    # --- Egress and Data Submission Logic --- 
    lkapi = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    egress_info = None
    recording_url = None

    if all([LIVEKIT_API_KEY, LIVEKIT_API_SECRET, AZURE_STORAGE_ACCOUNT_NAME, AZURE_STORAGE_CONTAINER_NAME, (AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_KEY)]):
        # Define a unique path within your Azure container
        recording_filename = f"{ctx.room.name}_{ctx.room.sid}.ogg" # Or .mp4, etc.
        recording_filepath_in_container = f"recordings/{recording_filename}"
        
        try:
            logging.info(f"Starting audio recording for room {ctx.room.name} to Azure Blob Storage")
            
            azure_upload_options = api.AzureBlobUpload(
                account_name=AZURE_STORAGE_ACCOUNT_NAME,
                container_name=AZURE_STORAGE_CONTAINER_NAME
            )
            if AZURE_STORAGE_ACCOUNT_KEY:
                azure_upload_options.account_key = AZURE_STORAGE_ACCOUNT_KEY
            elif AZURE_STORAGE_CONNECTION_STRING:
                # This part is still conceptual. Check LiveKit SDK for how it prefers Azure credentials.
                # It might parse the connection string or require specific components.
                logging.info("Attempting to use Azure Connection String for Egress. SDK behavior may vary.")
                # Potentially, the SDK might require you to parse the connection string and pass account_key explicitly.
                # For now, this assumes the SDK might handle it or you've set account_key as priority.
                if not AZURE_STORAGE_ACCOUNT_KEY: # If only connection string is available
                    logging.warning("Azure Connection String provided without Account Key. Egress might require Account Key. Please verify LiveKit SDK documentation.")

            req = api.RoomCompositeEgressRequest(
                room_name=ctx.room.name,
                audio_only=True,
                file_outputs=[api.EncodedFileOutput(
                    file_type=api.EncodedFileType.OGG, 
                    filepath=recording_filepath_in_container, 
                    azure=azure_upload_options
                )],
            )
            egress_info = await lkapi.egress.start_room_composite_egress(req)
            
            recording_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER_NAME}/{recording_filepath_in_container}"
            logging.info(f"Egress started with ID: {egress_info.egress_id}. Recording will be at: {recording_url}")

        except Exception as e:
            logging.error(f"Failed to start egress for room {ctx.room.name} to Azure: {e}", exc_info=True)
    else:
        logging.warning("Recording to Azure is not configured due to missing environment variables.")

    # --- Helper function to fetch custom prompt ---
    async def fetch_custom_prompt(user_id: str, api_url: str, api_key: str) -> str | None:
        if not api_url or not api_key:
            logging.warning("Prompt API URL or Key not configured. Cannot fetch custom prompt.")
            return None

        url = f"{api_url}/{user_id}"
        headers = {
            "X-Internal-API-Key": api_key, # Or "Authorization": f"Bearer {api_key}" depending on API design
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient() as client:
                logging.info(f"Fetching custom prompt for user {user_id} from {url}")
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    prompt_text = data.get("prompt_text")
                    if prompt_text:
                        logging.info(f"Custom prompt found for user {user_id}")
                        return prompt_text
                    else:
                        logging.warning(f"Prompt text missing in response for user {user_id}")
                        return None
                elif response.status_code == 404:
                    logging.info(f"No custom prompt found for user {user_id}")
                    return None
                else:
                    logging.error(f"Error fetching prompt for user {user_id}: {response.status_code} - {response.text}")
                    return None
        except httpx.RequestError as e:
            logging.error(f"Request error fetching prompt for user {user_id}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error fetching prompt for user {user_id}: {e}", exc_info=True)
            return None

    # --- Determine User ID for Custom Prompt ---
    # This logic assumes the agent is primarily interacting with one other human participant.
    # If multiple human participants, this needs refinement (e.g., which user's prompt to use?)
    clerk_user_id = None
    human_participant_identity = None

    # Wait for participants to be available, with a timeout
    for _ in range(10): # Try for a few seconds
        if len(ctx.room.participants) > 1: # Check if there's more than just the agent
            break
        await agents.utils.sleep(0.5)

    for p_sid, p_info in ctx.room.participants.items():
        # Assuming agent's identity is known or different from typical user IDs
        # If agent's identity can be None or same format as user IDs, this needs a more robust check.
        # For now, let's assume the agent has a distinct identity or we are looking for any other participant.
        # A better way would be to pass the agent's own configured identity and compare against it.
        # Let's assume the agent's identity is not the one we are looking for.
        # A common pattern is that the agent's identity might be something like "agent-session-xyz"
        # while user identities are "user-clerk-id-abc".
        # For this example, we'll take the first participant that isn't the agent itself.
        # This assumes the agent's own `ctx.participant.identity` is set and known.
        if p_info.identity != ctx.participant.identity: # `ctx.participant` is the agent itself
            human_participant_identity = p_info.identity
            logging.info(f"Found human participant with identity: {human_participant_identity}")
            break

    if human_participant_identity:
        clerk_user_id = human_participant_identity # Assuming participant identity is the Clerk User ID
    else:
        logging.warning(f"Could not determine a unique human participant identity in room {ctx.room.name}. Will use default prompt.")
        # Fallback: could also try ctx.room.metadata if set at room creation, e.g.,
        # if ctx.room.metadata:
        #     try:
        #         room_meta = json.loads(ctx.room.metadata)
        #         clerk_user_id = room_meta.get("clerk_user_id")
        #         if clerk_user_id:
        #              logging.info(f"Using clerk_user_id from room metadata: {clerk_user_id}")
        #     except json.JSONDecodeError:
        #         logging.warning("Room metadata is not valid JSON.")


    # --- Fetch Custom Prompt or Use Default ---
    custom_instructions = None
    if clerk_user_id and PROMPT_API_URL and PROMPT_API_KEY:
        custom_instructions = await fetch_custom_prompt(clerk_user_id, PROMPT_API_URL, PROMPT_API_KEY)

    agent_instructions = custom_instructions if custom_instructions else "You are a helpful voice AI assistant. Please be kind and empathetic."
    logging.info(f"Initializing agent with instructions: '{agent_instructions[:100]}...'") # Log first 100 chars

    # --- Agent Session Setup --- 
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            voice="coral"
        )
    )
    current_agent = Assistant(instructions=agent_instructions) # Pass dynamic instructions

    # --- Shutdown Hook for Transcript and Data Submission --- 
    async def shutdown_hook():
        logging.info(f"Shutdown hook called for room: {ctx.room.name}")
        transcript_content = ""
        
        if hasattr(session, 'history'): # Access history from the 'session' object
            transcript_data = session.history.to_dict() 
            transcript_content = json.dumps(transcript_data, indent=2)
            logging.info(f"Transcript captured for room {ctx.room.name}. Length: {len(transcript_content)}")
        else:
            logging.warning(f"Session history not available on AgentSession for room {ctx.room.name}")
            transcript_content = json.dumps([{"error": "Transcript not available"}])

        if egress_info:
            try:
                logging.info(f"Stopping egress: {egress_info.egress_id}")
                await lkapi.egress.stop_egress(api.StopEgressRequest(egress_id=egress_info.egress_id))
                logging.info(f"Egress {egress_info.egress_id} stopped.")
            except Exception as e:
                logging.error(f"Error stopping egress {egress_info.egress_id}: {e}")
        
        if ANALYTICS_BACKEND_URL and ANALYTICS_INTERNAL_API_KEY:
            payload = {
                "call_id": ctx.room.sid,
                "transcript": transcript_content,
                "recording_url": recording_url 
            }
            headers = {
                "Authorization": f"Bearer {ANALYTICS_INTERNAL_API_KEY}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    logging.info(f"Sending data to analytics backend for room {ctx.room.sid}: {ANALYTICS_BACKEND_URL}")
                    response = await client.post(ANALYTICS_BACKEND_URL, json=payload, headers=headers)
                    response.raise_for_status()
                    logging.info(f"Data successfully sent to analytics backend for room {ctx.room.sid}. Status: {response.status_code}")
                except httpx.HTTPStatusError as e:
                    logging.error(f"HTTP error sending data for room {ctx.room.sid}: {e.response.status_code} - {e.response.text}")
                except httpx.RequestError as e:
                    logging.error(f"Request error sending data for room {ctx.room.sid}: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error sending data for room {ctx.room.sid}: {e}")
        else:
            logging.warning("Analytics backend URL or API key not configured. Cannot send data.")

        await lkapi.aclose()

    ctx.add_shutdown_callback(shutdown_hook)

    # --- Start Agent Session and Connect --- 
    await session.start(
        room=ctx.room,
        agent=current_agent, # Use the agent instance with dynamic instructions
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()
    logging.info(f"Agent connected to room: {ctx.room.name}")

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )
    
    # The agent will now run until the job is complete or interrupted.
    # The shutdown_hook will be called upon termination.
    logging.info(f"Agent entrypoint for room {ctx.room.name} completed setup. Agent is running.")


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
