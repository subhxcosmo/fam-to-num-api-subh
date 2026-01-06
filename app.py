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

def extract_fam_info(text, query=""):
    """Extract FAM information from text file content"""
    info = {}
    
    if not text:
        return info
    
    # Check if this response is for our query
    if query:
        # Look for "Verified Data for: query" pattern
        verified_pattern = rf'Verified Data for:\s*{re.escape(query)}'
        if not re.search(verified_pattern, text, re.IGNORECASE):
            # Also check for just the query in the text
            if query.lower() not in text.lower():
                print(f"⚠️ Text doesn't seem to be for query: {query}")
                # Still try to parse, might be in file
    
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
    
    # If no fam_id found but we have query, use query
    if not info.get('fam_id') and query:
        info['fam_id'] = query
    
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

def download_and_read_file(client, message):
    """Download and read the attached .txt file"""
    try:
        print(f"📥 Downloading file from message ID: {message.id}")
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
            temp_path = tmp.name
        
        # Download the file
        download_result = client.download_media(message, file=temp_path)
        
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

def wait_for_bot_response(client, sent_message_id, query, max_wait=30):
    """
    Wait for bot response that matches our query
    Returns (success, data) tuple
    """
    start_time = time.time()
    last_checked_id = sent_message_id
    
    print(f"⏳ Waiting for bot response (max {max_wait}s)...")
    
    while time.time() - start_time < max_wait:
        try:
            # Get new messages since last check
            messages = client.get_messages(
                -1003674153946, 
                min_id=last_checked_id,
                limit=10
            )
            
            if messages:
                last_checked_id = max(last_checked_id, max(m.id for m in messages) if messages else last_checked_id)
            
            for message in messages:
                try:
                    # Check if message is from a bot
                    sender = client.get_entity(message.sender_id)
                    if not (hasattr(sender, 'bot') and sender.bot):
                        continue
                    
                    print(f"🤖 Found bot message ID: {message.id}")
                    print(f"   📝 Text: {message.message[:100] if message.message else 'No text'}")
                    print(f"   📎 Has media: {bool(message.media)}")
                    
                    # Check if this is for our query
                    is_for_our_query = False
                    message_content = ""
                    
                    # Check message text first
                    if message.message and query.lower() in message.message.lower():
                        print(f"   ✅ Message text contains our query: {query}")
                        is_for_our_query = True
                        message_content = message.message
                    
                    # Check file content if available
                    if message.media and not is_for_our_query:
                        print("   📁 Checking file content...")
                        file_content = download_and_read_file(client, message)
                        
                        if file_content:
                            # Check if file is for our query
                            if query.lower() in file_content.lower():
                                print(f"   ✅ File content contains our query: {query}")
                                is_for_our_query = True
                                message_content = file_content
                            else:
                                print(f"   ⚠️ File is not for our query")
                    
                    # If we found our data, parse and return it
                    if is_for_our_query and message_content:
                        print(f"   🎯 Found matching response for query: {query}")
                        fam_data = extract_fam_info(message_content, query)
                        
                        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
                            print(f"   ✅ Successfully parsed FAM data")
                            return True, fam_data
                        else:
                            print(f"   ⚠️ Could not parse FAM data from response")
                    
                except Exception as e:
                    print(f"⚠️ Error processing message {message.id}: {e}")
                    continue
            
            # If no messages yet, wait a bit
            if not messages:
                elapsed = time.time() - start_time
                print(f"⏰ No new messages yet... ({elapsed:.1f}s elapsed)")
                time.sleep(1)  # Check more frequently
            
        except Exception as e:
            print(f"⚠️ Error getting messages: {e}")
            time.sleep(2)
    
    print(f"⏰ Timeout after {max_wait} seconds")
    return False, None

def get_fam_data_from_telegram_fast(query):
    """
    Fast version: Send command and wait for matching response
    """
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
        
        # Wait for bot response that matches our query
        success, fam_data = wait_for_bot_response(client, sent_message_id, query, max_wait=25)
        
        if success:
            return fam_data
        else:
            print(f"❌ No matching response found for query: {query}")
            return None
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        # Don't disconnect - keep connection alive
        pass

# Cache to prevent duplicate queries
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
                # Remove expired cache
                del response_cache[query]
    return None

def set_cached_response(query, data):
    """Cache the response"""
    with cache_lock:
        response_cache[query] = (time.time(), data)
    print(f"💾 Cached response for: {query}")

