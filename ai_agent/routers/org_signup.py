from fastapi import APIRouter, HTTPException,Header,Query,Depends,Form
from pydantic import BaseModel, EmailStr, Field, constr
from services.org_service import robot_authenticate_and_create_session, authenticate_and_create_session,get_session_details,authenticate_super_admin,get_org_list,org_login_service,org_login_service_bypass,get_users_by_org,get_sessions_by_users,get_chat_by_session,activate_deactivate_org,get_users_by_org_with_chatonly,signup_organization,update_pin_by_user_id
from utils.constants import MESSAGE,HTTP_STATUS,FRONTEND_URL,TOKEN_EXPIRE, TOKEN_EXPIRE_ROBOT
from utils.helpers import api_response,aes_decrypt,aes_encrypt
from utils.jwt_utils import create_access_token
from utils.deps import jwt_required
import json
from fastapi.responses import RedirectResponse
from datetime import datetime
from typing import Optional
from utils.metrics import org_auth_requests
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
def utcnow(): return datetime.now(UTC)

router = APIRouter()

class ChangePinRequest(BaseModel):
    # exactly 4 digits, zero-padded allowed (e.g., "0073")
    new_pin: constr(pattern=r'^\d{4}$') = Field(..., description="4-digit PIN")

class OrgSignupRequest(BaseModel):
    first_name: str 
    last_name: str
    org_name: str
    address: str
    mobile: str
    email: EmailStr
 
    
class OrgLoginRequest(BaseModel):
    email: str
    password: str
    
    
class OrgLoginRequestBypass(BaseModel):
    email: str

class OrgActDeactive(BaseModel):
    org_id: str
    status: int
    

# Super Admin Login Request Body
class SuperLoginRequest(BaseModel):
    email: EmailStr
    password: str
    tokenLoginPlatform: str  # 'web', 'android', 'ios'
    
    
    
@router.post("/pin-change")
async def change_my_pin(
    data: ChangePinRequest,
    user: dict = Depends(jwt_required)
):
    user_id = user.get("user_id")
    if not user_id:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_TOKEN)

    ok, reason = update_pin_by_user_id(user_id=user_id, new_pin=data.new_pin)
    if not ok:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=reason)

    return api_response(code=HTTP_STATUS.OK, message="PIN updated successfully")
 

@router.get("/orgs-list")
async def get_organizations(user=Depends(jwt_required)):
    if user["user_type"] != "superAdmin":  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    organizations = await get_org_list()
    return api_response(code=HTTP_STATUS.OK,data=organizations)
    
# Super Admin Login Endpoint
@router.post("/super-admin/login")
async def super_admin_login(request: SuperLoginRequest):
    # Call the service to authenticate and generate JWT token
    result = await authenticate_super_admin(request)
    if result["success"]:
       return api_response(data=result["data"],code=HTTP_STATUS.OK,message=result["message"])
    else:
       return api_response(code=HTTP_STATUS.BAD_REQUEST,message=result["message"])
    
    
@router.post("/org-login")
async def org_login(request: OrgLoginRequest):
    res = await org_login_service(request.email, request.password)
    return res


@router.post("/org-login-bypass")
async def org_login(request: OrgLoginRequestBypass,user=Depends(jwt_required)):
    if user["user_type"] != "superAdmin":  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    res = await org_login_service_bypass(request.email)
    return res

@router.post("/org-activate-deactivate")
async def org_login(request: OrgActDeactive,user=Depends(jwt_required)):
    if user["user_type"] != "superAdmin":  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    res = await activate_deactivate_org(request.org_id, request.status)
    return res


@router.get("/users-list")
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=5000),
    user=Depends(jwt_required)
):
    if not user["org_id"]:  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    org_id = user["org_id"]
    users =await get_users_by_org(org_id, offset=offset, limit=limit)
    return users


@router.get("/users-list-with-chatonly")
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=5000),
    user=Depends(jwt_required)
):
    if not user["org_id"]:  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    org_id = user["org_id"]
    users =await get_users_by_org_with_chatonly(org_id, offset=offset, limit=limit)
    return users


@router.get("/sessions-list")
async def list_sessions(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    user_id: str = Query(...),
    user=Depends(jwt_required)
):
    if not user["org_id"]:  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    org_id = user["org_id"]
    sessions =await get_sessions_by_users(org_id,user_id, offset=offset, limit=limit)
    return sessions

@router.get("/chat-list")
async def list_sessions(
    session_id: str = Query(...),
    user=Depends(jwt_required)
):
    if not user["org_id"]:  # Check if user is Super Admin
        return api_response(code=HTTP_STATUS.UNAUTHORIZED,message=MESSAGE.INVALID_TOKEN)
    chats =await get_chat_by_session(session_id)
    return chats


@router.post("/signup-org")
async def signup_org(request: OrgSignupRequest):
    result = await signup_organization(request.model_dump())
    return result




@router.post("/encrypt")
async def encrypt(api_key: str = Form(...),
    data: str = Form(...)):
    encrypted_json = aes_encrypt(data, api_key)
    return encrypted_json

