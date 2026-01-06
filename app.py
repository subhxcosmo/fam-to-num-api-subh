import os
import re
import time
import json
import tempfile
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Telegram client will be initialized only when needed
telegram_client = None
client_lock = threading.Lock()

def get_telegram_client():
    """Get Telegram client - initialize only when needed"""
    global telegram_client
    
    with client_lock:
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
    with client_lock:
        if telegram_client and telegram_client.is_connected():
            telegram_client.disconnect()
            telegram_client = None
            print("✅ Telegram client disconnected")

def extract_fam_info_from_text(text):
    """Extract FAM information from text content"""
    info = {}
    
    if not text:
        return info
    
    print(f"🔍 Parsing text (length: {len(text)} chars)...")
    
    # Try multiple patterns for each field
    patterns = {
        'fam_id': [
            r'FAM ID\s*[:=]\s*([^\n\r]+)',
            r'FAM\s*[:=]\s*([^\n\r]+)',
            r'ID\s*[:=]\s*([^\n\r]+)',
            r'FAM\s+ID\s*[:=]\s*([^\n\r]+)'
        ],
        'name': [
            r'NAME\s*[:=]\s*([^\n\r]+)',
            r'Name\s*[:=]\s*([^\n\r]+)'
        ],
        'phone': [
            r'PHONE\s*[:=]\s*([^\n\r]+)',
            r'Phone\s*[:=]\s*([^\n\r]+)',
            r'Mobile\s*[:=]\s*([^\n\r]+)',
            r'Contact\s*[:=]\s*([^\n\r]+)'
        ],
        'type': [
            r'TYPE\s*[:=]\s*([^\n\r]+)',
            r'Type\s*[:=]\s*([^\n\r]+)',
            r'Category\s*[:=]\s*([^\n\r]+)'
        ]
    }
    
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info[field] = match.group(1).strip()
                print(f"   ✅ Found {field}: {info[field]}")
                break
    
    # If no patterns matched, try line-by-line parsing
    if not info:
        print("   ⚠️ No pattern matches, trying line-by-line...")
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
    
    return info