@app.route('/api', methods=['GET'])
def get_fam_info():
    """API endpoint - fast response with query matching"""
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
        fam_data = get_fam_data_from_telegram_fast(query)
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
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
                'error': 'No FAM information found for this query',
                'query': query,
                'note': 'Bot may be responding with data for a different query'
            }), 404
            
    except Exception as e:
        print(f"💥 API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/api/stream', methods=['GET'])
def get_fam_info_stream():
    """
    Streaming API endpoint - returns immediate updates
    Uses Server-Sent Events (SSE)
    """
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter'
        }), 400
    
    def generate():
        """Generate SSE events"""
        import time
        import json
        
        # Initial response
        yield f"data: {json.dumps({'status': 'started', 'query': query, 'timestamp': time.time()})}\n\n"
        
        # Check cache first
        cached_data = get_cached_response(query)
        if cached_data:
            yield f"data: {json.dumps({'status': 'cached', 'query': query, 'data': cached_data, 'timestamp': time.time()})}\n\n"
            return
        
        try:
            client = get_telegram_client()
            chat_id = -1003674153946
            
            # Send command
            command = f"/fam {query}"
            sent_message = client.send_message(chat_id, command)
            sent_message_id = sent_message.id
            
            yield f"data: {json.dumps({'status': 'sent', 'message_id': sent_message_id, 'timestamp': time.time()})}\n\n"
            
            # Wait for response
            start_time = time.time()
            max_wait = 30
            last_checked_id = sent_message_id
            
            while time.time() - start_time < max_wait:
                # Check for new messages
                messages = client.get_messages(chat_id, min_id=last_checked_id, limit=5)
                
                if messages:
                    last_checked_id = max(last_checked_id, max(m.id for m in messages))
                    
                    for message in messages:
                        try:
                            sender = client.get_entity(message.sender_id)
                            if hasattr(sender, 'bot') and sender.bot:
                                # Check if this is for our query
                                if message.message and query.lower() in message.message.lower():
                                    yield f"data: {json.dumps({'status': 'bot_response', 'message': message.message[:100], 'timestamp': time.time()})}\n\n"
                                    
                                    # Parse and return data
                                    fam_data = extract_fam_info(message.message, query)
                                    if fam_data:
                                        set_cached_response(query, fam_data)
                                        yield f"data: {json.dumps({'status': 'success', 'data': fam_data, 'timestamp': time.time()})}\n\n"
                                        return
                        
                        except:
                            continue
                
                # Send heartbeat
                yield f"data: {json.dumps({'status': 'waiting', 'elapsed': time.time() - start_time, 'timestamp': time.time()})}\n\n"
                time.sleep(1)
            
            # Timeout
            yield f"data: {json.dumps({'status': 'timeout', 'query': query, 'timestamp': time.time()})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'error': str(e), 'timestamp': time.time()})}\n\n"
    
    return app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'  # Disable buffering for nginx
        }
    )

@app.route('/health', methods=['GET'])
def health():
    """Simple health check"""
    return jsonify({
        'status': 'ok',
        'service': 'FAM API',
        'timestamp': time.time(),
        'cache_size': len(response_cache)
    })

@app.route('/cache/clear', methods=['GET'])
def clear_cache():
    """Clear response cache"""
    with cache_lock:
        count = len(response_cache)
        response_cache.clear()
    
    return jsonify({
        'success': True,
        'message': f'Cache cleared ({count} entries removed)',
        'timestamp': time.time()
    })

@app.route('/cache/stats', methods=['GET'])
def cache_stats():
    """Get cache statistics"""
    with cache_lock:
        stats = {
            'size': len(response_cache),
            'queries': list(response_cache.keys()),
            'entries': []
        }
        
        for query, (cached_time, data) in response_cache.items():
            stats['entries'].append({
                'query': query,
                'cached_time': cached_time,
                'age_seconds': time.time() - cached_time,
                'data_keys': list(data.keys()) if data else []
            })
    
    return jsonify(stats)

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'service': 'Telegram FAM API',
        'description': 'Fast API that matches bot responses with queries',
        'features': [
            'Query matching: Ensures bot response is for the correct query',
            'Fast response: Returns data as soon as bot sends it',
            'Caching: Prevents duplicate requests',
            'Streaming: Real-time updates via /api/stream endpoint'
        ],
        'usage': 'GET /api?fam=upi@fam',
        'example': f'/api?fam=sugarsingh@fam',
        'streaming_example': f'/api/stream?fam=sugarsingh@fam',
        'endpoints': {
            '/api': 'Get FAM information (fast with cache)',
            '/api/stream': 'Streaming API for real-time updates',
            '/health': 'Health check',
            '/cache/clear': 'Clear response cache',
            '/cache/stats': 'Cache statistics'
        }
    })

# Close connection when app shuts down
import atexit
atexit.register(close_telegram_client)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting FAST FAM API on port {port}")
    print(f"📱 Target group: -1003674153946")
    print(f"🎯 Features: Query matching, caching, fast responses")
    
    # Try to initialize Telegram client on startup
    try:
        get_telegram_client()
        print("✅ Pre-initialized Telegram client")
    except Exception as e:
        print(f"⚠️ Telegram initialization deferred: {e}")
    
    # Run with single worker, no threading
    app.run(host='0.0.0.0', port=port, debug=False, threaded=False)
