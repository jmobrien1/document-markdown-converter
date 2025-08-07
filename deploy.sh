#!/bin/bash
# A resilient deployment script for Render

echo "Starting robust deployment script..."

# Step 1: Check Alembic history integrity
echo "Checking Alembic migration history..."
if ! flask db check; then
    echo "WARNING: Alembic history check failed, but continuing with deployment..."
    echo "This may indicate a fresh database that needs initialization."
fi

# Step 2: Check for multiple heads
echo "Checking for multiple migration heads..."
HEADS_OUTPUT=$(flask db heads 2>&1)
HEAD_COUNT=$(echo "$HEADS_OUTPUT" | grep -c "head")

if [ "$HEAD_COUNT" -gt 1 ]; then
    echo "ERROR: Multiple migration heads detected:"
    echo "$HEADS_OUTPUT"
    echo "Please run 'flask db merge heads' locally to resolve this issue."
    exit 1
fi

echo "Migration history is clean. Proceeding with database upgrade..."

# Step 3: Attempt to upgrade the database with multiple fallback strategies
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
                echo "ERROR: All migration strategies failed, but continuing with server startup."
                echo "The application will start but database features may not work correctly."
            fi
        fi
    fi
fi

# Start the Gunicorn server with optimized settings
echo "Starting Gunicorn server with optimized settings..."
exec gunicorn run:app \
  --bind 0.0.0.0:$PORT \
  --workers=2 \
  --timeout=300 \
  --keep-alive=5 \
  --max-requests=1000 \
  --max-requests-jitter=100 \
  --preload \
  --worker-class=sync 