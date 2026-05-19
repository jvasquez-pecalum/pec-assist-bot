# n8n Email Intake Workflow — Implementation Plan

> **Goal:** Pipe inbound emails from `pec.assist@pecalum.com` Outlook inbox into the existing `email-task` FastAPI service, replacing the IMAP polling path that Microsoft 365 blocks via Basic Auth.
>
> **Approach:** "Route 1" — n8n's native Microsoft Outlook trigger node with delegated OAuth, polling every 1 minute, then POST to `/email/process`. No Entra app changes required.
>
> **Status when this plan was written:**
> - `email-task` service deployed on the VM, `/email/process` endpoint working with dedup (commits `2a25ba2`, `21351d8`, `bbba566`)
> - `email_requests` table in Supabase has RLS disabled (matches `processed_messages` pattern)
> - No producer wired up — service is invoked manually via `docker compose exec`

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│ NODE 1: Microsoft Outlook trigger                │
│   Operation:  "On New Email"                     │
│   Credential: pec.assist@pecalum.com OAuth       │
│   Folder:     Inbox                              │
│   Polling:    every 1 minute                     │
│   Output:     full Graph message object          │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ NODE 2: IF — skip loops / auto-replies           │
│   Skip if from = pec.assist@pecalum.com          │
│   Skip if subject starts with "Auto-Reply" /     │
│           "Out of Office" / "Undeliverable"      │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ NODE 3: Code — normalize payload                 │
│   Extract: subject, body (prefer text over HTML) │
│            from.name, from.address               │
│            internetMessageId (RFC822) for dedup  │
│   Truncate body to 50000 chars                   │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ NODE 4: HTTP Request — POST /email/process       │
│   URL:    http://email-task:8001/email/process   │
│   Header: X-API-Key: {{ $env.WEBHOOK_API_KEY }}  │
│   Body:   normalized JSON                        │
│   onError: continueErrorOutput                   │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ NODE 5: Microsoft Outlook — mark message as read │
│   Uses the Outlook message id from NODE 1        │
│   Only fires on the success branch of NODE 4     │
└──────────────────────────────────────────────────┘

Workflow settings:
  errorWorkflow:    gZxrCH09fh6NK7CU (PEC-Error-Handler)
  executionTimeout: 300s
  active:           false  ← user activates after review
```

---

## Prerequisites

### 1. n8n credential for pec.assist mailbox

- In n8n UI: **Credentials → New → Microsoft Outlook OAuth2 API**
- Click **Sign in with Microsoft**, sign in as `pec.assist@pecalum.com`
- Complete MFA if prompted (likely required — M365 default)
- Save credential — name it `pec-assist-outlook`
- n8n stores the refresh token (~90 day lifetime per Microsoft default)
- **If the pec.assist password is ever rotated, this credential will break** — re-sign-in required

### 2. `WEBHOOK_API_KEY` exposed to the n8n container

The HTTP node uses `{{ $env.WEBHOOK_API_KEY }}` to authenticate to the email service.

Edit `~/ai-initiative/docker-compose.yml` on the VM, in the `n8n:` service `environment:` block, add:

```yaml
  n8n:
    environment:
      # ... existing vars ...
      - WEBHOOK_API_KEY=${WEBHOOK_API_KEY}   # ← add this line
