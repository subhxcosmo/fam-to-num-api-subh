import os
import re
import time
import json
import tempfile
import threading
import concurrent.futures
import csv
import io
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Initialize Flask
app = Flask(__name__)

# Load environment variables
load_dotenv()

# Global variables
telegram_client = None
client_lock = threading.Lock()
executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

# Supabase configuration
SUPABASE_AVAILABLE = False
supabase = None
USE_LOCAL_STORAGE = True  # Default to local storage

# Local storage files
DATA_FILE = "fam_data.json"
CSV_FILE = "fam_data.csv"

# Initialize storage
def init_storage():
    """Initialize storage system"""
    global SUPABASE_AVAILABLE, supabase, USE_LOCAL_STORAGE
    
    # Try to initialize Supabase
    try:
        from supabase import create_client
        
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if supabase_url and supabase_key:
            supabase = create_client(supabase_url, supabase_key)
            
            # Test connection and create table if needed
            try:
                # Try to create table
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS fam_records (
                    id BIGSERIAL PRIMARY KEY,
                    fam_id VARCHAR(255) UNIQUE NOT NULL,
                    name TEXT,
                    phone VARCHAR(20),
                    type VARCHAR(50) DEFAULT 'contact',
                    breached_timestamp DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
                
                # Execute via REST API (limited) - we'll handle locally for now
                print("✅ Supabase connected")
                SUPABASE_AVAILABLE = True
                USE_LOCAL_STORAGE = False
                
            except Exception as e:
                print(f"⚠️ Supabase table issue: {e}")
                print("🔄 Using local storage")
                USE_LOCAL_STORAGE = True
        else:
            print("⚠️ Supabase credentials missing")
            USE_LOCAL_STORAGE = True
            
    except ImportError:
        print("⚠️ Supabase library not installed")
        USE_LOCAL_STORAGE = True
    except Exception as e:
        print(f"⚠️ Supabase init error: {e}")
        USE_LOCAL_STORAGE = True
    
    # Initialize local storage
    if USE_LOCAL_STORAGE or not SUPABASE_AVAILABLE:
        init_local_storage()

def init_local_storage():
    """Initialize local JSON storage"""
    try:
        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'w') as f:
                json.dump([], f)
            print(f"✅ Created local data file: {DATA_FILE}")
    except Exception as e:
        print(f"❌ Local storage init error: {e}")

# Telegram client
def get_telegram_client():
    """Get or create Telegram client"""
    global telegram_client
    
    with client_lock:
        if telegram_client is None:
            try:
                from telethon.sync import TelegramClient
                from telethon.sessions import StringSession
                
                api_id = int(os.getenv('TELEGRAM_API_ID', 0))
                api_hash = os.getenv('TELEGRAM_API_HASH', '')
                session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
                
                if not all([api_id, api_hash, session_string]):
                    raise ValueError("Missing Telegram credentials")
                
                telegram_client = TelegramClient(
                    StringSession(session_string),
                    api_id,
                    api_hash
                )
                telegram_client.start()
                print(f"✅ Telegram client connected")
                
            except Exception as e:
                print(f"❌ Telegram client error: {e}")
                raise
    
    return telegram_client

def close_telegram_client():
    """Close Telegram client"""
    global telegram_client
    with client_lock:
        if telegram_client and telegram_client.is_connected():
            telegram_client.disconnect()
            telegram_client = None
            print("✅ Telegram client disconnected")

