"""
Script to set up Supabase database tables
Run this once to create the necessary tables
"""
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def setup_supabase():
    """Set up Supabase database tables"""
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("❌ SUPABASE_URL and SUPABASE_KEY required in .env")
        return
    
    try:
        supabase = create_client(supabase_url, supabase_key)
        print("✅ Connected to Supabase")
        
        # Create table using SQL (run this in Supabase SQL editor)
        print("\n📋 Run this SQL in Supabase SQL Editor:")
        print("""
        CREATE TABLE IF NOT EXISTS fam_records (
            id SERIAL PRIMARY KEY,
            fam_id TEXT UNIQUE NOT NULL,
            name TEXT,
            phone TEXT,
            type TEXT DEFAULT 'contact',
            breached_timestamp DOUBLE PRECISION,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
        );
        
        -- Create index for faster queries
        CREATE INDEX IF NOT EXISTS idx_fam_id ON fam_records(fam_id);
        
        -- Create updated_at trigger
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = TIMEZONE('utc', NOW());
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS update_fam_records_updated_at ON fam_records;
        CREATE TRIGGER update_fam_records_updated_at
            BEFORE UPDATE ON fam_records
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)
        
        print("\n✅ Copy the above SQL and run it in Supabase SQL Editor")
        print("   Dashboard -> SQL Editor -> New Query -> Paste -> Run")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    setup_supabase()
