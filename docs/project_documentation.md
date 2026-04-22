# PEC Teams AI Bot - Project Documentation

> **Last Updated:** April 21, 2026  
> **Status:** Production Ready

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Infrastructure & Services](#infrastructure--services)
4. [n8n Workflows](#n8n-workflows)
5. [Database Schema](#database-schema)
6. [Notification System](#notification-system)
7. [Configuration](#configuration)
8. [Troubleshooting History](#troubleshooting-history)
9. [How to Extend](#how-to-extend)

---

## Project Overview

The **PEC Teams AI Bot** (PEC Assist) is an AI-powered IT support assistant that:
- Monitors Microsoft Teams messages via webhook
- Classifies intent and urgency using OpenAI GPT-4o mini
- Creates Asana tasks for support requests
- Sends contextual replies to users
- Polls Asana for updates and notifies users via Teams DM

### Key Features
- 🤖 AI-powered message classification (9 intent categories)
- 🎫 Automatic Asana task creation with urgency-based formatting
- 📊 Priority detection (Critical/High/Medium/Low)
- 🔔 8 types of Teams DM notifications for task updates
- 🧠 Conversation memory per chat session
- 🦾 Atomic claim system to prevent duplicate processing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERACTION                                │
│  Microsoft Teams Message → PEC-Assist Bot (Azure Bot Framework)             │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              N8N WORKFLOWS                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   PEC-Intake    │→ │ PEC-Classifier  │→ │      PEC-Responder          │  │
│  │   (Webhook)     │  │  (AI + Asana)   │  │   (Teams Reply)             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
│           │                    │                        │                   │
│           │                    ▼                        │                   │
│           │           ┌─────────────────┐               │                   │
│           │           │  Asana-Poller   │───────────────┘                   │
│           │           │  (Every 5 min)  │                                   │
│           │           └─────────────────┘                                   │
│           │                    │                                            │
│           ▼                    ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         SUPABASE DATABASE                            │   │
│  │  processed_messages | error_log                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         EXTERNAL SERVICES                            │   │
│  │  Microsoft Graph API  |  Asana API  |  OpenAI API                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Infrastructure & Services

### Docker Services (docker-compose.yml)

```yaml
Services:
  n8n:           Workflow automation platform (port 5678)
  caddy:         Reverse proxy (ports 443, 8080, 8081, 9443)
  asana-task:    FastAPI service for Asana integration (port 8000)
  frontend:      Web UI (port 8080)
  iic:           Streamlit interface (port 8081)
```

### Caddy Configuration

**Port 9443** - API Gateway:
```
pecn8n.westus2.cloudapp.azure.com:9443 {
    handle_path /asana/* {
        reverse_proxy asana-task:8000
    }
    reverse_proxy n8n:5678
}
```

### Asana FastAPI Service

**Endpoint:** `POST /asana/tasks`

**Features:**
- Creates tasks with emoji urgency prefix (🔴🟠🟡🟢)
- Auto-calculates due dates based on urgency
- Formats rich markdown notes
- Returns task_id and task_url

**Environment Variables:**
- `ASANA_TOKEN` - Personal Access Token
- `ASANA_PROJECT_ID` - IT Support project
- `ASANA_WORKSPACE_ID` - pecalum.com workspace

---

## n8n Workflows

### 1. PEC-Intake (3CpsxZLMLHAXPnFz)

**Trigger:** Webhook from Microsoft Teams

**Flow:**
```
Webhook → Parse Resource → Atomic Claim → Execute PEC-Classifier
```

**Key Features:**
- Validates Teams webhook payload
- Parses chatId and messageId from resource path
- Atomic claim via Supabase INSERT with conflict resolution
- Prevents duplicate processing

**Webhook URL:**
```
https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events
```

---

### 2. PEC-Classifier (zHSGTpk1RJGPD9MY)

**Trigger:** Called by PEC-Intake

**Flow:**
```
Fetch Message → Strip HTML → LLM Analysis → Update Classification
                                                    ↓
                              Requires Task? → YES → Build Asana Payload
                                                    ↓
                                        Create Asana Task
                                                    ↓
                              Build Responder Data → Execute PEC-Responder
                                                    ↓
                                        Update Asana Reference (Supabase)
```

**AI Classification:**

| Intent Category | Description |
|-----------------|-------------|
| password_reset | Forgotten passwords, account lockouts |
| software_issue | App crashes, bugs, installation failures |
| hardware_issue | Broken screens, peripherals, printer problems |
| access_request | Permissions, folder access, VPN |
| data_engineering | ETL failures, data pipelines |
| business_reports | Report generation, scheduling |
| business_intelligence | Dashboard issues, KPI queries |
| ai_initiatives | AI/ML requests, automation |
| general_inquiry | Policy questions, how-to, greetings |

**Urgency Levels:**
- 🔴 **Critical** - Cannot work at all (ETA: immediate)
- 🟠 **High** - Significant impact, imminent deadline (ETA: 30 min)
- 🟡 **Medium** - Work impacted, workaround exists (ETA: 1 hour)
- 🟢 **Low** - General question (ETA: 2 hours)

**Asana Task Creation:**
- POST to `https://pecn8n.westus2.cloudapp.azure.com:9443/asana/tasks`
- Task name format: `[🟡 Urgency] Intent - User Name`
- Auto-due date: Critical (+1 day), High (+3 days), Medium (+7 days), Low (+14 days)

---

### 3. PEC-Responder (HJ9NigH9QU1bORGE)

**Trigger:** Called by PEC-Classifier

**Flow:**
```
Build Reply Message → Send Reply (Teams) → Update Status: Replied
```

**Reply Format:**
```
[AI-generated response based on intent/urgency]

🎫 Ticket reference: #[last 6 digits of message ID]
(Automated response from PEC Assist)
```

---

### 4. Asana-Poller (bi8LtU1JETJwjZQq)

**Trigger:** Schedule (Every 5 minutes)

**Flow:**
```
Schedule Trigger → Fetch Asana Tasks → Check Tasks Changed
                                              ↓
                                   Find User in Supabase
                                              ↓
                                   Format Notification
                                              ↓
                                   Send Teams DM → Update Section in Supabase
```

**API Call:**
```
GET https://app.asana.com/api/1.0/projects/1213992435706056/tasks
?opt_fields=gid,name,assignee,completed,modified_at,due_on,notes,subtasks,memberships.section.name
&modified_since=[10 minutes ago]
```

---

## Notification System

### 8 Notification Types (Priority Order)

| Priority | Icon | Type | Trigger Condition | Message Preview |
|----------|------|------|-------------------|-----------------|
| 1 | 🔄 | **Reopened** | `wasCompleted && !isNowCompleted` | Ticket reopened for additional work |
| 2 | ✅ | **Resolved** | `task.completed` | Ticket has been resolved |
| 3 | 📋 | **Assigned** | First time assigned | Assigned to someone |
| 4 | 📅 | **Due Date Changed** | `dueDate !== previousDueDate` | Target date is now [date] |
| 5 | 💬 | **New Comment** | `notes.length increased` | New Comment: "[preview]" |
| 6 | 📝 | **Subtasks Added** | `subtaskCount increased` | Broken down into [N] steps |
| 7 | 🔧 | **Work Started** | Section → "In Progress" | Now being worked on |
| 8 | 👀 | **Under Review** | Section → "Review" | Being reviewed |

### Notification Logic (Pseudocode)
```javascript
if (wasReopened) → 🔄 Reopened
else if (completed) → ✅ Resolved
else if (firstAssigned) → 📋 Assigned
else if (dueDateChanged) → 📅 Due Date
else if (newComment) → 💬 Comment
else if (subtasksAdded) → 📝 Subtasks
else if (section → In Progress) → 🔧 Work Started
else if (section → Review) → 👀 Under Review
```

---

## Database Schema

### Table: `processed_messages`

| Column | Type | Description |
|--------|------|-------------|
| id | bigint | Primary key |
| message_id | text | Teams message ID |
| chat_id | text | Teams chat/conversation ID |
| intent | text | AI-classified intent |
| urgency | text | critical/high/medium/low |
| summary | text | AI-generated summary |
| requires_task | boolean | Whether Asana task created |
| response_tone | text | urgent/professional/friendly |
| status | text | processing/classified/replied/completed |
| sender_name | text | Display name of sender |
| sender_id | text | AAD user ID |
| message_content | text | Original message (optional) |
| classified_at | timestamp | When classified |
| replied_at | timestamp | When reply sent |
| created_at | timestamp | Record creation |
| processed_at | timestamp | When processing started |
| **asana_task_id** | text | Asana task GID |
| **asana_task_url** | text | Asana permalink |
| **asana_task_section** | text | Current board column |
| **asana_task_due_date** | date | Due date |
| **asana_task_notes** | text | Cached notes (for change detection) |
| **asana_subtask_count** | integer | Number of subtasks |

### Table: `error_log`

| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| workflow | text | Workflow name |
| node_name | text | Node that failed |
| message_id | text | Related message (if any) |
| error_message | text | Error description |
| payload | jsonb | Full error context |
| created_at | timestamp | When error occurred |

---

## Configuration

### Environment Variables

Create `.env` file:

```bash
# Asana
ASANA_TOKEN=your_asana_token_here
ASANA_PROJECT_ID=1213992435706056
ASANA_WORKSPACE_ID=1199594988171821

# Supabase
SUPABASE_URL=https://qreudqsajkthyrtsvbkn.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# OpenAI
OPENAI_API_KEY=sk-...

# Microsoft (configured in n8n UI)
# - OAuth2 for Graph API
# - Bot Framework credentials
```

### n8n Credentials

| Credential | Type | Used In |
|------------|------|---------|
| PEC Assist | Microsoft OAuth2 | Fetch Message, Send Reply, Send Teams DM |
| Supabase account | API Key | All Supabase nodes |
| OpenAi account | API Key | LLM Analysis |

---

## Troubleshooting History

### Issue 1: Asana Webhook 500 Errors
**Problem:** Asana webhooks failed handshake (500 errors)
**Solution:** Abandoned webhook approach, implemented polling instead
**Status:** ✅ Resolved

### Issue 2: PEC-Responder 405 Error
**Problem:** Double execution of PEC-Responder (connection loop)
**Root Cause:** "Update Asana Reference" → "Execute PEC-Responder" created duplicate run
**Fix:** Removed connection from Update Asana Reference to Execute PEC-Responder
**Status:** ✅ Resolved

### Issue 3: JSON Body with Newlines
**Problem:** Teams API rejected messages with newlines in JSON body
**Error:** `JSON parameter needs to be valid JSON`
**Fix:** Changed to keypair body format with proper escaping
**Status:** ✅ Resolved

### Issue 4: Assignee Detection
**Problem:** Asana returns assignee as `{gid, resource_type}` without name/email
**Fix:** Check for `task.assignee.gid` existence instead of name field
**Status:** ✅ Resolved

### Issue 5: Content-Type Header
**Problem:** Teams API required explicit Content-Type for write requests
**Fix:** Used keypair body format which automatically sets headers
**Status:** ✅ Resolved

---

## How to Extend

### Adding a New Notification Type

1. **Update `Check Tasks Changed` node** to extract new field:
```javascript
return {
  json: {
    // existing fields...
    newField: task.new_api_field
  }
};
```

2. **Add column to Supabase**:
```sql
ALTER TABLE processed_messages ADD COLUMN new_field TYPE;
```

3. **Update `Format Notification` node**:
```javascript
if (newCondition) {
  message = '🔔 **New Type** Your request...';
  shouldNotify = true;
}
```

4. **Update `Update Section in Supabase` node** to persist new field

5. **Update PEC-Classifier** to initialize field for new tasks

### Adding New Intent Category

1. **Update LLM Analysis system message** in PEC-Classifier:
```
- new_intent — Description of when to use it
```

2. **Update Asana Payload builder** (if different handling needed)

3. **Test with sample messages**

### Changing Polling Frequency

Edit `Schedule Trigger` in Asana-Poller:
```javascript
{
  "rule": {
    "interval": [{
      "field": "minutes",
      "minutesInterval": 5  // Change this
    }]
  }
}
```

### Adding Slack Integration

1. Create new workflow: `PEC-Slack-Responder`
2. Clone PEC-Responder structure
3. Change HTTP node to POST to Slack webhook
4. Update PEC-Classifier to call both responders

---

## API Endpoints

### Asana Service

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/asana/tasks` | Create new task |
| GET | `/asana/health` | Health check |

### n8n Webhooks

| Method | Endpoint | Workflow |
|--------|----------|----------|
| POST | `/webhook/teams-events` | PEC-Intake |

### Microsoft Graph

| Method | Endpoint | Used For |
|--------|----------|----------|
| GET | `/v1.0/me/chats/{id}/messages/{id}` | Fetch message |
| POST | `/v1.0/me/chats/{id}/messages` | Send reply/DM |

---

## Monitoring

### Check Workflow Executions
```bash
# List recent executions
curl "http://localhost:5678/api/v1/executions?limit=10" \
  -H "X-N8N-API-KEY: $N8N_API_KEY"
```

### Check Supabase Records
```sql
-- Recent messages
SELECT message_id, intent, urgency, asana_task_id, status, created_at
FROM processed_messages
ORDER BY created_at DESC
LIMIT 10;

-- Error log
SELECT workflow, node_name, error_message, created_at
FROM error_log
ORDER BY created_at DESC
LIMIT 10;
```

### Check Asana Tasks
Visit: https://app.asana.com/0/1213992435706056/list

---

## Team Contacts

- **Primary Developer:** Julio Vasquez (jvasquez@pecalum.com)
- **Infrastructure:** Azure VM (pecn8n.westus2.cloudapp.azure.com)
- **Asana Workspace:** pecalum.com

---

## License

Internal use only - Paramount Extrusions Company (PEC)

---

*Generated by Kimi Code CLI on April 9, 2026*
