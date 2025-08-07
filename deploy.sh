#!/bin/bash
# A resilient deployment script for Render

echo "Starting robust deployment script..."

# Attempt to upgrade the database, but don't exit on error
echo "Attempting database migration..."
if flask db upgrade; then
    echo "Database migration successful."
else
    echo "WARNING: Database migration failed, but continuing with server startup."
    # Optional: You could add logic here to notify you of the failure.
fi

# Start the Gunicorn server
echo "Starting Gunicorn server..."
exec gunicorn run:app --bind 0.0.0.0:$PORT 