import os
import re
import time
import json
import tempfile
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
    """Extract FAM information from text file content"""
    info = {}
    
    if not text:
        return info
    
    print(f"📖 Parsing text content (length: {len(text)}):")
    print("-" * 50)
    print(text[:500])
    print("-" * 50)
    
    # FAM ID - multiple patterns
    patterns = [
        r'FAM ID\s*[:=]\s*([^\n\r]+)',
        r'FAM\s*[:=]\s*([^\n\r]+)',
        r'ID\s*[:=]\s*([^\n\r]+)',
        r'FAM\s+ID\s*[:=]\s*([^\n\r]+)'
    ]
    
    for pattern in patterns:
        fam_match = re.search(pattern, text, re.IGNORECASE)
        if fam_match:
            info['fam_id'] = fam_match.group(1).strip()
            break
    
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
    
    # If we couldn't extract with patterns, try line by line
    if not info:
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if 'fam' in key and 'id' in key:
                    info['fam_id'] = value
                elif 'name' in key:
                    info['name'] = value
                elif 'phone' in key:
                    info['phone'] = value
                elif 'type' in key:
                    info['type'] = value
    
    print(f"✅ Extracted info: {info}")
    return info

def download_and_read_file(client, message):
    """Download and read the attached .txt file"""
    try:
        print(f"📥 Downloading file from message ID: {message.id}")
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
            temp_path = tmp.name
        
        # Download the file
        download_result = client.download_media(message, file=temp_path)
        print(f"📁 Downloaded to: {download_result or temp_path}")
        
        # Read the file content
        with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        print(f"📄 Read {len(content)} characters from file")
        return content
        
    except Exception as e:
        print(f"❌ Error downloading/reading file: {e}")
        return None

