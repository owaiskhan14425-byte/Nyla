from datetime import datetime, timedelta
from pymongo import ReturnDocument
from bson import ObjectId
from utils.helpers import (
    generate_api_key,
    generate_session_id,
    generate_message_id,
    hash_password,
    api_response,
    generate_random_password,
    serialize_mongo_doc,
    generate_org_code
)
from services.mongo_client import (
    org_collection,
    sessions,
    users,
    tokenValidations,
    superAdmin,
)
from utils.constants import MESSAGE, HTTP_STATUS, TOKEN_EXPIRE,SUPER_ADMIN_TOKEN_EXPIRE,TOKEN_EXPIRE_ROBOT
from utils.logger import log_error
from utils.key_manager import assign_key_to_session
from utils.jwt_utils import create_access_token
from bson import ObjectId
from services.mongo_client import db
import time

from services.dedupe_auto import _get_logs_collection_name_for_org
from utils.helpers import decode_user_id,generate_4digit_pin
import re
from typing import Optional,Union
from datetime import timezone
UTC = timezone.utc
def utcnow(): return datetime.now(UTC)

_PIN_RE = re.compile(r'^\d{4}$')



def update_pin_by_user_id(user_id: str, new_pin: str) -> tuple[bool, str]:
    """
    Update the 4-digit PIN for a user identified only by user_id.
    Returns (ok, reason). Fails if user not found or ambiguous.
    """
    if not _PIN_RE.match(new_pin or ""):
        return False, "PIN must be exactly 4 digits"

    # Guard against ambiguous user_id across orgs/user_types
    count = users.count_documents({"user_id": user_id})
    if count == 0:
        return False, "User not found"
    if count > 1:
        # If you prefer to update all, replace with update_many and remove this guard.
        return False, "Multiple user records found for this user_id; cannot safely update"

    res = users.update_one(
        {"user_id": user_id},
        {"$set": {"pin": new_pin, "updated_at": utcnow()}}
    )
    if res.matched_count == 0:
        return False, "User not found"

    return True, ""





# org login
async def org_login_service(email: str, password: str) -> str:
    org = org_collection.find_one({"email": email})
    if not org or org.get("status") != "active":
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_ORG)

    hashed_password = hash_password(password)
    if org["password"] != hashed_password:
        return api_response(
            code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_PASSWORD
        )

    payload = {"org_id": str(org["_id"]), "email": org["email"], "type": "organization"}
    token = create_access_token(payload,TOKEN_EXPIRE)

    token_doc = {
        "user_id": str(org["_id"]),
        "org_name": org["org_name"],
        "email": org["email"],
        "token": token,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "loginType": "organization",
    }
    tokenValidations.update_one(
        {"user_id": str(org["_id"])}, {"$set": token_doc}, upsert=True
    )
    return api_response(
        code=HTTP_STATUS.OK, message=MESSAGE.LOGIN_SUCCESS, data={"token": token}
    )


async def org_login_service_bypass(email: str) -> str:
    org = org_collection.find_one({"email": email})
    if not org or org.get("status") != "active":
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_ORG)
    payload = {"org_id": str(org["_id"]), "email": org["email"], "type": "organization"}
    token = create_access_token(payload,TOKEN_EXPIRE)

    token_doc = {
        "user_id": str(org["_id"]),
        "org_name": org["org_name"],
        "email": org["email"],
        "token": token,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "loginType": "organization",
    }
    tokenValidations.update_one(
        {"user_id": str(org["_id"])}, {"$set": token_doc}, upsert=True
    )
    return api_response(
        code=HTTP_STATUS.OK, message=MESSAGE.LOGIN_SUCCESS, data={"token": token}
    )


# super admin login


