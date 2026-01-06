-- Run this in Supabase SQL Editor to create the table
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

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_fam_id ON fam_records(fam_id);

-- Enable Row Level Security (optional)
ALTER TABLE fam_records ENABLE ROW LEVEL SECURITY;

-- Create policy for anonymous access
CREATE POLICY "Allow anonymous read/write" ON fam_records
    FOR ALL USING (true);