def get_fam_data_from_telegram(query):
    """Main function to get FAM data from Telegram - handles .txt file attachments"""
    client = None
    try:
        # Get client
        client = get_telegram_client()
        
        # Target chat ID
        chat_id = -1003674153946
        
        # Send command
        command = f"/fam {query}"
        print(f"📤 Sending to chat {chat_id}: {command}")
        
        # Send message and save its ID
        sent_message = client.send_message(chat_id, command)
        sent_message_id = sent_message.id
        print(f"📨 Sent message ID: {sent_message_id}")
        
        # Wait for bot to respond
        print("⏳ Waiting for bot responses (10 seconds)...")
        time.sleep(10)  # Increased wait time for bot to process and send file
        
        # Get messages after our command
        messages = client.get_messages(chat_id, min_id=sent_message_id, limit=10)
        print(f"📨 Found {len(messages)} messages after ours")
        
        # Look for bot messages with .txt attachments
        for message in messages:
            try:
                # Check if message is from a bot
                sender = client.get_entity(message.sender_id)
                if not (hasattr(sender, 'bot') and sender.bot):
                    continue
                
                print(f"🤖 Checking bot message ID: {message.id}")
                print(f"   📝 Text preview: {message.message[:100] if message.message else 'No text'}")
                print(f"   📎 Has media: {bool(message.media)}")
                
                # Check if this is a reply to our message
                is_reply = False
                if hasattr(message, 'reply_to') and message.reply_to:
                    is_reply = True
                    reply_to_id = message.reply_to.reply_to_msg_id
                    print(f"   ↪️ Is reply to ID: {reply_to_id} (our ID: {sent_message_id})")
                
                # Check if message has media (the .txt file)
                if message.media:
                    print("   📁 Found media attachment, attempting to download...")
                    
                    # Download and read the file
                    file_content = download_and_read_file(client, message)
                    
                    if file_content:
                        # Check if this looks like FAM data
                        if any(keyword in file_content.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                            print(f"   ✅ Found FAM data in file!")
                            return extract_fam_info(file_content)
                        else:
                            print(f"   ⚠️ File doesn't contain FAM data")
                            print(f"   📄 File content preview: {file_content[:200]}...")
                    else:
                        print("   ❌ Could not read file content")
                
                # Also check message text (just in case)
                if message.message and any(keyword in message.message.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                    print(f"   ✅ Found FAM data in message text!")
                    return extract_fam_info(message.message)
                    
            except Exception as e:
                print(f"⚠️ Error processing message {message.id}: {e}")
                continue
        
        # If we didn't find anything, try one more time with more messages
        print("🔄 Trying with more messages (up to 20)...")
        messages = client.get_messages(chat_id, limit=20)
        
        for message in messages:
            try:
                # Only check messages after ours
                if message.id <= sent_message_id:
                    continue
                
                sender = client.get_entity(message.sender_id)
                if not (hasattr(sender, 'bot') and sender.bot):
                    continue
                
                if message.media:
                    print(f"📁 Checking late bot message ID: {message.id} for file...")
                    file_content = download_and_read_file(client, message)
                    
                    if file_content and any(keyword in file_content.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                        print(f"✅ Found late file with FAM data!")
                        return extract_fam_info(file_content)
                        
            except Exception as e:
                print(f"⚠️ Error processing late message {message.id}: {e}")
                continue
        
        print("❌ No FAM data found in any bot messages")
        return None
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        # Don't disconnect - keep connection alive for next request
        pass

@app.route('/api', methods=['GET'])
def get_fam_info():
    """API endpoint - downloads .txt file from bot"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    print(f"\n" + "="*60)
    print(f"🔍 Processing request for: {query}")
    print("="*60)
    
    try:
        fam_data = get_fam_data_from_telegram(query)
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
            # Ensure fam_id is set (use query if not found)
            if not fam_data.get('fam_id'):
                fam_data['fam_id'] = query
            
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No FAM information found in bot response',
                'query': query,
                'note': 'Bot may have sent data in a format we cannot parse'
            }), 404
            
    except Exception as e:
        print(f"💥 API Error: {str(e)}")
        import traceback
        traceback.print_exc()
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
        'description': 'Gets FAM information from Telegram bot. The bot sends data in .txt file attachments.',
        'usage': 'GET /api?fam=upi@fam',
        'example': f'/api?fam=sugarsingh@fam',
        'example_data': {
            'fam_id': 'sugarsingh@fam',
            'name': 'Siddhartha S',
            'phone': '7993764802',
            'type': 'contact'
        },
        'endpoints': {
            '/api': 'Get FAM information from .txt file',
            '/health': 'Health check',
            '/test': 'Test Telegram connection',
            '/debug': 'Debug bot responses'
        }
    })

@app.route('/test', methods=['GET'])
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

@app.route('/debug/<query>', methods=['GET'])
def debug_query(query):
    """Debug endpoint to see raw bot responses and files"""
    try:
        client = get_telegram_client()
        chat_id = -1003674153946
        
        # Send command
        command = f"/fam {query}"
        sent_message = client.send_message(chat_id, command)
        
        # Wait for responses
        time.sleep(8)
        
        # Get messages after our command
        messages = client.get_messages(chat_id, limit=15)
        
        debug_info = {
            'query': query,
            'our_message_id': sent_message.id,
            'bot_responses': []
        }
        
        for msg in messages:
            if msg.id > sent_message.id:
                try:
                    sender = client.get_entity(msg.sender_id)
                    is_bot = hasattr(sender, 'bot') and sender.bot
                    
                    response_data = {
                        'id': msg.id,
                        'date': str(msg.date),
                        'is_bot': is_bot,
                        'text': msg.message or '',
                        'has_media': bool(msg.media),
                        'media_type': str(type(msg.media)) if msg.media else None
                    }
                    
                    # Try to download and read file if present
                    if msg.media and is_bot:
                        try:
                            with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
                                temp_path = tmp.name
                            
                            download_path = client.download_media(msg, file=temp_path)
                            with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                                file_content = f.read()
                            
                            response_data['file_content'] = file_content[:500] + '...' if len(file_content) > 500 else file_content
                            response_data['file_size'] = len(file_content)
                            
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                                
                        except Exception as file_error:
                            response_data['file_error'] = str(file_error)
                    
                    debug_info['bot_responses'].append(response_data)
                    
                except Exception as e:
                    debug_info['bot_responses'].append({
                        'id': msg.id,
                        'error': str(e)
                    })
        
        # Sort by ID (newest first)
        debug_info['bot_responses'].sort(key=lambda x: x['id'], reverse=True)
        
        return jsonify(debug_info)
        
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
    print(f"📱 Target group: -1003674153946")
    print(f"📄 Bot sends data in .txt file attachments")
    
    # Try to initialize Telegram client on startup
    try:
        get_telegram_client()
        print("✅ Pre-initialized Telegram client")
    except Exception as e:
        print(f"⚠️ Telegram initialization deferred: {e}")
    
    # Run with single worker, no threading
    app.run(host='0.0.0.0', port=port, debug=False, threaded=False)
