#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# This command will run the db.create_all() for you on every deploy.
# It's safe because create_all() doesn't re-create existing tables.
flask create-db