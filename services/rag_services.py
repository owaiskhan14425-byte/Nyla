from datetime import datetime
from services.llm_model import ask_llm, robot_ask_llm
from services.mongo_client import unique_question
from utils.constants import SIMILARITY_THRESHOLD, BUFFER_SIZE
from services.vectorstore_singleton import get_retriever
from utils.helpers import similarity_score
from utils.logger import log_error,log_data_dict
from utils.key_manager import get_key_for_session, assign_key_to_session
from dotenv import load_dotenv
import os
import time
from threading import Thread
from services.org_service import get_unique_message_id,get_org_collection_name_from_session,async_get_org_collection_name_from_session
from services.feedback_service import get_org_id_by_session, get_org_id_by_session_robot_test
from utils.helpers import normalize_question
# load_dotenv()
# OPENAI_KEYS_Demo = os.getenv("OPENAI_KEYS_Demo")
# In-memory chat buffer, key is session_id!
user_buffers = {}  

def get_buffer(session_id):  
    # print("Current buffer:", user_buffers.get(session_id, [])[-BUFFER_SIZE * 2:])
    return user_buffers.get(session_id, [])[-BUFFER_SIZE*2:]

def update_buffer(session_id, question, answer):
    buf = user_buffers.setdefault(session_id, [])
    buf.append({"role": "user", "content": question})
    buf.append({"role": "assistant", "content": answer})
    if len(buf) > BUFFER_SIZE * 2:
        user_buffers[session_id] = buf[-BUFFER_SIZE * 2:]

def buffer_as_history(session_id):
    return get_buffer(session_id) # get current buffer memory  

def save_conversation(log, session_id):  # save all conversation to DB
    collection_name = get_org_collection_name_from_session(session_id)
    if collection_name is not None:
        try:
            collection_name.insert_one(log)
        except Exception as e:
            print(f"Error saving conversation for {log.get('session_id')}: {e}")
            log_error(f"Error saving conversation for {log.get('session_id')}: {e}")

def save_unique_question(log): # save unique question to DB
    try:
        # now = datetime.now()
        # current_time = now.strftime("%H:%M:%S")
        # print("Unique DB insertion time  :", current_time)
        unique_question.insert_one(log)
        # print("Unique DB insertion time  completed :", current_time)
    except Exception as e:
        print(f"Error saving unique response for {log.get('session_id')}: {e}")
        log_error(f"Error saving unique response for {log.get('session_id')}: {e}")
        
async def robot_rag_ask(session_id, question, user_info=None):
    # org_id = get_org_id_by_session_robot_test(session_id)
    openai_key = get_key_for_session(session_id)
    if not openai_key:
        openai_key = assign_key_to_session(session_id)
        if not openai_key:
            raise ValueError("Session not initialized or expired, no OpenAI key assigned. Please re-authenticate.")
    norm_question = normalize_question(question)
    message_id = await get_unique_message_id()
    answer = await robot_ask_llm(session_id, norm_question, user_info=user_info, openai_key=openai_key)
    text_answer, tool_label, tool_used = answer
    # print('answer',text_answer)
    # print("tool label :",tool_label)
    # print("tool used: ",tool_used)
    auth_status = tool_label in ("transaction", "both")
    rag_log = {
        "session_id": session_id,
        "question": question,
        "answer": text_answer,
        "timestamp": datetime.now().isoformat(),
        "message_id": message_id
    }
    log_data_dict(rag_log)
    log = {
        "session_id": session_id,
        "question": question,
        "answer": text_answer,
        "timestamp": datetime.now().isoformat(),
        "message_id": message_id
    }
    Thread(target=save_conversation, args=(log, session_id)).start()
    update_buffer(session_id, question, text_answer)
    
    return text_answer, tool_label, tool_used, message_id, auth_status


async def rag_ask(session_id, question, user_info=None):
    org_id = get_org_id_by_session(session_id) # Implement this lookup
    retriever = get_retriever(org_id)
    docs = retriever.invoke(question)  # get relevant documents from the retriever

    context = "\n".join(doc.page_content for doc in docs) # context that the model will see
    # print(context)
    openai_key = get_key_for_session(session_id) # get the openai key for the session
    if not openai_key:   
        openai_key = assign_key_to_session(session_id) 
        if not openai_key:
            raise ValueError("Session not initialized or expired, no OpenAI key assigned. Please re-authenticate.")  
    chat_history = buffer_as_history(session_id)
    if not chat_history:
        coll = get_org_collection_name_from_session(session_id)
        if coll is not None:
            # get last 10, newest first
            history = list(
                coll.find({"session_id": session_id})
                    .sort("timestamp", -1)
                    .limit(10)
            )
            # make it oldest -> newest for a natural chat order
            history = list(reversed(history))

            for item in history:
                q = item.get("question")
                a = item.get("answer")
                if q is not None and a is not None:
                    update_buffer(session_id, q, a)

            # IMPORTANT: refresh local variable after we mutated the buffer
            chat_history = buffer_as_history(session_id)
        else:
            print(f"No collection found for session_id: {session_id}")

    answer = await ask_llm(context, chat_history, question, user_info=user_info, openai_key=openai_key) # get the answer from the model
    # print(answer)

    similarity = similarity_score(question, context,org_id) # calculate the similarity score between the question and the context
    message_id = await get_unique_message_id()
    
    rag_log = {
        "session_id": session_id,    # For per-session chat history
        "question": question,
        "answer": answer,
        "context": context,
        "similarity": similarity,
        "timestamp": datetime.now().isoformat(),
        "message_id":message_id
    }
    log_data_dict(rag_log)

    log = {

        "session_id": session_id,    # For per-session chat history
        "question": question,
        "answer": answer,
        "similarity": similarity,
        "timestamp": datetime.now().isoformat(),
        "message_id":message_id
    }

    # Save conversation and unique question in parallel
    Thread(target=save_conversation, args=(log,session_id)).start()

    if similarity < SIMILARITY_THRESHOLD: # if the similarity score is below the threshold
        Thread(target=save_unique_question, args=(log,)).start()
    # print(similarity)

    update_buffer(session_id, question, answer)
    return answer,message_id

def reset_user_conversation(session_id):
    user_buffers[session_id] = []

def remove_user_buffers(session_id):
    user_buffers.pop(session_id, None)

def get_all_buffers():
    # For debug route: returns session_id as key, list of (q, a) as value.
    return user_buffers.copy()

def get_user_buffer(session_id):
    # Returns buffer for one session_id
    return get_buffer(session_id)


async def add_chat(session_id, question,answer,flag):
    message_id = await get_unique_message_id()
    
    rag_log = {
        "session_id": session_id,    # For per-session chat history
        "question": question,
        "answer": answer,
        "flag":flag,
        "timestamp": datetime.now().isoformat(),
        "message_id":message_id
    }
    log_data_dict(rag_log)
    save_conversation(rag_log,session_id)
    return True

