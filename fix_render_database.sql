-- Fix Render PostgreSQL Database
-- Run this script directly in your Render PostgreSQL database

-- Add all missing subscription columns to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'trial';
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_tier VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_payment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS next_payment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_end_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS on_trial BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_pages_processed_current_month INTEGER DEFAULT 0;

-- Update existing users with default values
UPDATE users SET 
    subscription_status = 'trial',
    current_tier = 'free',
    on_trial = FALSE,
    pro_pages_processed_current_month = 0
WHERE subscription_status IS NULL 
   OR current_tier IS NULL 
   OR on_trial IS NULL 
   OR pro_pages_processed_current_month IS NULL;

-- Verify the columns were added
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN (
    'subscription_status', 
    'current_tier', 
    'subscription_start_date', 
    'last_payment_date', 
    'next_payment_date',
    'trial_start_date',
    'trial_end_date',
    'on_trial',
    'pro_pages_processed_current_month'
)
ORDER BY column_name;

-- Test query to ensure columns work
SELECT id, email, subscription_status, current_tier, on_trial, pro_pages_processed_current_month 
FROM users LIMIT 1; 