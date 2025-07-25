# Database Schema Fix Guide

## 🚨 Critical Issue: Missing Trial Columns

Your PostgreSQL database is missing the following columns that are defined in the User model:

- `trial_start_date` (TIMESTAMP)
- `trial_end_date` (TIMESTAMP) 
- `on_trial` (BOOLEAN)
- `pro_pages_processed_current_month` (INTEGER)

## 🔧 Quick Fix Options

### Option 1: Run the Automated Fix Script (Recommended)

```bash
# From the project root directory
python3 fix_db_schema.py
```

This script will:
1. Try to run the fix within Flask app context
2. Fall back to direct database connection if needed
3. Add all missing columns automatically
4. Provide detailed feedback on what was fixed

### Option 2: Manual SQL Commands

If the automated script fails, run these SQL commands directly in your database:

```sql
-- Add trial columns to users table
ALTER TABLE users ADD COLUMN trial_start_date TIMESTAMP;
ALTER TABLE users ADD COLUMN trial_end_date TIMESTAMP;
ALTER TABLE users ADD COLUMN on_trial BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN pro_pages_processed_current_month INTEGER DEFAULT 0;

-- Add pages_processed column to conversions table (if missing)
ALTER TABLE conversions ADD COLUMN pages_processed INTEGER;
```

### Option 3: Flask App Context Fix

```bash
# Run within Flask app context
python3 migrations/run_schema_fix.py
```

### Option 4: Direct Database Fix

```bash
# Run direct database connection fix
python3 migrations/fix_database_schema.py
```

## 🔍 Verification

After running the fix, verify the columns exist:

```sql
-- Check users table columns
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
ORDER BY ordinal_position;

-- Check conversions table columns
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'conversions' 
ORDER BY ordinal_position;
```

## 🚀 After the Fix

1. **Restart your application** - The schema mismatch error should be resolved
2. **Test the account page** - `/account` should now load without errors
3. **Verify user functionality** - All user-related features should work correctly

## 📋 What This Fixes

- ✅ `/account` page loading (was crashing with 500 error)
- ✅ User status API (`/user-status`)
- ✅ Stats API (`/stats`) 
- ✅ History API (`/history`)
- ✅ All user relationship queries
- ✅ Trial and premium feature functionality

## 🔄 Migration History

The missing columns were supposed to be added by migration `2650ead023bc_add_trial_and_usage_tracking_fields.py`, but it appears this migration wasn't applied to your production database.

## 🛠️ Troubleshooting

### If the script fails:

1. **Check database connection** - Ensure DATABASE_URL is set correctly
2. **Check permissions** - Ensure your database user has ALTER TABLE permissions
3. **Check table existence** - Ensure the users table exists
4. **Manual verification** - Run the SQL commands manually if needed

### Common Error Messages:

- `DATABASE_URL environment variable not set` - Set your database connection string
- `Permission denied` - Check database user permissions
- `Table does not exist` - The users table needs to be created first

## 📞 Support

If you continue to have issues:

1. Check the error messages from the fix script
2. Verify your database connection settings
3. Ensure you have proper database permissions
4. Consider running the SQL commands manually

---

**Note**: This fix is safe and only adds missing columns. It won't affect existing data. 