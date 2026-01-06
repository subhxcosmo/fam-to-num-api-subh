import os
import re
import time
import json
import tempfile
import threading
import csv
import io
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Try to import Supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("⚠️ Supabase not installed, using local JSON storage")

load_dotenv()

app = Flask(__name__)

# Telegram client will be initialized only when needed
telegram_client = None
client_lock = threading.Lock()

# Database instance
supabase = None
USE_SUPABASE = False

# Local JSON storage as fallback
DATA_FILE = "fam_data.json"
CSV_FILE = "fam_data.csv"

def init_database():
    """Initialize database connection"""
    global supabase, USE_SUPABASE
    
    if SUPABASE_AVAILABLE:
        supabase_url = os.getenv('SUPABASE_URL', '')
        supabase_key = os.getenv('SUPABASE_KEY', '')
        
        if supabase_url and supabase_key:
            try:
                supabase = create_client(supabase_url, supabase_key)
                print("✅ Connected to Supabase")
                USE_SUPABASE = True
                
                # Create table if not exists
                create_table_query = """
                CREATE TABLE IF NOT EXISTS fam_records (
                    id SERIAL PRIMARY KEY,
                    fam_id TEXT UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    type TEXT,
                    breached_timestamp DOUBLE PRECISION,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                """
                
                try:
                    supabase.table('fam_records').select('*').limit(1).execute()
                    print("✅ Fam records table exists")
                except:
                    print("⚠️ Table may need to be created manually in Supabase dashboard")
                    
            except Exception as e:
                print(f"⚠️ Supabase connection failed: {e}")
                print("🔄 Falling back to local JSON storage")
                USE_SUPABASE = False
        else:
            print("⚠️ Supabase credentials not found, using local JSON storage")
            USE_SUPABASE = False
    else:
        print("⚠️ Supabase library not installed, using local JSON storage")
        USE_SUPABASE = False
    
    # Initialize local storage
    init_local_storage()

def init_local_storage():
    """Initialize local JSON storage"""
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
        print(f"✅ Created local data file: {DATA_FILE}")

def save_to_database(fam_data):
    """Save FAM data to database"""
    try:
        if not fam_data or not fam_data.get('fam_id'):
            return False
        
        fam_id = fam_data.get('fam_id')
        
        # Prepare data
        record = {
            'fam_id': fam_id,
            'name': fam_data.get('name', ''),
            'phone': fam_data.get('phone', ''),
            'type': fam_data.get('type', 'contact'),
            'breached_timestamp': time.time(),
            'updated_at': datetime.now().isoformat()
        }
        
        if USE_SUPABASE and supabase:
            try:
                # Check if record exists
                existing = supabase.table('fam_records') \
                    .select('*') \
                    .eq('fam_id', fam_id) \
                    .execute()
                
                if existing.data and len(existing.data) > 0:
                    # Update existing record
                    response = supabase.table('fam_records') \
                        .update(record) \
                        .eq('fam_id', fam_id) \
                        .execute()
                    print(f"✅ Updated existing record in Supabase: {fam_id}")
                else:
                    # Insert new record
                    response = supabase.table('fam_records') \
                        .insert(record) \
                        .execute()
                    print(f"✅ Inserted new record to Supabase: {fam_id}")
                
                return True
                
            except Exception as e:
                print(f"❌ Supabase error: {e}")
                # Fall back to local storage
                USE_SUPABASE = False
        
        # Local JSON storage
        return save_to_local_json(fam_data)
        
    except Exception as e:
        print(f"❌ Database save error: {e}")
        return False

def save_to_local_json(fam_data):
    """Save to local JSON file"""
    try:
        # Read existing data
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = []
        
        # Check if exists
        fam_id = fam_data.get('fam_id')
        existing_index = -1
        for i, record in enumerate(data):
            if record.get('fam_id') == fam_id:
                existing_index = i
                break
        
        # Add timestamp
        fam_data['breached_timestamp'] = time.time()
        fam_data['updated_at'] = datetime.now().isoformat()
        
        if existing_index >= 0:
            # Update
            data[existing_index] = fam_data
            print(f"✅ Updated local record: {fam_id}")
        else:
            # Add new
            data.append(fam_data)
            print(f"✅ Added new local record: {fam_id}")
        
        # Save
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Update CSV
        update_csv(data)
        
        return True
        
    except Exception as e:
        print(f"❌ Local JSON save error: {e}")
        return False

