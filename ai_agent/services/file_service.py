import os
from datetime import datetime
from services.mongo_client import rag_files,unique_question
from bson import ObjectId
from utils.logger import log_error
from utils.constants import UPLOAD_BASE,VECTORSTORE_BASE,MESSAGE
import shutil

from uuid import uuid4
from datetime import datetime
from services.mongo_client import face_images
from utils.constants import IMAGE_STORAGE_BASE_PATH
UPLOAD_FOLDER = "pdf_files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_STORAGE_BASE_PATH, exist_ok=True)

ALLOWED_EXTENSIONS = [".pdf", ".txt", ".docx"]

def _resolve_abs_path(stored_path: str) -> str:
    
    if not stored_path:
        return ""

    p = os.path.normpath(stored_path)

    # If already absolute, return as-is
    if os.path.isabs(p):
        return p

    # If path already begins with the base dir (e.g. 'face_images/...')
    head = p.split(os.sep, 1)[0]
    base_head = os.path.normpath(IMAGE_STORAGE_BASE_PATH)
    if head == base_head or p.startswith(base_head + os.sep):
        return os.path.abspath(p)

    # Otherwise, join with the base dir
    return os.path.abspath(os.path.join(IMAGE_STORAGE_BASE_PATH, p))
    
def _prune_empty_dirs(abs_path: str, user_id: str):
   
    try:
        # leaf folder
        leaf_dir = os.path.dirname(abs_path)
        if os.path.isdir(leaf_dir) and not os.listdir(leaf_dir):
            os.rmdir(leaf_dir)

        # user dir
        user_dir = os.path.join(IMAGE_STORAGE_BASE_PATH, user_id)
        if os.path.isdir(user_dir) and not os.listdir(user_dir):
            os.rmdir(user_dir)
    except Exception:
        pass
    
def delete_multiple_face_images(user_id: str, image_ids: list) -> dict:
    """
    Delete multiple images for this user: delete FILE FIRST, then Mongo doc.
    Returns: {"deleted": [...ids...], "failed": [{"image_id": "...", "reason": "..."}]}
    """
    deleted, failed = [], []

    for img_id in image_ids:
        try:
            try:
                oid = ObjectId(img_id)
            except Exception:
                failed.append({"image_id": img_id, "reason": "Invalid ObjectId"})
                continue

            doc = face_images.find_one({"_id": oid, "user_id": user_id})
            if not doc:
                failed.append({"image_id": img_id, "reason": MESSAGE.IMAGE_NOT_FOUND})
                continue

            stored_path = doc.get("image_path")
            if not stored_path:
                failed.append({"image_id": img_id, "reason": MESSAGE.IMAGE_PATH_MISSING})
                continue

            abs_path = _resolve_abs_path(stored_path)

            # 1) delete the file first
            if not abs_path or not os.path.exists(abs_path):
                failed.append({"image_id": img_id, "reason": "File not found on disk", "path": abs_path})
                continue

            try:
                os.remove(abs_path)
            except Exception as e:
                failed.append({"image_id": img_id, "reason": f"Disk delete error: {e}", "path": abs_path})
                continue

            # 2) if file deletion succeeded, delete Mongo doc
            face_images.delete_one({"_id": oid, "user_id": user_id})
            deleted.append(img_id)

            # 3) prune empty dirs (best-effort)
            _prune_empty_dirs(abs_path, user_id)

        except Exception as e:
            log_error(f"delete_multiple_face_images error: {e}")
            failed.append({"image_id": img_id, "reason": str(e)})

    return {"deleted": deleted, "failed": failed}