```

Then add the value to `~/ai-initiative/.env` (or wherever docker-compose loads from):

```bash
# Pull the actual value from email-task's .env
WEBHOOK_API_KEY=$(grep ^WEBHOOK_API_KEY= ~/ai-initiative/pec-assist-bot/src/email_task_service/.env | cut -d= -f2)
echo "WEBHOOK_API_KEY=$WEBHOOK_API_KEY" >> ~/ai-initiative/.env
```

Then restart n8n:

```bash
cd ~/ai-initiative
docker compose up -d n8n
```

Verify the env var is set inside the container:

```bash
docker compose exec n8n env | grep WEBHOOK_API_KEY
```

**Alternative if you'd rather not touch n8n compose:** create an n8n "Header Auth" credential storing the API key as a header (`X-API-Key: <value>`), and reference that credential in the HTTP Request node instead of `{{ $env.WEBHOOK_API_KEY }}`. Cleaner secrets management but adds one credential to maintain.

### 3. Verify email service is healthy

```bash
docker compose exec email-task python3 -c "
import urllib.request; print(urllib.request.urlopen('http://localhost:8001/email/health').read().decode())
"
```

Expected: JSON with `status: healthy`.

---

## Workflow JSON (for MCP creation)

If using `mcp__n8n-mcp-full__n8n_create_workflow`, the payload structure:

```json
{
  "name": "PEC-Email-Intake",
  "active": false,
  "settings": {
    "executionTimeout": 300,
    "errorWorkflow": "gZxrCH09fh6NK7CU",
    "executionOrder": "v1",
    "callerPolicy": "workflowsFromSameOwner"
  },
  "nodes": [
    {
      "id": "outlook-trigger",
      "name": "On New Email",
      "type": "n8n-nodes-base.microsoftOutlookTrigger",
      "typeVersion": 1,
      "position": [240, 0],
      "parameters": {
        "event": "messageReceived",
        "folderId": "inbox",
        "pollTimes": { "item": [{ "mode": "everyMinute" }] },
        "options": {
          "downloadAttachments": false
        }
      },
      "credentials": {
        "microsoftOutlookOAuth2Api": {
          "id": "<REPLACE_WITH_pec-assist-outlook_CRED_ID>",
          "name": "pec-assist-outlook"
        }
      }
    },
    {
      "id": "filter-loops",
      "name": "Skip Auto-Replies",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2.3,
      "position": [464, 0],
      "parameters": {
        "conditions": {
          "options": { "caseSensitive": false, "typeValidation": "strict", "version": 3 },
          "conditions": [
            {
              "leftValue": "={{ $json.from?.emailAddress?.address }}",
              "rightValue": "pec.assist@pecalum.com",
              "operator": { "type": "string", "operation": "notEquals" }
            },
            {
              "leftValue": "={{ $json.subject }}",
              "rightValue": "^(Auto-Reply|Out of Office|Undeliverable|Automatic reply)",
              "operator": { "type": "string", "operation": "notRegex" }
            }
          ],
          "combinator": "and"
        }
      }
    },
    {
      "id": "normalize",
      "name": "Normalize Payload",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [688, -96],
      "parameters": {
        "jsCode": "const msg = $input.first().json;\n\n// Prefer plain text body; fall back to bodyPreview; strip HTML if needed\nlet body = '';\nif (msg.body?.contentType === 'text') {\n  body = msg.body.content || '';\n} else if (msg.body?.content) {\n  // crude HTML strip — keeps text content, drops tags\n  body = msg.body.content.replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ').trim();\n} else {\n  body = msg.bodyPreview || '';\n}\n\n// Truncate to 50k chars to satisfy ProcessRequest body max_length\nif (body.length > 50000) {\n  body = body.substring(0, 50000);\n}\n\nreturn [{\n  json: {\n    subject: (msg.subject || '(no subject)').substring(0, 500),\n    body: body,\n    from_name: (msg.from?.emailAddress?.name || '').substring(0, 200),\n    from_email: msg.from?.emailAddress?.address || 'unknown@unknown',\n    message_id: msg.internetMessageId || msg.id,\n    _outlook_id: msg.id  // keep for mark-as-read step\n  }\n}];"
      }
    },
    {
      "id": "post-process",
      "name": "POST /email/process",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [912, -96],
      "parameters": {
        "method": "POST",
        "url": "http://email-task:8001/email/process",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            { "name": "Content-Type", "value": "application/json" },
            { "name": "X-API-Key", "value": "={{ $env.WEBHOOK_API_KEY }}" }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={{ { subject: $json.subject, body: $json.body, from_name: $json.from_name, from_email: $json.from_email, message_id: $json.message_id } }}",
        "options": {
          "timeout": 60000
        }
      },
      "onError": "continueErrorOutput"
    },
    {
      "id": "mark-read",
      "name": "Mark Email Read",
      "type": "n8n-nodes-base.microsoftOutlook",
      "typeVersion": 2,
      "position": [1136, -96],
      "parameters": {
        "resource": "message",
        "operation": "update",
        "messageId": "={{ $('Normalize Payload').item.json._outlook_id }}",
        "updateFields": {
          "isRead": true
        }
      },
      "credentials": {
        "microsoftOutlookOAuth2Api": {
          "id": "<REPLACE_WITH_pec-assist-outlook_CRED_ID>",
          "name": "pec-assist-outlook"
        }
      }
    }
  ],
  "connections": {
    "On New Email": {
      "main": [[{ "node": "Skip Auto-Replies", "type": "main", "index": 0 }]]
    },
    "Skip Auto-Replies": {
      "main": [
        [{ "node": "Normalize Payload", "type": "main", "index": 0 }],
        []
      ]
    },
    "Normalize Payload": {
      "main": [[{ "node": "POST /email/process", "type": "main", "index": 0 }]]
    },
    "POST /email/process": {
      "main": [
        [{ "node": "Mark Email Read", "type": "main", "index": 0 }],
        []
      ]
    }
  }
}
```

**Note on credential ID:** After creating the OAuth credential in n8n UI, get its ID from the credential URL (e.g., `https://pecn8n.westus2.cloudapp.azure.com:9443/credential/abc123`). Substitute `<REPLACE_WITH_pec-assist-outlook_CRED_ID>` in both Outlook nodes.

---

## Execution steps

### 1. Set up the n8n OAuth credential (manual, n8n UI)

