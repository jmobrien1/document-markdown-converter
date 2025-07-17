#!/usr/bin/env bash
# exit on error
set -o errexit

# DEBUG: List the contents of the secrets directory
echo "--- Listing contents of /etc/secrets/ ---"
ls -la /etc/secrets/
echo "----------------------------------------"

pip install --upgrade pip
pip install -r requirements.txt