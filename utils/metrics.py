from prometheus_client import Counter, Gauge, Histogram

# Count how many times users started speaking
voice_requests_total = Counter(
    "voice_requests_total", "Total number of voice-based messages received"
)

# Gauge: how many WS connections are currently open
active_ws_sessions = Gauge(
    "active_ws_sessions", "Number of currently active WebSocket sessions"
) 

ask_from_rag = Counter(
    "ask_from_rag", "Total number of request from RAG"
    
)

ask_from_rag_websocket = Counter(
    "ask_from_rag_websocket", "Total number of request from RAG websocket"
    
)
rag_ask_latency = Histogram(
    "rag_ask_latency_seconds",
    "Time taken by rag_ask function (seconds)"
)

# NEW: Track /org/auth calls
org_auth_requests = Counter(
    "org_auth_total",
    "Number of /org/auth endpoint calls"
)