1. Open `https://pecn8n.westus2.cloudapp.azure.com:9443`
2. **Credentials → New → Microsoft Outlook OAuth2 API**
3. Click **Sign in with Microsoft** → sign in as `pec.assist@pecalum.com` → complete MFA
4. Name credential `pec-assist-outlook`, save
5. Copy the credential ID from the URL — needed for workflow JSON

### 2. Expose `WEBHOOK_API_KEY` to the n8n container (VM)

```bash
# Pull the value from email-task .env
KEY=$(grep ^WEBHOOK_API_KEY= ~/ai-initiative/pec-assist-bot/src/email_task_service/.env | cut -d= -f2)

# Add to ~/ai-initiative/.env
echo "WEBHOOK_API_KEY=$KEY" >> ~/ai-initiative/.env

# Edit docker-compose.yml — add to n8n environment:
#   - WEBHOOK_API_KEY=${WEBHOOK_API_KEY}
nano ~/ai-initiative/docker-compose.yml

# Restart n8n to pick up the new env var
cd ~/ai-initiative
docker compose up -d n8n

# Verify
docker compose exec n8n env | grep WEBHOOK_API_KEY
```

### 3. Create the workflow

Either:
- **Manually in the n8n UI** — recreate the 5 nodes per the JSON above
- **Via MCP** — call `mcp__n8n-mcp-full__n8n_create_workflow` with the JSON payload above, substituting `<REPLACE_WITH_pec-assist-outlook_CRED_ID>` with the actual ID

Workflow should be created with `active: false`.

### 4. Manual test (workflow still inactive)

1. In n8n UI, open the workflow
2. Send a test email from your personal account to `pec.assist@pecalum.com` with subject `n8n smoke test`
3. Click **"Execute Workflow"** at the top — runs once, fetches up to 10 recent messages from inbox
4. Verify each node turns green and check the output of each:
   - **On New Email** — should output the test email object
   - **Skip Auto-Replies** — should route to the true branch (your email isn't an auto-reply)
   - **Normalize Payload** — output JSON has `subject`, `body`, `from_email`, `message_id`
   - **POST /email/process** — HTTP 200, response includes `correlation_id`, `classification`, `asana_response`
   - **Mark Email Read** — success, message marked read in Outlook
5. Confirm in Asana: ticket created with friendly ID-NN
6. Confirm in your inbox: branded HTML auto-reply received
7. Check Outlook for `pec.assist@pecalum.com`: original test email is now read

### 5. Activate

In n8n UI, toggle **Active** on the workflow. Now polling every 1 min.

### 6. End-to-end smoke test (active)

Send another test email. Wait ~90 seconds. Should see:
- Asana ticket in project `1213992435706056`
- Auto-reply email in your inbox
- Original email marked as read in `pec.assist@pecalum.com` inbox

---

## Rollback

If anything misbehaves:

```bash
# Deactivate workflow via n8n UI (toggle Active off)
# OR via MCP:
#   mcp__n8n-mcp-full__n8n_update_partial_workflow with operation deactivate
```

This stops polling immediately. Nothing else needs to be reverted — no code or compose changes affect `asana-task` or `email-task` directly.

---

## Known limitations / future work

1. **Refresh token expiry** — Microsoft default is ~90 days of inactivity. With 1-min polling this won't trigger, but if you ever pause the workflow for >90 days, the credential will need re-auth.
2. **Single-user dependency** — workflow auth is tied to the `pec.assist@pecalum.com` user account. If that account is disabled or password rotated, intake breaks. Future: migrate to Route 3 (app-only Graph subscription) to remove user dependency.
3. **No attachment processing** — Node 1 has `downloadAttachments: false`. Body text only. If users send screenshots of errors, the LLM classifier only sees the message text.
4. **HTML strip is crude** — the regex in Normalize Payload removes tags but doesn't decode entities. Most emails work; complex HTML may leave artifacts in classification text. Upgrade path: use a real HTML-to-text library if classification quality suffers.
5. **No backoff on failure** — `executionTimeout: 300s` caps a single run, but on repeated POST failures the workflow keeps trying every minute. The email-task service has dedup so duplicates don't create duplicate tickets; the redundant LLM calls are the only cost.
6. **Loop prevention is heuristic** — relies on sender address + subject regex. Bounces from misconfigured external mail servers might slip through. Add header-based filtering (`Auto-Submitted: auto-replied` per RFC 3834) if needed.

---

## Validation checklist for the next session

- [ ] OAuth credential created and named `pec-assist-outlook`
- [ ] Credential ID copied for workflow JSON
- [ ] `WEBHOOK_API_KEY` env var verified inside `n8n` container
- [ ] Workflow created inactive with all 5 nodes
- [ ] Manual test execution: all nodes green
- [ ] Asana ticket created on manual test
- [ ] Auto-reply received on manual test
- [ ] Email marked as read in pec.assist inbox
- [ ] Workflow activated
- [ ] Active-mode end-to-end test passes