def update_csv(data):
    """Update CSV file from JSON data"""
    try:
        if not data:
            return
        
        # Define CSV columns
        fieldnames = ['fam_id', 'name', 'phone', 'type', 'breached_timestamp', 'updated_at']
        
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in data:
                # Prepare row
                row = {
                    'fam_id': record.get('fam_id', ''),
                    'name': record.get('name', ''),
                    'phone': record.get('phone', ''),
                    'type': record.get('type', 'contact'),
                    'breached_timestamp': record.get('breached_timestamp', time.time()),
                    'updated_at': record.get('updated_at', datetime.now().isoformat())
                }
                writer.writerow(row)
        
        print(f"📊 Updated CSV file: {CSV_FILE}")
        
    except Exception as e:
        print(f"❌ CSV update error: {e}")

def get_from_database(fam_id):
    """Get FAM data from database"""
    try:
        if USE_SUPABASE and supabase:
            try:
                response = supabase.table('fam_records') \
                    .select('*') \
                    .eq('fam_id', fam_id) \
                    .execute()
                
                if response.data and len(response.data) > 0:
                    print(f"✅ Found in Supabase: {fam_id}")
                    return response.data[0]
                    
            except Exception as e:
                print(f"❌ Supabase query error: {e}")
        
        # Fall back to local storage
        return get_from_local_json(fam_id)
        
    except Exception as e:
        print(f"❌ Database query error: {e}")
        return None

