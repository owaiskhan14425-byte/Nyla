from dotenv import load_dotenv
import openai
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from services.feedback_service import get_org_id_by_session_robot_test
from services.fundpilot_prompt import prompt, Nyla_Prompt
from utils.constants import MAX_TOKEN
from utils.helpers import normalize_question, get_user_info_prompt
from utils.logger import log_error
import pytz
from datetime import datetime
import time
from services.llm.runtime_state import set_runtime
from services.llm.tools import TOOLS
from services.llm.graph import build_llm_graph

load_dotenv()

# """language detection"""

def detect_language(text, openai_key=None): 
   prompt = f"""
You are a language script classifier. Reply ONLY with one word from this list: English, Hinglish(text is written in Hindi but using English/Latin script), Marathi, Malay, Italian, Spanish, French, German, Gujarati etc.
Example: 
   - If the text is written in Hindi but using English/Latin script, then must reply: Hinglish  
   - If the text is written in English, then must reply: English
   - If the text is written in any language (e.g. Italian, Malay, Marathi , Spanish, French, German etc.), then must reply with the respective language name only .
You can detect any language, reply that language name only.
check scripts first means user can write hindi in english script so that you should answer in Highlish language. 
Be careful: Users may ask in Hinglish, English, Gujarati, etc. so reply that language


Text: "{text}"
"""
   
   client = openai.OpenAI(api_key=openai_key)
   
   for attempt in range(1):
      try:
         response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=10,
            temperature=0.0
            )
         lang = response.choices[0].message.content.strip()
         # print("language :", lang)
         return lang
      except Exception as e:
         print(f"Attempt {attempt+1} failed: {e}")
         log_error(f"Attempt {attempt+1} failed: {e}")
         
         time.sleep(1)
   return "English"

def detect_language_robot(text, openai_key=None): 
   prompt = f"""
You are a language script classifier. Reply ONLY with one word from this list: English, Hindi, Marathi, Malay, Italian, Spanish, French, German, Gujarati etc.
Example: 
   - If the text is written in Hindi (Devanagari script or Hinglish written in Latin letters) then must reply: Hindi  
   - If the text is written in English, then must reply: English
   - If the text is written in Marathi, then must reply: Marathi
   - If the text is written in any language (e.g. Italian, Malay, Marathi , Spanish, French, German etc.), then must reply with the respective language name only .
You can detect any language, reply that language name only. 
Be careful: Users may ask in Hindi, English, Gujarati, etc. so reply that language

Text: "{text}"
"""
   
   client = openai.OpenAI(api_key=openai_key)
   
   for attempt in range(1):
      try:
         response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=10,
            temperature=0.0
            )
         lang = response.choices[0].message.content.strip()
         # print("language :", lang)
         return lang
      except Exception as e:
         print(f"Attempt {attempt+1} failed: {e}")
         log_error(f"Attempt {attempt+1} failed: {e}")
         
         time.sleep(1)
   return "English"

async def ask_llm(context: str, chat_history: str, question: str, user_info=None, max_retries: int = 3,openai_key=None):
   client = openai.OpenAI(api_key=openai_key)
   ist = pytz.timezone("Asia/Kolkata")
   ist_time = datetime.now(ist)
   today = ist_time.strftime("%A, %d %B %Y, %I:%M %p")
   # today = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
   language = detect_language(question, openai_key=openai_key) # Detect the language of the user's question
   norm_question = normalize_question(question) # Normalize the user's question
   user_info_for_prompt = get_user_info_prompt(user_info) # Get the user info prompt if any
   
   system_prompt = prompt.format(
      question=norm_question,
      current_date_info=today,
      language=language,
      MAX_TOKEN=MAX_TOKEN,
      User_Info=user_info_for_prompt
   )
   system_messages = [
      {"role": "system", "content": system_prompt},
      {"role": "system", "content": f"Context: {context}"},
   ] + chat_history + [{"role": "user", "content": norm_question}]


   # Try GPT-4.1-mini first
   for attempt in range(max_retries):
      try:
         completion = client.chat.completions.create(
               model="gpt-4.1-mini",
               messages=system_messages,
               max_tokens=MAX_TOKEN,
               temperature=0.0,
         )
         
         answer =  completion.choices[0].message.content
         return answer
      except Exception as e:
            log_error(f"error ------ {e}")
         
            if hasattr(e, "status_code") and e.status_code == 409:
               # If 409, switch to GPT-3.5-Turbo immediately
               for attempt in  range(max_retries):
                  try:
                     completion = client.chat.completions.create(
                           model="gpt-3.5-turbo",
                           messages= system_messages,

                           max_tokens=MAX_TOKEN,
                           temperature=0.0,
                     )
                     return completion.choices[0].message.content
                  except Exception:
                     log_error(f"error llm model: {e}")
                     #print(f"GPT-3.5 error attempt {attempt + 1}: {e}")
                     time.sleep(1) 
               return "Sorry, I'm having trouble processing your request right now. Please try again later."
            else :
               #print(f"GPT-4.1 error attempt {attempt + 1}: {e}")
               time.sleep(1)  # Optional backoff

   # After all retries, return fallback message
   return "Apologies, I'm unable to process your request at the moment. Please try again in a little while."



