#!/usr/bin/env bash
# exit on error
set -o errexit

# DEBUG: List the contents of the secrets directory
echo "--- Listing contents of /etc/secrets/ ---"
ls -la /etc/secrets/
echo "----------------------------------------"

pip install --upgrade pip
pip install -r requirements.txt

# Run database migrations
echo "--- Running database migrations ---"
export FLASK_APP=run.py
export FLASK_CONFIG=production
flask db upgrade
echo "--- Database migrations completed ---"