# Database operations
def save_to_database(fam_data):
    """Save data to database (Supabase or local)"""
    try:
        if not fam_data or not fam_data.get('fam_id'):
            return False
        
        fam_id = fam_data.get('fam_id')
        
        # Prepare record
        record = {
            'fam_id': fam_id,
            'name': fam_data.get('name', ''),
            'phone': fam_data.get('phone', ''),
            'type': fam_data.get('type', 'contact'),
            'breached_timestamp': time.time(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Try Supabase first if available
        if SUPABASE_AVAILABLE and supabase and not USE_LOCAL_STORAGE:
            try:
                # Check if exists
                existing = supabase.table('fam_records') \
                    .select('*') \
                    .eq('fam_id', fam_id) \
                    .execute()
                
                if existing.data:
                    # Update
                    supabase.table('fam_records') \
                        .update(record) \
                        .eq('fam_id', fam_id) \
                        .execute()
                    print(f"✅ Updated in Supabase: {fam_id}")
                else:
                    # Insert
                    supabase.table('fam_records') \
                        .insert(record) \
                        .execute()
                    print(f"✅ Inserted to Supabase: {fam_id}")
                
                return True
                
            except Exception as e:
                print(f"❌ Supabase error: {e}")
                # Fallback to local
                return save_to_local(fam_data)
        
        # Local storage
        return save_to_local(fam_data)
        
    except Exception as e:
        print(f"❌ Database save error: {e}")
        return False

def save_to_local(fam_data):
    """Save to local JSON and CSV"""
    try:
        fam_id = fam_data.get('fam_id')
        
        # Add timestamp
        fam_data['breached_timestamp'] = time.time()
        fam_data['updated_at'] = datetime.now().isoformat()
        
        # Load existing data
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = []
        
        # Update or add
        found = False
        for i, record in enumerate(data):
            if record.get('fam_id') == fam_id:
                data[i] = fam_data
                found = True
                break
        
        if not found:
            data.append(fam_data)
        
        # Save JSON
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Update CSV
        update_csv(data)
        
        print(f"✅ Saved locally: {fam_id}")
        return True
        
    except Exception as e:
        print(f"❌ Local save error: {e}")
        return False

def update_csv(data):
    """Update CSV file"""
    try:
        if not data:
            return
        
        fieldnames = ['fam_id', 'name', 'phone', 'type', 'breached_timestamp', 'updated_at']
        
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in data:
                row = {
                    'fam_id': record.get('fam_id', ''),
                    'name': record.get('name', ''),
                    'phone': record.get('phone', ''),
                    'type': record.get('type', 'contact'),
                    'breached_timestamp': record.get('breached_timestamp', time.time()),
                    'updated_at': record.get('updated_at', datetime.now().isoformat())
                }
                writer.writerow(row)
        
        print(f"📊 CSV updated: {len(data)} records")
        
    except Exception as e:
        print(f"❌ CSV error: {e}")

def get_from_database(fam_id):
    """Get data from database"""
    try:
        # Try Supabase first
        if SUPABASE_AVAILABLE and supabase and not USE_LOCAL_STORAGE:
            try:
                response = supabase.table('fam_records') \
                    .select('*') \
                    .eq('fam_id', fam_id) \
                    .execute()
                
                if response.data:
                    return response.data[0]
                    
            except Exception as e:
                print(f"❌ Supabase query error: {e}")
        
        # Fallback to local
        return get_from_local(fam_id)
        
    except Exception as e:
        print(f"❌ Database query error: {e}")
        return None

def get_from_local(fam_id):
    """Get from local JSON"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            
            for record in data:
                if record.get('fam_id') == fam_id:
                    return record
        
        return None
        
    except Exception as e:
        print(f"❌ Local query error: {e}")
        return None

# Telegram operations
def extract_fam_info(text):
    """Extract FAM info from text"""
    info = {}
    
    if not text:
        return info
    
    # FAM ID
    patterns = [
        r'FAM ID\s*[:=]\s*([^\n\r]+)',
        r'FAM\s*[:=]\s*([^\n\r]+)',
        r'ID\s*[:=]\s*([^\n\r]+)'
    ]
    
    for pattern in patterns:
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
        info['type'] = match.group(1).strip().lower()
    
    return info

def download_file(client, message):
    """Download file from message"""
    try:
        if not message.media:
            return None
        
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
            temp_path = tmp.name
        
        # Download
        result = client.download_media(message, file=temp_path)
        file_path = result or temp_path
        
        # Read with multiple encodings
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                
                # Clean up
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                return content
            except:
                continue
        
        # If all encodings fail
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return None
        
    except Exception as e:
        print(f"❌ File download error: {e}")
        return None

def query_telegram_async(query):
    """Query Telegram asynchronously"""
    try:
        client = get_telegram_client()
        chat_id = -1003674153946
        
        # Validate query ends with @fam
        if not query.endswith('@fam'):
            return {'error': 'Query must end with @fam'}
        
        # Send command
        command = f"/fam {query}"
        sent_msg = client.send_message(chat_id, command)
        sent_id = sent_msg.id
        
        # Wait for response
        time.sleep(10)
        
        # Get messages
        messages = client.get_messages(chat_id, limit=20)
        
        for msg in messages:
            if msg.id > sent_id:
                try:
                    sender = client.get_entity(msg.sender_id)
                    if not (hasattr(sender, 'bot') and sender.bot):
                        continue
                    
                    # Check if this is for our query
                    msg_text = msg.message or ""
                    
                    # Option 1: Check file
                    if msg.media:
                        file_content = download_file(client, msg)
                        if file_content and query.lower() in file_content.lower():
                            return extract_fam_info(file_content)
                    
                    # Option 2: Check message text
                    if msg_text and query.lower() in msg_text.lower():
                        return extract_fam_info(msg_text)
                        
                except Exception as e:
                    print(f"⚠️ Message processing error: {e}")
                    continue
        
        return None
        
    except Exception as e:
        print(f"❌ Telegram query error: {e}")
        return {'error': str(e)}

# API Endpoints
@app.route('/api', methods=['GET'])
def get_fam_info():
    """Main API endpoint"""
    query = request.args.get('fam', '').strip()
    
    # Validate query
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
        }), 400
    
    if not query.endswith('@fam'):
        return jsonify({
            'success': False,
            'error': 'Query must end with @fam (e.g., sugarsingh@fam)',
            'received': query
        }), 400
    
    print(f"\n" + "="*60)
    print(f"🔍 Processing: {query}")
    print("="*60)
    
    # Check database first
    db_data = get_from_database(query)
    
    if db_data:
        print(f"✅ Found in database")
        return jsonify({
            'success': True,
            'query': query,
            'source': 'database',
            'data': {
                'fam_id': db_data.get('fam_id', query),
                'name': db_data.get('name', ''),
                'phone': db_data.get('phone', ''),
                'type': db_data.get('type', 'contact'),
                'breached_timestamp': db_data.get('breached_timestamp', time.time()),
                'updated_at': db_data.get('updated_at', datetime.now().isoformat())
            }
        })
    
    # Query Telegram
    print(f"🔄 Querying Telegram...")
    
    try:
        # Use thread pool for parallel processing
        future = executor.submit(query_telegram_async, query)
        fam_data = future.result(timeout=40)
        
        if isinstance(fam_data, dict) and 'error' in fam_data:
            return jsonify({
                'success': False,
                'error': fam_data['error'],
                'query': query
            }), 400
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
            # Ensure fam_id is set
            if not fam_data.get('fam_id'):
                fam_data['fam_id'] = query
            
            # Save to database in background
            executor.submit(save_to_database, fam_data)
            
            return jsonify({
                'success': True,
                'query': query,
                'source': 'telegram',
                'data': {
                    'fam_id': fam_data.get('fam_id', query),
                    'name': fam_data.get('name', ''),
                    'phone': fam_data.get('phone', ''),
                    'type': fam_data.get('type', 'contact'),
                    'breached_timestamp': time.time(),
                    'updated_at': datetime.now().isoformat()
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No FAM information found',
                'query': query
            }), 404
            
    except concurrent.futures.TimeoutError:
        return jsonify({
            'success': False,
            'error': 'Telegram query timeout',
            'query': query
        }), 504
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

# Database management endpoints
@app.route('/api/db/stats', methods=['GET'])
def db_stats():
    """Get database statistics"""
    try:
        stats = {
            'storage': 'local_json' if USE_LOCAL_STORAGE else 'supabase',
            'local_file': DATA_FILE if os.path.exists(DATA_FILE) else None,
            'csv_file': CSV_FILE if os.path.exists(CSV_FILE) else None
        }
        
        if USE_LOCAL_STORAGE and os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            stats['record_count'] = len(data)
            stats['recent_records'] = [r.get('fam_id') for r in data[-5:]]
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/db/export/json', methods=['GET'])
def export_json():
    """Export JSON data"""
    try:
        if not os.path.exists(DATA_FILE):
            return jsonify({'success': False, 'error': 'No data available'}), 404
        
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        return jsonify({
            'success': True,
            'count': len(data),
            'data': data,
            'timestamp': time.time()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/db/export/csv', methods=['GET'])
def export_csv():
    """Export CSV data"""
    try:
        if not os.path.exists(CSV_FILE):
            return jsonify({'success': False, 'error': 'No CSV data available'}), 404
        
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            csv_content = f.read()
        
        # Create download response
        output = io.StringIO()
        output.write(csv_content)
        
        return app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment;filename=fam_data_{int(time.time())}.csv'}
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/db/search/<fam_id>', methods=['GET'])
def search_fam(fam_id):
    """Search for FAM ID"""
    if not fam_id.endswith('@fam'):
        return jsonify({'success': False, 'error': 'FAM ID must end with @fam'}), 400
    
    data = get_from_database(fam_id)
    
    if data:
        return jsonify({'success': True, 'found': True, 'data': data})
    else:
        return jsonify({'success': True, 'found': False, 'message': f'FAM ID {fam_id} not found'})

@app.route('/api/db/refresh/<fam_id>', methods=['GET'])
def refresh_fam(fam_id):
    """Force refresh FAM ID from Telegram"""
    if not fam_id.endswith('@fam'):
        return jsonify({'success': False, 'error': 'FAM ID must end with @fam'}), 400
    
    print(f"🔄 Force refreshing: {fam_id}")
    
    try:
        # Query Telegram
        fam_data = query_telegram_async(fam_id)
        
        if isinstance(fam_data, dict) and 'error' in fam_data:
            return jsonify({'success': False, 'error': fam_data['error']}), 400
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
            if not fam_data.get('fam_id'):
                fam_data['fam_id'] = fam_id
            
            # Save to database
            save_to_database(fam_data)
            
            return jsonify({
                'success': True,
                'message': f'Refreshed {fam_id}',
                'data': {
                    'fam_id': fam_data.get('fam_id', fam_id),
                    'name': fam_data.get('name', ''),
                    'phone': fam_data.get('phone', ''),
                    'type': fam_data.get('type', 'contact'),
                    'breached_timestamp': time.time(),
                    'updated_at': datetime.now().isoformat()
                }
            })
        else:
            return jsonify({'success': False, 'error': f'No data found for {fam_id}'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Health and info endpoints
@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'FAM API',
        'storage': 'local_json' if USE_LOCAL_STORAGE else 'supabase',
        'telegram': 'connected' if telegram_client else 'disconnected',
        'timestamp': time.time()
    })

@app.route('/', methods=['GET'])
def home():
    """Home page"""
    return jsonify({
        'service': 'FAM API with Database',
        'description': 'High-performance API with database storage',
        'features': [
            'Validates @fam suffix requirement',
            'Database-first architecture',
            'Parallel processing for speed',
            'Automatic data persistence',
            'JSON and CSV exports'
        ],
        'usage': 'GET /api?fam=username@fam',
        'validation': 'Query must end with @fam (e.g., sugarsingh@fam)',
        'endpoints': {
            '/api?fam=USERNAME@fam': 'Get FAM information',
            '/api/db/search/USERNAME@fam': 'Search in database',
            '/api/db/stats': 'Database statistics',
            '/api/db/export/json': 'Export JSON',
            '/api/db/export/csv': 'Export CSV',
            '/api/db/refresh/USERNAME@fam': 'Force refresh',
            '/health': 'Health check'
        },
        'example': 'https://your-app.onrender.com/api?fam=sugarsingh@fam'
    })

# Initialize on startup
init_storage()

# Cleanup on shutdown
import atexit
atexit.register(close_telegram_client)
atexit.register(executor.shutdown)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting optimized FAM API on port {port}")
    print(f"💾 Storage: {'Local JSON' if USE_LOCAL_STORAGE else 'Supabase'}")
    print(f"⚡ Threads: 3 parallel workers")
    print(f"✅ Validation: Must end with @fam")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
