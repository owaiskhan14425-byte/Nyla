import secrets
import numpy as np
from fastapi.responses import JSONResponse
from sklearn.metrics.pairwise import cosine_similarity
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
from hashlib import sha256
import json
import os
from fastapi import Request
from utils.constants import MESSAGE, HTTP_STATUS
from utils.jwt_utils import get_jwt_payload
from datetime import datetime
import pytz
import random
import string
from bson import ObjectId
from datetime import datetime
import re
from services.vectorstore_singleton import get_embedding_model
from services.vectorstore_loader import batch_retrain_all_orgs
from typing import Dict, Any, List
from secrets import randbelow
load = batch_retrain_all_orgs()
print(load)

def generate_4digit_pin() -> str:
    return f"{randbelow(10000):04d}"



def decode_user_id(encoded_id: str) -> str:
    try:
        decoded_bytes = base64.b64decode(encoded_id)
        return decoded_bytes.decode("utf-8")
    except Exception as e:
        print(f"Error decoding user_id: {e}")
        return encoded_id


def generate_org_code(org_name):
    # Remove spaces, take first 3 letters, and uppercase
    clean_name = re.sub(r'\s+', '', org_name)
    prefix = clean_name[:3].upper()
    # Generate two random 4-digit numbers
    num1 = random.randint(1000, 9999)
    num2 = random.randint(1000, 9999)
    return f"{prefix}-{num1}-{num2}-AI"



