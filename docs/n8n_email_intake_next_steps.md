# PEC Email Intake — Live Runbook

> **Status:** Workflow created (inactive), credential live, admin consent applied.
>
> **Goal:** Any user who emails `pec.assist@pecalum.com` receives an auto-reply and gets an Asana case created automatically.
>
> **Known values:**
> - Tenant ID: `0a2d7824-f235-4d58-979b-06beadedd107`
> - App (Client) ID: `0d973b10-a569-4c48-b68b-825a6e1eb6ba`
> - Credential: `pec-assist-graph` (ID: `4OOSlCASgmNPIC0Q`, type: `oAuth2Api`)
> - Workflow: `PEC-Email-Intake` (ID: `aA0naiBjMVXSxbm5`, inactive)
> - Error workflow: `gZxrCH09fh6NK7CU` (PEC-Error-Handler, active)

---

## Architecture (final — Route 1 with HTTP Request nodes)

Why HTTP Request nodes instead of n8n's native Outlook trigger: the native Microsoft Outlook OAuth2 credential type hardcodes a request for Contacts, Calendars, Mail.Send, MailboxSettings, and `.Shared` scopes — far more than we need or were granted. Using a generic OAuth2 credential with HTTP Request nodes lets us stay within the single approved scope: `Mail.ReadWrite`.

```
┌──────────────────────────────────────────────────┐
│ Every Minute (Schedule Trigger)                  │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ Get Unread Messages (HTTP GET)                   │
│   GET /me/mailFolders/inbox/messages             │
│   $filter=isRead eq false                        │
│   $select=id,subject,body,bodyPreview,from,      │
│           internetMessageId,receivedDateTime     │
│   $top=25  $orderby=receivedDateTime asc         │
│   Auth: pec-assist-graph (OAuth2)                │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ Split Messages (SplitOut on `value`)             │
│   one item per unread message                    │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ Skip Auto-Replies (IF)                           │
│   from != pec.assist@pecalum.com  AND            │
│   subject !~ "^(Auto-Reply|Out of Office|        │
│              Undeliverable|Automatic reply)"     │
└──────────────────────────────────────────────────┘
                       ↓ true
┌──────────────────────────────────────────────────┐
│ Normalize Payload (Code, runOnceForEachItem)     │
│   Extract: subject, body, from.name, from.email  │
│   Prefer plain text body; strip HTML if needed   │
│   Truncate body to 50000 chars                   │
│   message_id = internetMessageId (RFC822)        │
│   _graph_id  = Outlook message id (for PATCH)    │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ POST /email/process (HTTP POST)                  │
│   http://email-task:8001/email/process           │
│   X-API-Key: {{ $env.WEBHOOK_API_KEY }}          │
│   Body: normalized JSON                          │
│   onError: continueErrorOutput                   │
└──────────────────────────────────────────────────┘
                       ↓ success
┌──────────────────────────────────────────────────┐
│ Mark Email Read (HTTP PATCH)                     │
│   PATCH /me/messages/{_graph_id}                 │
│   Body: { "isRead": true }                       │
│   Auth: pec-assist-graph (OAuth2)                │
└──────────────────────────────────────────────────┘
```

**Failure modes:**
- GET fails → workflow errors → PEC-Error-Handler handles it
- POST fails → email stays unread → picked up again next poll (email-task dedup prevents duplicate tickets)
- PATCH fails → email stays unread → retried next poll
- Net result: the unread state acts as a natural retry queue

---

## Prerequisites checklist

- [x] Admin consent granted for `Mail.ReadWrite` (delegated) on PEC Assist Bot
- [x] OAuth credential `pec-assist-graph` created and signed in as `pec.assist@pecalum.com`
- [x] Workflow `PEC-Email-Intake` created (inactive)
- [ ] `WEBHOOK_API_KEY` verified inside n8n container (Step 1 below)

---

## Step 1 — Verify `WEBHOOK_API_KEY` in n8n container (VM SSH)

```bash
docker compose exec n8n env | grep WEBHOOK_API_KEY
```

If missing:

```bash
KEY=$(grep ^WEBHOOK_API_KEY= ~/ai-initiative/pec-assist-bot/src/email_task_service/.env | cut -d= -f2)
echo "WEBHOOK_API_KEY=$KEY" >> ~/ai-initiative/.env

# Add to n8n service in docker-compose.yml:
#   environment:
#     - WEBHOOK_API_KEY=${WEBHOOK_API_KEY}

nano ~/ai-initiative/docker-compose.yml
docker compose up -d n8n
docker compose exec n8n env | grep WEBHOOK_API_KEY
```

---

## Step 2 — Manual test (workflow inactive)

1. Send a test email from your personal account to `pec.assist@pecalum.com` with subject `n8n smoke test`
2. In the n8n UI, open `PEC-Email-Intake` (https://pecn8n.westus2.cloudapp.azure.com:9443/workflow/aA0naiBjMVXSxbm5)
3. Click **Execute Workflow**
4. Verify each node:

| Node | Expected output |
|---|---|
| Every Minute | (manual trigger fires the chain) |
| Get Unread Messages | 200 OK, `value` array with your test email |
| Split Messages | One item per unread message |
| Skip Auto-Replies | Routes to true branch (your email isn't an auto-reply) |
| Normalize Payload | JSON with `subject`, `body`, `from_email`, `message_id`, `_graph_id` |
| POST /email/process | HTTP 200, response includes `correlation_id`, `classification`, `asana_response` |
| Mark Email Read | 200/204, message now `isRead: true` |

5. Confirm in **Asana** — ticket created in project `1213992435706056`
6. Confirm in **your inbox** — branded HTML auto-reply received
7. Confirm in **pec.assist inbox** — original test email marked as read

---

## Step 3 — Activate

Toggle **Active** on in the n8n UI. Workflow polls every 1 minute from this point.

---

## Step 4 — End-to-end live test

Send another email from any account to `pec.assist@pecalum.com`. Wait up to 90 seconds. Verify:

- [ ] Asana ticket created
- [ ] Auto-reply received in sender's inbox
- [ ] Original email marked as read in `pec.assist@pecalum.com`

---

## Full user journey

```
User sends email to pec.assist@pecalum.com
        ↓  (≤1 min)
n8n Schedule Trigger fires
        ↓
HTTP GET Graph API → unread messages
        ↓
Split into individual items
        ↓
Filter out auto-replies / loops
        ↓
Normalize (subject, body, sender, message_id)
        ↓
POST /email/process → email-task FastAPI service
        ├── LLM classifies the request
        ├── Creates Asana task with friendly ID (ID-NN)
        └── Sends branded HTML auto-reply to the user
        ↓
HTTP PATCH Graph API → mark message read
```

---

## Rollback

Deactivate the workflow in n8n UI (toggle Active off). Polling stops immediately. No other services are affected — `email-task` and `asana-task` services keep running for any manual or direct API invocations.

---

## Known limitations

1. **Credential is bound to pec.assist user account.** If pec.assist is disabled or has its password rotated, the credential's refresh token will eventually fail and require re-auth in n8n. Refresh token TTL is ~90 days of inactivity; with 1-min polling this won't trigger naturally.
2. **No attachment processing.** Body text only. Screenshots/images aren't seen by the classifier. Upgrade path: add `$expand=attachments` to the GET and pass to the service.
3. **Crude HTML stripping.** Regex-based — strips tags but doesn't decode entities. Most real emails are fine; complex marketing HTML may leave artifacts.
4. **Polling lag.** Up to 60 seconds between an email arriving and processing starting. Acceptable for support intake; switch to Graph change-notification webhooks if low-latency becomes a requirement.