# This service checks login details and creates the JWT token
async def authenticate_super_admin(request):
    # Step 1: Retrieve the user from DB by email
    user = superAdmin.find_one({"email": request.email})

    if not user:
        return {"success": False, "message": MESSAGE.INVALID_CREDENTAILS}

    # Step 2: Verify the password (assuming it's hashed using SHA-256)
    hashed_password = hash_password(request.password)
    if user["password"] != hashed_password:
        return {"success": False, "message": MESSAGE.INVALID_CREDENTAILS}

    # Step 3: Create the JWT token
    user_id = str(user["_id"])
    data = {"user_id": user_id, "user_type": "superAdmin"}
    token = create_access_token(data, SUPER_ADMIN_TOKEN_EXPIRE)

    existing_token = tokenValidations.find_one(
        {"user_id": user_id, "loginType": "superAdmin"}
    )

    # If the user already has a token, replace it with the new one
    if existing_token:
        token_data = {
            "user_id": user_id,
            "tokenLoginPlatform": request.tokenLoginPlatform,
            "loginType": "superAdmin",
            "createdAt": datetime.now(),
            "token": token,
            "updatedAt": datetime.now(),
        }

        # Replace the old token with the new one
        tokenValidations.update_one(
            {"user_id": user_id, "loginType": "superAdmin"}, {"$set": token_data}
        )
    else:
        # If no token exists, create a new entry
        token_data = {
            "user_id": user_id,
            "tokenLoginPlatform": request.tokenLoginPlatform,
            "loginType": "superAdmin",
            "createdAt": datetime.now(),
            "token": token,
            "updatedAt": datetime.now(),
        }

        # Insert the new token into the tokenValidations collection
        tokenValidations.insert_one(token_data)

    # Return the successful login response with the token
    return {"success": True, "message": MESSAGE.LOGIN_SUCCESS, "data": {"token": token}}


async def get_org_list() -> list:
     orgs = list(org_collection.find({}, {"api_key": 0,"password":0,"collectionName":0}).sort("created_at", -1))
     orgs = make_json_serializable(orgs)
     return orgs
 
def make_json_serializable(obj):
    if isinstance(obj, dict):
     return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, (datetime, ObjectId)):
        return str(obj)
    else:
        return obj


# for auth
async def authenticate_and_create_session(
    api_key, user_id, current_web_session_id, user_info=None, user_type=0, isAsm=0, new_chat=False
):
    # ✨ Projection: fetch only what you use
    org = org_collection.find_one({"api_key": api_key}, {"_id": 1})
    if not org:
        return {"code": HTTP_STATUS.UNAUTHORIZED, "message": MESSAGE.INVALID_API_KEY}
    org_id = str(org["_id"])

    # ✨ Normalize once
    user_info = user_info or {}
    user_type = int(user_type) if isinstance(user_type, (int, str)) else 0

    now = utcnow()
    expire_time = now + timedelta(minutes=TOKEN_EXPIRE)

    # --- user upsert kept as your two-step, but with projections ---
    existing_user = users.find_one(
        {"user_id": user_id, "user_type": user_type, "org_id": org_id},
        {"_id": 1,"pin":1,"auth_status":True}
    )
    
    decoded_id= decode_user_id(user_id)
    arn_value = decoded_id.split("ARN|")[-1]   # take the part after ARN|
    if existing_user:
        update_fields = {
            "user_info": user_info,
            "updated_at": now,
            "arn_id": int(arn_value),
        }
        if not existing_user.get("pin"):
            update_fields["pin"] = generate_4digit_pin()
            
        if not existing_user.get("auth_status"):
            update_fields["auth_status"] = True

        users.update_one(
            {"_id": existing_user["_id"]},
            {"$set": update_fields},
        )
    else:
        users.insert_one({
            "user_id": user_id,
            "user_info": user_info,
            "user_type": user_type,
            "created_at": now,
            "updated_at": now,
            "org_id": org_id,
            "arn_id":int(arn_value),
            "pin": generate_4digit_pin(),
            "auth_status": True
            
        })

    if not new_chat:
        # ✨ Only fields needed; sort uses index if present
        last_session = sessions.find_one(
            {
                "user_id": user_id,
                "user_type": user_type,
                "org_id": org_id,
                "current_web_session_id": current_web_session_id,
                "expire_timestamp": {"$gt": now},
            },
            sort=[("timestamp", -1)],
            projection={"session_id": 1, "_id": 1}
        )
        if last_session:
            # ✨ combine update to avoid second read
            sessions.update_one(
                {"_id": last_session["_id"]},
                {"$set": {"user_info": user_info, "updated_at": now}},
            )
            # keep your key assignment
            assigned_key = assign_key_to_session(last_session["session_id"])
            if assigned_key is None:
                return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INTERNAL_SERVER_ERROR)
            return {"code": HTTP_STATUS.OK, "data": {"session_id": last_session["session_id"]}}

    # new session path unchanged, but uses utc/clean ints
    session_id = await get_unique_session_id()
    assigned_key = assign_key_to_session(session_id)
    if assigned_key is None:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INTERNAL_SERVER_ERROR)

    sessions.insert_one({
        "session_id": session_id,
        "user_id": user_id,
        "user_type": user_type,
        "user_info": user_info,
        "org_id": org_id,
        "timestamp": now,
        "expire_timestamp": expire_time,
        "current_web_session_id": current_web_session_id,
        "isAsm": isAsm,
        "memory_clean_status": False
    })
    return {"code": HTTP_STATUS.OK, "data": {"session_id": session_id}}

