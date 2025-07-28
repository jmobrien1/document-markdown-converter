-- Add missing subscription columns to users table
-- This script can be run directly on your PostgreSQL database

-- Add subscription_status column
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'trial';

-- Add current_tier column
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_tier VARCHAR(50) DEFAULT 'free';

-- Add subscription_start_date column
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMP;

-- Add last_payment_date column
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_payment_date TIMESTAMP;

-- Add next_payment_date column
ALTER TABLE users ADD COLUMN IF NOT EXISTS next_payment_date TIMESTAMP;

-- Update existing users to have proper default values
UPDATE users SET 
    subscription_status = 'trial',
    current_tier = 'free'
WHERE subscription_status IS NULL OR current_tier IS NULL;

-- Verify the columns were added
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('subscription_status', 'current_tier', 'subscription_start_date', 'last_payment_date', 'next_payment_date')
ORDER BY column_name; 