# PEC Assist - Teams Bot PoC

A proof-of-concept AI-powered IT support assistant for Microsoft Teams using n8n workflow automation.

## Overview

**Workflow**: PoC-Teams-Webhooks  
**Endpoint**: `/webhook/teams-events`  
**Status**: Active (with known limitations)

## Features

### ✅ Working Features

1. **Teams Webhook Integration**
   - Receives messages via Microsoft Graph change notifications
   - Validation token handling for subscription setup
   - Chat ID and message ID extraction from resource URLs

2. **Message Fetching**
   - Retrieves full message details from Microsoft Graph API
   - OAuth authentication with Microsoft account

3. **Bot Detection (Loop Prevention)**
   - Checks if message contains auto-reply text to prevent infinite loops
   - Successfully prevents double-reply scenarios

4. **AI-Powered Intent Classification**
   - OpenAI GPT-4o-mini integration
   - Classifies messages into: password_reset, software_issue, hardware_issue, access_request, general_inquiry
   - Determines urgency level: low, medium, high, critical
   - Summarizes the request
   - Identifies if a task should be created

5. **Auto-Reply System**
   - Sends acknowledgment message to Teams chat
   - Professional automated response

### ⚠️ Known Limitations

1. **Duplicate Message Handling** (Supabase integration failed)
   - **Issue**: Microsoft Graph sends duplicate webhooks for the same message
   - **Attempted Solution**: Supabase `processed_messages` table for deduplication
   - **Problem**: Credential type mismatch between Supabase nodes (supabaseApi) and HTTP Request nodes (httpHeaderAuth)
   - **Current Status**: Deduplication removed - workflow processes duplicate webhooks
   - **Impact**: May send multiple auto-replies for the same message (mitigated by bot detection)

## Technical Architecture

### Workflow Flow

```
Webhook → Validation? → Parse Resource → Has Valid Data? → Fetch Message
                                                         ↓
                         Send Reply ← Parse LLM JSON ← LLM Analysis ← Is From Bot?
                                ↑                              ↓
                                └──────── Create Asana Task? ←──┘ (if requires_task=true)
```

### Node Details

| Node | Type | Purpose |
|------|------|---------|
| Webhook | Webhook | Receives POST from Microsoft Graph |
| If | If | Checks for validationToken (subscription setup) |
| Respond to Webhook | Webhook Response | Returns validation token |
| Parse Resource | Code | Extracts chatId/messageId from notification |
| Has Valid Data? | If | Validates extracted IDs |
| Fetch Message | HTTP Request | GET message from Graph API |
| Is From Bot? | If | Prevents reply loops |
| OpenAI Chat Model | LLM | GPT-4o-mini model |
| LLM Analysis | AI Agent | Classifies intent & urgency |
| Parse LLM JSON | Code | Extracts clean JSON from LLM output |
| Create Asana Task? | If | Routes to Asana if `requires_task=true` |
| Asana HTTP Request | HTTP Request | POST to FastAPI `/tasks` endpoint |
| Send Reply | HTTP Request | POST auto-reply to Teams |

### Credentials

| Credential | Type | Purpose |
|------------|------|---------|
| Microsoft OAuth | microsoftOAuth2Api | Graph API access |
| OpenAI | openAiApi | LLM classification |

## Setup Instructions

### 1. Microsoft Graph Subscription

Create a subscription for chat messages:

```bash
POST https://graph.microsoft.com/v1.0/subscriptions
Content-Type: application/json

{
  "changeType": "created",
  "notificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",
  "resource": "/chats/getAllMessages",
  "expirationDateTime": "2026-04-08T20:00:00+00:00",
  "clientState": "your-secret-client-state"
}
```

### 2. Required Microsoft Graph Permissions

Ensure your app registration has these permissions:
- `Chat.Read.All`
- `ChatMessage.Send`
- `User.Read`

### 3. OpenAI Configuration

- Model: `gpt-4o-mini`
- Temperature: `0.1` (low for consistent classification)
- System prompt includes PEC Aluminum IT support context

## LLM Classification Prompt

```
You are an IT support classifier for PEC Aluminum. Analyze the message and classify it EXACTLY as follows:

USER MESSAGE: {{ $json.body.content }}
SENDER: {{ $json.from.user.displayName }}

CLASSIFICATION RULES:
1. password_reset: Forgotten passwords, can't login, password expired, account locked
2. software_issue: App crashes, errors, bugs, software not working
3. hardware_issue: Computer won't start, broken screen, mouse/keyboard not working
4. access_request: Need permissions, access to folders, new software license
5. general_inquiry: Questions about policies, how-to questions

URGENCY RULES:
- critical: User cannot work at all
- high: Significant impact (meeting in <1 hour, urgent deadline)
- medium: Work impacted but workaround exists
- low: General questions, no immediate impact

Respond with ONLY this JSON format (no markdown):
{"intent": "...", "urgency": "low|medium|high|critical", "summary": "...", "requires_task": true|false, "response_tone": "professional|friendly|urgent"}
```

## Asana Task Integration

When `requires_task: true` from LLM classification, n8n calls the FastAPI Asana Task Service to create a tracked task.

### Architecture

```
Parse LLM JSON → requires_task=true?
                      ↓ Yes
              HTTP Request Node
                      ↓
         POST /tasks (FastAPI Service)
                      ↓
              Asana Task Created
```

### FastAPI Service

Located in `asana_task_service/`:
- **Endpoint**: `POST /tasks` - Creates Asana tasks
- **Features**: Urgency-based due dates, auto-tagging, rich descriptions
- **Health Check**: `GET /health`

See `asana_task_service/README.md` for setup and n8n configuration.

## Future Improvements

1. **Persistent Deduplication**
   - Create separate HTTP Header Auth credential for Supabase REST API
   - Or use Supabase nodes exclusively without HTTP Request nodes for Supabase operations
   - Implement proper PostgreSQL functions for atomic check-and-insert

2. **Enhanced Task Integration**
   - ~Create SharePoint list items or Planner tasks for `requires_task: true`~ ✅ Asana integration complete
   - Add Microsoft Planner as alternative task backend
   - Send notifications to appropriate IT support channels

3. **Enhanced Responses**
   - Intent-specific response templates
   - Knowledge base integration for self-service
   - Follow-up question handling

4. **Monitoring & Analytics**
   - Track intent distribution
   - Response time metrics
   - User satisfaction ratings
   - Asana task completion tracking

## Troubleshooting

### Duplicate Replies
The current implementation may send multiple replies for the same message due to Microsoft Graph sending duplicate webhooks. The bot detection helps mitigate this but doesn't eliminate it entirely.

### Graph API Errors
- Ensure OAuth token hasn't expired
- Verify app registration has required permissions
- Check subscription hasn't expired

### LLM Parsing Errors
The Parse LLM JSON Code node handles malformed responses with sensible defaults.
