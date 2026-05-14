# Asana Task Service

FastAPI microservice that creates Asana tasks from n8n webhook calls. Part of the PEC Assist Teams Bot ecosystem.

## Architecture Flow

```
MS Teams Message
      ↓
Microsoft Graph Webhook
      ↓
n8n Workflow (PoC-Teams-Webhooks)
      ↓
LLM Classification (requires_task: true)
      ↓
HTTP Request Node → FastAPI /tasks endpoint
      ↓
Asana Task Created
```

## Quick Start

### 1. Install Dependencies

```bash
cd src/asana_task_service
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Asana credentials
```

### 3. Run the Service

```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check |
| `/tasks` | POST | Create Asana task |

## Request Format

n8n should POST to `/tasks` with this JSON body:

```json
{
  "title": "Password Reset Request - John Doe",
  "description": "User cannot access their account",
  "intent": "password_reset",
  "urgency": "high",
  "summary": "User locked out of account",
  "sender_name": "John Doe",
  "sender_email": "john.doe@pecaluminum.com",
  "message_id": "123456789",
  "chat_id": "19:abc123@thread.v2"
}
```

### Required Fields

- `title` - Task title
- `intent` - One of: `password_reset`, `software_issue`, `hardware_issue`, `access_request`, `general_inquiry`
- `urgency` - One of: `low`, `medium`, `high`, `critical`

### Optional Fields

- `description` - Full message content
- `summary` - LLM-generated summary
- `sender_name` / `sender_email` - Reporter info
- `message_id` / `chat_id` - Teams reference IDs
- `assignee` - Asana user GID
- `due_date` - YYYY-MM-DD format (auto-calculated from urgency if not provided)
- `tags` - Additional tags array

## Response Format

```json
{
  "success": true,
  "task_id": "1201234567890123",
  "task_url": "https://app.asana.com/0/120.../120...",
  "message": "Task created successfully in Asana",
  "created_at": "2026-04-09T00:00:00Z",
  "asana_response": { ... }
}
```

## Asana Setup

### 1. Create Personal Access Token

1. Go to https://app.asana.com/0/developer-console
2. Click "Create New Personal Access Token"
3. Copy the token to your `.env` file

### 2. Get Project ID

1. Open your Asana project
2. Copy the project ID from the URL: `https://app.asana.com/0/<PROJECT_ID>/list`
3. Add to `.env` as `ASANA_PROJECT_ID`

### 3. Create Tags (Optional)

Create these tags in your Asana project for auto-tagging:
- `password_reset`
- `software_issue`
- `hardware_issue`
- `access_request`
- `urgency_low`, `urgency_medium`, `urgency_high`, `urgency_critical`

## n8n Integration

Add an HTTP Request node after "Parse LLM JSON" in your workflow:

**Node Configuration:**

| Setting | Value |
|---------|-------|
| Method | POST |
| URL | `http://your-fastapi-server:8000/tasks` |
| Authentication | None (or add API key if you implement auth) |
| Send Body | Yes |
| Content Type | JSON |

**Body (JSON):**

```json
{
  "title": "{{ $json.intent.replace('_', ' ').title() }} - {{ $('Fetch Message').first().json.from.user.displayName }}",
  "description": "{{ $json.body.content }}",
  "intent": "{{ $json.intent }}",
  "urgency": "{{ $json.urgency }}",
  "summary": "{{ $json.summary }}",
  "sender_name": "{{ $('Fetch Message').first().json.from.user.displayName }}",
  "sender_email": "{{ $('Fetch Message').first().json.from.user.email }}",
  "message_id": "{{ $('Parse Resource').first().json.messageId }}",
  "chat_id": "{{ $('Parse Resource').first().json.chatId }}"
}
```

**Condition:** Only execute when `$json.requires_task` is `true`

## Features

- ✅ Intent × urgency SLA model with business-day + US holiday awareness (critical → +4 business hours via `due_at`; lower urgencies → N business days via `due_on`)
- ✅ Visual priority indicators (🔴🟠🟡🟢 emojis)
- ✅ Rich task descriptions with metadata
- ✅ Auto-tagging by intent and urgency
- ✅ Comprehensive error handling
- ✅ Health check endpoint for monitoring

## Due-date logic

Due dates are computed by [`due_date.py`](due_date.py).

- All math runs in `BUSINESS_TIMEZONE` (default `America/Los_Angeles`).
- Business days skip Saturday, Sunday, and US federal holidays (via the `holidays` package).
- `critical` urgency emits Asana's `due_at` field with a deadline `+4 business hours` from the request, clipped to `[BUSINESS_HOURS_START, BUSINESS_HOURS_END)`.
- All other urgencies emit Asana's `due_on` with a date computed from the per-intent SLA matrix (see `SLA_MATRIX` in [`due_date.py`](due_date.py)).
- If the client supplies an explicit `due_date`, past dates return HTTP 400, and weekends/holidays are rolled forward to the next business day.

To tune SLAs, edit the `SLA_MATRIX` constant. To change the business calendar window, edit the env vars in `.env`.

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py due_date.py .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t asana-task-service .
docker run -p 8000:8000 --env-file .env asana-task-service
```