@router.post("/auth")
async def auth_user(
    api_key: str = Form(...),
    encrypted_data: str = Form(...),
    new_chat: Optional[bool] = Form(False)
):
    org_auth_requests.inc()   # increment counter
    if not api_key:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.API_KEY_MISSING)

    if not encrypted_data:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.ENCRYPTED_DATA_MISSING)

    try:
        decrypted_json = aes_decrypt(encrypted_data, api_key)
        user_data = json.loads(decrypted_json) if isinstance(decrypted_json, str) else decrypted_json
        if isinstance(user_data, str):
            user_data = json.loads(user_data)
    except Exception as e:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=f"AES decryption failed: {str(e)}")

    #  Normalize once
    user_id   = (user_data.get("user_id") or "000").strip()
    user_info = user_data.get("user_info") or {}
    user_type = int(user_data.get("user_type") or 0)
    isAsm     = user_data.get("isAsm", 0)
    current_web_session_id = user_data.get("current_web_session_id") or ("current_web_session_id_" + utcnow().strftime("%Y%m%d%H%M%S"))

    # unchanged call
    result = await authenticate_and_create_session(
        api_key,
        user_id,
        user_info=user_info,
        user_type=user_type,
        current_web_session_id=current_web_session_id,
        isAsm=isAsm,
        new_chat=new_chat,
    )

    if result["code"] != HTTP_STATUS.OK:
        return api_response(code=result["code"], message=result["message"])

    session_id = result["data"]["session_id"]

    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "user_type": user_type
    }
    token = create_access_token(payload, TOKEN_EXPIRE)

    frontend_url = f"{FRONTEND_URL}?token={token}"
    return RedirectResponse(url=frontend_url, status_code=302)

    
 
@router.post("/auth-test")
async def auth_user(
    api_key: str = Form(...),
    encrypted_data: str = Form(...),
    new_chat: Optional[bool] = Form(False)
):
    if not api_key:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.API_KEY_MISSING)

    if not encrypted_data:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.ENCRYPTED_DATA_MISSING)

    try:
        decrypted_json = aes_decrypt(encrypted_data, api_key)
        #  Avoid double json.loads; handle both dict/str safely
        user_data = json.loads(decrypted_json) if isinstance(decrypted_json, str) else decrypted_json
        if isinstance(user_data, str):
            user_data = json.loads(user_data)
    except Exception as e:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=f"AES decryption failed: {str(e)}")

    #  Normalize once
    user_id   = (user_data.get("user_id") or "000").strip()
    user_info = user_data.get("user_info") or {}
    user_type = int(user_data.get("user_type") or 0)
    isAsm     = user_data.get("isAsm", 0)
    current_web_session_id = user_data.get("current_web_session_id") or ("current_web_session_id_" + utcnow().strftime("%Y%m%d%H%M%S"))

    # unchanged call
    result = await authenticate_and_create_session(
        api_key,
        user_id,
        user_info=user_info,
        user_type=user_type,
        current_web_session_id=current_web_session_id,
        isAsm=isAsm,
        new_chat=new_chat,
    )

    if result["code"] != HTTP_STATUS.OK:
        return api_response(code=result["code"], message=result["message"])

    session_id = result["data"]["session_id"]

    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "user_type": user_type
    }
    token = create_access_token(payload, TOKEN_EXPIRE)
    
    return token
    
@router.post("/auth-test-robot")
async def auth_user(
    api_key: str = Form(...),
    encrypted_data: str = Form(...),
    new_chat: Optional[bool] = Form(False)
):
    if not api_key:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.API_KEY_MISSING)

    if not encrypted_data:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.ENCRYPTED_DATA_MISSING)

    try:
        decrypted_json = aes_decrypt(encrypted_data, api_key)
        #  Avoid double json.loads; handle both dict/str safely
        user_data = json.loads(decrypted_json) if isinstance(decrypted_json, str) else decrypted_json
        if isinstance(user_data, str):
            user_data = json.loads(user_data)
    except Exception as e:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=f"AES decryption failed: {str(e)}")

    #  Normalize once
    user_id   = (user_data.get("user_id") or "000").strip()
    user_info = user_data.get("user_info") or {}
    user_type = int(user_data.get("user_type") or 0)
    isAsm     = user_data.get("isAsm", 0)
    current_web_session_id = user_data.get("current_web_session_id") or ("current_web_session_id_" + utcnow().strftime("%Y%m%d%H%M%S"))

    # unchanged call
    result = await robot_authenticate_and_create_session(
        api_key,
        user_id,
        user_info=user_info,
        user_type=user_type,
        current_web_session_id=current_web_session_id,
        isAsm=isAsm,
        new_chat=new_chat,
    )

    if result["code"] != HTTP_STATUS.OK:
        return api_response(code=result["code"], message=result["message"])

    session_id = result["data"]["session_id"]

    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "user_type": user_type
    }
    token = create_access_token(payload, TOKEN_EXPIRE_ROBOT)
    
    return token
 
@router.get("/session-details")
async def session_details(session_id: str = Query(...),
#user=Depends(jwt_required),
):
    details = await get_session_details(session_id)
    
    return details



