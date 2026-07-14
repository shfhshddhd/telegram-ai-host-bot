import google.generativeai as genai
from config import GEMINI_API_KEY, SYSTEM_PROMPT
from database import db
import asyncio
from typing import Optional
import json
from datetime import datetime

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-1.5-flash"

class AIHandler:
    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
    
    async def generate_reply(self, message_text: str, host_user_id: int, chat_id: int,
                            chat_title: str = "", sender_name: str = "someone", host_name: str = "User") -> Optional[str]:
        conversation_history = await db.get_conversation_summary(host_user_id, chat_id)
        saved_context = await db.get_context(host_user_id, chat_id) or {}
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        prompt = f"""[SYSTEM]
Current time: {current_time}
Your name: {host_name}
Conversation partner: {sender_name}
Chat/Group: {chat_title}

[CONTEXT]
Additional context: {json.dumps(saved_context)}

[FULL CONVERSATION HISTORY]
{conversation_history}

[CURRENT MESSAGE]
{sender_name}: {message_text}

[INSTRUCTIONS]
Reply as {host_name}. You have FULL memory of the conversation above.
Refer to previous topics naturally. Be human. Be casual.
Write ONLY your reply message, nothing else:"""
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.model.generate_content(
                prompt, generation_config={"temperature": 0.85, "top_p": 0.95, "top_k": 40, "max_output_tokens": 300}
            ))
            reply = response.text.strip()
            
            await db.save_message(host_user_id, chat_id, chat_title, "user", message_text, sender_name)
            await db.save_message(host_user_id, chat_id, chat_title, "assistant", reply, host_name)
            
            keywords = []
            for word in (message_text + " " + reply).lower().split():
                if len(word) > 4 and word not in ['kya', 'hai', 'aap', 'kaise', 'thik', 'nahi', 'koi', 'sab', 'bahut', 'apna', 'mere', 'abhi', 'yahan', 'wahan']:
                    keywords.append(word)
            await db.save_context(host_user_id, chat_id, {"keywords": list(set(keywords))[-20:], "updated_at": current_time})
            
            return reply
        except Exception as e:
            print(f"❌ AI Error: {e}")
            return None

ai_handler = AIHandler()
