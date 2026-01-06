"""
Simplified version that might work better on Render
"""
import os
import re
import json
from flask import Flask, request, jsonify
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Telegram settings
API_ID = int(os.getenv('TELEGRAM_API_ID', 0))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
SESSION_STRING = os.getenv('TELEGRAM_SESSION_STRING', '')
CHAT_ID = -1003674153946

def parse_fam_response(text):
    """Parse response from bot"""
    if not text:
        return {}
    
    info = {}
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

def get_fam_info_sync(query):
    """Synchronous function to get FAM info"""
    client = None
    try:
        # Create client
        client = TelegramClient(
            StringSession(SESSION_STRING),
            API_ID,
            API_HASH
        )
        
        # Connect
        client.start()
        print(f"✅ Connected as {client.get_me().first_name}")
        
        # Send command
        command = f"/fam {query}"
        client.send_message(CHAT_ID, command)
        print(f"📤 Sent: {command}")
        
        # Wait for response (simplified - check last few messages)
        response = None
        for message in client.iter_messages(CHAT_ID, limit=10):
            if message.sender and message.sender.bot:
                if message.message:
                    response = message.message
                    break
                elif message.media:
                    # Try to download file
                    try:
                        path = client.download_media(message, file='temp_')
                        with open(path, 'r', encoding='utf-8') as f:
                            response = f.read()
                        os.remove(path)
                        break
                    except:
                        continue
        
        if response:
            return parse_fam_response(response)
        return {}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}
    finally:
        if client and client.is_connected():
            client.disconnect()

@app.route('/api', methods=['GET'])
def api_endpoint():
    """Main API endpoint"""
    query = request.args.get('fam', '')
    
    if not query:
        return jsonify({
            'error': 'Missing fam parameter',
            'example': '/api?fam=upi@fam'
        }), 400
    
    try:
        info = get_fam_info_sync(query)
        
        if info:
            return jsonify({
                'success': True,
                'query': query,
                'data': info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No information found',
                'query': query
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/')
def home():
    return jsonify({
        'service': 'FAM Info API',
        'usage': '/api?fam=username@fam'
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
