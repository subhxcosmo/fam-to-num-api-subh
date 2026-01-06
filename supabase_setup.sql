-- Create table in Supabase SQL Editor
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

-- Create index for faster searches
CREATE INDEX IF NOT EXISTS idx_fam_data_fam_id ON fam_data(fam_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc', NOW());
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger
CREATE TRIGGER update_fam_data_updated_at 
    BEFORE UPDATE ON fam_data 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