def download_txt_file(client, message):
    """Download and read .txt file from bot message"""
    try:
        if not message.media:
            print("   ⚠️ No media attached to message")
            return None
        
        print(f"   📥 Downloading .txt file from message {message.id}...")
        
        # Create a temporary file with .txt extension
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
            temp_path = tmp.name
        
        # Download the media (should be a .txt file)
        result_path = client.download_media(message, file=temp_path)
        final_path = result_path if result_path else temp_path
        
        print(f"   💾 Downloaded to: {final_path}")
        
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        file_content = None
        
        for encoding in encodings:
            try:
                with open(final_path, 'r', encoding=encoding) as f:
                    file_content = f.read()
                print(f"   ✅ Successfully read with {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"   ⚠️ Error reading with {encoding}: {e}")
                continue
        
        # If all encodings fail, try with errors ignore
        if not file_content:
            try:
                with open(final_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
                print(f"   ⚠️ Read with errors ignored")
            except Exception as e:
                print(f"   ❌ Could not read file: {e}")
                file_content = None
        
        # Clean up temp file
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
        except:
            pass
        
        if file_content:
            print(f"   📄 File content length: {len(file_content)} chars")
            print(f"   📄 First 500 chars: {file_content[:500]}...")
            return file_content
        else:
            print("   ❌ No content read from file")
            return None
            
    except Exception as e:
        print(f"   ❌ Error downloading file: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_message_for_query_data(client, message, query):
    """Check if a message contains data for our query"""
    try:
        # Get sender info
        sender = client.get_entity(message.sender_id)
        if not (hasattr(sender, 'bot') and sender.bot):
            return None
        
        print(f"\n🤖 Checking bot message ID: {message.id}")
        
        # Check message text for query match
        message_text = message.message or ""
        has_query_in_text = query.lower() in message_text.lower()
        
        # Check if message has media (.txt file)
        has_media = bool(message.media)
        
        print(f"   📝 Text preview: {message_text[:100]}")
        print(f"   🔍 Query in text: {has_query_in_text}")
        print(f"   📎 Has media: {has_media}")
        
        # Priority 1: Check attached .txt file
        if has_media:
            print("   📁 Checking attached file...")
            file_content = download_txt_file(client, message)
            
            if file_content:
                # Check if file contains our query
                if query.lower() in file_content.lower():
                    print(f"   ✅ File contains our query: {query}")
                    return extract_fam_info_from_text(file_content)
                else:
                    print(f"   ⚠️ File doesn't contain query: {query}")
                    # Still check if it has FAM data
                    if any(keyword in file_content.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                        print(f"   ✅ File has FAM data (might be for different query)")
                        return extract_fam_info_from_text(file_content)
        
        # Priority 2: Check message text
        if has_query_in_text and message_text.strip():
            print(f"   ✅ Message text contains query: {query}")
            # Check if text has actual data (not just "Verified Data for:")
            if any(keyword in message_text.upper() for keyword in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']):
                return extract_fam_info_from_text(message_text)
            else:
                print(f"   ⚠️ Message text has query but no FAM data")
        
        return None
        
    except Exception as e:
        print(f"   ❌ Error checking message: {e}")
        import traceback
        traceback.print_exc()
        return None

def wait_for_bot_response_with_file(client, sent_message_id, query, max_wait=30):
    """
    Wait for bot response with .txt file that matches our query
    """
    start_time = time.time()
    last_checked_id = sent_message_id
    
    print(f"⏳ Waiting for bot response with .txt file (max {max_wait}s)...")
    
    while time.time() - start_time < max_wait:
        try:
            # Get new messages since last check
            messages = client.get_messages(
                -1003674153946, 
                min_id=last_checked_id,
                limit=10
            )
            
            if messages:
                # Update last checked ID
                new_max_id = max(m.id for m in messages)
                if new_max_id > last_checked_id:
                    last_checked_id = new_max_id
                    print(f"📨 Got {len(messages)} new messages, last ID: {last_checked_id}")
            
            # Check each message
            for message in messages:
                fam_data = check_message_for_query_data(client, message, query)
                if fam_data:
                    return True, fam_data
            
            # If no valid messages yet, wait
            elapsed = time.time() - start_time
            if elapsed > 5 and elapsed < max_wait - 5:
                print(f"⏰ Still waiting... ({elapsed:.1f}s elapsed)")
            
            # Check more frequently at first, then slower
            if elapsed < 10:
                time.sleep(1)  # Check every second for first 10 seconds
            else:
                time.sleep(2)  # Then check every 2 seconds
            
        except Exception as e:
            print(f"⚠️ Error in wait loop: {e}")
            time.sleep(2)
    
    print(f"⏰ Timeout after {max_wait} seconds")
    return False, None

def get_fam_data_with_file(query):
    """
    Get FAM data by downloading bot's .txt file
    """
    client = None
    try:
        # Get client
        client = get_telegram_client()
        
        # Target chat ID
        chat_id = -1003674153946
        
        # Send command
        command = f"/fam {query}"
        print(f"\n📤 Sending to chat {chat_id}: {command}")
        
        # Send message
        sent_message = client.send_message(chat_id, command)
        sent_message_id = sent_message.id
        print(f"📨 Sent message ID: {sent_message_id}")
        
        # Wait for bot response with .txt file
        success, fam_data = wait_for_bot_response_with_file(
            client, sent_message_id, query, max_wait=35
        )
        
        if success:
            print(f"✅ Successfully extracted data for: {query}")
            return fam_data
        else:
            print(f"❌ No .txt file data found for query: {query}")
            
            # Last resort: check recent messages for any data
            print("🔄 Checking recent messages as last resort...")
            messages = client.get_messages(chat_id, limit=20)
            
            for message in messages:
                if message.id > sent_message_id:
                    fam_data = check_message_for_query_data(client, message, query)
                    if fam_data:
                        print(f"✅ Found data in recent messages")
                        return fam_data
            
            return None
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        # Keep connection alive
        pass

# Cache system
response_cache = {}
cache_lock = threading.Lock()
CACHE_TIMEOUT = 300  # 5 minutes

def get_cached_response(query):
    """Get cached response if available and not expired"""
    with cache_lock:
        if query in response_cache:
            cached_time, cached_data = response_cache[query]
            if time.time() - cached_time < CACHE_TIMEOUT:
                print(f"💾 Using cached response for: {query}")
                return cached_data
            else:
                del response_cache[query]
    return None

def set_cached_response(query, data):
    """Cache the response"""
    with cache_lock:
        response_cache[query] = (time.time(), data)
    print(f"💾 Cached response for: {query}")

@app.route('/api', methods=['GET'])
def get_fam_info():
    """Main API endpoint - downloads .txt file from bot"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    print(f"\n" + "="*70)
    print(f"🎯 API Request for: {query}")
    print("="*70)
    
    # Check cache first
    cached_data = get_cached_response(query)
    if cached_data:
        return jsonify({
            'success': True,
            'query': query,
            'data': cached_data,
            'cached': True,
            'timestamp': time.time()
        })
    
    try:
        fam_data = get_fam_data_with_file(query)
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
            # Ensure fam_id is set
            if not fam_data.get('fam_id'):
                fam_data['fam_id'] = query
            
            # Cache the response
            set_cached_response(query, fam_data)
            
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_data,
                'cached': False,
                'timestamp': time.time()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No FAM information found in bot\'s .txt file',
                'query': query,
                'note': 'The bot may not have responded with a .txt file'
            }), 404
            
    except Exception as e:
        print(f"💥 API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/api/debug', methods=['GET'])
def debug_api():
    """Debug endpoint to see what bot sends"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({'error': 'Missing fam parameter'}), 400
    
    try:
        client = get_telegram_client()
        chat_id = -1003674153946
        
        # Send command
        command = f"/fam {query}"
        sent_message = client.send_message(chat_id, command)
        
        # Wait for response
        time.sleep(12)
        
        # Get messages
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
                    
                    resp = {
                        'id': msg.id,
                        'date': str(msg.date),
                        'is_bot': is_bot,
                        'text': msg.message or '',
                        'has_media': bool(msg.media),
                        'media_info': str(type(msg.media)) if msg.media else None
                    }
                    
                    # Try to download file if present
                    if msg.media and is_bot:
                        try:
                            with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
                                temp_path = tmp.name
                            
                            client.download_media(msg, file=temp_path)
                            
                            # Try to read
                            try:
                                with open(temp_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                resp['file_content_preview'] = content[:1000]
                                resp['file_length'] = len(content)
                                
                                # Check for query in file
                                resp['query_in_file'] = query.lower() in content.lower()
                                
                                # Check for FAM data patterns
                                resp['has_fam_patterns'] = any(
                                    pattern in content.upper() 
                                    for pattern in ['FAM ID', 'NAME:', 'PHONE:', 'TYPE:']
                                )
                                
                            except:
                                resp['file_error'] = 'Could not read file'
                            
                            # Clean up
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                                
                        except Exception as file_e:
                            resp['file_error'] = str(file_e)
                    
                    debug_info['bot_responses'].append(resp)
                    
                except Exception as e:
                    debug_info['bot_responses'].append({
                        'id': msg.id,
                        'error': str(e)
                    })
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'service': 'FAM API (.txt file version)',
        'timestamp': time.time(),
        'cache_size': len(response_cache)
    })

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'service': 'Telegram FAM API',
        'description': 'Downloads and reads .txt files from bot responses',
        'important': 'The bot sends data in attached .txt files, not in message text',
        'usage': 'GET /api?fam=upi@fam',
        'debug': 'GET /api/debug?fam=upi@fam (see what bot actually sends)',
        'example_response': {
            'success': True,
            'query': 'sugarsingh@fam',
            'data': {
                'fam_id': 'sugarsingh@fam',
                'name': 'Siddhartha S',
                'phone': '7993764802',
                'type': 'contact'
            }
        }
    })

# Close connection on shutdown
import atexit
atexit.register(close_telegram_client)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting TXT FILE FAM API on port {port}")
    print(f"📱 Target group: -1003674153946")
    print(f"📄 Bot sends: Message + .txt file attachment")
    print(f"🎯 Will download and parse .txt files")
    
    try:
        get_telegram_client()
        print("✅ Pre-initialized Telegram client")
    except Exception as e:
        print(f"⚠️ Telegram initialization deferred: {e}")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=False)
