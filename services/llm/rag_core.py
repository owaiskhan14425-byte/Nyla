# services/llm/rag_core.py
import os
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import pytz

from services.vectorstore_singleton import get_retriever
from services.feedback_service import get_org_id_by_session_robot_test
from services.llm.runtime_state import require_runtime, get_runtime
from utils.helpers import get_user_info_prompt
from utils.logger import log_error
from services.fundpilot_prompt import prompt_for_robot  

load_dotenv()
OPENAI_FALLBACK_KEY = os.getenv("OPENAI_KEYS_Demo")

def rag_answer(question: str) -> str:
    from services.rag_services import buffer_as_history
    """
    Former `_rag_answer` moved out of tools.py.
    Reads ContextVar runtime, builds context, and calls OpenAI.
    """
    require_runtime()
    rt = get_runtime()
    session_id = rt["session_id"]
    openai_key = rt["openai_key"] 
    
    user_info = rt["user_info"] or {}

    if not openai_key:
        raise ValueError("Session not initialized or expired, no OpenAI key assigned. Please re-authenticate.")

    org_id = rt["org_id"] or get_org_id_by_session_robot_test(session_id)
    retriever = get_retriever(org_id)
    docs = retriever.invoke(question)
    context = "\n".join(doc.page_content for doc in docs)
    ist = pytz.timezone("Asia/Kolkata")
    ist_time = datetime.now(ist)
    today = ist_time.strftime("%A, %d %B %Y, %I:%M %p")

    user_info_for_prompt = get_user_info_prompt(user_info) # Get the user info prompt if any

    system_prompt = prompt_for_robot.format(
        question = question,
        current_date_info=today,
        MAX_TOKEN=100,
        User_Info=user_info_for_prompt or "",
    )

    # buffer history (your own session buffer)
    history = buffer_as_history(session_id)  # list of dicts: {"role": "...", "content": "..."}

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Context: {context}"},
    ] + history + [{"role": "user", "content": question}]

    client = OpenAI(api_key=openai_key)
    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=100,
            temperature=0.0,
        )
        # print(completion.choices[0].message.content)
        return completion.choices[0].message.content
    except Exception as e:
        log_error(f"rag tool gpt-4.1-mini error: {e}")
        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=100,
                temperature=0.0,
            )
            return completion.choices[0].message.content
        except Exception as e2:
            log_error(f"rag tool fallback gpt-3.5-turbo error: {e2}")
            return "Sorry, I'm having trouble processing your request right now."
