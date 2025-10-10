from datetime import datetime, timezone
from services.mongo_client import sessions
from utils.key_manager import decrement_key_for_session
from services.rag_services import remove_user_buffers
from utils.logger import log_error

def cleanup_expired_sessions():
    now = datetime.now(timezone.utc)

    try:
        # Step 1: Fetch all expired sessions where memory hasn't been cleaned yet
        expired_sessions = list(sessions.find({
            "expire_timestamp": {"$lte": now},
            "memory_clean_status": False
        }))
        
        print(expired_sessions)
        print(now)

        cleared_sessions = []
        failed_sessions = []

        # Step 2: Loop through sessions and clean them
        for session in expired_sessions:
            session_id = session.get("session_id")
            try:
                # Step 3a: Remove from OpenAI key map & buffer
                decrement_key_for_session(session_id)
                remove_user_buffers(session_id)

                # Step 3b: Mark memory as cleaned
                sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {"memory_clean_status": True}}
                )

                cleared_sessions.append(session_id)

            except Exception as e:
                log_error(f"Failed to clean session {session_id}: {str(e)}")
                failed_sessions.append({
                    "session_id": session_id,
                    "error": str(e)
                })

        # Step 4: Return structured result (used in router for api_response)
        return {
            "cleared_sessions": cleared_sessions,
            "failed_sessions": failed_sessions,
            "error": None
        }

    except Exception as e:
        log_error(f"Unexpected error during cleanup: {str(e)}")
        return {
            "cleared_sessions": [],
            "failed_sessions": [],
            "error": str(e)
        }
