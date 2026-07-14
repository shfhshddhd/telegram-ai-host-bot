import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH, BOT_TOKEN
from database import db, init_db
from ai_handler import ai_handler
from userbot_handler import userbot_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
os.makedirs("sessions", exist_ok=True)
bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
pending_registrations = {}

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    sender = await event.get_sender()
    name = sender.first_name or "User"
    text = f"""👋 Namaste {name}!

Main ek **AI User Host Bot** hoon. Aap apna Telegram account host kar sakte hain aur main AI se aapki taraf se reply dunga.

**Memory Feature:** 🔥 Bot aapki saari baatcheet **permanently yaad rakhta hai** (PostgreSQL database mein).

**Commands:**
• /host - Apna account host karein
• /status - Hosting status dekhein
• /toggle - Auto-reply on/off
• /history - Apni recent chats ka history
• /clearhistory all - History clear karein
• /unhost - Hosting hata dein
• /help - Madad

⚠️ Bot aapke account ka access leta hai. Trusted use ke liye.
"""
    await event.reply(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/host'))
async def host_handler(event):
    sender = await event.get_sender()
    user_id = sender.id
    if await db.is_host(user_id):
        await event.reply("✅ Aap already hosted hain! /status se details dekhein.")
        return
    pending_registrations[user_id] = {"step": "phone"}
    await event.reply("📱 **Hosting Started!**\n\nKripya apna phone number international format mein bhejein.\nJaise: +919876543210\n\n❌ /cancel se cancel karein")

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_handler(event):
    user_id = event.sender_id
    if user_id in pending_registrations:
        temp_client = pending_registrations[user_id].get("temp_client")
        if temp_client:
            await temp_client.disconnect()
        del pending_registrations[user_id]
        await event.reply("❌ Registration cancelled.")
    else:
        await event.reply("Koi pending registration nahi hai.")

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    user_id = event.sender_id
    host = await db.get_host(user_id)
    if not host:
        await event.reply("❌ Aap abhi hosted nahi hain. /host se start karein.")
        return
    status = "🟢 Active" if host.get("active") else "🔴 Inactive"
    auto_reply = "🟢 On" if host.get("auto_reply") else "🔴 Off"
    async with db.pool.acquire() as conn:
        count_row = await conn.fetchval("SELECT COUNT(*) FROM chat_history WHERE host_user_id = $1", user_id)
        msg_count = count_row or 0
    text = f"""📊 **Hosting Status**

👤 Name: {host.get('name', 'N/A')}
📱 Phone: {host.get('phone', 'N/A')}
✅ Status: {status}
🤖 Auto-Reply: {auto_reply}
💬 Messages Stored: {msg_count}
📅 Since: {host.get('created_at', 'N/A')}

Commands: /toggle, /history, /clearhistory all, /unhost"""
    await event.reply(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/toggle'))
async def toggle_handler(event):
    user_id = event.sender_id
    if not await db.is_host(user_id):
        await event.reply("❌ Aap hosted nahi hain. Pehle /host karein.")
        return
    new_state = await db.toggle_auto_reply(user_id)
    state_text = "ON ✅" if new_state else "OFF ❌"
    await event.reply(f"🤖 Auto-reply ab **{state_text}** hai!")

@bot.on(events.NewMessage(pattern=r'/clearhistory(?:\s+(.+))?'))
async def clear_history_handler(event):
    user_id = event.sender_id
    if not await db.is_host(user_id):
        await event.reply("❌ Aap hosted nahi hain.")
        return
    args = event.pattern_match.group(1)
    if not args:
        await event.reply("Kis chat ka history clear karna hai? /clearhistory all se saara clear ho jayega.")
        return
    if args.strip().lower() == "all":
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_history WHERE host_user_id = $1", user_id)
            await conn.execute("DELETE FROM conversation_context WHERE host_user_id = $1", user_id)
        await event.reply("✅ **Sabhi chats ka history clear kar diya gaya!**")
    else:
        await event.reply("❌ /clearhistory all use karein.")

@bot.on(events.NewMessage(pattern='/history'))
async def history_handler(event):
    user_id = event.sender_id
    if not await db.is_host(user_id):
        await event.reply("❌ Aap hosted nahi hain.")
        return
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT chat_id, chat_title, 
                   (SELECT message_text FROM chat_history ch2 WHERE ch2.host_user_id = $1 AND ch2.chat_id = ch.chat_id ORDER BY timestamp DESC LIMIT 1) as last_msg,
                   (SELECT MAX(timestamp) FROM chat_history ch3 WHERE ch3.host_user_id = $1 AND ch3.chat_id = ch.chat_id) as last_time,
                   (SELECT COUNT(*) FROM chat_history ch4 WHERE ch4.host_user_id = $1 AND ch4.chat_id = ch.chat_id) as msg_count
            FROM chat_history ch WHERE host_user_id = $1
            ORDER BY last_time DESC NULLS LAST LIMIT 10
        """, user_id)
    if not rows:
        await event.reply("📭 Koi chat history nahi hai.")
        return
    text = "📜 **Aapki Recent Chats:**\n\n"
    for i, row in enumerate(rows, 1):
        title = row['chat_title'] or f"Chat {row['chat_id']}"
        last_msg = (row['last_msg'] or "No messages")[:40]
        msg_count = row['msg_count']
        last_time = row['last_time'].strftime("%d-%b %H:%M") if row['last_time'] else "N/A"
        text += f"{i}. **{title}** - 💬 {msg_count} msgs | ⏰ {last_time}\n   \"{last_msg}...\"\n\n"
    await event.reply(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/unhost'))
async def unhost_handler(event):
    user_id = event.sender_id
    if not await db.is_host(user_id):
        await event.reply("❌ Aap hosted nahi hain.")
        return
    await userbot_manager.stop_userbot(user_id)
    await db.remove_host(user_id)
    await event.reply("✅ **Hosting removed!** Aapka saara data delete kar diya gaya hai.")

@bot.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    text = """❓ **Help / Madad**

**🤖 Ye Bot Kya Hai?**
Aap apna Telegram account host karte hain. Jab koi aapko message karega, AI insaani tarah reply karega. Kisi ko nahi pata chalega ki bot hai!

**🧠 Memory System**
• Saari baatcheet PostgreSQL database mein save hoti hai
• Bot purani baatein yaad rakhta hai
• Chahe bot 100 baar restart ho, sab yaad rahega
• /history se saari chats dekh sakte hain
• /clearhistory all se saaf kar sakte hain

**Commands:**
• /start - Bot start
• /host - Account host karein
• /status - Status check
• /toggle - Auto-reply on/off
• /history - Chat history
• /clearhistory all - History clear
• /unhost - Hosting hata dein
• /help - Ye help

**⚠️ Important:** Bot aapke account ka access leta hai."""
    await event.reply(text, parse_mode='markdown')

@bot.on(events.NewMessage())
async def message_handler(event):
    if event.text and event.text.startswith('/'):
        return
    user_id = event.sender_id
    text = event.text.strip() if event.text else ""
    if user_id not in pending_registrations:
        return
    reg = pending_registrations[user_id]
    step = reg.get("step")
    if step == "phone":
        if not text.startswith('+') or not text[1:].isdigit():
            await event.reply("❌ Invalid format. Send: +919876543210")
            return
        temp_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await temp_client.connect()
        try:
            sent_code = await temp_client.send_code_request(text)
            reg["step"] = "code"
            reg["phone"] = text
            reg["temp_client"] = temp_client
            reg["phone_code_hash"] = sent_code.phone_code_hash
            await event.reply("✅ **Code sent!** Telegram OTP enter karein. Jaise: 12345\n\n❌ /cancel")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
            await temp_client.disconnect()
            del pending_registrations[user_id]
    elif step == "code":
        code = text.strip()
        temp_client = reg.get("temp_client")
        phone = reg.get("phone")
        try:
            await temp_client.sign_in(phone=phone, code=code, phone_code_hash=reg["phone_code_hash"])
            me = await temp_client.get_me()
            session_str = temp_client.session.save()
            await db.add_host(user_id=user_id, phone_number=phone, session_string=session_str, name=me.first_name or "User")
            await userbot_manager.start_userbot_from_session(user_id, session_str)
            await event.reply(f"✅ **Hosting Successful!** 🎉\n\n👤 Account: {me.first_name}\n🧠 Memory: Active (PostgreSQL)\n\nAb jab koi aapko message karega, AI reply karega purani baatein yaad rakh ke!\n\nCommands: /status, /toggle, /history, /unhost")
            await temp_client.disconnect()
            del pending_registrations[user_id]
        except SessionPasswordNeededError:
            reg["step"] = "2fa_password"
            await event.reply("🔐 **2FA Password Required!** Apna password bhejein.")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    elif step == "2fa_password":
        password = text.strip()
        temp_client = reg.get("temp_client")
        try:
            await temp_client.sign_in(password=password)
            me = await temp_client.get_me()
            session_str = temp_client.session.save()
            await db.add_host(user_id=user_id, phone_number=reg["phone"], session_string=session_str, name=me.first_name or "User")
            await userbot_manager.start_userbot_from_session(user_id, session_str)
            await event.reply(f"✅ **Hosting Successful!** 🎉\n\n👤 Account: {me.first_name}\n🧠 Memory: Active\n\nAI ab aapki taraf se reply karega!")
            await temp_client.disconnect()
            del pending_registrations[user_id]
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")

async def restore_hosts():
    print("🔄 Restoring hosts with memory...")
    hosts = await db.get_all_hosts()
    for host_data in hosts:
        user_id = host_data['user_id']
        session = host_data.get('session_string')
        name = host_data.get('name', 'Unknown')
        if session:
            try:
                await userbot_manager.start_userbot_from_session(user_id, session)
                print(f"✅ Restored: {name}")
            except Exception as e:
                print(f"❌ Failed: {name}: {e}")
                await db.set_active(user_id, False)
    print(f"🔄 {len(hosts)} hosts restored with memory.")

async def main():
    print("╔════════════════════════════════╗")
    print("║  AI USER HOST BOT WITH MEMORY ║")
    print("╚════════════════════════════════╝")
    await init_db()
    await bot.start(bot_token=BOT_TOKEN)
    await restore_hosts()
    print("✅ Ready! Memory system active with PostgreSQL")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        asyncio.run(userbot_manager.stop_all())
