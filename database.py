import asyncpg
import json
from datetime import datetime
from typing import Optional, List, Dict

class PostgresDB:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS hosts (
                    user_id BIGINT PRIMARY KEY,
                    phone TEXT,
                    session_string TEXT,
                    name TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    auto_reply BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id BIGSERIAL PRIMARY KEY,
                    host_user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    chat_title TEXT,
                    role TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    sender_name TEXT,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (host_user_id) REFERENCES hosts(user_id) ON DELETE CASCADE
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_history_lookup 
                ON chat_history(host_user_id, chat_id, timestamp DESC)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_context (
                    id BIGSERIAL PRIMARY KEY,
                    host_user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    context_data JSONB,
                    last_updated TIMESTAMP DEFAULT NOW(),
                    UNIQUE(host_user_id, chat_id),
                    FOREIGN KEY (host_user_id) REFERENCES hosts(user_id) ON DELETE CASCADE
                )
            """)
        print("✅ PostgreSQL connected & tables ready")
    
    async def disconnect(self):
        if self.pool:
            await self.pool.close()
    
    async def add_host(self, user_id: int, phone: str, session_string: str, name: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO hosts (user_id, phone, session_string, name, active, auto_reply)
                VALUES ($1, $2, $3, $4, TRUE, TRUE)
                ON CONFLICT (user_id) 
                DO UPDATE SET session_string = $3, name = $4, active = TRUE, updated_at = NOW()
            """, user_id, phone, session_string, name)
    
    async def remove_host(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_history WHERE host_user_id = $1", user_id)
            await conn.execute("DELETE FROM conversation_context WHERE host_user_id = $1", user_id)
            result = await conn.execute("DELETE FROM hosts WHERE user_id = $1", user_id)
            return result != "DELETE 0"
    
    async def get_host(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM hosts WHERE user_id = $1", user_id)
            return dict(row) if row else None
    
    async def get_all_hosts(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM hosts WHERE active = TRUE")
            return [dict(row) for row in rows]
    
    async def is_host(self, user_id: int) -> bool:
        host = await self.get_host(user_id)
        return host is not None
    
    async def toggle_auto_reply(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE hosts SET auto_reply = NOT auto_reply, updated_at = NOW()
                WHERE user_id = $1 RETURNING auto_reply
            """, user_id)
            return row['auto_reply'] if row else None
    
    async def set_active(self, user_id: int, active: bool):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE hosts SET active = $2, updated_at = NOW() WHERE user_id = $1", user_id, active)
    
    async def save_message(self, host_user_id: int, chat_id: int, chat_title: str, role: str, message_text: str, sender_name: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO chat_history (host_user_id, chat_id, chat_title, role, message_text, sender_name)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, host_user_id, chat_id, chat_title, role, message_text, sender_name)
    
    async def get_conversation_history(self, host_user_id: int, chat_id: int, limit: int = 100) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, message_text, sender_name, timestamp 
                FROM chat_history WHERE host_user_id = $1 AND chat_id = $2
                ORDER BY timestamp DESC LIMIT $3
            """, host_user_id, chat_id, limit)
            return [dict(row) for row in reversed(rows)]
    
    async def get_conversation_summary(self, host_user_id: int, chat_id: int) -> str:
        messages = await self.get_conversation_history(host_user_id, chat_id, 100)
        if not messages:
            return "No previous conversation."
        context_parts = []
        for msg in messages:
            role = msg['role']
            text = msg['message_text']
            name = msg.get('sender_name', '')
            if role == 'user':
                context_parts.append(f"{name or 'User'}: {text}")
            elif role == 'assistant':
                context_parts.append(f"You: {text}")
            else:
                context_parts.append(f"System: {text}")
        return "\n".join(context_parts)
    
    async def save_context(self, host_user_id: int, chat_id: int, context_data: dict):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO conversation_context (host_user_id, chat_id, context_data, last_updated)
                VALUES ($1, $2, $3::jsonb, NOW())
                ON CONFLICT (host_user_id, chat_id)
                DO UPDATE SET context_data = $3::jsonb, last_updated = NOW()
            """, host_user_id, chat_id, json.dumps(context_data))
    
    async def get_context(self, host_user_id: int, chat_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT context_data FROM conversation_context
                WHERE host_user_id = $1 AND chat_id = $2
            """, host_user_id, chat_id)
            return row['context_data'] if row else None

db = None

async def init_db():
    global db
    from config import DATABASE_URL
    db = PostgresDB(DATABASE_URL)
    await db.connect()
    return db
