import os
import re
import time
import json
import csv
import tempfile
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

# ========== DATABASE CONFIGURATION ==========
# Using Supabase (free tier) for storage
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
SUPABASE_TABLE = 'fam_data'
USE_DATABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# Local storage files
JSON_DB_FILE = 'fam_database.json'
CSV_DB_FILE = 'fam_database.csv'
QUERY_COUNTER_FILE = 'query_counter.txt'

# Telegram client
telegram_client = None
client_lock = threading.Lock()

# Query counter for every 200th query
query_counter = 0
counter_lock = threading.Lock()

# ========== DATABASE FUNCTIONS ==========
def init_local_database():
    """Initialize local JSON and CSV databases if they don't exist"""
    if not os.path.exists(JSON_DB_FILE):
        with open(JSON_DB_FILE, 'w') as f:
            json.dump({}, f)
    
    if not os.path.exists(CSV_DB_FILE):
        with open(CSV_DB_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['fam_id', 'name', 'phone', 'type', 'breached_timestamp', 'created_at'])

def load_query_counter():
    """Load query counter from file"""
    global query_counter
    try:
        if os.path.exists(QUERY_COUNTER_FILE):
            with open(QUERY_COUNTER_FILE, 'r') as f:
                query_counter = int(f.read().strip())
    except:
        query_counter = 0
    return query_counter

def save_query_counter():
    """Save query counter to file"""
    global query_counter
    try:
        with open(QUERY_COUNTER_FILE, 'w') as f:
            f.write(str(query_counter))
    except:
        pass

def increment_query_counter():
    """Increment and save query counter"""
    global query_counter
    with counter_lock:
        query_counter += 1
        save_query_counter()
        return query_counter

