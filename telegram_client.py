import os
import asyncio
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv

load_dotenv()

class TelegramFamBot:
    def __init__(self):
        # Get credentials from environment variables
        self.api_id = os.getenv('TELEGRAM_API_ID', '')
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        self.phone = os.getenv('TELEGRAM_PHONE', '')  # Optional: for login
        
        # Validate required credentials
        if not self.api_id or not self.api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
        
        # Target chat ID
        self.chat_id = -1003674153946  # Your group ID
        
        # Initialize client
        self.client = None
        self.initialize_client()
        
        # Response tracking
        self.last_response = None
        self.response_event = asyncio.Event()
        
        # Setup message handler
        self.setup_handlers()
    
    def initialize_client(self):
        """Initialize Telegram client with session string or phone"""
        try:
            if self.session_string:
                print("🔧 Initializing with session string...")
                # Validate session string format
                if len(self.session_string) < 10:
                    raise ValueError("Session string too short")
                
                self.client = TelegramClient(
                    StringSession(self.session_string),
                    int(self.api_id),
                    self.api_hash
                )
                print("✅ Client initialized with session string")
            elif self.phone:
                print("🔧 Initializing with phone number...")
                self.client = TelegramClient(
                    'session',
                    int(self.api_id),
                    self.api_hash
                )
                print("✅ Client initialized with phone")
            else:
                raise ValueError("Either TELEGRAM_SESSION_STRING or TELEGRAM_PHONE is required")
                
        except ValueError as e:
            print(f"❌ Invalid session string: {e}")
            raise
        except Exception as e:
            print(f"❌ Error initializing client: {e}")
            raise
    
    def setup_handlers(self):
        """Setup event handlers for bot responses"""
        
        @self.client.on(events.NewMessage(chats=self.chat_id))
        async def handler(event):
            # Check if message is from a bot or contains FAM info
            sender = await event.get_sender()
            message_text = event.message.message or ""
            
            # Debug logging
            print(f"📥 Received message from {'bot' if sender.bot else 'user'}: {message_text[:100]}...")
            
            # Check if this looks like a FAM response
            if (sender.bot and 
                any(keyword in message_text.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:'])):
                
                print(f"✅ Found FAM response from bot")
                self.last_response = message_text
                self.response_event.set()
                
                # Also check for media/documents
                if event.message.media:
                    try:
                        print("📎 Downloading media file...")
                        # Download and read the file
                        path = await event.message.download_media(file='downloads/')
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                            self.last_response = file_content
                            print(f"📄 File content length: {len(file_content)}")
                        os.remove(path)  # Clean up
                    except Exception as e:
                        print(f"⚠️ Could not read media file: {e}")
    
    async def connect(self):
        """Connect to Telegram"""
        try:
            await self.client.start(phone=self.phone if self.phone else None)
            me = await self.client.get_me()
            print(f"✅ Connected as {me.first_name} (@{me.username})")
            return True
        except SessionPasswordNeededError:
            print("🔒 Two-factor authentication required")
            # For 2FA, you'll need to handle this manually or set it up in advance
            password = os.getenv('TELEGRAM_PASSWORD')
            if password:
                await self.client.start(phone=self.phone, password=password)
                me = await self.client.get_me()
                print(f"✅ Connected with 2FA as {me.first_name}")
                return True
            else:
                raise Exception("Two-factor authentication required but no password provided")
        except Exception as e:
            print(f"❌ Connection error: {e}")
            raise
    
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
            print(f"📤 Sending command: {command}")
            
            # Ensure we're in the correct chat
            entity = await self.client.get_entity(self.chat_id)
            await self.client.send_message(entity, command)
            print(f"✅ Command sent to chat ID: {self.chat_id}")
            
            # Wait for response with timeout
            try:
                print("⏳ Waiting for bot response...")
                await asyncio.wait_for(self.response_event.wait(), timeout=timeout)
                
                if self.last_response:
                    print(f"📨 Received response: {self.last_response[:200]}...")
                    return self.last_response
                else:
                    print("⚠️ No response captured")
                    return None
                    
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for bot response")
                return None
                
        except Exception as e:
            print(f"❌ Error sending command: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Telegram"""
        if self.client:
            await self.client.disconnect()
            print("🔌 Disconnected from Telegram")
