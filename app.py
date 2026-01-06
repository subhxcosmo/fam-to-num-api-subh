import os
import json
import re
import time
import asyncio
from threading import Lock
from flask import Flask, request, jsonify
from telegram_client import TelegramFamBot
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize Telegram bot
telegram_bot = TelegramFamBot()

# Lock for thread-safe operations
bot_lock = Lock()

def parse_fam_info(text):
    """Parse FAM information from bot response text"""
    info = {}
    
    # Extract FAM ID
    fam_match = re.search(r'FAM ID\s*:\s*([^\n]+)', text)
    if fam_match:
        info['fam_id'] = fam_match.group(1).strip()
    
    # Extract NAME
    name_match = re.search(r'NAME\s*:\s*([^\n]+)', text)
    if name_match:
        info['name'] = name_match.group(1).strip()
    
    # Extract PHONE
    phone_match = re.search(r'PHONE\s*:\s*([^\n]+)', text)
    if phone_match:
        info['phone'] = phone_match.group(1).strip()
    
    # Extract TYPE
    type_match = re.search(r'TYPE\s*:\s*([^\n]+)', text)
    if type_match:
        info['type'] = type_match.group(1).strip().lower()
    
    return info

@app.route('/api', methods=['GET'])
def get_fam_info():
    """API endpoint to get FAM information"""
    # Get query parameter
    query = request.args.get('fam', '')
    
    if not query:
        return jsonify({
            'error': 'Missing fam parameter. Use /api?fam=upi@fam',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    try:
        with bot_lock:
            # Get the event loop for async operations
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Ensure bot is connected
            if not telegram_bot.client.is_connected():
                loop.run_until_complete(telegram_bot.connect())
            
            # Send command and wait for response
            response_text = loop.run_until_complete(
                telegram_bot.send_fam_command(query)
            )
            
            # Parse the response
            if response_text:
                fam_info = parse_fam_info(response_text)
                if fam_info:
                    return jsonify({
                        'success': True,
                        'query': query,
                        'data': fam_info
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Could not parse FAM information',
                        'raw_response': response_text[:500]  # Limit response size
                    }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': 'No response from bot or timeout'
                }), 504
                
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'Telegram FAM API'
    })

@app.route('/', methods=['GET'])
def index():
    """Homepage with API instructions"""
    return jsonify({
        'message': 'Telegram FAM API',
        'usage': 'GET /api?fam=upi@fam',
        'example': '/api?fam=sugarsingh@fam',
        'endpoints': {
            '/api': 'Get FAM information',
            '/health': 'Health check',
            '/': 'This page'
        }
    })

if __name__ == '__main__':
    # Initialize Telegram bot connection
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_bot.connect())
        print("✅ Telegram bot connected successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not connect to Telegram: {e}")
    
    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