async def robot_authenticate_and_create_session(
    api_key, user_id, current_web_session_id, user_info=None, user_type=0, isAsm=0, new_chat=False
):
    # ✨ Projection: fetch only what you use
    org = org_collection.find_one({"api_key": api_key}, {"_id": 1})
    if not org:
        return {"code": HTTP_STATUS.UNAUTHORIZED, "message": MESSAGE.INVALID_API_KEY}
    org_id = str(org["_id"])

    # ✨ Normalize once
    user_info = user_info or {}
    user_type = int(user_type) if isinstance(user_type, (int, str)) else 0

    now = utcnow()
    expire_time = now + timedelta(minutes=TOKEN_EXPIRE_ROBOT)

    # --- user upsert kept as your two-step, but with projections ---
    existing_user = users.find_one(
        {"user_id": user_id, "user_type": user_type, "org_id": org_id},
        {"_id": 1,"pin": 1,"auth_status":1}
    )
    
    decoded_id= decode_user_id(user_id)
    arn_value = decoded_id.split("ARN|")[-1]   # take the part after ARN|
    if existing_user:
        update_fields = {
            "user_info": user_info,
            "updated_at": now,
            "arn_id": int(arn_value),
        }
        if not existing_user.get("pin"):
            update_fields["pin"] = generate_4digit_pin()
        
        if not existing_user.get("auth_status"):
            update_fields["auth_status"] = True

        users.update_one(
            {"_id": existing_user["_id"]},
            {"$set": update_fields},
        )
    else:
        users.insert_one({
            "user_id": user_id,
            "user_info": user_info,
            "user_type": user_type,
            "created_at": now,
            "updated_at": now,
            "org_id": org_id,
            "arn_id":int(arn_value),
            "pin": generate_4digit_pin(),
            "auth_status": True,
        })

    if not new_chat:
        # ✨ Only fields needed; sort uses index if present
        last_session = sessions.find_one(
            {
                "user_id": user_id,
                "user_type": user_type,
                "org_id": org_id,
                "current_web_session_id": current_web_session_id,
                "expire_timestamp": {"$gt": now},
            },
            sort=[("timestamp", -1)],
            projection={"session_id": 1, "_id": 1}
        )
        if last_session:
            # ✨ combine update to avoid second read
            sessions.update_one(
                {"_id": last_session["_id"]},
                {"$set": {"user_info": user_info, "updated_at": now}},
            )
            # keep your key assignment
            assigned_key = assign_key_to_session(last_session["session_id"])
            if assigned_key is None:
                return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INTERNAL_SERVER_ERROR)
            return {"code": HTTP_STATUS.OK, "data": {"session_id": last_session["session_id"]}}

    # new session path unchanged, but uses utc/clean ints
    session_id = await get_unique_session_id()
    assigned_key = assign_key_to_session(session_id)
    if assigned_key is None:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INTERNAL_SERVER_ERROR)

    sessions.insert_one({
        "session_id": session_id,
        "user_id": user_id,
        "user_type": user_type,
        "user_info": user_info,
        "org_id": org_id,
        "timestamp": now,
        "expire_timestamp": expire_time,
        "current_web_session_id": current_web_session_id,
        "isAsm": isAsm,
        "memory_clean_status": False
    })
    return {"code": HTTP_STATUS.OK, "data": {"session_id": session_id}}


