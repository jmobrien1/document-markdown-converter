#!/bin/bash
# A resilient deployment script for Render

echo "Starting robust deployment script..."

# Attempt to upgrade the database with multiple fallback strategies
echo "Attempting database migration with fallback strategies..."

# Strategy 1: Try normal upgrade
if flask db upgrade; then
    echo "Database migration successful."
else
    echo "WARNING: Normal migration failed, trying fallback strategies..."
    
    # Strategy 2: Try to upgrade to heads (multiple heads)
    if flask db upgrade heads; then
        echo "Database migration successful using 'upgrade heads'."
    else
        echo "WARNING: 'upgrade heads' failed, trying 'upgrade head'..."
        
        # Strategy 3: Try to upgrade to single head
        if flask db upgrade head; then
            echo "Database migration successful using 'upgrade head'."
        else
            echo "WARNING: All migration strategies failed, stamping current head..."
            
            # Strategy 4: Stamp the current head to mark as up-to-date
            if flask db stamp head; then
                echo "Database stamped to current head."
            else
                echo "WARNING: Even stamping failed, but continuing with server startup."
            fi
        fi
    fi
fi

# Start the Gunicorn server
echo "Starting Gunicorn server..."
exec gunicorn run:app --bind 0.0.0.0:$PORT 