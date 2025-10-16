from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.rag_services import get_buffer, buffer_as_history, get_retriever, update_buffer
from services.llm_streaming import ask_llm_stream
from utils.logger import log_error
from utils.metrics import ask_from_rag_websocket
router = APIRouter()

@router.websocket("/ws/ask")
async def websocket_rag(websocket: WebSocket):
    await websocket.accept()
    ask_from_rag_websocket.inc()
    try:
        while True:
            data = await websocket.receive_json()
            question = data.get("question", "").strip()
            session_id = data.get("session_id", "")
            user_info = data.get("user_info")  # <-- add this

            if not question or not session_id:
                await websocket.send_json({"error": "Missing question, user_id, or session_id"})
                continue

            retriever = get_retriever()
            docs = retriever.get_relevant_documents(question)
            context = "\n".join(doc.page_content for doc in docs)
            chat_history = buffer_as_history(session_id)

            # pass user_info here
            final_answer = ''
            async for token in ask_llm_stream(context, chat_history, question, user_info=user_info):
                await websocket.send_json({"token": token})
                final_answer += token
            update_buffer(session_id, question, final_answer)
    except WebSocketDisconnect:
        log_error(f"Client disconnected websocket")
        print("Client disconnected")