# ----------------------
# Function to Save Metadata
# ----------------------
def save_image_metadata(user_id: str, image_path: str, folder_name: str = None) -> None:
    """
    Inserts or replaces image metadata in MongoDB.
    If same user_id + folder_name already exists, replaces previous entry.
    """
    from services.org_service import get_org_and_arn_by_user_id

    org_id, arn_id = get_org_and_arn_by_user_id(user_id)
    now = datetime.now()

    try:
        existing_doc = face_images.find_one({"user_id": user_id, "folder_name": folder_name})

        record = {
            "user_id": user_id,
            "image_path": image_path.replace("\\", "/"),
            "folder_name": folder_name,
            "org_id": org_id,
            "arn_id": arn_id,
            "update_at": now,
        }
        record["created_at"] = now
        face_images.insert_one(record)

    except Exception as e:
        log_error(f"Error saving image metadata for {user_id}: {e}")
        
        
def get_images_grouped_by_folder(user_id: str) -> dict:
    """Fetch all images for a user, grouped by folder_name."""
    from utils.helpers import serialize_mongo_doc
    from utils.logger import log_error

    grouped = {}

    try:
        images = list(face_images.find({"user_id": user_id}))
        for img in images:
            folder = img.get("folder_name") or "default"
            grouped.setdefault(folder, []).append(serialize_mongo_doc(img))
    except Exception as e:
        log_error(f"Error getting grouped images: {e}")
        return {"images": []}

    return {
        "images": [
            {"folder_name": folder, "images": imgs}
            for folder, imgs in sorted(grouped.items(), key=lambda x: x[0].lower())
        ]
    }


# ----------------------
# Function to Handle Image Storage (with Folder)
# ----------------------
def handle_image_storage(image_file, user_id: str, folder_name: str = None) -> dict:
     

    try:
        # Define base directory
        if folder_name:
            upload_dir = os.path.join(IMAGE_STORAGE_BASE_PATH, user_id, folder_name)
        else:
            upload_dir = os.path.join(IMAGE_STORAGE_BASE_PATH, user_id)

        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        file_extension = image_file.filename.split('.')[-1].lower()
        new_filename = f"{uuid4().hex}.{file_extension}"
        file_path = os.path.join(upload_dir, new_filename)

        # Save image to disk
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)

        # Save or update metadata in DB
        save_image_metadata(user_id, file_path, folder_name)

        return {
            "message": MESSAGE.IMAGE_UPLOAD,
            "user_id": user_id,
            "folder_name": folder_name or "default",
            "image_path": file_path.replace("\\", "/"),
        }

    except Exception as e:
        log_error(f"Error in handle_image_storage: {e}")
        return {
            "message": MESSAGE.IMAGE_NOT_UPLOAD,
            "error": str(e),
        }

# ----------------------
# Function to Get All Images for the User
# ----------------------
def get_all_images(user_id: str) -> list:
    from utils.helpers import serialize_mongo_doc
    try:
        images = list(face_images.find({"user_id": user_id}))
        images_list = [serialize_mongo_doc(u) for u in images]
        return images_list
    except Exception as e:
        print(f"Error retrieving images for {user_id}: {e}")
        return []

