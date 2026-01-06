import os
import asyncio
import re
import tempfile
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from dotenv import load_dotenv

load_dotenv()

class TelegramFamBot:
    def __init__(self):
        # Get credentials from environment variables
        self.api_id = int(os.getenv('TELEGRAM_API_ID', 0))
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        if not self.api_id or not self.api_hash:
            raise ValueError("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH")
        
        if not self.session_string:
            print("⚠️ WARNING: TELEGRAM_SESSION_STRING not set")
        
        # Target chat ID
        self.chat_id = -1003674153946  # Your group ID
        
        # Initialize client
        self.client = None
        self.initialize_client()
        
        # Response tracking
        self.last_response = None
        self.response_received = asyncio.Event()
        self.command_message_id = None
        
    def initialize_client(self):
        """Initialize Telegram client"""
        try:
            self.client = TelegramClient(
                StringSession(self.session_string) if self.session_string else None,
                self.api_id,
                self.api_hash
            )
            print("✅ Telegram client initialized")
        except Exception as e:
            print(f"❌ Error initializing client: {e}")
            raise
    
    async def connect(self):
        """Connect to Telegram"""
        try:
            if not self.client.is_connected():
                await self.client.start()
                me = await self.client.get_me()
                username = me.username or "No username"
                print(f"✅ Connected as {me.first_name} (@{username})")
            
            # Setup message handler
            await self.setup_handlers()
            
            return True
        except SessionPasswordNeededError:
            print("❌ Two-factor authentication required")
            raise Exception("Two-factor authentication required. Please login via CLI first.")
        except FloodWaitError as e:
            print(f"❌ Flood wait required: {e.seconds} seconds")
            raise Exception(f"Flood wait: Try again in {e.seconds} seconds")
        except Exception as e:
            print(f"❌ Connection error: {e}")
            raise
    
    async def setup_handlers(self):
        """Setup event handler for bot responses"""
        
        @self.client.on(events.NewMessage(chats=self.chat_id))
        async def handler(event):
            try:
                # Only process messages after our command
                if self.command_message_id and event.message.id <= self.command_message_id:
                    return
                
                sender = await event.get_sender()
                if sender and sender.bot:
                    message_text = event.message.message or ""
                    
                    # Check for text response
                    if message_text and any(keyword in message_text.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:', 'FAM:']):
                        self.last_response = message_text
                        self.response_received.set()
                        print(f"📥 Received bot text response")
                    
                    # Check for document
                    elif event.message.media and hasattr(event.message.media, 'document'):
                        try:
                            print("📄 Downloading document...")
                            # Create temp file
                            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as tmp:
                                tmp_path = tmp.name
                            
                            # Download file
                            await event.message.download_media(file=tmp_path)
                            
                            # Read file
                            with open(tmp_path, 'r', encoding='utf-8', errors='ignore') as f:
                                file_content = f.read()
                                self.last_response = file_content
                            
                            # Clean up
                            os.unlink(tmp_path)
                            
                            self.response_received.set()
                            print(f"📥 Received document with {len(file_content)} chars")
                        except Exception as e:
                            print(f"❌ Error processing document: {e}")
            except Exception as e:
                print(f"❌ Handler error: {e}")
    
    async def send_fam_command(self, query, timeout=30):
        """
        Send /fam command to the group and wait for response
        """
        try:
            # Reset response tracking
            self.last_response = None
            self.response_received.clear()
            self.command_message_id = None
            
            # Send command
            command = f"/fam {query}"
            print(f"📤 Sending: {command}")
            
            message = await self.client.send_message(self.chat_id, command)
            self.command_message_id = message.id
            
            # Wait for response
            try:
                await asyncio.wait_for(self.response_received.wait(), timeout=timeout)
                print(f"✅ Response received")
                return self.last_response
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for response")
                return None
                
        except Exception as e:
            print(f"❌ Error sending command: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Telegram"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            print("✅ Disconnected")
