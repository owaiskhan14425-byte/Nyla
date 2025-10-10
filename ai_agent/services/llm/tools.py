# services/llm/tools.py
import json
from langchain.tools import tool
from dotenv import load_dotenv

from services.llm.runtime_state import require_runtime, get_runtime
from services.llm.rag_core import rag_answer
from utils.api_client import (
    api_all_investors,
    api_scheme_details,
    api_purchase_order,
    api_search_client,
)
from utils.helpers import parse_funds_full, build_pretty_lines
from utils.helpers import parse_search_client_min, pretty_search_client_min

load_dotenv()

DEBUG_LOG = False  # Flip False in production


def _dprint(*args, **kwargs):
    if DEBUG_LOG:
        print("[TOOL]", *args, **kwargs)


# ----------------------------------------------------------------------
# RAG TOOL
# ----------------------------------------------------------------------
@tool
def rag_tool(question: str) -> str:
    """Answer general/explain questions or any question(non-transaction)"""
    require_runtime()
    rt = get_runtime()
    # _dprint("rag_tool:", question, "| session:", rt.get("session_id"))
    ans = rag_answer(question)
    return ans


# ----------------------------------------------------------------------
# SEARCH CLIENT
# ----------------------------------------------------------------------
@tool
def search_client(name: str) -> str:
    """Search client(s) by name and return list of matching records.
    If name already exits use that name"""
    
    _dprint("search_client:", name)

    # Your API always returns a dict with 'folioData'
    res = api_search_client(name) or {}
    clients = parse_search_client_min(res)

    if not clients:
        payload = {
            "clients": [],
            "pretty": f"No clients found for '{name}'.",
            "count": 0
        }
        return json.dumps(payload, ensure_ascii=False)

    # pretty = pretty_search_client_min(clients)
    payload = {
        "clients": clients,          # FULL list (all matches)
        # "pretty": pretty,            # human-readable (first max_n lines)
        "count": len(clients)        # total matches
    }
    return json.dumps(payload, ensure_ascii=False)
# ----------------------------------------------------------------------
# ALL INVESTORS
# ----------------------------------------------------------------------
@tool
def all_investors(client_id: str) -> str:
    """List user's funds (FULL: keep raw + structured)"""
    # _dprint("all_investors:", client_id)
    res = api_all_investors(client_id)
    funds_struct = parse_funds_full(res)         # keep everything
    # pretty = build_pretty_lines(funds_struct)    # chat/LLM friendly lines
    payload = {
        "funds": funds_struct,   # [{ raw: {...}, structured: {...} }]
        # "pretty": pretty,        # multiline string
        "count": len(funds_struct)
    }
    return json.dumps(payload, ensure_ascii=False)

# ----------------------------------------------------------------------
# SCHEME DETAILS
# ----------------------------------------------------------------------
@tool
def scheme_details(pcode: str) -> str:
    """Get scheme details by pcode."""
    # _dprint("scheme_details: pcode =", pcode)
    res = api_scheme_details(pcode)
    return json.dumps(res)


# ----------------------------------------------------------------------
# PURCHASE
# ----------------------------------------------------------------------
@tool
def purchase(
    amount: float,
    pcode: str,
    schemeName: str,
    schemeCodes: str,
    trType: str,
    schemeType: str,
    minimumAmount: float,
    nseMemberId: str,
    clientCode: str,
    client_id: str,
    folio: str = "New",
) -> str:
    """Place an order for the given scheme and client."""
    payload = {
        "client_id": client_id,
        "nseMemberId": nseMemberId,
        "schemeType": schemeType,
        "minimumAmount": minimumAmount,
        "amount": amount,
        "trType": trType,
        "folio": folio,
        "schemeName": schemeName,
        "schemeCodes": schemeCodes,
        "clientCode": clientCode,
        "pcode": pcode,
    }
    # _dprint("purchase:", payload)
    res = api_purchase_order(**payload)
    return json.dumps(res)

# ----------------------------------------------------------------------
# TOOL REGISTRY
# ----------------------------------------------------------------------
TOOLS = [rag_tool, search_client, all_investors, scheme_details, purchase]
