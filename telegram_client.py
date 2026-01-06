import os
import asyncio
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel
from dotenv import load_dotenv

load_dotenv()

class TelegramFamBot:
    def __init__(self):
        # Get credentials from environment variables
        self.api_id = int(os.getenv('TELEGRAM_API_ID', 0))
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        if not all([self.api_id, self.api_hash, self.session_string]):
            raise ValueError("Missing Telegram credentials in environment variables")
        
        # Target chat ID
        self.chat_id = -1003674153946  # Your group ID
        
        # Initialize client with string session
        self.client = TelegramClient(
            StringSession(self.session_string),
            self.api_id,
            self.api_hash
        )
        
        # Response tracking
        self.last_response = None
        self.response_event = asyncio.Event()
        
        # Setup message handler
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup event handlers for bot responses"""
        
        @self.client.on(events.NewMessage(chats=self.chat_id))
        async def handler(event):
            # Check if message is from a bot or contains FAM info
            sender = await event.get_sender()
            if sender.bot:
                message_text = event.message.message or ""
                
                # Check if this looks like a FAM response
                if any(keyword in message_text.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                    self.last_response = message_text
                    self.response_event.set()
                    
                    # Also check for media/documents
                    if event.message.media:
                        try:
                            # Download and read the file
                            path = await event.message.download_media()
                            with open(path, 'r', encoding='utf-8') as f:
                                file_content = f.read()
                                self.last_response = file_content
                            os.remove(path)  # Clean up
                        except:
                            pass
    
    async def connect(self):
        """Connect to Telegram"""
        await self.client.start()
        print(f"✅ Connected as {await self.client.get_me().username}")
    
    async def send_fam_command(self, query, timeout=30):
        """
        Send /fam command to the group and wait for response
        """
        try:
            # Reset response tracking
            self.last_response = None
            self.response_event.clear()
            
            # Send command to the group
            command = f"/fam {query}"
            await self.client.send_message(self.chat_id, command)
            print(f"📤 Sent command: {command}")
            
            # Wait for response with timeout
            try:
                await asyncio.wait_for(self.response_event.wait(), timeout=timeout)
                
                if self.last_response:
                    return self.last_response
                else:
                    return None
                    
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for bot response")
                return None
                
        except Exception as e:
            print(f"❌ Error sending command: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Telegram"""
        await self.client.disconnect()
