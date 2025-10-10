from dotenv import load_dotenv
import os
load_dotenv()
FRONTEND_URL = os.getenv("FRONTEND_URL")
# HUGGINGFACE_EMBEDDING_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
EMBEDDING_MODEL = "text-embedding-3-small"
BUFFER_SIZE = 10
MAX_TOKEN = 250
VECTOR_DIR = "memory_index"
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
SIMILARITY_THRESHOLD = 0.30
TOKEN_EXPIRE  = 180 #in minutes
SUPER_ADMIN_TOKEN_EXPIRE = 180
TOKEN_EXPIRE_ROBOT  = 15000
UPLOAD_BASE = "pdf_files"
VECTORSTORE_BASE = "vectorstores"
ALLOWED_EXTENSIONS = [".pdf", ".txt", ".docx"]
IMAGE_STORAGE_BASE_PATH = "face_images"
FACE_AUTH_TIME_RESET = 10
#ERROR CODE
class HTTP_STATUS:
    OK = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    NOT_FOUND = 404
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    

#MESSAGE FOR ERROR AND RESPONSE
class MESSAGE:
    # General errors
    FILE_TOO_LARGE = f"File too large. Maximum allowed size is {MAX_FILE_SIZE_MB}MB."
    INVALID_AUDIO_FORMAT = "Unsupported audio format."
    UNAUTHORIZED = "Invalid or missing token."
    USER_NOT_FOUND = "User not registered."
    INTERNAL_ERROR = "Something went wrong. Please try again."
    WRONG_EXTENSION = "Only .pdf, .txt, and .docx files are allowed"
    
    ENCRYPTED_DATA_MISSING = "Missing encrypted_data"
    INTERNAL_SERVER_ERROR = "Session not initialized or expired, no OpenAI key assigned. Please re-authenticate."

    # STT/TTS
    TRANSCRIPTION_FAILED = "Could not transcribe the audio."
    TTS_ERROR = "Could not generate speech."
    API_KEY_MISSING = "API key missing in headers"
    INVALID_API_KEY = "Invalid API key"
    ORG_ALREADY_EXIST = "Organization or email already exists."
    ORG_CREATED = "Organization created successfully."


    #SESSION 
    INVALID_SESSION_ID= "Invalid session_id."
    INVALID_TOKEN  = "Payload is None (token invalid/expired)"
    MISSING_HEADER = "Missing or invalid Authorization header"
    SESSION_NOT_GET_IN_TOKEN = "Missing session_id in token"
    
    # SESSION CLEANUP
    CLEANUP_SUCCESS = "Expired sessions cleaned successfully."
    CLEANUP_NONE_FOUND = "No expired sessions found."
    CLEANUP_ALL_FAILED = "Cleanup failed for all sessions."
    CLEANUP_PARTIAL_FAILED = "Partial cleanup completed. Some sessions failed."
    CLEANUP_UNEXPECTED_ERROR = "Unexpected cleanup failure"
    
    def expired_token(e):
        return f"Invalid or expired token: {e}"
    
    #FEEDBACK
    ALREADY_FEEDBACK_DONE = "Feedback already submitted for this session."
    FEEDBACK_DONE = "Feedback received!"
    
    CLIENT_REQUIREMENT= "Client requirement form submitted successfully"
    
    #LIKEDISLIKE
    RESPONSE_RECORDED = "Response recorded"
    LIKE_DISLIKE_UNDO =  "Dislike successfully undone"
    NOT_LIKE_DISLIKE_FOUND =  "No dislike found for this ID in your session"
    MSG_ID_NOT_FOUND = "message_id not found"
    
    
    #AUTH
    INVALID_CREDENTAILS = "Invalid credentials"
    LOGIN_SUCCESS = "Login successful"
    INVALID_ORG = "Invalid org or inactive"
    INVALID_PASSWORD = "Invalid password"
    NOT_FOUND = 'org not found'
    UPDATED = 'DOC updated'
    
    
    #FACE IMAGE
    
    IMAGE_NOT_UPLOAD = 'Image not  updated '
    IMAGE_UPLOAD = 'Image uploaded successfully'
    IMAGE_REQUIRED ='Image is required.'
    IMAGE_DELETED_SUCCESS ="Images processed successfully"
    IMAGE_PATH_MISSING = "Missing image_path"
    IMAGE_NOT_FOUND = "Image not found for this user"
    FOLDER_REQUIRED= "Folder name is required"
    
    

    
    #SIGNUP 
    def failed_org(e):
       return f"Failed to create organization: {str(e)}"
   





