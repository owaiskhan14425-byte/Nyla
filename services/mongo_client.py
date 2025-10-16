
import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
from utils.logger import log_error

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
unique_question = db["unique_question"]
rag_files=db["rag_files"]
users=db["users"]
org_collection=db["organization"]
sessions=db["sessions"]
feedback = db["feedback"]
wrong_answers = db["wrong_answer"]
client_requirement = db["client_requirement"]
tokenValidations = db["tokenValidations"]
tokenValidationsUser = db["tokenValidationsUser"]
superAdmin = db["superAdmin"]
face_images = db["face_images"]


""" Check session Id is present in rag"""
def is_valid_session(session_id: str) -> bool:
    return sessions.find_one({"session_id": session_id}) is not None


def count_unique_users():
    return users.count_documents({})

def user_exists(user_id: str) -> bool:
    return users.find_one({"user_id": user_id}) is not None