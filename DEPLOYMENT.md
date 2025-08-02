# Deployment Guide

## Environment Variables for Production

### Core Application
```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=your-secure-secret-key-here
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Redis/Celery
CELERY_BROKER_URL=redis://host:port/0
CELERY_RESULT_BACKEND=redis://host:port/0
REDIS_URL=redis://host:port/0
```

### Google Cloud Services
```bash
# Google Cloud Storage
GCS_BUCKET_NAME=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json

# Google Document AI
DOCAI_PROCESSOR_ID=your-processor-id
```

### Payment Processing
```bash
# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
```

### Email Configuration
```bash
# Email (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### RAG Service Configuration
```bash
# RAG Service (optional - can be disabled)
ENABLE_RAG=true
RAG_MODEL=all-MiniLM-L6-v2
RAG_MAX_TOKENS=500
RAG_CHUNK_OVERLAP=50
```

## Vector Search Library

The application uses **Annoy** (Approximate Nearest Neighbors Oh Yeah) for vector similarity search instead of FAISS. This choice was made because:

- **Deployment-friendly**: Annoy has fewer build dependencies and works better on platforms like Render
- **Lighter weight**: Smaller memory footprint and faster installation
- **Good performance**: Provides excellent approximate nearest neighbor search for RAG applications
- **No SWIG dependency**: Avoids the SWIG build issues that commonly occur with FAISS

## Verification Steps

### 1. Health Check
```bash
curl https://your-app.onrender.com/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": 1234567890.123,
  "version": "1.0.0",
  "services": {
    "database": "healthy",
    "celery": "healthy",
    "rag_service": "healthy"
  }
}
```

### 2. Metrics Check
```bash
curl -H "X-API-Key: your-api-key" https://your-app.onrender.com/api/v1/metrics
```

Expected response:
```json
{
  "timestamp": 1234567890.123,
  "rag_service": {
    "initializations": 1,
    "import_errors": 0,
    "init_errors": 0,
    "queries_processed": 0,
    "chunks_created": 0,
    "embeddings_generated": 0,
    "is_available": true,
    "is_enabled": true,
    "model_name": "all-MiniLM-L6-v2",
    "last_health_check": 1234567890.123
  },
  "database": {
    "connections": "healthy"
  }
}
```

### 3. Core Functionality Test
1. Upload a document
2. Verify conversion completes
3. Check PDF viewer works
4. Test export functionality

### 4. RAG Functionality Test (if enabled)
1. Complete a document conversion
2. Ask a question about the document
3. Verify answer is generated with citations

## Troubleshooting

### Application Won't Start
- Check logs for `ModuleNotFoundError`
- Verify all required environment variables are set
- Ensure database is accessible

### RAG Service Issues
- Check `ENABLE_RAG` environment variable
- Verify ML dependencies are installed
- Check logs for import errors
- Service will fallback to text search if ML unavailable

### Database Issues
- Verify `DATABASE_URL` is correct
- Check database migrations have been run
- Ensure database is accessible from Render

### Celery Issues
- Verify Redis connection
- Check Celery worker is running
- Ensure `CELERY_BROKER_URL` is set correctly

### Vector Search Issues
- Annoy should install without issues on most platforms
- If Annoy fails, the system will fallback to text search
- Check logs for any Annoy-specific errors

## Monitoring

### Health Endpoints
- `/api/v1/health` - Overall application health
- `/api/v1/metrics` - Detailed service metrics

### Log Levels
- `DEBUG` - Development (verbose)
- `INFO` - Production (recommended)
- `WARNING` - Minimal logging
- `ERROR` - Errors only

### Key Metrics to Monitor
- RAG service availability
- Database connection health
- Celery worker status
- Error rates
- Response times
- Vector search performance 