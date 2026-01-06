import os
import re
import time
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Telegram client will be initialized only when needed
telegram_client = None

def get_telegram_client():
    """Get Telegram client - initialize only when needed"""
    global telegram_client
    
    if telegram_client is None:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
        
        api_id = int(os.getenv('TELEGRAM_API_ID', 0))
        api_hash = os.getenv('TELEGRAM_API_HASH', '')
        session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        if not all([api_id, api_hash, session_string]):
            raise ValueError("Missing Telegram credentials in environment variables")
        
        telegram_client = TelegramClient(
            StringSession(session_string),
            api_id,
            api_hash
        )
        telegram_client.start()
        print(f"✅ Telegram client connected")
    
    return telegram_client

def close_telegram_client():
    """Close Telegram client if connected"""
    global telegram_client
    if telegram_client and telegram_client.is_connected():
        telegram_client.disconnect()
        telegram_client = None
        print("✅ Telegram client disconnected")

def extract_fam_info(text):
    """Extract FAM information from text response"""
    info = {}
    
    # FAM ID
    fam_match = re.search(r'FAM ID\s*[:=]\s*([^\n]+)', text, re.IGNORECASE)
    if not fam_match:
        fam_match = re.search(r'FAM\s*[:=]\s*([^\n]+)', text, re.IGNORECASE)
    if fam_match:
        info['fam_id'] = fam_match.group(1).strip()
    
    # NAME
    name_match = re.search(r'NAME\s*[:=]\s*([^\n]+)', text, re.IGNORECASE)
    if name_match:
        info['name'] = name_match.group(1).strip()
    
    # PHONE
    phone_match = re.search(r'PHONE\s*[:=]\s*([^\n]+)', text, re.IGNORECASE)
    if phone_match:
        info['phone'] = phone_match.group(1).strip()
    
    # TYPE
    type_match = re.search(r'TYPE\s*[:=]\s*([^\n]+)', text, re.IGNORECASE)
    if type_match:
        info['type'] = type_match.group(1).strip().lower()
    
    return info

def get_fam_data_from_telegram(query):
    """Main function to get FAM data from Telegram"""
    client = None
    try:
        # Get client
        client = get_telegram_client()
        
        # Target chat ID
        chat_id = -1003674153946
        
        # Send command
        command = f"/fam {query}"
        print(f"📤 Sending to chat {chat_id}: {command}")
        
        # Send message
        client.send_message(chat_id, command)
        
        # Wait for bot to respond
        print("⏳ Waiting for bot response...")
        time.sleep(5)  # Increased wait time
        
        # Get bot response from recent messages
        response_text = None
        
        # Check last 20 messages
        messages = client.get_messages(chat_id, limit=20)
        
        for message in messages:
            # Check if message is from a bot
            sender = client.get_entity(message.sender_id)
            if hasattr(sender, 'bot') and sender.bot:
                print(f"🤖 Found message from bot: {message.id}")
                
                # Check text content
                if message.message:
                    message_text = message.message
                    if any(keyword in message_text.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:', 'FAM:']):
                        print(f"📝 Found text response")
                        response_text = message_text
                        break
                
                # Check for document
                elif message.media:
                    try:
                        print("📄 Downloading document...")
                        # Download file
                        file_path = client.download_media(message, file='temp_fam')
                        
                        # Read file
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                            response_text = file_content
                        
                        # Clean up
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        
                        print(f"📖 Read {len(file_content)} chars from document")
                        break
                    except Exception as e:
                        print(f"⚠️ Could not read document: {e}")
                        continue
        
        if response_text:
            print(f"✅ Got response: {response_text[:100]}...")
            return extract_fam_info(response_text)
        else:
            print("❌ No valid bot response found")
            return None
            
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        # Close client on error
        if client and client.is_connected():
            client.disconnect()
        raise
    
    finally:
        # Don't disconnect - keep connection alive for next request
        pass

@app.route('/api', methods=['GET'])
def get_fam_info():
    """API endpoint - synchronous, simple"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    print(f"🔍 Processing request for: {query}")
    
    try:
        fam_data = get_fam_data_from_telegram(query)
        
        if fam_data and fam_data.get('fam_id'):
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_data
            })
        elif fam_data:
            # Partial data
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_data,
                'note': 'Partial information retrieved'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No FAM information found',
                'query': query
            }), 404
            
    except Exception as e:
        print(f"💥 API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Simple health check"""
    return jsonify({
        'status': 'ok',
        'service': 'FAM API',
        'timestamp': time.time()
    })

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'service': 'Telegram FAM API',
        'usage': 'GET /api?fam=upi@fam',
        'example': f'/api?fam=sugarsingh@fam',
        'endpoints': {
            '/api': 'Get FAM information',
            '/health': 'Health check'
        }
    })

@app.route('/test-telegram', methods=['GET'])
def test_telegram():
    """Test Telegram connection"""
    try:
        client = get_telegram_client()
        me = client.get_me()
        
        return jsonify({
            'success': True,
            'telegram': {
                'connected': client.is_connected(),
                'user': {
                    'id': me.id,
                    'first_name': me.first_name,
                    'username': me.username
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Close connection when app shuts down
import atexit
atexit.register(close_telegram_client)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting FAM API on port {port}")
    
    # Try to initialize Telegram client on startup
    try:
        get_telegram_client()
        print("✅ Pre-initialized Telegram client")
    except Exception as e:
        print(f"⚠️ Telegram initialization deferred: {e}")
    
    # Run with single worker, no threading
    app.run(host='0.0.0.0', port=port, debug=False, threaded=False)