RAG_TOOLS = {"rag_tool"}
TRANSACTION_TOOLS = {"search_client", "all_investors", "scheme_details", "purchase", "family_member"}


def _collect_tools(msgs):
   tools = set()
   for m in msgs:
      if hasattr(m, "tool_calls") and m.tool_calls:
         for t in m.tool_calls:
               name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
               if name:
                  tools.add(name)
      if type(m).__name__ == "ToolMessage":
         name = getattr(m, "name", None)
         if name:
               tools.add(name)
   return tools


def _categorize(tools):
   rag = [t for t in tools if t in RAG_TOOLS]
   txn = [t for t in tools if t in TRANSACTION_TOOLS]
   if rag and txn:
      label = "both"
   elif rag:
      label = "rag"
   elif txn:
      label = "transaction"
   else:
      label = "none"
   return {"label": label, "used": {"rag": rag, "transaction": txn}}

async def robot_ask_llm(session_id, question, user_info=None, openai_key=None):
   if not openai_key:
      raise ValueError("Missing OpenAI key. Please re-authenticate.")

   # Runtime setup
   org_id = get_org_id_by_session_robot_test(session_id)
   set_runtime(session_id=session_id, org_id=org_id, openai_key=openai_key, user_info=user_info)

   # LLM setup
   llm = ChatOpenAI(
      model="gpt-4.1-mini",
      temperature=0,
      api_key=openai_key,
      output_version="responses/v1",
   )
   llm_with_tools = llm.bind_tools(TOOLS)
   graph = build_llm_graph(llm_with_tools)

   # State management
   config = {"configurable": {"thread_id": session_id}}
   state = graph.get_state(config)
   prev_len = len(state.values["messages"]) if (state and state.values.get("messages")) else 0

   # Seed prompt
   if prev_len > 0:
      seed = [HumanMessage(content=question)]
   else:
      ist = pytz.timezone("Asia/Kolkata")
      now_str = datetime.now(ist).strftime("%A, %d %B %Y, %I:%M %p")
      system_rules = Nyla_Prompt.format(time=now_str)
      seed = [SystemMessage(content=system_rules), HumanMessage(content=question)]

   # Run graph to completion
   for _ in graph.stream({"messages": seed}, config, stream_mode="values"):
      pass

   # === DEBUG: print complete AIMessage objects (JSON style) ===
   print("\n================= FULL RAW MESSAGES =================")
   state_check = graph.get_state(config)
   if state_check and state_check.values and "messages" in state_check.values:
      for i, msg in enumerate(state_check.values["messages"], 1):
         print(f"\n--- Message {i} ({type(msg).__name__}) ---")
         try:
               import json
               from langchain_core.messages import BaseMessage

               if isinstance(msg, BaseMessage):
                  msg_dict = msg.dict()
                  print(json.dumps(msg_dict, indent=2, ensure_ascii=False))
               else:
                  print(repr(msg))
         except Exception as e:
               print("Error serializing message:", e)
               print(repr(msg))
   else:
      print("⚠️ No messages found.")
   print("======================================================\n")

   # Collect new state
   new_state = graph.get_state(config)
   all_msgs = (new_state.values.get("messages") if (new_state and new_state.values) else []) or []
   turn_msgs = all_msgs[prev_len:]

   # Extract last AI text
   def _last_ai_text(msgs):
      for m in reversed(msgs):
         if type(m).__name__ in ("AIMessage", "AIMessageChunk"):
               content = getattr(m, "content", "")
               if isinstance(content, list):
                  content = "".join(
                     p.get("text", "")
                     for p in content
                     if isinstance(p, dict) and p.get("type") == "text"
                  )
               return str(content).strip()
      return ""

   final_text = _last_ai_text(turn_msgs) or _last_ai_text(all_msgs)

   # Tool categorization
   used_tools = _collect_tools(turn_msgs)
   categorized = _categorize(used_tools)

   return final_text.strip(), categorized["label"], categorized["used"]

