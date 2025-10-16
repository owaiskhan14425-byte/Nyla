# routers/feedback.py

from fastapi import APIRouter, HTTPException, Request, Query, Body, Depends
from pydantic import BaseModel, Field, EmailStr
from services.feedback_service import (
    get_user_id_by_session,
    undo_dislike_feedback,
    save_feedback,
    feedback_exists,
    save_dislike_feedback,
    get_feedbacks_by_user_ids,
    get_feedback_stats,
    save_requirement,
    get_feedbacks_by_org,
)
from utils.helpers import get_session_id_from_token, api_response
from services.org_service import async_get_org_collection_name_from_session
from utils.constants import HTTP_STATUS, MESSAGE
from typing import List, Optional
from utils.deps import jwt_required

router = APIRouter()


class FeedbackRequest(BaseModel):
    rating: int
    review: Optional[str] = ""


class DislikeRequest(BaseModel):
    status: int
    message_id: str
    
class getFeedbacks(BaseModel):
    user_ids: Optional[List[str]] = None  


class RequirementRequest(BaseModel):
    full_name: str
    phone: str
    email: EmailStr
    arn_id: str
    description: Optional[str] = ""
    user_id: str


@router.post("/client_requirement")
def contact_us(data: RequirementRequest):
    try:
        result = save_requirement(data.model_dump())
        if result:
            return api_response(code=HTTP_STATUS.OK, message=MESSAGE.CLIENT_REQUIREMENT)
        else:
            return api_response(
                code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=MESSAGE.INTERNAL_ERROR
            )
    except Exception as e:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=str(e))


class UndoDislikeRequest(BaseModel):
    message_id: str


@router.get("/feedback/average")
def feedback_average(user_id: str = Query(None)):
    stats = get_feedback_stats(user_id)
    return api_response(code=HTTP_STATUS.OK, data=stats)


@router.post("/get-feedbacks")
async def get_feedbacks(
    data: getFeedbacks,
    user=Depends(jwt_required),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    
    if "org_id" not in user:
        return api_response(
            code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_TOKEN
        )
    org_id = user["org_id"]
    feedbacks =await get_feedbacks_by_org(org_id,offset,limit,data.user_ids)
    return feedbacks


@router.post("/save-feedback")
async def post_feedback(request: Request, data: FeedbackRequest):

    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response
    if not session_id:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN
        )

    user_id = get_user_id_by_session(session_id)
    if not user_id:
        return api_response(
            code=HTTP_STATUS.NOT_FOUND, message=MESSAGE.INVALID_SESSION_ID
        )

    # if feedback_exists(session_id):
    #     return api_response(
    #         code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.ALREADY_FEEDBACK_DONE
    #     )

    save_feedback(session_id, data.rating, data.review, user_id)
    return api_response(code=HTTP_STATUS.OK, message=MESSAGE.FEEDBACK_DONE)


@router.post("/like-dislike")
async def submit_dislike(request: Request, data: DislikeRequest):
    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response

    if not session_id:
        return api_response(
            code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN
        )
    collection_name = await async_get_org_collection_name_from_session(session_id)
    result = save_dislike_feedback(
        message_id=data.message_id,
        status=data.status,
        collection_name=collection_name,
    )
    if result["success"]:
        return api_response(code=HTTP_STATUS.OK, message=result["message"])
    else:
        return api_response(
            code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=result["message"]
        )


@router.post("/like-dislike/undo")
async def undo_dislike(request: Request, data: UndoDislikeRequest):
    session_id, user_info, error_response = get_session_id_from_token(request)
    if error_response:
        return error_response

    collection_name = await async_get_org_collection_name_from_session(session_id)
    result = undo_dislike_feedback(data.message_id, collection_name)

    if result["success"]:
        return api_response(code=HTTP_STATUS.OK, message=result["message"])
    else:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=result["message"])
