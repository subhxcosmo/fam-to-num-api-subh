"""
Setup script for Supabase database
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def setup_supabase():
    """Setup Supabase table and permissions"""
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("❌ Supabase credentials not found in .env")
        print("Please add:")
        print("SUPABASE_URL=your_project_url")
        print("SUPABASE_KEY=your_anon_key")
        return False
    
    headers = {
        'apikey': supabase_key,
        'Authorization': f'Bearer {supabase_key}',
        'Content-Type': 'application/json'
    }
    
    # Create table using SQL endpoint
    sql = """
    CREATE TABLE IF NOT EXISTS fam_data (
        id BIGSERIAL PRIMARY KEY,
        fam_id TEXT NOT NULL UNIQUE,
        name TEXT,
        phone TEXT,
        type TEXT DEFAULT 'contact',
        breached_timestamp DOUBLE PRECISION,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
    );
    
    CREATE INDEX IF NOT EXISTS idx_fam_data_fam_id ON fam_data(fam_id);
    """
    
    try:
        response = requests.post(
            f'{supabase_url}/rest/v1/rpc/exec_sql',
            headers=headers,
            json={'query': sql}
        )
        
        if response.status_code == 200:
            print("✅ Supabase table created successfully")
            print(f"📊 Table URL: {supabase_url}/rest/v1/fam_data")
            print(f"🔑 Use headers: apikey: {supabase_key[:20]}...")
            return True
        else:
            print(f"❌ Error creating table: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Setting up Supabase database...")
    if setup_supabase():
        print("🎉 Setup complete!")
        print("\nAdd to your .env file:")
        print(f"SUPABASE_URL=your_project_url")
        print(f"SUPABASE_KEY=your_anon_key")
    else:
        print("⚠️ Manual setup required:")
        print("1. Go to Supabase Dashboard")
        print("2. Open SQL Editor")
        print("3. Run the SQL from supabase_setup.sql")
