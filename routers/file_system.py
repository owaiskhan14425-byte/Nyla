from fastapi import APIRouter, UploadFile, File,Depends,Form
from pydantic import BaseModel
from typing import List
from services import file_service
from services.file_service import (
    get_uploaded_file_metadata,
    check_files_existence,
    get_unique_question_metadata,
    get_pdf_files_info_from_disk,
    delete_single_uploaded_file,
    remove_vectorstore_dir
)
import os
from services.vectorstore_loader import retrain_and_replace_vectorstore
from services.vectorstore_singleton import reload_vectorstore
from utils.constants import MAX_FILE_SIZE_BYTES,HTTP_STATUS,MESSAGE
from utils.helpers import api_response
from utils.deps import jwt_required
from services.mongo_client import rag_files
from services.file_service import handle_image_storage, get_all_images
from utils.helpers import api_response
from utils.constants import HTTP_STATUS, MESSAGE
from services.file_service import delete_multiple_face_images,get_images_grouped_by_folder

 

router = APIRouter()

class DeleteImagesRequest(BaseModel):
    image_ids: List[str]
    


#for face image start

@router.post("/delete-multiple-images")
async def delete_multiple_images(
    data: DeleteImagesRequest,
    token: dict = Depends(jwt_required)
):
    """
    Delete multiple face images for the authenticated user.
    """
    user_id = token.get("user_id")
    if not user_id:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_TOKEN)
    # Check if image is provided
    if not data.image_ids:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.IMAGE_REQUIRED)
    try:
        result = delete_multiple_face_images(user_id, data.image_ids)
        return api_response(
            code=HTTP_STATUS.OK,
            message=MESSAGE.IMAGE_DELETED_SUCCESS,
            data=result
        )
    except Exception as e:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=str(e))

@router.post("/upload-image")
async def upload_image(
    token: str = Depends(jwt_required),
    image: UploadFile = File(...),
    folder_name: str = Form(...),  
):
    # Get the user_id from the JWT token
    user_id = token["user_id"]
    if not user_id:
        return api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_TOKEN)
   
    # Check if image is provided
    if not image:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.IMAGE_REQUIRED)
    
    if not folder_name.strip():
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.FOLDER_REQUIRED)
    
    try:
        # Handle the image storage logic (check if already exists, replace if needed)
        result = handle_image_storage(image, user_id,folder_name.strip())

        # Return success response
        return api_response(code=HTTP_STATUS.OK, data=result)
    
    except Exception as e:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=f"Error: {str(e)}")

# ----------------------
# Image Retrieval Endpoint
# ----------------------
@router.get("/get-face")
async def get_images(token: dict = Depends(jwt_required)):
    """Return user's images grouped by folder."""
    user_id = token.get("user_id")

    if not user_id:
        return api_response(
            code=HTTP_STATUS.UNAUTHORIZED,
            message=MESSAGE.INVALID_TOKEN
        )

    try:
        data = get_images_grouped_by_folder(user_id)

        if not data["images"]:
            return api_response(
                code=HTTP_STATUS.OK,
                message=MESSAGE.IMAGE_NOT_FOUND,
                data={"images": []}
            )

        return api_response(
            code=HTTP_STATUS.OK,
            data=data
        )

    except Exception as e:
        return api_response(
            code=HTTP_STATUS.INTERNAL_SERVER_ERROR,
            message=f"Error: {str(e)}"
        )
 
#for face image end

# ----------------------
# Delete files endpoint
# ----------------------
class DeleteRequest(BaseModel):
    file_id:str
    org_id :str

@router.post("/delete-files")
async def delete_files(request: DeleteRequest):
    org_id = request.org_id
    result = delete_single_uploaded_file(org_id, request.file_id)
    if not result["ok"]:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=result["reason"])

    # After delete, check if any files remain for this org
    remaining = rag_files.count_documents({"org_id": org_id})
    if remaining > 0:
        created = retrain_and_replace_vectorstore(org_id)
        print(created)
        if created:
            reload_vectorstore(org_id)
            msg = f"File deleted, retrained index. Remaining files: {remaining}."
        else:
            # No valid docs got indexed (e.g., all files unsupported/empty)
            remove_vectorstore_dir(org_id)  # ensure no stale index dir
            msg = "File deleted. No valid documents to index; index cleared."
    else:
        # No files left → ensure the index dir is removed and skip reload
        remove_vectorstore_dir(org_id)
        msg = "File deleted. No files remain; index cleared."

    return api_response(code=HTTP_STATUS.OK, data={"deleted": request.file_id}, message=msg)
    


# ----------------------
# Upload file endpoint
# ----------------------
@router.post("/upload-file")
async def upload_file(org_id: str = File(...), file: UploadFile = File(...)):
    original_filename = file.filename

    if not file_service.is_allowed_file(original_filename):
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.WRONG_EXTENSION)
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.FILE_TOO_LARGE)

    upload_dir = file_service.get_org_upload_dir(org_id)
    new_filename = file_service.generate_custom_filename(original_filename)
    file_path = os.path.join(upload_dir, new_filename)
    with open(file_path, "wb") as buffer:
        buffer.write(file_bytes)

    file_service.save_file_metadata(new_filename, original_filename, org_id)
    retrain_and_replace_vectorstore(org_id)
    reload_vectorstore(org_id)

    data = {
        "original_filename": original_filename,
        "stored_filename": new_filename,
        "org_id": org_id,
    }
    return api_response(code=HTTP_STATUS.OK, data=data)

# ----------------------
# List uploaded files endpoint
# ----------------------
@router.get("/uploaded-files")
async def list_uploaded_files(org_id: str):
    metadata_list = [f for f in get_uploaded_file_metadata() if f.get("org_id") == org_id]
    files_list = check_files_existence(metadata_list, org_id)
    return api_response(code=HTTP_STATUS.OK, data=files_list)


@router.get("/unique_question")
async def list_unique_question():
    metadata_list = get_unique_question_metadata()
    return api_response(code=HTTP_STATUS.OK,data=metadata_list)

@router.get("/pdf-files-info")
async def get_pdf_files_info():
    try:
        info = get_pdf_files_info_from_disk()
        return api_response(
            data=info,
            code=HTTP_STATUS.OK,
            message=f"{info['count']} PDF file(s) found."
        )
    except Exception as e:
        return api_response(
            code=HTTP_STATUS.INTERNAL_SERVER_ERROR,
            message="Failed to retrieve PDF files.",
            data={"error": str(e)}
        )