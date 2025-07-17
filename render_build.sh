#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Set the FLASK_APP environment variable
export FLASK_APP=run.py

# Apply database migrations
flask db upgrade