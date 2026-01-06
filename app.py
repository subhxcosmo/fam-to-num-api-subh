import os
import re
import time
import json
import csv
import io
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Storage files
DATA_FILE = "fam_data.json"
CSV_FILE = "fam_data.csv"

# Initialize storage
def init_storage():
    """Initialize local storage"""
    try:
        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'w') as f:
                json.dump([], f)
            print(f"✅ Created local data file: {DATA_FILE}")
    except Exception as e:
        print(f"❌ Storage init error: {e}")

init_storage()

# Database operations
def save_to_database(fam_data):
    """Save data to local JSON and CSV"""
    try:
        if not fam_data or not fam_data.get('fam_id'):
            return False
        
        fam_id = fam_data.get('fam_id')
        
        # Add timestamps
        fam_data['breached_timestamp'] = time.time()
        fam_data['updated_at'] = datetime.now().isoformat()
        fam_data['created_at'] = fam_data.get('created_at', datetime.now().isoformat())
        
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
        
        print(f"✅ Saved to database: {fam_id}")
        return True
        
    except Exception as e:
        print(f"❌ Database save error: {e}")
        return False

def update_csv(data):
    """Update CSV file"""
    try:
        if not data:
            return
        
        fieldnames = ['fam_id', 'name', 'phone', 'type', 'breached_timestamp', 'created_at', 'updated_at']
        
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
                    'created_at': record.get('created_at', datetime.now().isoformat()),
                    'updated_at': record.get('updated_at', datetime.now().isoformat())
                }
                writer.writerow(row)
        
        print(f"📊 CSV updated: {len(data)} records")
        
    except Exception as e:
        print(f"❌ CSV error: {e}")

def get_from_database(fam_id):
    """Get data from database"""
    try:
        if not os.path.exists(DATA_FILE):
            return None
        
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        for record in data:
            if record.get('fam_id') == fam_id:
                return record
        
        return None
        
    except Exception as e:
        print(f"❌ Database query error: {e}")
        return None

def get_all_records():
    """Get all records from database"""
    try:
        if not os.path.exists(DATA_FILE):
            return []
        
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
        
    except Exception as e:
        print(f"❌ Get all records error: {e}")
        return []

