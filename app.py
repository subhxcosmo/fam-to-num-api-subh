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
    
    # Clean up text
    text = text.strip()
    
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
    
    return info

def get_fam_data_from_telegram(query):
    """Main function to get FAM data from Telegram - handles bot's reply chain"""
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
        
        # Wait for bot to respond (initial "fetching" message)
        print("⏳ Waiting for bot responses...")
        
        # Track bot messages
        bot_messages = []
        start_time = time.time()
        timeout = 30  # Maximum wait time in seconds
        
        while time.time() - start_time < timeout:
            # Get recent messages
            messages = client.get_messages(chat_id, limit=20)
            
            for message in messages:
                # Skip our own message
                if message.id == sent_message_id:
                    continue
                
                # Check if message is from a bot and after our command
                if message.id > sent_message_id:
                    sender = client.get_entity(message.sender_id)
                    if hasattr(sender, 'bot') and sender.bot:
                        # Check if this is a reply to our message
                        if (hasattr(message, 'reply_to') and 
                            message.reply_to and 
                            message.reply_to.reply_to_msg_id == sent_message_id):
                            
                            bot_messages.append({
                                'id': message.id,
                                'text': message.message or '',
                                'media': message.media,
                                'date': message.date,
                                'is_reply': True
                            })
                            print(f"💬 Bot replied to our message: ID {message.id}")
                        
                        # Also check if it's a direct response (not necessarily a reply)
                        elif 'fetching' in (message.message or '').lower():
                            print(f"⏱️ Bot is fetching: {message.message}")
                        elif any(keyword in (message.message or '').upper() for keyword in ['FAM', 'NAME', 'PHONE', 'TYPE']):
                            bot_messages.append({
                                'id': message.id,
                                'text': message.message or '',
                                'media': message.media,
                                'date': message.date,
                                'is_reply': False
                            })
                            print(f"📝 Bot sent response: ID {message.id}")
            
            # Check if we have the actual data response (not the "fetching" message)
            for msg in bot_messages:
                if msg['text'] and not 'fetching' in msg['text'].lower():
                    # This looks like the actual response
                    response_text = msg['text']
                    
                    # Check if there's media/document
                    if not response_text.strip() and msg['media']:
                        try:
                            print("📄 Downloading document from reply...")
                            file_path = client.download_media(msg, file='temp_fam_doc')
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                response_text = f.read()
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except Exception as e:
                            print(f"⚠️ Could not read document: {e}")
                    
                    if response_text.strip():
                        print(f"✅ Found actual response: {response_text[:200]}...")
                        return extract_fam_info(response_text)
            
            # Wait before checking again
            time.sleep(2)
            
            # If we have any bot messages but no actual data yet, check documents
            for msg in bot_messages:
                if msg['media']:
                    try:
                        print("📄 Trying to download media attachment...")
                        file_path = client.download_media(msg, file='temp_fam_file')
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        
                        if file_content.strip():
                            print(f"✅ Found data in document: {file_content[:200]}...")
                            return extract_fam_info(file_content)
                    except Exception as e:
                        print(f"⚠️ Could not process media: {e}")
        
        # If timeout, check for any document in the chat
        print("⏰ Timeout - checking for any documents...")
        messages = client.get_messages(chat_id, limit=30)
        for message in messages:
            if message.id > sent_message_id:
                sender = client.get_entity(message.sender_id)
                if hasattr(sender, 'bot') and sender.bot and message.media:
                    try:
                        print("📄 Downloading last document found...")
                        file_path = client.download_media(message, file='temp_last_doc')
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        
                        if file_content.strip():
                            print(f"✅ Found data in last document")
                            return extract_fam_info(file_content)
                    except Exception as e:
                        print(f"⚠️ Could not process last document: {e}")
        
        print("❌ No valid bot response found after timeout")
        return None
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        raise
    
    finally:
        # Don't disconnect - keep connection alive for next request
        pass

@app.route('/api', methods=['GET'])
def get_fam_info():
    """API endpoint - handles bot's reply chain"""
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
        'description': 'Gets FAM information from Telegram bot. The bot first sends "fetching..." then replies with actual data.',
        'usage': 'GET /api?fam=upi@fam',
        'example': f'/api?fam=sugarsingh@fam',
        'endpoints': {
            '/api': 'Get FAM information',
            '/health': 'Health check',
            '/test': 'Test Telegram connection'
        }
    })

@app.route('/test', methods=['GET'])
def test_telegram():
    """Test Telegram connection"""
    try:
        client = get_telegram_client()
        me = client.get_me()
        
        # Try to access the group
        chat_id = -1003674153946
        try:
            chat = client.get_entity(chat_id)
            chat_title = chat.title if hasattr(chat, 'title') else 'Unknown'
            chat_access = True
        except:
            chat_title = "Access denied"
            chat_access = False
        
        return jsonify({
            'success': True,
            'telegram': {
                'connected': client.is_connected(),
                'user': {
                    'id': me.id,
                    'first_name': me.first_name,
                    'username': me.username
                },
                'group': {
                    'id': chat_id,
                    'title': chat_title,
                    'accessible': chat_access
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
    """Debug endpoint to see raw bot responses"""
    try:
        client = get_telegram_client()
        chat_id = -1003674153946
        
        # Send command
        command = f"/fam {query}"
        sent_message = client.send_message(chat_id, command)
        
        # Wait and collect all messages
        time.sleep(8)
        
        # Get messages after our command
        messages = client.get_messages(chat_id, limit=30)
        
        bot_responses = []
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
                        'is_reply': hasattr(msg, 'reply_to') and bool(msg.reply_to)
                    }
                    
                    # If it's a reply, check what it's replying to
                    if response_data['is_reply']:
                        response_data['reply_to_id'] = msg.reply_to.reply_to_msg_id
                        response_data['is_reply_to_our_command'] = (msg.reply_to.reply_to_msg_id == sent_message.id)
                    
                    bot_responses.append(response_data)
                except:
                    continue
        
        # Sort by ID (newest first)
        bot_responses.sort(key=lambda x: x['id'], reverse=True)
        
        return jsonify({
            'query': query,
            'our_message_id': sent_message.id,
            'bot_responses': bot_responses,
            'count': len(bot_responses)
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
    print(f"📱 Target group: -1003674153946")
    print(f"🤖 Bot behavior: Sends 'fetching...' then replies with data")
    
    # Try to initialize Telegram client on startup
    try:
        get_telegram_client()
        print("✅ Pre-initialized Telegram client")
    except Exception as e:
        print(f"⚠️ Telegram initialization deferred: {e}")
    
    # Run with single worker, no threading
    app.run(host='0.0.0.0', port=port, debug=False, threaded=False)
