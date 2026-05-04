# Email Task Service

FastAPI microservice that creates Asana tickets from emails. Part of the PEC Assist ecosystem.

> **Note:** As of 2026-05-03, this service is **queue-driven**. It no longer runs a background IMAP poller. Instead, an external orchestrator (e.g. n8n) polls the inbox and pushes emails to this service via the `/email/simulate` endpoint.

## What It Does

- Receives email data via HTTP POST (from n8n or other orchestrator)
- Classifies intent/urgency via OpenAI GPT-4o-mini
- Creates Asana tasks by calling the existing `asana-task` service
- Sends auto-reply emails via SMTP
- Persists toggle state in Supabase

## Architecture

```
Email User
    ↓
IMAP Inbox (Outlook/Exchange)  ← polled by n8n
    ↓
n8n Email Trigger (IMAP)
    ↓
POST /email/simulate  →  Email Task Service (FastAPI)
    ├─ OpenAI Classifier
    ├─ Asana Task Client → existing asana-task:8000
    ├─ SMTP Email Sender
    └─ Supabase Config Manager
```

## Quick Start

### 1. Install Dependencies

```bash
cd src/email_task_service
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Run Locally

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### 4. Run Tests

```bash
# Unit tests
pytest tests/test_services.py -v

# Integration tests (mocked external APIs)
TEST_MODE=true MOCK_OPENAI=true MOCK_SMTP=true MOCK_ASANA=true pytest -m integration -v
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/email/health` | GET | Health + active channel |
| `/email/config` | GET | Current toggle state |
| `/email/config/toggle` | POST | Switch channel (`teams` or `email`) |
| `/email/logs` | GET | Last N log lines (`?lines=100&fmt=text`) |
| `/email/diagnostics` | GET | Full diagnostic snapshot |
| `/email/simulate` | POST | Run an email through the pipeline |

### Processing an Email

```bash
curl -X POST http://localhost:8001/email/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "My monitor is broken",
    "body": "The screen is completely black.",
    "from_name": "Alice Smith",
    "from_email": "alice@pecalum.com",
    "message_id": "abc123"
  }'
```

## Toggle Usage

```bash
# Check current mode
curl http://localhost:8001/email/config

# Switch to email mode
curl -X POST http://localhost:8001/email/config/toggle \
  -H "Content-Type: application/json" \
  -d '{"channel": "email"}'

# Switch back to Teams
curl -X POST http://localhost:8001/email/config/toggle \
  -H "Content-Type: application/json" \
  -d '{"channel": "teams"}'
```

## Docker Deployment

```bash
cd ~/ai-initiative
docker-compose up -d --build email-task
docker-compose restart caddy
```

## Troubleshooting

| Issue | Check |
|-------|-------|
| No auto-replies | `GET /email/diagnostics` SMTP ping + logs |
| No Asana tasks | `GET /email/diagnostics` Asana service ping |
| Wrong classification | `POST /email/simulate` with the email subject/body |

## Safety

- Default: `email` channel is **disabled**. Teams continues to work normally.
- The service can be stopped without affecting any other container.
- Zero changes to the existing `asana_task_service` code.