def store_in_supabase(fam_data):
    """Store data in Supabase database"""
    if not USE_DATABASE:
        return False
    
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
        }
        
        # Prepare data for Supabase
        supabase_data = {
            'fam_id': fam_data.get('fam_id', ''),
            'name': fam_data.get('name', ''),
            'phone': fam_data.get('phone', ''),
            'type': fam_data.get('type', 'contact'),
            'breached_timestamp': fam_data.get('breached_timestamp', time.time()),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Insert into Supabase
        response = requests.post(
            f'{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}',
            headers=headers,
            json=supabase_data
        )
        
        if response.status_code in [200, 201]:
            print(f"✅ Stored in Supabase: {fam_data.get('fam_id')}")
            return True
        else:
            print(f"❌ Supabase error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Supabase connection error: {e}")
        return False

def store_in_local_database(fam_data):
    """Store data in local JSON and CSV databases"""
    try:
        fam_id = fam_data.get('fam_id', '')
        if not fam_id:
            return False
        
        # Prepare record
        record = {
            'fam_id': fam_id,
            'name': fam_data.get('name', ''),
            'phone': fam_data.get('phone', ''),
            'type': fam_data.get('type', 'contact'),
            'breached_timestamp': fam_data.get('breached_timestamp', time.time()),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Store in JSON database
        with open(JSON_DB_FILE, 'r+') as f:
            data = json.load(f)
            data[fam_id] = record
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
        
        # Store in CSV database
        with open(CSV_DB_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                record['fam_id'],
                record['name'],
                record['phone'],
                record['type'],
                record['breached_timestamp'],
                record['created_at']
            ])
        
        print(f"✅ Stored locally: {fam_id}")
        return True
        
    except Exception as e:
        print(f"❌ Local storage error: {e}")
        return False

def store_in_database(fam_data):
    """Store data in both local and cloud databases"""
    # Always store locally
    local_success = store_in_local_database(fam_data)
    
    # Store in Supabase if configured
    cloud_success = False
    if USE_DATABASE:
        cloud_success = store_in_supabase(fam_data)
    
    return local_success or cloud_success

def get_from_database(fam_id):
    """Retrieve data from database"""
    # First check local JSON database
    try:
        with open(JSON_DB_FILE, 'r') as f:
            data = json.load(f)
            if fam_id in data:
                print(f"📂 Found in database: {fam_id}")
                return data[fam_id]
    except:
        pass
    
    return None

def should_store_in_database():
    """Check if this is every 200th query"""
    global query_counter
    return query_counter % 200 == 0 and query_counter > 0

# ========== TELEGRAM FUNCTIONS ==========
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
    
    # FAM ID patterns
    fam_patterns = [
        r'FAM ID\s*[:=]\s*([^\n\r]+)',
        r'FAM\s*[:=]\s*([^\n\r]+)',
        r'ID\s*[:=]\s*([^\n\r]+)'
    ]
    
    for pattern in fam_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info['fam_id'] = match.group(1).strip()
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
    
    # Add breached timestamp
    info['breached_timestamp'] = time.time()
    
    return info

def download_txt_file(client, message):
    """Download and read .txt file from bot message"""
    try:
        if not message.media:
            return None
        
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
            temp_path = tmp.name
        
        # Download file
        client.download_media(message, file=temp_path)
        
        # Read file
        with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Clean up
        os.remove(temp_path)
        
        return content
        
    except Exception as e:
        print(f"❌ File download error: {e}")
        return None

def get_fam_data_from_telegram(query):
    """Get FAM data from Telegram bot"""
    client = None
    try:
        client = get_telegram_client()
        chat_id = -1003674153946
        
        # Send command
        print(f"📤 Sending: /fam {query}")
        sent_msg = client.send_message(chat_id, f"/fam {query}")
        
        # Wait for response
        time.sleep(12)
        
        # Get messages
        messages = client.get_messages(chat_id, limit=15)
        
        for msg in messages:
            if msg.id > sent_msg.id:
                try:
                    sender = client.get_entity(msg.sender_id)
                    if hasattr(sender, 'bot') and sender.bot:
                        # Check for file
                        if msg.media:
                            file_content = download_txt_file(client, msg)
                            if file_content and query.lower() in file_content.lower():
                                fam_data = extract_fam_info_from_text(file_content)
                                if fam_data.get('fam_id'):
                                    return fam_data
                        
                        # Check message text
                        if msg.message and query.lower() in msg.message.lower():
                            fam_data = extract_fam_info_from_text(msg.message)
                            if fam_data.get('fam_id'):
                                return fam_data
                                
                except Exception as e:
                    print(f"⚠️ Message processing error: {e}")
        
        return None
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        raise
    
    finally:
        # Keep connection alive
        pass

# ========== MAIN API FUNCTION ==========
def get_fam_info_with_storage(query):
    """
    Main function to get FAM info with database storage
    """
    # Increment query counter
    query_number = increment_query_counter()
    print(f"🔍 Query #{query_number} for: {query}")
    
    # First, check database
    db_data = get_from_database(query)
    if db_data:
        print(f"📊 Returning from database")
        return {
            'success': True,
            'data': db_data,
            'source': 'database',
            'query_number': query_number
        }
    
    # If not in database, get from Telegram
    print(f"📡 Fetching from Telegram...")
    fam_data = get_fam_data_from_telegram(query)
    
    if fam_data and fam_data.get('fam_id'):
        # Ensure fam_id is set
        if not fam_data.get('fam_id'):
            fam_data['fam_id'] = query
        
        # Store every 200th query
        if should_store_in_database():
            print(f"💾 Storing in database (query #{query_number} is 200th)")
            store_in_database(fam_data)
        
        return {
            'success': True,
            'data': fam_data,
            'source': 'telegram',
            'query_number': query_number,
            'stored_in_db': should_store_in_database()
        }
    
    return {
        'success': False,
        'error': 'No data found',
        'query_number': query_number
    }

# ========== FLASK ROUTES ==========
@app.route('/api', methods=['GET'])
def api_endpoint():
    """Main API endpoint"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    try:
        result = get_fam_info_with_storage(query)
        
        if result['success']:
            response_data = {
                'success': True,
                'query': query,
                'data': result['data'],
                'source': result['source'],
                'query_number': result.get('query_number', 0)
            }
            
            if result.get('stored_in_db'):
                response_data['note'] = 'Stored in database (200th query)'
            
            return jsonify(response_data)
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error'),
                'query': query,
                'query_number': result.get('query_number', 0)
            }), 404
            
    except Exception as e:
        print(f"💥 API Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/database/stats', methods=['GET'])
def database_stats():
    """Get database statistics"""
    try:
        # Load JSON database
        with open(JSON_DB_FILE, 'r') as f:
            json_data = json.load(f)
        
        # Count CSV records
        csv_count = 0
        if os.path.exists(CSV_DB_FILE):
            with open(CSV_DB_FILE, 'r') as f:
                csv_count = sum(1 for _ in f) - 1  # Subtract header
        
        return jsonify({
            'success': True,
            'json_records': len(json_data),
            'csv_records': max(0, csv_count),
            'query_counter': query_counter,
            'next_storage_at': (200 - (query_counter % 200)) if query_counter > 0 else 200,
            'database_enabled': USE_DATABASE,
            'sample_record': list(json_data.values())[0] if json_data else None
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/database/search/<fam_id>', methods=['GET'])
def database_search(fam_id):
    """Search in database"""
    data = get_from_database(fam_id)
    
    if data:
        return jsonify({
            'success': True,
            'found': True,
            'data': data
        })
    else:
        return jsonify({
            'success': True,
            'found': False,
            'message': f'FAM ID {fam_id} not found in database'
        })

@app.route('/database/export/json', methods=['GET'])
def export_json():
    """Export JSON database"""
    try:
        with open(JSON_DB_FILE, 'r') as f:
            data = json.load(f)
        
        response = jsonify(data)
        response.headers['Content-Disposition'] = 'attachment; filename=fam_database.json'
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/database/export/csv', methods=['GET'])
def export_csv():
    """Export CSV database"""
    try:
        with open(CSV_DB_FILE, 'r') as f:
            csv_content = f.read()
        
        response = app.response_class(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=fam_database.csv'}
        )
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'FAM API with Database',
        'query_counter': query_counter,
        'database_enabled': USE_DATABASE,
        'database_size': len(get_from_database('dummy') or {}),
        'timestamp': time.time()
    })

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'service': 'FAM API with Database Storage',
        'description': 'Stores every 200th query in database for future use',
        'features': [
            'No cache system - always checks database first',
            'Stores every 200th query in JSON and CSV databases',
            'Uses Supabase cloud storage (if configured)',
            'Indexed by fam_id for fast lookup'
        ],
        'usage': 'GET /api?fam=upi@fam',
        'example': '/api?fam=sugarsingh@fam',
        'database_endpoints': {
            '/database/stats': 'Database statistics',
            '/database/search/{fam_id}': 'Search in database',
            '/database/export/json': 'Export JSON database',
            '/database/export/csv': 'Export CSV database'
        }
    })

# ========== INITIALIZATION ==========
def init_app():
    """Initialize application"""
    # Create local database files
    init_local_database()
    
    # Load query counter
    load_query_counter()
    
    print(f"🚀 FAM API with Database initialized")
    print(f"📊 Query counter: {query_counter}")
    print(f"💾 Next storage at query: {200 - (query_counter % 200)} more queries")
    print(f"☁️  Supabase enabled: {USE_DATABASE}")
    
    # Try to initialize Telegram client
    try:
        get_telegram_client()
        print("✅ Telegram client pre-initialized")
    except Exception as e:
        print(f"⚠️ Telegram initialization deferred: {e}")

# Initialize on import
init_app()

# Cleanup on exit
import atexit
atexit.register(close_telegram_client)
atexit.register(save_query_counter)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🌐 Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
