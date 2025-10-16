from datetime import datetime
from services.mongo_client import sessions,feedback ,users,client_requirement
from typing import Optional, List
from utils.constants import MESSAGE,HTTP_STATUS
from pymongo import ReturnDocument
from utils.helpers import api_response,serialize_mongo_doc


def save_requirement(data: dict):
    user_id = data['user_id']

    # Get user document
    user_doc = users.find_one({"user_id": user_id})
    org_id = user_doc.get("org_id", "") if user_doc else ""

    # Prepare doc
    doc = {
        "full_name": data['full_name'],
        "phone": data['phone'],
        "email": data['email'],
        "arn_id": data['arn_id'],
        "description": data.get('description', ''),
        "user_id": user_id,
        "org_id": org_id,
        "timestamp": datetime.now()
    }
    client_requirement.insert_one(doc)
    return True



def get_feedback_stats(user_id=None):
    match_stage = {}
    if user_id:
        match_stage = {"user_id": user_id}
    pipeline = [
        {"$match": match_stage} if match_stage else {},
        {"$group": {
            "_id": None,
            "avg_rating": {"$avg": "$rating"},
            "count": {"$sum": 1}
        }}
    ]
    # Remove empty dict if not filtering
    pipeline = [stage for stage in pipeline if stage]
    result = list(feedback.aggregate(pipeline))
    if result:
        return {
            "average_rating": round(result[0]["avg_rating"], 2) if result[0]["count"] else 0,
            "count": result[0]["count"]
        }
    return {
        "average_rating": 0,
        "count": 0
    }



def get_feedbacks_by_user_ids(user_ids: Optional[List[str]] = None):
    query = {}
    if user_ids:
        query["user_id"] = {"$in": user_ids}
    return feedback.find(query).sort("timestamp", -1)


async def get_feedbacks_by_org(org_id:str,offset: int = 0, limit: int = 20,user_ids: list = None):
    query = {"org_id": org_id}

    if user_ids:  
        query["user_id"] = {"$in": user_ids}
    feedback_cursor = feedback.find(query).sort("timestamp",-1).skip(offset).limit(limit)
    feedback_list = [serialize_mongo_doc(u) for u in feedback_cursor]
    return api_response(code=HTTP_STATUS.OK, data=feedback_list)


def get_user_id_by_session(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if session and "user_id" in session:
        return session["user_id"]
    return None

def get_isAsm_by_session(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if session and "isAsm" in session:
        return session["isAsm"]
    return None

def get_org_id_by_session(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if session and "org_id" in session:
        return session["org_id"]
    return None

def get_org_id_by_session_robot_test(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if session and "org_id" in session:
        return session["org_id"]
    return None

def feedback_exists(session_id: str) -> bool:
    return  feedback.find_one({"session_id": session_id}) is not None

def save_feedback(session_id: str, rating: int, review: str,user_id:str):
    org_id = get_org_id_by_session(session_id)
    feedback.insert_one({
        "session_id": session_id,
        "rating": rating,
        "review": review,
        "timestamp": datetime.now(),
        "user_id":user_id,
        "org_id":org_id,
    })

   # ----------------  SAVE like / dislike ----------------
def save_dislike_feedback(message_id: str, status: int,collection_name:any):
    """
    status =  1   → like
    status =  0    → dislike
    """

    try:
        
        doc = collection_name.find_one_and_update(
            {"message_id": message_id},                 # unique id of the message
            {
                "$set": {
                    "status": status,         # flat field
                    "status_at": datetime.now()
                }
            },
            return_document=ReturnDocument.AFTER
        )

        if doc is None:
            return {"success": False, "message": MESSAGE.MSG_ID_NOT_FOUND}

        return {"success": True, "message": MESSAGE.RESPONSE_RECORDED}

    except Exception as e:
        return {"success": False, "message": str(e)}    

# ----------------  UNDO feedback ----------------
def undo_dislike_feedback(message_id: str,collection_name: any):
    """
    Removes the feedback field so it’s as if the user never liked/disliked.
    """

    try:
         
        result = collection_name.update_one(
            {"message_id": message_id},
            {"$unset": {"status": "", "status_at": ""}}
        )

        if result.matched_count == 0:
            return {"success": False, "message": MESSAGE.MSG_ID_NOT_FOUND}

        if result.modified_count == 0:
            return {"success": True, "message": MESSAGE.NOT_LIKE_DISLIKE_FOUND}

        return {"success": True, "message": MESSAGE.LIKE_DISLIKE_UNDO}

    except Exception as e:
        return {"success": False, "message": str(e)}