def is_allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def generate_custom_filename(original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"redvision_{timestamp}{ext}"

def save_file(file_data, new_filename: str) -> str:
    filepath = os.path.join(UPLOAD_FOLDER, new_filename)
    with open(filepath, "wb") as buffer:
        buffer.write(file_data)
    return filepath

def save_file_metadata(stored_filename: str, original_filename: str, org_id: str) -> None:
    rag_files.insert_one({
        "org_id": org_id,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "uploaded_at": datetime.now()
    })

def get_uploaded_file_metadata() -> list:
    return [
        {
            **file,
            "_id": str(file["_id"])  # Convert ObjectId to string for JSON serialization
        }
        for file in rag_files.find()
    ]
    
def get_unique_question_metadata() -> list:
    return [
    {
        **file,
        "_id": str(file["_id"])  # Convert ObjectId to string for JSON serialization
    }
    for file in unique_question.find()
]

def check_files_existence(metadata_list: list, org_id: str) -> list:
    upload_dir = get_org_upload_dir(org_id)
    existing_files = os.listdir(upload_dir)
    return [
        {
            "stored_filename": file.get("stored_filename"),
            "original_filename": file.get("original_filename"),
            "id": file.get("_id"),
            "exists": file.get("stored_filename") in existing_files
        }
        for file in metadata_list
    ]
    

def get_org_upload_folder(org_id: str) -> str:
    return os.path.join(UPLOAD_BASE, f"org_{org_id}")
    

def delete_multiple_uploaded_files(org_id: str, file_ids: list) -> dict:
    successful, failed = [], []

    for file_id in file_ids:
        try:
            try:
                oid = ObjectId(file_id)
            except Exception:
                failed.append({"file_id": file_id, "reason": "Invalid ObjectId"})
                continue

            # Only delete files that belong to the same org
            file_doc = rag_files.find_one({"_id": oid, "org_id": org_id})
            if not file_doc:
                failed.append({"file_id": file_id, "reason": "File not found for this org"})
                continue

            stored_filename = file_doc.get("stored_filename")
            if not stored_filename:
                failed.append({"file_id": file_id, "reason": "Missing stored_filename"})
                continue
            print(stored_filename)
            upload_folder = get_org_upload_folder(org_id)
            file_path = os.path.join(upload_folder, stored_filename)
            print(upload_folder)
            print(file_path)
            # Delete file from disk if present
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print('file removed-->',file_path)
                except Exception as e:
                    failed.append({"file_id": file_id, "reason": f"Disk delete error: {e}"})
                    continue
            else:
                print('file not found-->',file_path)
                failed.append({"file_id": file_id, "reason": "File not found on disk"})

            # Delete Mongo entry (org-scoped)
            rag_files.delete_one({"_id": oid, "org_id": org_id})
            successful.append(file_id)

        except Exception as e:
            log_error(f"Delete file error (org={org_id}, id={file_id}): {e}")
            failed.append({"file_id": file_id, "reason": str(e)})

    return {"successful": successful, "failed": failed}
 

def get_pdf_files_info_from_disk() -> dict:
    try:
        files = os.listdir(UPLOAD_FOLDER)
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        return {
            "count": len(pdf_files),
            "pdf_files": pdf_files
        }
    except Exception as e:
        raise Exception(f"Error reading PDF files: {str(e)}")
    
    
    
def get_org_upload_dir(org_id: str) -> str:
    path = os.path.join(UPLOAD_BASE, f"org_{org_id}")
    os.makedirs(path, exist_ok=True)
    return path

def get_org_vectorstore_dir(org_id: str) -> str:
    path = os.path.join(VECTORSTORE_BASE, f"org_{org_id}")
    os.makedirs(path, exist_ok=True)
    return path


def get_org_upload_folder(org_id: str) -> str:
    return os.path.join(UPLOAD_BASE, f"org_{org_id}")
 
def remove_vectorstore_dir(org_id: str):
    vec_dir = get_org_vectorstore_dir(org_id)
    if os.path.isdir(vec_dir):
        shutil.rmtree(vec_dir, ignore_errors=True)
        
def delete_single_uploaded_file(org_id: str, file_id: str) -> dict:
    try:
        try:
            oid = ObjectId(file_id)
        except Exception:
            return {"ok": False, "reason": "Invalid ObjectId"}

        file_doc = rag_files.find_one({"_id": oid, "org_id": org_id})
        if not file_doc:
            return {"ok": False, "reason": "File not found for this org"}

        stored_filename = file_doc.get("stored_filename")
        if not stored_filename:
            return {"ok": False, "reason": "Missing stored_filename in metadata"}

        upload_folder = get_org_upload_folder(org_id)
        file_path = os.path.join(upload_folder, stored_filename)

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                return {"ok": False, "reason": f"Disk delete error: {e}"}
        # Delete metadata regardless (so the DB stays consistent)
        rag_files.delete_one({"_id": oid, "org_id": org_id})
        return {"ok": True}
    except Exception as e:
        log_error(f"Delete file error (org={org_id}, id={file_id}): {e}")
        return {"ok": False, "reason": str(e)}
