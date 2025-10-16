from fastapi import FastAPI,Request
from routers import rag, report,websocket_rag,org_signup,feedback,file_system
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from utils.logger import log_error
from fastapi.responses import JSONResponse
from routers import admin_dedupe_auto
import os
from utils.constants import IMAGE_STORAGE_BASE_PATH
from fastapi.staticfiles import StaticFiles 

app = FastAPI(title="Redvision AI Agent")

@app.exception_handler(Exception)

async def global_exception_handler(request: Request, exc: Exception):
    log_error(f"Unhandled exception at {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "code": 500,
            "message": f"Internal server error main file {exc}",
            "data": []
        }
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FACE_IMAGE_DIR = os.path.join(IMAGE_STORAGE_BASE_PATH)
os.makedirs(FACE_IMAGE_DIR, exist_ok=True)
app.mount("/face_images", StaticFiles(directory=FACE_IMAGE_DIR), name="face_images")

app.include_router(rag.router, prefix="/rag") 
app.include_router(websocket_rag.router)
app.include_router(org_signup.router, prefix="/org")
app.include_router(feedback.router)
app.include_router(file_system.router, prefix="/file_system")
app.include_router(report.router, prefix="/report")
app.include_router(admin_dedupe_auto.router)


Instrumentator().instrument(app).expose(app)