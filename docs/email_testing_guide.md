# Email Task Service — Testing Guide

> **Generated:** 2026-05-07  
> **Service:** `src/email_task_service/` (FastAPI on port 8001)

---

## 1. Architecture Overview

The email functionality is **queue-driven** (no background IMAP polling). An external orchestrator (e.g. n8n) polls the inbox and pushes emails to this service via HTTP POST.

```
Email User
    ↓
IMAP Inbox (Outlook/Exchange)  ← polled by n8n
    ↓
n8n Email Trigger (IMAP)
    ↓
POST /email/simulate  →  Email Task Service (FastAPI:8001)
    ├─ OpenAI GPT-4o-mini Classifier
    ├─ Asana Task Client → asana-task:8000
    ├─ SMTP Email Sender (auto-reply)
    └─ Supabase Config Manager (toggle state)
```

### Key Components

| Component | Purpose | Real API / Library |
|-----------|---------|-------------------|
| **OpenAIClassifier** | Classifies email intent & urgency | `https://api.openai.com/v1/chat/completions` (gpt-4o-mini) |
| **AsanaTaskClient** | Creates tickets in Asana | Calls internal `asana-task` service (port 8000), which then hits `https://app.asana.com/api/1.0/tasks` |
| **SMTPEmailSender** | Sends auto-reply emails | `aiosmtplib` → `smtp.office365.com:587` (STARTTLS) |
| **SupabaseConfigManager** | Stores channel toggle + email request log | Supabase REST API (`/rest/v1/channel_config`, `/rest/v1/email_requests`) |
| **IMAPClient** | Legacy direct IMAP polling (unused in queue mode) | `imap-tools` → `outlook.office365.com:993` |
| **GraphEmailClient** | Alternative to IMAP via Microsoft Graph | `https://graph.microsoft.com/v1.0/users/{email}/messages` |

---

## 2. API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | None | Service info & endpoint list |
| `/email/health` | GET | None | Health check + active channel |
| `/email/config` | GET | None | Current toggle state (teams vs email) |
| `/email/config/toggle` | POST | `X-API-Key` | Switch active channel |
| `/email/logs` | GET | None | Last N log lines (`?lines=100&fmt=text`) |
| `/email/diagnostics` | GET | None | Full diagnostic snapshot |
| `/email/simulate` | POST | `X-API-Key` | **Main testing endpoint** — run any email through the full pipeline |

### The Asana Task Service (Dependency)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | None | Health check |
| `/tasks` | POST | `X-API-Key` | Create Asana task |

---

## 3. Environment Configuration

Copy `src/email_task_service/.env.example` to `.env` and fill in:

```bash
cd src/email_task_service
cp .env.example .env
```

### Required Variables for Real Testing

```env
# 1. OpenAI (for classification)
OPENAI_API_KEY=sk-...

# 2. SMTP / IMAP (Office 365 app password)
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
IMAP_HOST=outlook.office365.com
IMAP_PORT=993
IMAP_USER=pec.assist@pecalum.com
IMAP_PASSWORD=your_app_password
SENDER_ADDRESS=pec.assist@pecalum.com

# 3. Asana Task Service
ASANA_SERVICE_URL=http://localhost:8000          # or http://asana-task:8000 in Docker
ASANA_SERVICE_API_KEY=change-me-same-as-asana-service-key

# 4. Supabase (for channel toggle + deduplication)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# 5. Security
WEBHOOK_API_KEY=change-me-generate-a-strong-secret
```

### Testing-Specific Toggles (set to `true` for safe local testing)

| Variable | Effect when `true` |
|----------|-------------------|
| `MOCK_OPENAI=true` | Returns fake classification (no OpenAI API call) |
| `MOCK_ASANA=true` | Returns fake task ID (no Asana API call) |
| `MOCK_SMTP=true` | Fake "sent" reply (no real email sent) |
| `SKIP_CHANNEL_CHECK=true` | Bypass Supabase channel check (useful if Supabase is unavailable) |
| `TEST_MODE=true` | General test mode flag |

---

## 4. Setup Steps to Test

### Step 1: Install Dependencies

```bash
cd src/email_task_service
# Use the project virtual environment
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Step 2: Start the Asana Task Service (Required Dependency)

The email service depends on the Asana service being reachable.

```bash
# Terminal 1 — Asana service (port 8000)
cd src/asana_task_service
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 8000
```

> The Asana service itself needs `ASANA_TOKEN` and `ASANA_PROJECT_ID` in its `.env` to create real tasks. If those are missing, it will return 503.

### Step 3: Start the Email Task Service

```bash
# Terminal 2 — Email service (port 8001)
cd src/email_task_service
..\..\.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 8001
```

### Step 4: Verify Health

```bash
curl http://localhost:8001/email/health
curl http://localhost:8000/health
```

---

## 5. Testing Scenarios

### Scenario A: Full Integration Test (All Real APIs)

Ensure your `.env` has:
```env
MOCK_OPENAI=false
MOCK_ASANA=false
MOCK_SMTP=false
SKIP_CHANNEL_CHECK=false
```

Run the simulate endpoint:

```bash
curl -X POST http://localhost:8001/email/simulate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $WEBHOOK_API_KEY" \
  -d '{
    "subject": "My monitor is broken",
    "body": "The screen is completely black since this morning.",
    "from_name": "Alice Smith",
    "from_email": "alice@pecalum.com",
    "message_id": "test-msg-001"
  }'