def get_from_local_json(fam_id):
    """Get from local JSON file"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            
            for record in data:
                if record.get('fam_id') == fam_id:
                    print(f"✅ Found in local JSON: {fam_id}")
                    return record
        
        return None
        
    except Exception as e:
        print(f"❌ Local JSON read error: {e}")
        return None

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
        
        # Read with multiple encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1']
        content = None
        
        for encoding in encodings:
            try:
                with open(temp_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except:
                continue
        
        # Clean up
        if os.path.exists(temp_path):
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
        print(f"📤 Sending to Telegram: /fam {query}")
        sent_message = client.send_message(chat_id, f"/fam {query}")
        sent_id = sent_message.id
        
        # Wait for bot response
        print("⏳ Waiting for bot response...")
        time.sleep(15)
        
        # Get messages
        messages = client.get_messages(chat_id, limit=20)
        
        for msg in messages:
            if msg.id > sent_id:
                try:
                    sender = client.get_entity(msg.sender_id)
                    if hasattr(sender, 'bot') and sender.bot:
                        print(f"🤖 Found bot message: {msg.id}")
                        
                        # Check for .txt file
                        if msg.media:
                            print("📁 Downloading .txt file...")
                            file_content = download_txt_file(client, msg)
                            
                            if file_content and query.lower() in file_content.lower():
                                print("✅ Found matching .txt file")
                                fam_data = extract_fam_info_from_text(file_content)
                                
                                if fam_data and fam_data.get('fam_id'):
                                    return fam_data
                        
                        # Check message text
                        if msg.message and query.lower() in msg.message.lower():
                            print("✅ Found matching message text")
                            fam_data = extract_fam_info_from_text(msg.message)
                            
                            if fam_data and fam_data.get('fam_id'):
                                return fam_data
                                
                except Exception as e:
                    print(f"⚠️ Message processing error: {e}")
        
        print("❌ No valid bot response found")
        return None
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        raise
    
    finally:
        # Keep connection alive
        pass

@app.route('/api', methods=['GET'])
def get_fam_info():
    """Main API endpoint - checks DB first, then Telegram"""
    query = request.args.get('fam', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing fam parameter',
            'example': '/api?fam=sugarsingh@fam'
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
    
    # If not in database, get from Telegram
    print(f"🔄 Not in database, querying Telegram...")
    
    try:
        fam_data = get_fam_data_from_telegram(query)
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
            # Ensure fam_id is set
            if not fam_data.get('fam_id'):
                fam_data['fam_id'] = query
            
            # Save to database
            save_to_database(fam_data)
            
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
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'query': query
        }), 500

@app.route('/api/search/<fam_id>', methods=['GET'])
def search_fam(fam_id):
    """Search for specific FAM ID in database"""
    db_data = get_from_database(fam_id)
    
    if db_data:
        return jsonify({
            'success': True,
            'found': True,
            'data': db_data
        })
    else:
        return jsonify({
            'success': True,
            'found': False,
            'message': f'FAM ID {fam_id} not found in database'
        })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    try:
        total_records = 0
        
        if USE_SUPABASE and supabase:
            try:
                response = supabase.table('fam_records') \
                    .select('*', count='exact') \
                    .execute()
                total_records = response.count or 0
            except:
                pass
        
        # Count local records
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            local_records = len(data)
        else:
            local_records = 0
        
        return jsonify({
            'success': True,
            'database_type': 'supabase' if USE_SUPABASE else 'local_json',
            'total_records': total_records or local_records,
            'local_records': local_records,
            'csv_available': os.path.exists(CSV_FILE),
            'files': {
                'json': DATA_FILE if os.path.exists(DATA_FILE) else None,
                'csv': CSV_FILE if os.path.exists(CSV_FILE) else None
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export/json', methods=['GET'])
def export_json():
    """Export all data as JSON"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            
            return jsonify({
                'success': True,
                'count': len(data),
                'data': data,
                'timestamp': time.time()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No data available'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    """Export all data as CSV download"""
    try:
        if os.path.exists(CSV_FILE):
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
        else:
            return jsonify({
                'success': False,
                'error': 'CSV file not available'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/refresh/<fam_id>', methods=['GET'])
def refresh_fam(fam_id):
    """Force refresh data for a FAM ID from Telegram"""
    try:
        print(f"🔄 Force refreshing: {fam_id}")
        
        fam_data = get_fam_data_from_telegram(fam_id)
        
        if fam_data and (fam_data.get('fam_id') or fam_data.get('name') or fam_data.get('phone')):
            if not fam_data.get('fam_id'):
                fam_data['fam_id'] = fam_id
            
            # Update database
            save_to_database(fam_data)
            
            return jsonify({
                'success': True,
                'message': f'Refreshed data for {fam_id}',
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
            return jsonify({
                'success': False,
                'error': f'Could not refresh data for {fam_id}'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    db_status = 'supabase' if USE_SUPABASE else 'local_json'
    
    return jsonify({
        'status': 'healthy',
        'service': 'FAM API with Database',
        'database': db_status,
        'timestamp': time.time(),
        'endpoints': [
            '/api?fam=upi@fam',
            '/api/search/fam_id',
            '/api/stats',
            '/api/export/json',
            '/api/export/csv',
            '/api/refresh/fam_id'
        ]
    })

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'service': 'FAM API with Cloud Database',
        'description': 'Stores all queries in database (Supabase cloud or local JSON)',
        'features': [
            'Database-first: Checks DB before querying Telegram',
            'Auto-save: All successful queries saved to database',
            'Dual format: JSON and CSV exports',
            'Free cloud: Uses Supabase free tier',
            'Local fallback: JSON storage if cloud unavailable'
        ],
        'usage': 'GET /api?fam=upi@fam',
        'database_endpoints': {
            '/api/search/<fam_id>': 'Search in database',
            '/api/stats': 'Database statistics',
            '/api/export/json': 'Export all data as JSON',
            '/api/export/csv': 'Download all data as CSV',
            '/api/refresh/<fam_id>': 'Force refresh from Telegram'
        }
    })

# Initialize on startup
init_database()

# Close connection on shutdown
import atexit
atexit.register(close_telegram_client)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting FAM API with Database on port {port}")
    print(f"💾 Database: {'Supabase' if USE_SUPABASE else 'Local JSON'}")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