# FAM info extraction
def extract_fam_info(text):
    """Extract FAM information from text"""
    info = {}
    
    if not text:
        return info
    
    # Clean the text
    text = text.strip()
    
    # Debug: Show first 500 chars
    print(f"📝 Parsing text (first 500 chars): {text[:500]}")
    
    # FAM ID patterns
    fam_patterns = [
        r'FAM ID\s*[:=]\s*([^\n\r]+)',
        r'FAM\s*[:=]\s*([^\n\r]+)',
        r'ID\s*[:=]\s*([^\n\r]+)',
        r'FAM\s+ID\s*[:=]\s*([^\n\r]+)'
    ]
    
    for pattern in fam_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info['fam_id'] = match.group(1).strip()
            print(f"✅ Found FAM ID: {info['fam_id']}")
            break
    
    # NAME
    name_match = re.search(r'NAME\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
    if name_match:
        info['name'] = name_match.group(1).strip()
        print(f"✅ Found NAME: {info['name']}")
    
    # PHONE
    phone_match = re.search(r'PHONE\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
    if phone_match:
        info['phone'] = match.group(1).strip()
        print(f"✅ Found PHONE: {info['phone']}")
    
    # TYPE
    type_match = re.search(r'TYPE\s*[:=]\s*([^\n\r]+)', text, re.IGNORECASE)
    if type_match:
        info['type'] = match.group(1).strip().lower()
        print(f"✅ Found TYPE: {info['type']}")
    
    # If no patterns matched, try line-by-line
    if not info:
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

# Telegram operations (SYNCHRONOUS)
class TelegramBot:
    """Synchronous Telegram bot client"""
    
    def __init__(self):
        self.client = None
        self.connected = False
    
    def connect(self):
        """Connect to Telegram synchronously"""
        try:
            # Import inside function to handle missing dependencies
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession
            
            api_id = int(os.getenv('TELEGRAM_API_ID', 0))
            api_hash = os.getenv('TELEGRAM_API_HASH', '')
            session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
            
            if not all([api_id, api_hash, session_string]):
                raise ValueError("Missing Telegram credentials")
            
            self.client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash
            )
            
            # Connect synchronously
            self.client.start()
            self.connected = True
            print(f"✅ Telegram client connected")
            
            return True
            
        except ImportError:
            print("❌ Telethon not installed. Install with: pip install telethon")
            return False
        except Exception as e:
            print(f"❌ Telegram connection error: {e}")
            return False
    
    def query_fam(self, fam_query):
        """Query FAM information from bot"""
        if not self.connected and not self.connect():
            return {'error': 'Telegram not connected'}
        
        try:
            chat_id = -1003674153946
            
            # Send command
            print(f"📤 Sending to Telegram: /fam {fam_query}")
            sent_message = self.client.send_message(chat_id, f"/fam {fam_query}")
            sent_id = sent_message.id
            
            # Wait for bot response
            print("⏳ Waiting 15 seconds for bot response...")
            time.sleep(15)
            
            # Get recent messages
            messages = self.client.get_messages(chat_id, limit=20)
            
            for msg in messages:
                if msg.id > sent_id:
                    try:
                        # Check if from bot
                        sender = self.client.get_entity(msg.sender_id)
                        if not (hasattr(sender, 'bot') and sender.bot):
                            continue
                        
                        print(f"🤖 Found bot message ID: {msg.id}")
                        
                        # Try to get text from message or file
                        text_content = ""
                        
                        # Check message text
                        if msg.message:
                            text_content = msg.message
                            print(f"📝 Message text: {text_content[:100]}...")
                        
                        # Check for file attachment
                        elif msg.media:
                            print("📁 Downloading file...")
                            try:
                                # Create temp file
                                import tempfile
                                with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
                                    temp_path = tmp.name
                                
                                # Download file
                                self.client.download_media(msg, file=temp_path)
                                
                                # Read file
                                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                                    try:
                                        with open(temp_path, 'r', encoding=encoding) as f:
                                            text_content = f.read()
                                        break
                                    except:
                                        continue
                                
                                # Clean up
                                if os.path.exists(temp_path):
                                    os.remove(temp_path)
                                    
                            except Exception as file_error:
                                print(f"❌ File download error: {file_error}")
                        
                        # Check if this is for our query
                        if text_content and fam_query.lower() in text_content.lower():
                            print(f"✅ Found response for: {fam_query}")
                            return extract_fam_info(text_content)
                            
                    except Exception as e:
                        print(f"⚠️ Message processing error: {e}")
                        continue
            
            print("❌ No valid bot response found")
            return None
            
        except Exception as e:
            print(f"❌ Telegram query error: {e}")
            return {'error': str(e)}

# Initialize Telegram bot
telegram_bot = TelegramBot()

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
                'created_at': db_data.get('created_at', datetime.now().isoformat()),
                'updated_at': db_data.get('updated_at', datetime.now().isoformat())
            }
        })
    
    # Query Telegram
    print(f"🔄 Querying Telegram...")
    
    try:
        fam_data = telegram_bot.query_fam(query)
        
        if isinstance(fam_data, dict) and 'error' in fam_data:
            return jsonify({
                'success': False,
                'error': fam_data['error'],
                'query': query
            }), 500
        
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
                    'created_at': datetime.now().isoformat(),
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

