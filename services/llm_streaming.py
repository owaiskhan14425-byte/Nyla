import os
import openai
from services.llm_model import  detect_language, prompt, MAX_TOKEN
from datetime import datetime
from utils.helpers import normalize_question,get_user_info_prompt
from utils.logger import log_error

async def ask_llm_stream(context: str, chat_history: str, question: str, user_info=None, openai_key=None):
    client = openai.OpenAI(api_key=openai_key)
    today = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    language = detect_language(question)
    user_info_for_prompt = get_user_info_prompt(user_info)
    norm_question = normalize_question(question)
    prompt_text = prompt.format(
        context=context,
        chat_history=chat_history,
        question=norm_question,
        current_date_info=today,
        language=language,
        MAX_TOKEN=MAX_TOKEN,
        User_Info=user_info_for_prompt
    )
    final = '' 
    try:
        stream = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=MAX_TOKEN,
            temperature=0.5,
            stream=True
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and hasattr(delta, "content") and delta.content:
                final += delta.content
                yield delta.content
        yield ""
        print(final)
        
        
    except Exception as e:
        log_error(f"streaming------: {e}")
        print("Streaming error", e)
        yield "[[ERROR]]"