def print_graph_history(session_id: str, graph):
   """Print the full conversation history for a given session"""
   config = {"configurable": {"thread_id": session_id}}
   
   try:
      # Get current state
      state = graph.get_state(config)
      
      if state and hasattr(state, 'values') and state.values and state.values.get("messages"):
         messages = state.values["messages"]
         print(f"\n=== CONVERSATION HISTORY (Session: {session_id}) ===")
         print(f"Total messages: {len(messages)}")
         print("-" * 80)
         
         for i, msg in enumerate(messages):
               msg_type = type(msg).__name__
               
               # Handle different message types
               if hasattr(msg, 'content'):
                  content = msg.content
                  
                  # Handle content that might be a list (for tool calls/responses)
                  if isinstance(content, list):
                     content_str = ""
                     for part in content:
                           if isinstance(part, dict):
                              if part.get("type") == "text":
                                 content_str += part.get("text", "")
                              else:
                                 content_str += str(part)
                           else:
                              content_str += str(part)
                     content = content_str
                  
                  print(f"{i+1}. [{msg_type}]:")
                  print(f"   Content: {content}")
                  
                  # Show tool calls if present
                  if hasattr(msg, 'tool_calls') and msg.tool_calls:
                     print(f"   Tool Calls:")
                     for j, tool_call in enumerate(msg.tool_calls):
                           tool_name = tool_call.get('name', 'Unknown')
                           tool_args = tool_call.get('args', {})
                           print(f"     {j+1}. {tool_name}({tool_args})")
                  
                  # Show additional info if available
                  if hasattr(msg, 'name') and msg.name:
                     print(f"   Name: {msg.name}")
                     
                  print("-" * 40)
                  
         print("=" * 80)
      else:
         print(f"No conversation history found for session: {session_id}")
         print("State details:")
         if state:
               print(f"  State exists: True")
               print(f"  Has values: {hasattr(state, 'values')}")
               if hasattr(state, 'values'):
                  print(f"  Values: {state.values}")
         else:
               print("  State: None")
         
   except Exception as e:
      print(f"Error retrieving history: {e}")
      import traceback
      traceback.print_exc()

# Alternative function to see ALL state history (all checkpoints)
def print_detailed_state_history(session_id: str, graph, limit: int = 10):
   """Print detailed state history with all checkpoints and messages"""
   config = {"configurable": {"thread_id": session_id}}
   
   try:
      print(f"\n=== DETAILED STATE HISTORY (Session: {session_id}) ===")
      
      states = list(graph.get_state_history(config, limit=limit))
      
      if not states:
         print("No state history found.")
         return
         
      print(f"Found {len(states)} states in history")
      print("=" * 80)
      
      for i, state_snapshot in enumerate(reversed(states)):  # Show in chronological order
         print(f"\n--- CHECKPOINT {i+1} ---")
         print(f"Step: {state_snapshot.step}")
         print(f"Next: {state_snapshot.next}")
         print(f"Created: {state_snapshot.created_at}")
         print(f"Config ID: {state_snapshot.config.get('configurable', {}).get('checkpoint_id', 'N/A')}")
         
         if state_snapshot.values and state_snapshot.values.get("messages"):
               messages = state_snapshot.values["messages"]
               print(f"Messages in this checkpoint: {len(messages)}")
               
               for j, msg in enumerate(messages):
                  msg_type = type(msg).__name__
                  content = getattr(msg, 'content', 'No content')
                  
                  # Handle list content
                  if isinstance(content, list):
                     content_str = ""
                     for part in content:
                           if isinstance(part, dict) and part.get("type") == "text":
                              content_str += part.get("text", "")
                           else:
                              content_str += str(part)
                     content = content_str
                  
                  print(f"  {j+1}. [{msg_type}]: {content[:100]}{'...' if len(str(content)) > 100 else ''}")
         else:
               print("No messages in this checkpoint")
         
         print("-" * 40)
      
      print("=" * 80)
      
   except Exception as e:
      print(f"Error retrieving detailed state history: {e}")
      import traceback
      traceback.print_exc()
