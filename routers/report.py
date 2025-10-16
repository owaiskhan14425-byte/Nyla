from fastapi import APIRouter,Request,Query
from utils.helpers import api_response,HTTP_STATUS,get_session_id_from_token,MESSAGE,decode_user_id
from services.report_service import get_session_conversations
from services.mongo_client import is_valid_session
from services.log_reader import read_log_as_json,search_log_by_session_id
from services.feedback_service import get_user_id_by_session,get_isAsm_by_session

router = APIRouter()


@router.get("/session-conversations")
async def session_conversations(request: Request, limit: int = Query(10, ge=1, le=100)):
    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response

    if not session_id:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN)
     
    if not is_valid_session(session_id):
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.INVALID_SESSION_ID)
    
    user_id = get_user_id_by_session(session_id)
    decoded_id= decode_user_id(user_id)
    arn_value = decoded_id.split("ARN|")[-1]   # take the part after ARN|
    # 4. Fetch conversation history (service layer)
    
    isAsm = get_isAsm_by_session(session_id)
    
    history =await get_session_conversations(session_id, limit)
    return api_response(code=HTTP_STATUS.OK, data={"conversations": history,'arn':arn_value,'isAsm':isAsm})


@router.get("/logs")
def get_logs(limit: int = Query(100, description="Number of recent logs to return (max 1000)")):
    log_path = "logs/rag.log"  # Path to your log file
    logs = read_log_as_json(log_path, limit=min(limit, 1000))
    return api_response(code=HTTP_STATUS.OK, data=logs)


@router.get("/logs/search")
def search_logs_by_session(session_id: str = Query(..., description="Session ID to filter logs"), limit: int = Query(100, description="Max logs to return")):
    log_path = "logs/rag.log"
    logs = search_log_by_session_id(log_path, session_id, limit=min(limit, 1000))
    return api_response(code=HTTP_STATUS.OK, data=logs)







