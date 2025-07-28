ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'trial';
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_tier VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_payment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS next_payment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_end_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS on_trial BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_pages_processed_current_month INTEGER DEFAULT 0;

UPDATE users SET 
    subscription_status = 'trial',
    current_tier = 'free',
    on_trial = FALSE,
    pro_pages_processed_current_month = 0
WHERE subscription_status IS NULL 
   OR current_tier IS NULL 
   OR on_trial IS NULL 
   OR pro_pages_processed_current_month IS NULL;

SELECT 'SUCCESS: All columns added successfully' as status;

SELECT id, email, subscription_status, current_tier, on_trial 
FROM users LIMIT 1; 