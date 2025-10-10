from fastapi import APIRouter, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from utils.metrics import ask_from_rag, rag_ask_latency
from utils.helpers import get_session_id_from_token
from datetime import datetime
from services.rag_services import (
    rag_ask,
    reset_user_conversation,
    remove_user_buffers,
    get_buffer,
    get_all_buffers,
    user_buffers,
    add_chat,
    robot_rag_ask,
)
from services.mongo_client import (
    is_valid_session,
)
from utils.constants import HTTP_STATUS, MESSAGE,FACE_AUTH_TIME_RESET
from utils.helpers import api_response
from utils.jwt_utils import get_jwt_payload
from utils.key_manager import decrement_key_for_session
from utils.key_manager import get_session_key_map, get_key_usage_stats
from services.session_cleanup import cleanup_expired_sessions
import time
from typing import Optional
from services.org_service import get_pin_and_auth_by_user_id,get_last_auth_time,update_last_auth_time,utcnow
from services.feedback_service import get_user_id_by_session

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str
    lang: Optional[str] = None


class AddChatRequest(BaseModel):
    question: str
    answer: str
    flag: str


@router.post("/ask")
async def ask(request: Request, data: QuestionRequest):
    ask_from_rag.inc()  # increment counter
    start = time.perf_counter()  # start timer

    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response

    if not session_id:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN
        )

    if not is_valid_session(session_id):
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.INVALID_SESSION_ID
        )
    try:
        answer, message_id = await rag_ask(
            session_id, data.question.strip(), user_info=user_info
        )
    except ValueError as ve:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=str(ve))
    except Exception as ex:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=str(ex))
    finally:
        duration = time.perf_counter() - start
        rag_ask_latency.observe(duration)  # record latency
    if not answer:
        return api_response(
            code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=MESSAGE.INTERNAL_ERROR
        )
    return api_response(
        code=HTTP_STATUS.OK, data={"answer": answer, "message_id": message_id}
    )


@router.post("/ask-robot")
async def ask(request: Request, data: QuestionRequest):

    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response

    if not session_id:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN)
    if not is_valid_session(session_id):
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.INVALID_SESSION_ID)
    try:
        answer,label,used_tools, message_id, auth_status_from_model= await robot_rag_ask(
            session_id, data.question.strip(), user_info=user_info)
    except ValueError as ve:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=str(ve))
    except Exception as ex:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=str(ex))
    if not answer:
        return api_response(
            code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=MESSAGE.INTERNAL_ERROR
        )
    user_id = get_user_id_by_session(session_id)
    pin,auth_status_user = get_pin_and_auth_by_user_id(user_id)
    
    auth = False
    diff_minutes =0
    if auth_status_user is True:
        if auth_status_from_model is True:
            last_auth_time = get_last_auth_time(session_id)
            now = utcnow()
            if last_auth_time:
                diff_minutes = (now - last_auth_time).total_seconds() / 60.0
            else:
                # No previous auth -> treat as expired to allow this auth
                diff_minutes = FACE_AUTH_TIME_RESET + 1

            if diff_minutes > FACE_AUTH_TIME_RESET:
                auth = True
                update_last_auth_time(session_id, now)
            else:
                auth = False
        else:
            auth = False
    else:
        # user-level toggle disables auth requirement => you wanted final False here
        # (keeping your original behavior: auth = auth_status_user)
        auth = bool(auth_status_user)
    
    data  = {
        "answer": answer,
        "label":label, 
        "used_tools":used_tools, 
        "message_id": message_id,
        "pin": pin,
        "auth": auth,
        "diff_minutes": diff_minutes,
    }
    return api_response(
        code=HTTP_STATUS.OK, data=data
    )


@router.post("/add-chat")  # ask user question
async def add_chats(request: Request, data: AddChatRequest):
    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response

    if not session_id:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN
        )

    if not is_valid_session(session_id):
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.INVALID_SESSION_ID
        )

    await add_chat(session_id, data.question.strip(), data.answer.strip(), data.flag)
    return api_response(code=HTTP_STATUS.OK)


@router.post("/reset")  # reset particular session_is
async def reset_conversation(request: Request):
    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response
    reset_user_conversation(session_id)
    return api_response(code=HTTP_STATUS.OK, message="conversation reset")


@router.post("/disconnect")  # remove session_id from user buffers
async def disconnect(request: Request):
    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response
    decrement_key_for_session(session_id)
    remove_user_buffers(session_id)
    return api_response(code=HTTP_STATUS.OK, message=f"Buffer cleared for {session_id}")


@router.post("/debug/clear-all-buffers")  # clear all buffer memory
def clear_all_buffers():
    user_buffers.clear()
    return api_response(code=HTTP_STATUS.OK, message="All buffer memories cleared")


@router.get("/debug/buffers")  # get all buffers
def show_all_buffers():
    data = get_all_buffers()
    return api_response(code=HTTP_STATUS.OK, data=data)


@router.get("/debug/buffer/{session_id}")  # get buffer for session_id
def show_user_buffer(session_id: str):
    buffer = get_buffer(session_id)
    return api_response(code=HTTP_STATUS.OK, data={"buffer": buffer})


@router.post(
    "/cleanup/expired-sessions"
)  # Cleanup expired sessions (remove buffer + key if expired)
def cleanup_expired_sessions_route():
    result = cleanup_expired_sessions()

    if result["error"]:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST,
            message=f"Unexpected cleanup failure: {result['error']}",
        )

    if result["cleared_sessions"] and result["failed_sessions"]:
        return api_response(
            code=HTTP_STATUS.OK,
            status="error",
            message=MESSAGE.CLEANUP_PARTIAL_FAILED,
            data=result,
        )

    elif result["cleared_sessions"]:
        return api_response(
            code=HTTP_STATUS.OK, message=MESSAGE.CLEANUP_SUCCESS, data=result
        )

    elif not result["cleared_sessions"] and not result["failed_sessions"]:
        return api_response(
            code=HTTP_STATUS.OK, message=MESSAGE.CLEANUP_NONE_FOUND, data=result
        )

    else:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST,
            message=MESSAGE.CLEANUP_ALL_FAILED,
            data=result,
        )


"""Open AI Key check"""


@router.get("/debug/session-keys")
def debug_session_keys():
    """
    Shows which session_id is using which OpenAI key.
    """
    data = get_session_key_map()
    return api_response(code=HTTP_STATUS.OK, data=data)


@router.get("/debug/key-usage")
def debug_key_usage():
    """
    Shows how many sessions are using each OpenAI key.
    """
    data = get_key_usage_stats()
    return api_response(code=HTTP_STATUS.OK, data=data)