# Database management endpoints
@app.route('/api/db/stats', methods=['GET'])
def db_stats():
    """Get database statistics"""
    try:
        data = get_all_records()
        
        stats = {
            'record_count': len(data),
            'storage_type': 'local_json',
            'data_file': DATA_FILE,
            'csv_file': CSV_FILE,
            'recent_records': [r.get('fam_id') for r in data[-10:]] if data else [],
            'timestamp': time.time()
        }
        
        return jsonify({'success': True, 'stats': stats})
        
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
        return jsonify({
            'success': True, 
            'found': False, 
            'message': f'FAM ID {fam_id} not found in database'
        })

@app.route('/api/db/refresh/<fam_id>', methods=['GET'])
def refresh_fam(fam_id):
    """Force refresh FAM ID from Telegram"""
    if not fam_id.endswith('@fam'):
        return jsonify({'success': False, 'error': 'FAM ID must end with @fam'}), 400
    
    print(f"\n🔄 Force refreshing: {fam_id}")
    
    try:
        fam_data = telegram_bot.query_fam(fam_id)
        
        if isinstance(fam_data, dict) and 'error' in fam_data:
            return jsonify({'success': False, 'error': fam_data['error']}), 500
        
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
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
            })
        else:
            return jsonify({'success': False, 'error': f'No data found for {fam_id}'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/db/export/json', methods=['GET'])
def export_json():
    """Export JSON data"""
    try:
        data = get_all_records()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data available'}), 404
        
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
            # Generate CSV if doesn't exist
            data = get_all_records()
            if not data:
                return jsonify({'success': False, 'error': 'No data available'}), 404
            update_csv(data)
        
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            csv_content = f.read()
        
        # Create download response
        return app.response_class(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment;filename=fam_data_{int(time.time())}.csv'}
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/db/clear', methods=['POST'])
def clear_database():
    """Clear all data (DANGEROUS - for testing only)"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
        
        if os.path.exists(CSV_FILE):
            os.remove(CSV_FILE)
        
        return jsonify({
            'success': True,
            'message': 'Database cleared',
            'timestamp': time.time()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Health and info endpoints
@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    telegram_status = 'connected' if telegram_bot.connected else 'disconnected'
    
    return jsonify({
        'status': 'healthy',
        'service': 'FAM API',
        'storage': 'local_json',
        'telegram': telegram_status,
        'timestamp': time.time(),
        'database_file': DATA_FILE,
        'records_count': len(get_all_records())
    })

@app.route('/test/telegram', methods=['GET'])
def test_telegram():
    """Test Telegram connection"""
    try:
        if telegram_bot.connect():
            me = telegram_bot.client.get_me()
            return jsonify({
                'success': True,
                'telegram': {
                    'connected': True,
                    'user': {
                        'id': me.id,
                        'first_name': me.first_name,
                        'username': me.username
                    }
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not connect to Telegram'
            }), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    """Home page"""
    return jsonify({
        'service': 'FAM API',
        'description': 'Synchronous Telegram FAM API with local database',
        'features': [
            '100% synchronous - no async/threading issues',
            '@fam suffix validation',
            'Local JSON + CSV database',
            'Fast repeat queries from database',
            'Automatic data persistence'
        ],
        'usage': 'GET /api?fam=username@fam',
        'validation': 'Query MUST end with @fam',
        'endpoints': {
            '/api?fam=USERNAME@fam': 'Get FAM information',
            '/api/db/search/USERNAME@fam': 'Search database',
            '/api/db/stats': 'Database statistics',
            '/api/db/export/json': 'Export JSON',
            '/api/db/export/csv': 'Download CSV',
            '/api/db/refresh/USERNAME@fam': 'Force refresh',
            '/health': 'Health check',
            '/test/telegram': 'Test Telegram connection'
        },
        'example': 'https://your-app.onrender.com/api?fam=sugarsingh@fam'
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    print(f"🚀 Starting FAM API on port {port}")
    print(f"💾 Storage: Local JSON + CSV")
    print(f"✅ Validation: Must end with @fam")
    print(f"⚡ Mode: 100% Synchronous (no async issues)")
    
    app.run(host='0.0.0.0', port=port, debug=False)
