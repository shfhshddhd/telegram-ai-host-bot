from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityMention
from telethon.sessions import StringSession
from database import db
from ai_handler import ai_handler
from config import API_ID, API_HASH
import asyncio

class UserBotManager:
    def __init__(self):
        self.clients = {}
    
    async def start_userbot_from_session(self, user_id: int, session_string: str):
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.start()
        me = await client.get_me()
        host = await db.get_host(user_id)
        host_name = host.get("name", me.first_name or "User") if host else (me.first_name or "User")
        print(f"✅ Userbot started: {host_name}")
        
        @client.on(events.NewMessage(incoming=True))
        async def auto_reply_handler(event):
            host = await db.get_host(user_id)
            if not host or not host.get("auto_reply", True):
                return
            me_now = await client.get_me()
            if event.sender_id == me_now.id:
                return
            
            chat_title = ""
            if event.is_group:
                is_mentioned = False
                if event.message.entities:
                    for entity in event.message.entities:
                        if isinstance(entity, MessageEntityMention) and entity.user_id == me_now.id:
                            is_mentioned = True
                            break
                if event.message.is_reply:
                    try:
                        replied_msg = await event.get_reply_message()
                        if replied_msg and replied_msg.sender_id == me_now.id:
                            is_mentioned = True
                    except:
                        pass
                if not is_mentioned:
                    return
                try:
                    chat = await event.get_chat()
                    chat_title = chat.title or "Group"
                except:
                    chat_title = "Group"
            else:
                chat_title = "Private Chat"
            
            sender = await event.get_sender()
            sender_name = sender.first_name or "someone"
            if hasattr(sender, 'username') and sender.username:
                sender_name = f"{sender.first_name or ''} (@{sender.username})"
            
            host = await db.get_host(user_id)
            host_name = host.get("name", me_now.first_name or "User") if host else (me_now.first_name or "User")
            print(f"💬 [{host_name}] Message from {sender_name}: {event.text[:60]}...")
            
            reply_text = await ai_handler.generate_reply(
                message_text=event.text, host_user_id=user_id, chat_id=event.chat_id,
                chat_title=chat_title, sender_name=sender_name, host_name=host_name
            )
            if reply_text:
                typing_duration = min(len(reply_text) * 0.03, 3.0)
                async with client.action(event.chat_id, "typing"):
                    await asyncio.sleep(typing_duration)
                await event.reply(reply_text)
                print(f"✅ [{host_name}] Replied: {reply_text[:60]}...")
            else:
                print(f"❌ [{host_name}] Failed to generate reply")
        
        self.clients[user_id] = client
        return client
    
    async def stop_userbot(self, user_id: int):
        if user_id in self.clients:
            await self.clients[user_id].disconnect()
            del self.clients[user_id]
            return True
        return False
    
    async def stop_all(self):
        for user_id, client in self.clients.items():
            try:
                await client.disconnect()
            except:
                pass
        self.clients.clear()

userbot_manager = UserBotManager()
