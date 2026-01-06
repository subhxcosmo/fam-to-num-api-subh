#!/usr/bin/env python3
"""
Script to generate Telegram session string
Run this locally to get your session string
"""
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("=" * 60)
    print("TELEGRAM SESSION STRING GENERATOR")
    print("=" * 60)
    
    # Get credentials from environment or input
    api_id = os.getenv('TELEGRAM_API_ID') or input("Enter your API ID: ")
    api_hash = os.getenv('TELEGRAM_API_HASH') or input("Enter your API Hash: ")
    phone = input("Enter your phone number (with country code, e.g., +919876543210): ")
    
    # Convert api_id to integer
    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ API ID must be a number!")
        return
    
    print("\n🔧 Creating client...")
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("📱 Starting authentication...")
        await client.start(phone=phone)
        
        # Get session string
        session_string = client.session.save()
        
        print("\n" + "=" * 60)
        print("✅ SESSION STRING GENERATED!")
        print("=" * 60)
        print(session_string)
        print("=" * 60)
        
        # Test connection
        me = await client.get_me()
        print(f"\n👤 Logged in as: {me.first_name} (@{me.username})")
        print(f"📞 Phone: {me.phone}")
        
        print("\n📝 IMPORTANT:")
        print("1. Copy the session string above")
        print("2. Add it to your Render environment variables as TELEGRAM_SESSION_STRING")
        print("3. Also add TELEGRAM_API_ID and TELEGRAM_API_HASH")
        print("4. Never share your session string with anyone!")

if __name__ == "__main__":
    asyncio.run(main())