```

**Expected flow:**
1. OpenAI classifies intent → `hardware_issue`, urgency → `high/medium`
2. Asana task created in your project
3. Auto-reply email sent to `alice@pecalum.com`
4. Record saved to Supabase `email_requests` table

### Scenario B: Safe Local Test (All Mocks)

Edit `.env`:
```env
MOCK_OPENAI=true
MOCK_ASANA=true
MOCK_SMTP=true
SKIP_CHANNEL_CHECK=true
```

Restart the service, then run the same `curl` above.  
**Result:** Classification, Asana response, and SMTP are all mocked. Nothing external is called.

### Scenario C: Run Pytest Suites

```bash
cd src/email_task_service

# 1. Unit tests (pure logic, no server needed)
..\..\.venv\Scripts\pytest.exe tests/test_services.py -v

# 2. Integration tests (uses test client, mocked externals)
$env:TEST_MODE="true"; $env:MOCK_OPENAI="true"; $env:MOCK_SMTP="true"; $env:MOCK_ASANA="true";
..\..\.venv\Scripts\pytest.exe -m integration -v

# 3. Real service tests (hits actual APIs — costs $ / sends email)
..\..\.venv\Scripts\pytest.exe -m real_services -v
```

### Scenario D: Test Individual Components

**Test OpenAI classification only:**
```bash
curl -X POST http://localhost:8001/email/simulate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $WEBHOOK_API_KEY" \
  -d '{"subject":"Forgot password","body":"Cant log in","from_name":"Bob","from_email":"bob@test.com","message_id":"test-002"}'
```

**Test SMTP only (skip Asana):**
Set `MOCK_ASANA=true` in `.env` and run simulate with a real recipient email.

**Test Asana only (skip OpenAI + SMTP):**
Set `MOCK_OPENAI=true MOCK_SMTP=true` in `.env`.

---

## 6. Database Setup (Supabase)

Before toggling channels or using deduplication, run this migration in the Supabase SQL Editor:

```sql
CREATE TABLE IF NOT EXISTS channel_config (
    channel_type VARCHAR(20) PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO channel_config (channel_type, is_active, updated_at)
VALUES
    ('teams', true, NOW()),
    ('email', false, NOW())
ON CONFLICT (channel_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS email_requests (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(500) UNIQUE NOT NULL,
    from_email VARCHAR(255),
    from_name VARCHAR(255),
    subject TEXT,
    intent VARCHAR(50),
    urgency VARCHAR(20),
    summary TEXT,
    requires_task BOOLEAN,
    asana_task_id VARCHAR(50),
    asana_task_url TEXT,
    replied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. Diagnostics & Troubleshooting

### Quick Diagnostic Curl

```bash
curl http://localhost:8001/email/diagnostics | python -m json.tool
```

Checks:
- Which env vars are set
- Supabase connectivity
- Asana service reachability
- SMTP config presence
- Last processed emails & errors

### View Logs

```bash
# JSON format (default)
curl "http://localhost:8001/email/logs?lines=50"

# Plain text
curl "http://localhost:email/logs?lines=50&fmt=text"
```

### Common Issues

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` | Pass correct `X-API-Key` header |
| `Classification failed` | Check `OPENAI_API_KEY` is set and valid |
| `Asana task creation failed` | Verify Asana service is running on port 8000 and has `ASANA_TOKEN` |
| `Auto-reply failed` | Verify `IMAP_PASSWORD` (used for SMTP auth) and that the account allows SMTP |
| `Channel inactive` | Either toggle to `email` via `/email/config/toggle` or set `SKIP_CHANNEL_CHECK=true` |
| `Supabase connection failed` | Check `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`, or enable `SKIP_CHANNEL_CHECK` |

---

## 8. File Map

```
src/email_task_service/
├── main.py              # FastAPI app, endpoints, auth
├── services.py          # Business logic: classifier, SMTP, Asana client, Supabase manager
├── models.py            # Pydantic request/response models
├── .env                 # Your credentials (gitignored)
├── .env.example         # Template
├── requirements.txt     # Python deps
├── Dockerfile           # Container build
├── migrations/
│   └── 001_channel_config_and_email_requests.sql
└── tests/
    ├── conftest.py      # Auto-loads .env for tests
    ├── test_services.py # Unit tests
    ├── test_integration.py   # Mocked integration tests
    └── test_real_services.py # Live API tests
```

---

## 9. One-Command Summary

```bash
# 1. Start Asana service (port 8000)
cd src/asana_task_service && uvicorn main:app --port 8000

# 2. Start Email service (port 8001) — new terminal
cd src/email_task_service && uvicorn main:app --port 8001

# 3. Run a test email — new terminal
curl -X POST http://localhost:8001/email/simulate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_WEBHOOK_API_KEY" \
  -d '{"subject":"Test","body":"Hello","from_name":"Tester","from_email":"test@example.com","message_id":"t1"}'
```
