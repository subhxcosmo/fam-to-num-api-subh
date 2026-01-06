import os
import re
import time
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Import telethon synchronously
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

class TelegramFamBot:
    def __init__(self):
        self.api_id = int(os.getenv('TELEGRAM_API_ID', 0))
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        self.chat_id = -1003674153946
        
        if not all([self.api_id, self.api_hash, self.session_string]):
            raise ValueError("Missing Telegram credentials")
        
        self.client = None
        self.last_bot_message_id = 0
    
    def connect(self):
        """Connect to Telegram synchronously"""
        if not self.client:
            self.client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash
            )
        
        if not self.client.is_connected():
            self.client.start()
            print(f"✅ Connected as {self.client.get_me().first_name}")
        
        return self.client
    
    def disconnect(self):
        """Disconnect from Telegram"""
        if self.client and self.client.is_connected():
            self.client.disconnect()
    
    def get_fam_info(self, query):
        """Get FAM information synchronously"""
        try:
            # Connect if not connected
            self.connect()
            
            # Send command
            command = f"/fam {query}"
            print(f"📤 Sending command: {command}")
            
            # Send message
            self.client.send_message(self.chat_id, command)
            
            # Wait a moment for bot to process
            time.sleep(3)
            
            # Get recent messages from bots
            response_text = None
            
            # Check last 15 messages for bot response
            for message in self.client.iter_messages(self.chat_id, limit=15):
                if message.sender and message.sender.bot:
                    print(f"📥 Found bot message: {message.id}")
                    
                    # Check text message
                    if message.message:
                        if any(keyword in message.message.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                            response_text = message.message
                            break
                    
                    # Check for document
                    elif message.media and hasattr(message.media, 'document'):
                        try:
                            # Download file
                            file_path = self.client.download_media(message, file='temp_doc')
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                response_text = f.read()
                            os.remove(file_path)
                            break
                        except Exception as e:
                            print(f"❌ Error reading document: {e}")
                            continue
            
            if response_text:
                return self.parse_fam_response(response_text)
            else:
                print("❌ No bot response found")
                return None
                
        except Exception as e:
            print(f"❌ Error in get_fam_info: {e}")
            raise
    
    def parse_fam_response(self, text):
        """Parse FAM response text"""
        info = {}
        
        # FAM ID
        fam_match = re.search(r'FAM ID\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
        if not fam_match:
            fam_match = re.search(r'FAM\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
        if fam_match:
            info['fam_id'] = fam_match.group(1).strip()
        
        # NAME
        name_match = re.search(r'NAME\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
        if name_match:
            info['name'] = name_match.group(1).strip()
        
        # PHONE
        phone_match = re.search(r'PHONE\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
        if phone_match:
            info['phone'] = phone_match.group(1).strip()
        
        # TYPE
        type_match = re.search(r'TYPE\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
        if type_match:
            info['type'] = type_match.group(1).strip().lower()
        
        return info

# Global bot instance
bot_instance = None

def get_bot():
    """Get or create bot instance"""
    global bot_instance
    if bot_instance is None:
        bot_instance = TelegramFamBot()
        bot_instance.connect()
    return bot_instance

@app.route('/api', methods=['GET'])
def api_endpoint():
    """Main API endpoint"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    try:
        bot = get_bot()
        fam_info = bot.get_fam_info(query)
        
        if fam_info and fam_info.get('fam_id'):
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_info
            })
        elif fam_info:
            # Partial info
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_info,
                'note': 'Partial information retrieved'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not retrieve FAM information',
                'query': query
            }), 404
            
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        bot = get_bot()
        if bot.client and bot.client.is_connected():
            status = 'connected'
        else:
            status = 'disconnected'
        
        return jsonify({
            'status': 'healthy',
            'telegram': status,
            'service': 'FAM API'
        })
    except Exception as e:
        return jsonify({
            'status': 'degraded',
            'telegram': 'error',
            'error': str(e)
        })

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'service': 'Telegram FAM API',
        'description': 'Get FAM information from Telegram bot',
        'usage': 'GET /api?fam=upi@fam',
        'example': 'https://' + request.host + '/api?fam=sugarsingh@fam',
        'endpoints': {
            '/api': 'Get FAM information',
            '/health': 'Health check',
            '/': 'This page'
        }
    })

@app.route('/test', methods=['GET'])
def test_connection():
    """Test Telegram connection"""
    try:
        bot = get_bot()
        me = bot.client.get_me()
        return jsonify({
            'success': True,
            'user': {
                'id': me.id,
                'first_name': me.first_name,
                'username': me.username,
                'phone': me.phone
            },
            'chat_id': bot.chat_id,
            'connected': bot.client.is_connected()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting FAM API on port {port}")
    
    # Initialize bot on startup
    try:
        get_bot()
        print("✅ Bot initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Bot initialization failed: {e}")
        print("⚠️ The bot will be initialized on first request")
    
    app.run(host='0.0.0.0', port=port, debug=False)
