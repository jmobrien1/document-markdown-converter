# 🚀 Render Database Fix Guide

## 🔥 Problem
Your Render PostgreSQL database is missing the `subscription_status` column (and others), causing this error:
```
psycopg2.errors.UndefinedColumn: column users.subscription_status does not exist
```

## ✅ Solution Options

### Option 1: Run SQL Script (Recommended)
1. Go to your Render dashboard
2. Navigate to your PostgreSQL database
3. Open the PostgreSQL console
4. Copy and paste the contents of `fix_render_database.sql`
5. Execute the script

### Option 2: Use Python Script
1. Deploy the updated code to Render
2. Run `fix_render_database.py` on your Render instance
3. The script will automatically add all missing columns

### Option 3: Manual SQL Commands
Run these commands one by one in your PostgreSQL console:

```sql
-- Add missing columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'trial';
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_tier VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_payment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS next_payment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_end_date TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS on_trial BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_pages_processed_current_month INTEGER DEFAULT 0;

-- Update existing users
UPDATE users SET 
    subscription_status = 'trial',
    current_tier = 'free',
    on_trial = FALSE,
    pro_pages_processed_current_month = 0
WHERE subscription_status IS NULL 
   OR current_tier IS NULL 
   OR on_trial IS NULL 
   OR pro_pages_processed_current_month IS NULL;
```

## 📋 Missing Columns Being Added

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `subscription_status` | VARCHAR(50) | 'trial' | User's subscription status |
| `current_tier` | VARCHAR(50) | 'free' | User's current plan tier |
| `subscription_start_date` | TIMESTAMP | NULL | When subscription started |
| `last_payment_date` | TIMESTAMP | NULL | Last payment date |
| `next_payment_date` | TIMESTAMP | NULL | Next payment due date |
| `trial_start_date` | TIMESTAMP | NULL | Trial start date |
| `trial_end_date` | TIMESTAMP | NULL | Trial end date |
| `on_trial` | BOOLEAN | FALSE | Whether user is on trial |
| `pro_pages_processed_current_month` | INTEGER | 0 | Pro usage tracking |

## 🧪 Verification

After running the fix, verify it worked by running:

```sql
-- Check if columns exist
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('subscription_status', 'current_tier', 'on_trial')
ORDER BY column_name;

-- Test query
SELECT id, email, subscription_status, current_tier, on_trial 
FROM users LIMIT 1;
```

## 🚀 Expected Results

After applying the fix:
- ✅ No more `UndefinedColumn` errors
- ✅ `/account` page loads without errors
- ✅ Pro features work properly
- ✅ User relationships load correctly
- ✅ All subscription logic functions

## 🔧 Troubleshooting

If you still get errors:

1. **Check column existence:**
   ```sql
   \d users
   ```

2. **Verify data types:**
   ```sql
   SELECT column_name, data_type FROM information_schema.columns 
   WHERE table_name = 'users' AND column_name LIKE '%subscription%';
   ```

3. **Test a simple query:**
   ```sql
   SELECT id, email, subscription_status FROM users LIMIT 1;
   ```

## 📞 Support

If you continue to have issues:
1. Check the Render logs for detailed error messages
2. Verify the database connection is working
3. Ensure you're running the commands on the correct database

---

**Note:** This fix is safe and will not affect existing user data. All existing users will be set to 'trial' status with 'free' tier by default. 