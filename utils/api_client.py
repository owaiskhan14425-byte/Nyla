import httpx
import asyncio
from utils.logger import log_error
import os
import requests
from typing import Dict, Any, List
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

WEALTH_ELITE_URL = os.getenv("WEALTH_ELITE_URL", "")
if not WEALTH_ELITE_URL:
    raise RuntimeError("Set WEALTH_ELITE_URL (with trailing slash).")

DEFAULT_TIMEOUT = 30

async def call_api(
    url: str,
    headers: dict,
    payload: dict = None,
    method: str = "POST",
    timeout: int = 20,
    retries: int = 3,
    backoff_factor: float = 1.0,
):
    attempt = 0

    while attempt < retries:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                method = method.upper()

                if method == "POST":
                    response = await client.post(url, headers=headers, json=payload)
                elif method == "GET":
                    response = await client.get(url, headers=headers, params=payload)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=payload)
                elif method == "DELETE":
                    response = await client.delete(url, headers=headers, params=payload)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response.json()

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            attempt += 1
            wait_time = backoff_factor * (2 ** (attempt - 1))
            print(f"⚠️ Attempt {attempt} failed: {e}. Retrying in {wait_time:.1f}s...")
            log_error(f"⚠️ Attempt {attempt} failed: {e}. Retrying in {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)

    return {"error": f"Failed after {retries} retries", "status": "failed"}

# ------------------------------------------------------------------------------
# Internal HTTP helper
# ------------------------------------------------------------------------------
def _post_json(path: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Simple POST helper with standard timeout & logging."""
    url = f"{WEALTH_ELITE_URL}{path}"
    print(f"[API] POST → {url}")
    r = requests.post(url, data=data, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    try:
        res_json = r.json()
        print(res_json)
        # return only 'data' part if it exists, else the whole JSON
        return res_json.get("data", res_json)
    except ValueError:
        # fallback if not valid JSON
        print(" Response not in JSON format")
        return {"error": "Invalid JSON response", "raw": r.text}
    


# ------------------------------------------------------------------------------
# SEARCH CLIENT
# ------------------------------------------------------------------------------
def api_search_client(name: str) -> Dict[str, Any]:
    """Search clients dynamically by name."""
    new=  _post_json("nse-invest/search-nse-invest-client", {
        "arnId": 9,
        "searchString": name
    })
    return new

# def search_client_by_name(name: str) -> List[Dict[str, Any]]:
#     """Return cleaned list of matching clients."""
#     res = api_search_client(name)
#     data = res.get("data") or []
#     cleaned = []
#     for item in data:
#         cleaned.append({
#             "clientId": item.get("ID"),
#             "clientCode": item.get("nseClientCode"),
#             "nseMemberId": item.get("nseMemberId"),
#             "name": item.get("name"),
#             "pan": item.get("pan"),
#             "email": item.get("email"),
#             "mobileNo": item.get("mobileNo"),
#         })
#     return cleaned


# ------------------------------------------------------------------------------
# ALL INVESTORS
# ------------------------------------------------------------------------------
def api_all_investment(client_id: str) -> Dict[str, Any]:
    """Fetch all investment folios for the given client."""
    return _post_json("api/client-wise-all-investment", {
        "agent_id": 9,
        "user_id": client_id,
        "view": 1
    })


# ------------------------------------------------------------------------------
# FAMILY MEMBER
# ------------------------------------------------------------------------------
def api_family_member(client_id: str) -> Dict[str, Any]:
    """Fetch NSE family member details."""
    return _post_json("nse-invest/get-nse-family-member", {
        "arnId": 9,
        "clientId": client_id,
        "clientType": "all"
    })

# ------------------------------------------------------------------------------
# SCHEME DETAILS
# ------------------------------------------------------------------------------
def api_scheme_details(pcode: str) -> Dict[str, Any]:
    """Fetch scheme details by product code (pcode)."""
    return _post_json("nse-invest/nse-invest-scheme-details-for-report", {
        "pcode": pcode
    })


# ------------------------------------------------------------------------------
# PURCHASE ORDER
# ------------------------------------------------------------------------------
def api_purchase_order(
    *,
    client_id: str,
    nseMemberId: str,
    clientCode: str,
    schemeType: str,
    minimumAmount: float,
    amount: float,
    trType: str,
    folio: str,
    schemeName: str,
    schemeCodes: str,
    pcode: str,
    depositoryName: str = "",
    type_: int = 1,
) -> Dict[str, Any]:
    """Place an additional purchase order for the client."""
    return _post_json("nse-invest/nse-invest-place-addtional-purchase-order-from-report", {
        "arnId": 9,
        "clientId": client_id,
        "nseMemberId": nseMemberId,
        "schemeType": schemeType,
        "minimumAmount": minimumAmount,
        "amount": amount,
        "depositoryName": depositoryName,
        "trType": trType,
        "folio": folio,
        "schemeName": schemeName,
        "schemeCodes": schemeCodes,
        "type": type_,
        "clientCode": clientCode,
        "pcode": pcode,
    })
