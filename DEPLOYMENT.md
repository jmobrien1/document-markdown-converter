# Deployment Guide

## Environment Variables

### Main Application (Web Service)

```bash
# Core Flask
FLASK_ENV=production
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql://username:password@host:port/database

# Celery and Redis
CELERY_BROKER_URL=redis://username:password@host:port
CELERY_RESULT_BACKEND=redis://username:password@host:port

# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS={"type":"service_account",...}
GOOGLE_CLOUD_PROJECT=your-project-id
GCS_BUCKET_NAME=your-bucket-name
DOCAI_PROCESSOR_ID=your-processor-id
DOCAI_PROCESSOR_REGION=us

# RAG Service (Optional)
ENABLE_RAG=true
RAG_MODEL=all-MiniLM-L6-v2
RAG_MAX_TOKENS=500
RAG_CHUNK_OVERLAP=50

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

### Celery Worker Environment Variables

**The Celery worker needs ALL the same environment variables as the main application:**

```bash
# Database (Required for worker to access database)
DATABASE_URL=postgresql://username:password@host:port/database

# Celery and Redis (Required for worker to connect)
CELERY_BROKER_URL=redis://username:password@host:port
CELERY_RESULT_BACKEND=redis://username:password@host:port

# Google Cloud (Required for file processing)
GOOGLE_APPLICATION_CREDENTIALS={"type":"service_account",...}
GOOGLE_CLOUD_PROJECT=your-project-id
GCS_BUCKET_NAME=your-bucket-name
DOCAI_PROCESSOR_ID=your-processor-id
DOCAI_PROCESSOR_REGION=us

# RAG Service (Required if ENABLE_RAG=true)
ENABLE_RAG=true
RAG_MODEL=all-MiniLM-L6-v2
RAG_MAX_TOKENS=500
RAG_CHUNK_OVERLAP=50

# Stripe (Required for payment processing)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (Required for notifications)
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

# Flask (Required for app context)
FLASK_ENV=production
SECRET_KEY=your-secret-key
```

**Important Notes:**
- The Celery worker needs access to the database to process conversions
- The worker needs Google Cloud credentials to upload/download files
- If RAG is enabled, the worker needs RAG environment variables
- The worker needs Stripe credentials for payment processing
- Email credentials are needed for user notifications

## Verification Steps

### 1. Health Check
```bash
curl https://your-app.onrender.com/api/v1/health
```

### 2. Test Core Functionality
- Upload a document
- Check conversion status
- Download results

### 3. Test RAG Features (if enabled)
```bash
# Test RAG query
curl -X POST https://your-app.onrender.com/api/v1/conversion/{job_id}/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is this document about?"}'
```

### 4. Check Metrics
```bash
curl https://your-app.onrender.com/api/v1/metrics \
  -H "X-API-Key: your-api-key"
```

## Troubleshooting

### Common Issues

1. **RAG Service Not Available**
   - Check `ENABLE_RAG=true` in both web and worker environments
   - Verify ML dependencies are installed
   - Check logs for import errors

2. **Database Connection Issues**
   - Verify `DATABASE_URL` in both environments
   - Check database is accessible from Render

3. **Google Cloud Issues**
   - Verify `GOOGLE_APPLICATION_CREDENTIALS` JSON is valid
   - Check service account has proper permissions
   - Verify bucket exists and is accessible

4. **Celery Worker Issues**
   - Check Redis connection in both environments
   - Verify worker has all required environment variables
   - Check worker logs for import errors

### Log Analysis

```bash
# Check web service logs
# Check worker logs
# Look for specific error messages:
# - "ModuleNotFoundError" → Missing dependencies
# - "Connection refused" → Database/Redis issues
# - "Permission denied" → Google Cloud credential issues
``` 