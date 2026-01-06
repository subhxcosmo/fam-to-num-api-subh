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
bot_initialized = False

# Create event loop for the main thread
main_loop = None

def init_telegram_bot():
    """Initialize Telegram bot once"""
    global telegram_bot, bot_initialized, main_loop
    
    with bot_lock:
        if not bot_initialized:
            try:
                # Create main event loop
                main_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(main_loop)
                
                # Initialize bot
                telegram_bot = TelegramFamBot()
                main_loop.run_until_complete(telegram_bot.connect())
                bot_initialized = True
                print("✅ Telegram bot initialized successfully")
            except Exception as e:
                print(f"❌ Error initializing Telegram bot: {e}")
                telegram_bot = None
                bot_initialized = False
                raise
    
    return telegram_bot

def parse_fam_info(text):
    """Parse FAM information from bot response text"""
    info = {}
    
    if not text:
        return info
    
    # Extract FAM ID
    fam_match = re.search(r'FAM ID\s*:\s*([^\n]+)', text, re.IGNORECASE)
    if fam_match:
        info['fam_id'] = fam_match.group(1).strip()
    else:
        # Try alternative pattern
        fam_match = re.search(r'FAM\s*:\s*([^\n]+)', text, re.IGNORECASE)
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

@app.before_request
def initialize_bot():
    """Initialize bot on first request (alternative to before_first_request)"""
    global bot_initialized
    if not bot_initialized:
        try:
            init_telegram_bot()
        except Exception as e:
            print(f"⚠️ Warning: Could not initialize Telegram bot: {e}")

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
        elif fam_info and (fam_info.get('name') or fam_info.get('phone')):
            # Return partial info if available
            return jsonify({
                'success': True,
                'query': query,
                'data': fam_info,
                'note': 'Partial information retrieved'
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
            'service': 'Telegram FAM API',
            'bot_initialized': bot_initialized
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

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to check Telegram connection"""
    try:
        if telegram_bot and telegram_bot.client.is_connected():
            return jsonify({
                'success': True,
                'message': 'Telegram bot is connected',
                'status': 'connected'
            })
        elif telegram_bot:
            return jsonify({
                'success': False,
                'message': 'Telegram bot initialized but not connected',
                'status': 'initialized'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Telegram bot not initialized',
                'status': 'not_initialized'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'status': 'error'
        })

if __name__ == '__main__':
    # Run Flask app
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Flask app on port {port}")
    
    # Try to initialize bot on startup (non-blocking)
    try:
        import threading
        def init_bot_async():
            try:
                init_telegram_bot()
            except Exception as e:
                print(f"⚠️ Bot initialization failed: {e}")
        
        thread = threading.Thread(target=init_bot_async)
        thread.daemon = True
        thread.start()
    except Exception as e:
        print(f"⚠️ Could not start bot initialization thread: {e}")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
