import os
import asyncio
import re
import time
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv

load_dotenv()

class TelegramFamBot:
    def __init__(self):
        # Get credentials from environment variables
        self.api_id = int(os.getenv('TELEGRAM_API_ID', 0))
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        if not all([self.api_id, self.api_hash, self.session_string]):
            print("⚠️ Missing Telegram credentials. Please check environment variables.")
            raise ValueError("Missing Telegram credentials")
        
        # Target chat ID
        self.chat_id = -1003674153946  # Your group ID
        
        # Initialize client with string session
        print("🔧 Initializing with session string...")
        self.client = TelegramClient(
            StringSession(self.session_string),
            self.api_id,
            self.api_hash
        )
        
        # Response tracking
        self.last_response = None
        self.response_event = asyncio.Event()
        self.last_message_id = None
        
        # Setup message handler
        self.setup_handlers()
        
        print("✅ Client initialized with session string")
    
    def setup_handlers(self):
        """Setup event handlers for bot responses"""
        
        @self.client.on(events.NewMessage(chats=self.chat_id))
        async def handler(event):
            try:
                # Only process messages after our command
                if self.last_message_id and event.message.id <= self.last_message_id:
                    return
                
                sender = await event.get_sender()
                message_text = event.message.message or ""
                
                # Check if this is likely a bot response
                if sender and sender.bot:
                    # Check for FAM info patterns
                    if any(keyword in message_text.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                        self.last_response = message_text
                        self.response_event.set()
                        print(f"📥 Received bot response: {message_text[:100]}...")
                        
                    # Also check for media/documents
                    elif event.message.media and hasattr(event.message.media, 'document'):
                        try:
                            print("📄 Downloading document from bot...")
                            path = await event.message.download_media(file='temp_')
                            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                file_content = f.read()
                                self.last_response = file_content
                            os.remove(path)  # Clean up
                            self.response_event.set()
                            print(f"📥 Received file content: {file_content[:100]}...")
                        except Exception as e:
                            print(f"❌ Error downloading file: {e}")
            except Exception as e:
                print(f"❌ Error in message handler: {e}")
    
    async def connect(self):
        """Connect to Telegram"""
        if not self.client.is_connected():
            await self.client.start()
            me = await self.client.get_me()
            print(f"✅ Connected as {me.first_name} (@{me.username})")
        return True
    
    async def send_fam_command(self, query, timeout=45):
        """
        Send /fam command to the group and wait for response
        """
        try:
            # Reset response tracking
            self.last_response = None
            self.response_event.clear()
            
            # Ensure we're connected
            if not self.client.is_connected():
                await self.connect()
            
            # Send command to the group
            command = f"/fam {query}"
            print(f"📤 Sending command to chat {self.chat_id}: {command}")
            
            # Send message and track its ID
            message = await self.client.send_message(self.chat_id, command)
            self.last_message_id = message.id
            
            # Wait for response with timeout
            print("⏳ Waiting for bot response...")
            try:
                await asyncio.wait_for(self.response_event.wait(), timeout=timeout)
                
                if self.last_response:
                    print(f"✅ Got response of length: {len(self.last_response)}")
                    return self.last_response
                else:
                    print("❌ No response content")
                    return None
                    
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for bot response")
                # Try to check if there are any recent bot messages
                async for message in self.client.iter_messages(
                    self.chat_id, 
                    limit=10,
                    from_user="bot"
                ):
                    if message.id > self.last_message_id:
                        self.last_response = message.message or ""
                        print(f"📥 Found late response: {self.last_response[:100]}...")
                        return self.last_response
                
                return None
                
        except SessionPasswordNeededError:
            print("❌ 2FA password required. Please authenticate.")
            raise Exception("Two-factor authentication required")
        except Exception as e:
            print(f"❌ Error in send_fam_command: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Telegram"""
        if self.client.is_connected():
            await self.client.disconnect()
            print("✅ Disconnected from Telegram")

def extract_info_from_response(response_text):
    """Extract information from bot response"""
    if not response_text:
        return {}
    
    info = {}
    
    # Try multiple patterns
    patterns = {
        'fam_id': [r'FAM ID\s*[:=]\s*([^\n]+)', r'FAM\s*[:=]\s*([^\n]+)', r'ID\s*[:=]\s*([^\n]+)'],
        'name': [r'NAME\s*[:=]\s*([^\n]+)', r'Name\s*[:=]\s*([^\n]+)'],
        'phone': [r'PHONE\s*[:=]\s*([^\n]+)', r'Phone\s*[:=]\s*([^\n]+)', r'Mobile\s*[:=]\s*([^\n]+)'],
        'type': [r'TYPE\s*[:=]\s*([^\n]+)', r'Type\s*[:=]\s*([^\n]+)', r'Category\s*[:=]\s*([^\n]+)']
    }
    
    for key, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                info[key] = match.group(1).strip()
                break
    
    return info