# for org create
async def signup_organization(data: dict) -> dict:
    existing = org_collection.find_one(
        {"email": data["email"]}
    )
    if existing:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.ORG_ALREADY_EXIST
        )
    api_key = await get_unique_api_key()
    random_password = generate_random_password()
    hashed_password = hash_password(random_password)
    org_name= data["org_name"]
    org_code  =await get_unique_org_code(org_name)
    collectionName  = f"org_{org_code}_Logs"
    org_data = {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "org_name": data["org_name"],
        "address": data["address"],
        "mobile": data["mobile"],
        "email": data["email"],
        "api_key": api_key,
        "org_code": org_code,
        "collectionName": collectionName,
        "status": "active",
        "password": hashed_password,
        "created_at": datetime.now(),
    }

    try:
        result = org_collection.insert_one(org_data)
        data = {
            "org_id": str(result.inserted_id),
            "api_key": org_data["api_key"],
            "random_password": random_password,
        }
        return api_response(code=HTTP_STATUS.OK, message=MESSAGE.ORG_CREATED, data=data)
    except Exception as e:
        log_error(f"error---: {e}")
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.failed_org(e))


#get collection name from session id  
def get_org_collection_name_from_session(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if not session:
        return None

    org_id = session.get("org_id")
    if not org_id:
        return None

    # Try both str and ObjectId for robustness
    org = org_collection.find_one({"_id": org_id}) or org_collection.find_one({"_id": ObjectId(org_id)})
    if not org:
        return None

    collection_name = org.get("collectionName")
    if not collection_name:
        return None

    return db[collection_name]



#get collection name from session id  
async def async_get_org_collection_name_from_session(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if not session:
        return None

    org_id = session.get("org_id")
    if not org_id:
        return None

    # Try both str and ObjectId for robustness
    org = org_collection.find_one({"_id": org_id}) or org_collection.find_one({"_id": ObjectId(org_id)})
    if not org:
        return None

    collection_name = org.get("collectionName")
    if not collection_name:
        return None

    return db[collection_name]

async def get_session_details(session_id: str):
    session = sessions.find_one({"session_id": session_id})
    if not session:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.INVALID_SESSION_ID
        )
    # Convert ObjectId to string if you want to return it
    session["_id"] = str(session["_id"])
    return api_response(code=HTTP_STATUS.OK, data={"session_id": session_id})


async def get_unique_org_code(org_name):
    while True:
        org_code = generate_org_code(org_name)
        if not org_collection.find_one({"org_code": org_code}):
            return org_code

async def get_unique_api_key():
    while True:
        api_key = generate_api_key()
        if not org_collection.find_one({"api_key": api_key}):
            return api_key


async def get_unique_session_id():
        ts = int(time.time()*1000)
        session_id = generate_session_id()
        return f"{session_id}{ts}"


async def get_unique_message_id():
        ts = int(time.time()*1000)
        message_id = generate_message_id()
        return f"{message_id}{ts}"

async def get_users_by_org(org_id: str, offset: int = 0, limit: int = 20):
    users_cursor = users.find({"org_id": org_id}).sort("created_at", -1).skip(offset).limit(limit)
    users_list = [serialize_mongo_doc(u) for u in users_cursor]
    user_len = len(users_list)
    data = {
         "user_len":user_len,
        "users_list":users_list,
       
    }
    return api_response(code=HTTP_STATUS.OK, data=data)

async def get_users_by_org_with_chatonly(org_id: str,  offset: int = 0, limit: int = 20):
    chat_col_name = _get_logs_collection_name_for_org(org_id)
    """
    Return users for this org who (1) have sessions and (2) those sessions have chat logs in `chat_col_name`.
    Sorted by the latest session timestamp (DESC), paginated.
    """
    pipeline = [
        # sessions for this org
        {"$match": {"org_id": org_id}},

        # join chat logs on session_id
        {"$lookup": {
            "from": chat_col_name,              # e.g. "org_WEA-3567-6284-AI_Logs"
            "localField": "session_id",
            "foreignField": "session_id",
            "as": "chats"
        }},

        # keep only sessions that have at least one chat
        {"$match": {"chats.0": {"$exists": True}}},

        # group by user_id to dedupe; capture latest session timestamp
        {"$group": {
            "_id": "$user_id",
            "last_session_ts": {"$max": "$timestamp"}
        }},

        # join back to users to fetch user record (and ensure same org)
        {"$lookup": {
            "from": "users",
            "let": {"uid": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$user_id", "$$uid"]},
                            {"$eq": ["$org_id", org_id]}
                        ]
                    }
                }}
            ],
            "as": "user"
        }},

        # only keep rows where a user doc exists
        {"$match": {"user.0": {"$exists": True}}},

        # flatten user
        {"$project": {
            "_id": 0,
            "user_id": "$_id",
            "last_session_ts": 1,
            "user": {"$arrayElemAt": ["$user", 0]}
        }},

        # sort by latest session desc
        {"$sort": {"last_session_ts": -1}},

        # paginate
        {"$skip": offset},
        {"$limit": limit},

        # final shape you want to return
        {"$project": {
            "user_id": 1,
            "last_session_ts": 1,
            "user_info": "$user.user_info",
            "user_type": "$user.user_type",
            "org_id": "$user.org_id",
            "created_at": "$user.created_at",
            "updated_at": "$user.updated_at"
        }}
    ]

    rows = list(sessions.aggregate(pipeline))
    # serialize datetimes/ObjectIds safely
    data = [serialize_mongo_doc(r) for r in rows]
    user_len = len(data)
    data_get = {
         "user_len":user_len,
        "users_list":data,
       
    }
    return api_response(code=HTTP_STATUS.OK, data=data_get)


