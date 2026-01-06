import os
import json
import re
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
from telegram_client import TelegramFamBot
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Global Telegram bot instance
telegram_bot = None
bot_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=1)

# Create event loop for the main thread
main_loop = asyncio.new_event_loop()

def init_telegram_bot():
    """Initialize Telegram bot once"""
    global telegram_bot
    with bot_lock:
        if telegram_bot is None:
            telegram_bot = TelegramFamBot()
            # Run async initialization in the main loop
            asyncio.set_event_loop(main_loop)
            main_loop.run_until_complete(telegram_bot.connect())
    return telegram_bot

def parse_fam_info(text):
    """Parse FAM information from bot response text"""
    info = {}
    
    # Extract FAM ID
    fam_match = re.search(r'FAM ID\s*:\s*([^\n]+)', text, re.IGNORECASE)
    if fam_match:
        info['fam_id'] = fam_match.group(1).strip()
    
    # Extract NAME
    name_match = re.search(r'NAME\s*:\s*([^\n]+)', text, re.IGNORECASE)
    if name_match:
        info['name'] = name_match.group(1).strip()
    
    # Extract PHONE
    phone_match = re.search(r'PHONE\s*:\s*([^\n]+)', text, re.IGNORECASE)
    if phone_match:
        info['phone'] = phone_match.group(1).strip()
    
    # Extract TYPE
    type_match = re.search(r'TYPE\s*:\s*([^\n]+)', text, re.IGNORECASE)
    if type_match:
        info['type'] = type_match.group(1).strip().lower()
    
    return info

async def async_get_fam_info(query):
    """Async function to get FAM information"""
    global telegram_bot
    
    if telegram_bot is None:
        telegram_bot = init_telegram_bot()
    
    # Ensure bot is connected
    if not telegram_bot.client.is_connected():
        await telegram_bot.connect()
    
    # Send command and wait for response
    response_text = await telegram_bot.send_fam_command(query)
    
    if response_text:
        return parse_fam_info(response_text)
    return None

def sync_get_fam_info(query):
    """Synchronous wrapper for async function"""
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(async_get_fam_info(query))
        return result
    finally:
        loop.close()

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
        # Use thread pool to run async code
        fam_info = executor.submit(sync_get_fam_info, query).result(timeout=60)
        
        if fam_info and fam_info.get('fam_id'):
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No valid response from bot',
                'query': query
            }), 404
            
    except asyncio.TimeoutError:
        return jsonify({
            'success': False,
            'error': 'Request timeout - bot took too long to respond',
            'query': query
        }), 504
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    try:
        # Quick check if bot is initialized
        if telegram_bot and telegram_bot.client.is_connected():
            status = 'connected'
        elif telegram_bot:
            status = 'initialized'
        else:
            status = 'not_initialized'
        
        return jsonify({
            'status': 'healthy',
            'telegram': status,
            'service': 'Telegram FAM API'
        })
    except:
        return jsonify({
            'status': 'healthy',
            'telegram': 'unknown',
            'service': 'Telegram FAM API'
        })

@app.route('/', methods=['GET'])
def index():
    """Homepage with API instructions"""
    return jsonify({
        'message': 'Telegram FAM API',
        'usage': 'GET /api?fam=upi@fam',
        'example': '/api?fam=sugarsingh@fam',
        'example_url': 'https://your-app.onrender.com/api?fam=sugarsingh@fam',
        'endpoints': {
            '/api': 'Get FAM information',
            '/health': 'Health check',
            '/': 'This page'
        }
    })

@app.before_first_request
def initialize():
    """Initialize Telegram bot on first request"""
    try:
        init_telegram_bot()
        print("✅ Telegram bot initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize Telegram bot: {e}")

if __name__ == '__main__':
    # Initialize on startup
    try:
        init_telegram_bot()
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize Telegram bot on startup: {e}")
    
    # Run Flask app
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
