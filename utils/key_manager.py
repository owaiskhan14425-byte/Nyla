import os
import json
from dotenv import load_dotenv
from utils.helpers import api_response



load_dotenv()
# Load from .env
OPENAI_KEYS = json.loads(os.getenv("OPENAI_KEYS", "[]"))

# Usage tracking
key_usage_count = {key: 0 for key in OPENAI_KEYS}
session_key_map = {}  # session_id → openai_key

def get_least_used_key():
    return min(key_usage_count, key=lambda k: key_usage_count[k])

def assign_key_to_session(session_id):
    key = get_least_used_key()
    if key is None:
        return None
    key_usage_count[key] += 1
    session_key_map[session_id] = key
    return key

def get_key_for_session(session_id):
    return session_key_map.get(session_id)

def decrement_key_for_session(session_id):
    key = session_key_map.pop(session_id, None)
    if key and key in key_usage_count and key_usage_count[key] > 0:
        key_usage_count[key] -= 1

def get_key_usage_stats():
    return key_usage_count.copy()

def get_session_key_map():
    return session_key_map.copy()
