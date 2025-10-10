
from services.org_service import async_get_org_collection_name_from_session,serialize_mongo_doc

async def get_session_conversations(session_id: str, limit: int = 10):
    collection_name =await async_get_org_collection_name_from_session(session_id)
    cursor = (
        collection_name.find({"session_id": session_id})
        .sort("timestamp", -1)  # Most recent first (descending)
        .limit(limit)
    )
    history = [serialize_mongo_doc(u) for u in cursor]
    return history

