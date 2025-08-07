#!/bin/bash

# Deployment migration script that handles multiple heads gracefully

echo "Starting database migration..."

# Try to upgrade to heads first
if flask db upgrade heads; then
    echo "Successfully upgraded to all heads"
elif flask db upgrade head; then
    echo "Successfully upgraded to single head"
else
    echo "Migration failed, attempting to stamp current head..."
    flask db stamp head
    echo "Database stamped to current head"
fi

echo "Starting Gunicorn server..."
exec gunicorn run:app --bind 0.0.0.0:$PORT 