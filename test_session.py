#!/usr/bin/env python3
"""
Test if your session string works
"""
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

async def test_session():
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    session_string = os.getenv('TELEGRAM_SESSION_STRING')
    
    if not all([api_id, api_hash, session_string]):
        print("❌ Missing environment variables")
        return
    
    try:
        client = TelegramClient(
            StringSession(session_string),
            int(api_id),
            api_hash
        )
        
        await client.start()
        me = await client.get_me()
        print(f"✅ Session is valid!")
        print(f"👤 User: {me.first_name} (@{me.username})")
        print(f"📞 Phone: {me.phone}")
        
        await client.disconnect()
        
    except Exception as e:
        print(f"❌ Invalid session: {e}")

if __name__ == "__main__":
    asyncio.run(test_session())