async def get_sessions_by_users(org_id:str,user_id: str, offset: int = 0, limit: int = 20):
    users_cursor = sessions.find({"user_id": user_id,"org_id":org_id}).sort("timestamp",-1).skip(offset).limit(limit)
    sessions_list = [serialize_mongo_doc(u) for u in users_cursor]
    return api_response(code=HTTP_STATUS.OK, data=sessions_list)

async def get_chat_by_session(session_id: str):
    collection_name =await async_get_org_collection_name_from_session(session_id)
     
    users_cursor = collection_name.find({"session_id": session_id}).sort("timestamp",-1)
    chat_list = [serialize_mongo_doc(u) for u in users_cursor]
    return api_response(code=HTTP_STATUS.OK, data=chat_list)


   # ----------------  SAVE like / dislike ----------------



async def activate_deactivate_org(org_id: str, status: int):
    """
    status =  1   → activate
    status =  0    → deactivate
    """
    status =  'active' if status else 'deactive'
    try:
        
        doc = org_collection.find_one_and_update(
            {"_id": ObjectId(org_id)},                 # unique id of the message
            {
                "$set": {
                    "status": status,         # flat field
                    "updated_at": datetime.now()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        if doc is None:
            return api_response(code=HTTP_STATUS.BAD_REQUEST)

        return api_response(code=HTTP_STATUS.OK,message=MESSAGE.UPDATED)

    except Exception as e:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR,message=str(e))
    
    

def get_org_and_arn_by_user_id(user_id: str) -> dict:
    org_id = None
    arn_id = None
    user_data = users.find_one({"user_id": user_id}, {"org_id": 1, "arn_id": 1, "_id": 0})
    if user_data:
        org_id = user_data.get("org_id")
        arn_id = user_data.get("arn_id")
    return org_id,arn_id


def get_pin_and_auth_by_user_id(user_id: str) -> dict:
    pin = None
    auth_status = None
    user_data = users.find_one({"user_id": user_id}, {"pin": 1, "auth_status": 1, "_id": 0})
    if user_data:
        pin = user_data.get("pin")
        auth_status = user_data.get("auth_status")
    return pin,auth_status

def to_aware_utc(dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
       
    if dt is None:
        return None
    if isinstance(dt, str):
        # Handle "Z" and no offset variants
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    # datetime case
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)  # treat naive as UTC
    return dt.astimezone(UTC)



def get_last_auth_time(session_id: str) -> Optional[datetime]:
    """
    Fetch and normalize last_auth_time for given session.
    """
    doc = sessions.find_one({"session_id": session_id}, {"last_auth_time": 1, "_id": 0})
    if not doc:
        return None
    return to_aware_utc(doc.get("last_auth_time"))

def update_last_auth_time(session_id: str, when: Optional[datetime] = None) -> None:
    """
    Sets last_auth_time on the session (updating updated_at as well).
    """
    ts = to_aware_utc(when) or utcnow()
    sessions.update_one(
        {"session_id": session_id},
        {"$set": {"last_auth_time": ts, "updated_at": ts}}
    )
     
    
    
