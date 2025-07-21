# Document Markdown Converter API Documentation

## Introduction

The Document Markdown Converter API allows programmatic access to upload documents (PDF, Word, etc.) and receive clean, readable Markdown output. This API is designed for developers who want to automate document conversion workflows or integrate conversion capabilities into their own applications.

## Authentication

All API requests must be authenticated using an API key. Pass your API key in the `X-API-Key` HTTP header with every request:

```
X-API-Key: <your_api_key>
```

If the API key is missing or invalid, the API will respond with a 401 Unauthorized error.

## Endpoints

### POST `/api/v1/convert`

Submit a document for conversion. This endpoint accepts a `multipart/form-data` POST request.

**Request Body:**
- `file` (required): The document file to convert (PDF, DOCX, etc.).
- `pro_conversion` (optional): Set to `on` to request a "pro" conversion (if your account supports it).

**Headers:**
- `X-API-Key: <your_api_key>`

**Response:**
- `202 Accepted` on successful submission.
- JSON body:
  ```json
  {
    "job_id": "<celery_task_id>",
    "status_url": "https://your-domain.com/api/v1/status/<job_id>"
  }
  ```

### GET `/api/v1/status/<job_id>`

Poll this endpoint to check the status of a submitted conversion job.

**Headers:**
- `X-API-Key: <your_api_key>`

**Response:**
- `200 OK` with a JSON body describing the job status and result.
- Example response when pending:
  ```json
  {
    "job_id": "...",
    "state": "PENDING",
    "conversion_status": "pending",
    ...
  }
  ```
- Example response when completed:
  ```json
  {
    "job_id": "...",
    "state": "SUCCESS",
    "conversion_status": "completed",
    "markdown": "# Your converted markdown..."
    ...
  }
  ```
- Example response when failed:
  ```json
  {
    "job_id": "...",
    "state": "FAILURE",
    "conversion_status": "failed",
    "error_message": "<error details>"
    ...
  }
  ```

## Example Workflow

### 1. Submit a file for conversion

```sh
curl -X POST https://your-domain.com/api/v1/convert \
  -H "X-API-Key: <your_api_key>" \
  -F "file=@/path/to/your/document.pdf" \
  -F "pro_conversion=on"
```

**Response:**
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status_url": "https://your-domain.com/api/v1/status/123e4567-e89b-12d3-a456-426614174000"
}
```

### 2. Poll for conversion status

```sh
curl -X GET https://your-domain.com/api/v1/status/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-API-Key: <your_api_key>"
```

**Example completed response:**
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "state": "SUCCESS",
  "conversion_status": "completed",
  "markdown": "# Your converted markdown..."
}
```

Replace `https://your-domain.com` with your actual API base URL and `<your_api_key>` with your user's API key. 