def serialize_mongo_doc(doc):
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = serialize_mongo_doc(v)
        elif isinstance(v, list):
            result[k] = [serialize_mongo_doc(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


def generate_random_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


# Function to hash the password (assuming SHA-256 hex)
def hash_password(password: str):
    return sha256(password.encode('utf-8')).hexdigest()


def utc_to_ist(dt):
    """Convert UTC datetime (or string) to Asia/Kolkata time string."""
    ist = pytz.timezone("Asia/Kolkata")
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    try:
        return dt.astimezone(ist).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def get_session_id_from_token(request: Request):
     
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None, None, api_response(code=401, message=MESSAGE.MISSING_HEADER)
    token = auth_header.split(" ")[1]

    try:
        payload = get_jwt_payload(token)
        if payload is None:
            return None, None, api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.INVALID_TOKEN)
    except Exception as e:
        return None, None, api_response(code=HTTP_STATUS.UNAUTHORIZED, message=MESSAGE.expired_token(e))

    session_id = payload["session_id"] if "session_id" in payload else None
    user_info = payload["user_info"] if "user_info" in payload else ""
    if not session_id:
        return None, None, api_response(code=HTTP_STATUS.BAD_REQUEST, message=MESSAGE.SESSION_NOT_GET_IN_TOKEN)
    return session_id, user_info, None



def aes_decrypt(encrypted_data, key):
    key = sha256(key.encode()).digest()
    encrypted_data = encrypted_data.strip()
    enc = base64.b64decode(encrypted_data,validate=True)
    iv = enc[:16]
    ciphertext = enc[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
    return decrypted.decode("utf-8")


def aes_encrypt(data, api_key):
    json_data = json.dumps(data).encode("utf-8")
    key = sha256(api_key.encode()).digest()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(json_data, AES.block_size))
    b64_encrypted = base64.b64encode(iv + ciphertext).decode("utf-8")
    return b64_encrypted





ALIASES = {
   "wealth light": "Wealth Elite",
   "wealth lite":"Wealth Elite",
   "wealthelite": "Wealth Elite",
   "wealthy light": "Wealth Elite",
   "advisor X": "Advisor X",
   "robo ": "Robo Advisory Platform",
   "zaheer baber": "Zahiruddin Babar",
   "zahir": "Zahiruddin Babar",
   "baber": "Zahiruddin Babar",
   "Singh Parihar": "Abhishek Singh Parihar",
   "redvsion" : "Redvision",
   "redvison" : "Redvision",
   "revision" : "Redvision"
   
}

def api_response(data=None,code=200, message="success"):
    if data is None:
        data = []
    success = code == 200
       
    return JSONResponse(
        status_code=code,
        content={
            "success": success,
            "code": code,
            "message": message,
            "data": data,
        }
    )

def generate_api_key() -> str:
    return secrets.token_hex(32)
def generate_session_id():
    return secrets.token_hex(32)
def generate_message_id():
    return secrets.token_hex(32)
def normalize_question(question):
    lower_q = question.lower()
    for alias, canonical in ALIASES.items():
        if alias in lower_q:
                question = question.replace(alias, canonical)
    return question

def get_user_info_prompt(user_info):
   if user_info and user_info.strip():
      return f"USER Information (It may be in raw data. (It is not History)): {user_info}"
   else:
      return ""
  
  
def similarity_score(query, context_text, org_id):
    if not context_text.strip():
        return 0.0
    embeddings = get_embedding_model()
    query_vec = embeddings.embed_query(query)
    context_vec = embeddings.embed_query(context_text)
    if np.linalg.norm(query_vec) == 0 or np.linalg.norm(context_vec) == 0:
        return 0.0
    return cosine_similarity([query_vec], [context_vec])[0][0]

# --- minimal helpers ---
def _to_float(x):
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None

def _mask_account(ac):
    s = str(ac or "").strip()
    if len(s) <= 6:
        return "******"
    return f"{s[:4]}{'*'*(len(s)-6)}{s[-3:]}"

def _first(*vals):
    for v in vals:
        if v not in (None, "", "NA", "N/A"):
            return v
    return None


# ------------ SIMPLE + FULL: parse all_investment ------------
def parse_funds_full(res):
    """
    Simple parser: keep ALL original fields (raw),
    and also provide a clean, LLM-friendly 'structured' block.
    Nothing is dropped.
    """
    folios = (res or {}).get("folioData") or []
    out = []

    for f in folios:
        # pick basic ids
        name = _first(f.get("FundName"), f.get("fundDesc"), f.get("schemeName"))
        pcode = _first(f.get("pcode"), f.get("schemeCode"), f.get("productCode"))

        # numbers (normalized)
        units = _to_float(_first(f.get("unit"), f.get("unitShow")))
        nav_value = _to_float(_first(f.get("folioCurNav"), f.get("nav")))
        invested = _to_float(_first(f.get("invCost"), f.get("investment")))
        current = _to_float(_first(f.get("curVal"), f.get("currentValue")))
        gain = _to_float(_first(f.get("gainLoss"), f.get("gain")))
        today_gain = _to_float(_first(f.get("todayGainLoss"), f.get("todaysGainLoss")))
        cagr = _to_float(f.get("cagr"))
        abs_rtn = _to_float(_first(f.get("absRtn"), f.get("absoluteReturn")))

        # build structured (clean + readable)
        structured = {
            "name": name,
            "pcode": pcode,
            "folio": f.get("folio"),
            "since": _first(f.get("invSince"), f.get("since")),
            "tr_mode": f.get("trMode"),
            "joint_holders": {
                "holder1": f.get("jointHolder1"),
                "holder2": f.get("jointHolder2"),
            },
            "units": units,
            "nav": {
                "date": _first(f.get("folioNavDate"), f.get("navDate")),
                "value": nav_value,
            },
            "valuation": {
                "invested": invested,
                "current": current,
                "gain": gain,
                "today_gain": today_gain,
                "cagr_pct": cagr,
                "abs_return_pct": abs_rtn,
            },
            "bank": {
                "name": f.get("bankName"),
                "account": _mask_account(f.get("bankAC")),
            },
        }

        # keep ALL original fields too (so nothing is ignored)
        out.append({
            "data": dict(f),          # full original item
            "structured": structured # neat, normalized view
        })

    return out


def build_pretty_lines(funds_struct, max_n=10):
    """
    Simple pretty summary (one line per fund).
    Uses only 'structured' (clean) view.
    """
    if not funds_struct:
        return "No funds found."

    lines = []
    for i, item in enumerate(funds_struct[:max_n], 1):
        s = item.get("structured", {})
        name = s.get("name") or "-"
        pcode = s.get("pcode") or "-"
        folio = s.get("folio") or "-"
        tr_mode = s.get("tr_mode") or "N/A"
        bank = (s.get("bank") or {}).get("name") or "N/A"

        v = s.get("valuation") or {}
        invested = v.get("invested")
        current = v.get("current")
        gain = v.get("gain")
        cagr = v.get("cagr_pct")

        perf = []
        if invested is not None and current is not None:
            perf.append(f"Invested ₹{invested:,.2f} → ₹{current:,.2f}")
        if gain is not None:
            perf.append(f"({'▲' if gain>=0 else '▼'} ₹{abs(gain):,.2f}" + (f" | CAGR {cagr:.2f}%" if cagr is not None else "") + ")")

        perf_str = " ".join(perf) if perf else "—"
        lines.append(
            f"{i}) {name} ({pcode}) • {perf_str} | Folio: {folio} | Holding: {tr_mode} | Bank: {bank}"
        )

    if len(funds_struct) > max_n:
        lines.append("... and more")
    return "\n".join(lines)


def parse_search_client_min(res):
    """
    Clean the client search response.
    Accepts:
      - list[...]                        → use as-is
      - dict with 'folioData' or 'data'  → use that list
      - anything else                    → []
    Keeps only essential identifiers (no contact/branch info).
    """
    # Normalize records
    if isinstance(res, list):
        records = res
    elif isinstance(res, dict):
        records = res.get("folioData") or res.get("data") or []
    else:
        records = []

    cleaned, seen = [], set()
    for d in records:
        if not isinstance(d, dict):
            continue
        item = {
            "name": d.get("name"),
            "pan": d.get("pan"),
            "nseClientCode": d.get("nseClientCode"),
            "modeOfHolding": d.get("modeOfHolding"),
            "nseMemberId": d.get("nseMemberId"),
            "ID": d.get("ID"),
        }
        # De-dupe on (ID, nseClientCode)
        key = (item.get("ID"), item.get("nseClientCode"))
        if key not in seen:
            cleaned.append(item)
            seen.add(key)

    return cleaned


def pretty_search_client_min(clients, max_n=20):
    """
    Build a readable summary string.
    Limits printed lines to max_n for readability.
    (This does NOT truncate the 'clients' list you return elsewhere.)
    """
    if not clients:
        return "No clients found."

    lines = []
    for i, c in enumerate(clients[:max_n], 1):
        name = c.get("name") or "-"
        pan  = c.get("pan") or "-"
        code = c.get("nseClientCode") or "-"
        cid  = c.get("ID") or "-"
        mode = c.get("modeOfHolding") or "-"
        nmem = c.get("nseMemberId") or "-"
        lines.append(
            f"{i}) {name} (PAN: {pan}) • Client Code: {code} | Client ID: {cid} | Holding: {mode} | NSE Member: {nmem}"
        )

    if len(clients) > max_n:
        lines.append("... and more")
    return "\n".join(lines)
