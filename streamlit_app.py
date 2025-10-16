import json
import requests
import streamlit as st
import time
import datetime as dt

# =========================
# Quick config
# =========================
DEFAULT_BASE_URL = "https://boundingly-unmothered-lula.ngrok-free.dev"
DEFAULT_ENDPOINT = "/rag/ask-robot"
DEFAULT_BEARER_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiVWtWRVZrbHphVzl1ZkVGU1RudzQiLCJzZXNzaW9uX2lkIjoiMTQxMmNkMGFhNzhkNmU4ZGU4ZmY3NWNkMjNiYmIyZTVjNjdlMTU3YmU4ZmY4NWNhN2NjOTkwYjE1M2FkMTU0ZDE3NTk1NTkzMDYwNDEiLCJ1c2VyX3R5cGUiOjAsImV4cCI6MTc2MDQ1OTMwNn0.v-UF8oKm0w7HSsaECAYx7lW-mEniOiO0TrH3NrTRHYA"
)

# --- Page setup (must be the first Streamlit command and only called once) ---
st.set_page_config(page_title="Nyla", page_icon="🤖", layout="wide")
st.markdown("""
    <style>
        .center-title {
            text-align: center;
            font-size: 48px;
            font-weight: 700;
            margin-top: 10px;
            color: #1E88E5;
        }
        .center-subtitle {
            text-align: center;
            font-size: 20px;
            color: gray;
            margin-top: -10px;
            margin-bottom: 40px;
        }
    </style>
    <h1 class="center-title">🤖 Nyla</h1>
    <p class="center-subtitle">Next-Gen Yield & Lending Assistant</p>
""", unsafe_allow_html=True)

# =========================
# Session state
# =========================
if "session_id" not in st.session_state:
    st.session_state.session_id = "streamlit-session-1"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_latency_ms" not in st.session_state:
    st.session_state.last_latency_ms = None

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.subheader("⚙️ Settings")
    base_url = st.text_input("Base URL", value=DEFAULT_BASE_URL)
    endpoint_path = st.text_input("Endpoint Path", value=DEFAULT_ENDPOINT)
    st.session_state.session_id = st.text_input("Session ID", value=st.session_state.session_id)
    bearer_token = st.text_input("Bearer Token", value=DEFAULT_BEARER_TOKEN, type="password")

    st.markdown("---")
    if st.button("🗑️ New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# =========================
# Show latency badge
# =========================
lat_s = f"{(st.session_state.last_latency_ms or 0)/1000:.2f}"
st.markdown(
    f"""
    <style>
      .latency-badge {{
        position: fixed; top: 12px; right: 16px;
        padding: 6px 10px; border-radius: 999px;
        background: rgba(0,0,0,.35); color: white;
        font-weight: 600; font-size: 14px;
      }}
    </style>
    <div class="latency-badge">⏱ {lat_s}s</div>
    """,
    unsafe_allow_html=True,
)

# =========================
# Helpers
# =========================
def render_history():
    for m in st.session_state.messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role and content:
            with st.chat_message(role):
                if role == "assistant" and m.get("api_start"):
                    # api_start now stores a string like "2.34 sec."
                    st.caption(f"API hit: {m['api_start']}")
                st.markdown(content)

def call_rag_api(base_url: str, path: str, question: str, token: str):
    url = base_url.rstrip("/") + path
    headers = {
        "Content-Type": "application/json",
        "X-Session-ID": st.session_state.session_id,
        "Authorization": f"Bearer {token.strip()}"
    }
    try:
        resp = requests.post(url, headers=headers, json={"question": question}, timeout=90)
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": f"{e}"}

    code = int(data.get("code", resp.status_code))
    if 200 <= code < 300:
        answer = ""
        if isinstance(data.get("data"), dict):
            answer = data["data"].get("answer") or ""
        else:
            answer = data.get("answer") or data.get("message") or ""
        return {"ok": True, "answer": answer}
    return {"ok": False, "error": data.get("message") or "Unknown error"}

# =========================
# UI
# =========================
render_history()

typed_text = st.chat_input("Type your message here…")
if typed_text:
    user_text = typed_text.strip()
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        ph = st.empty()

        with st.spinner("Thinking…"):
            t0 = time.perf_counter()
            result = call_rag_api(base_url, endpoint_path, user_text, bearer_token)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

        st.session_state.last_latency_ms = elapsed_ms
        elapsed_str = f"{elapsed_ms/1000:.2f} sec."

        if not result.get("ok"):
            err = result.get("error", "Unknown error")
            st.caption(f"API hit: {elapsed_str}")
            ph.error(f"❌ {err}")
            st.session_state.messages.append({
                "role": "assistant", "content": f"❌ {err}", "api_start": elapsed_str
            })
        else:
            answer = (result.get("answer") or "").strip() or "_(No answer text returned)_"
            st.caption(f"API hit: {elapsed_str}")
            ph.markdown(answer)
            st.session_state.messages.append({
                "role": "assistant", "content": answer, "api_start": elapsed_str
            })

