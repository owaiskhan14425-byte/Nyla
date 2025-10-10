# services/llm/runtime_state.py
from typing import Any, Dict, Optional
from contextvars import ContextVar

_DEFAULT: Dict[str, Any] = {
    "session_id": None,
    "org_id": None,
    "openai_key": None,
    "user_info": None,
}
_RUNTIME: ContextVar[Dict[str, Any]] = ContextVar("llm_runtime", default=_DEFAULT.copy())

def set_runtime(session_id: str, org_id: Optional[str], openai_key: Optional[str], user_info: Optional[dict]):
    _RUNTIME.set({
        "session_id": session_id,
        "org_id": org_id,
        "openai_key": openai_key,
        "user_info": user_info or {},
    })

def get_runtime() -> Dict[str, Any]:
    return _RUNTIME.get()

def require_runtime():
    if not _RUNTIME.get().get("session_id"):
        raise RuntimeError("LLM runtime not initialized for this request")
