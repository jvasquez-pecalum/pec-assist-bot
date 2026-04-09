# Fix: PEC Workflows — 403 Forbidden / InsufficientPrivileges Errors

**Date:** 2026-04-06
**Status:** Ready to execute
**Tool:** Use `mcp__n8n-mcp-full` MCP tools for all changes

---

## Problem Summary

The PEC-Classifier and PEC-Responder workflows are failing with `403 Forbidden - InsufficientPrivileges` when trying to fetch/reply to certain Teams chat messages. The error occurs intermittently — some executions succeed, others fail.

### Root Cause

The Microsoft Graph subscription resource is set to `/me/chats/getAllMessages` which is an **invalid hybrid path**. Microsoft Graph has two distinct resources:

| Resource | Permission Type | Scope |
|----------|----------------|-------|
| `/chats/getAllMessages` | Application | ALL chats in the tenant |
| `/me/chats/allMessages` | Delegated | Only chats the user is a member of |

The current `/me/chats/getAllMessages` is being interpreted as the application-level resource, so PEC Assist receives notifications for **every chat in the tenant** — including chats between other users that PEC Assist cannot access.

### Evidence

- **Failing execution 2586:** chatId `19:79c6e780-adf5-44b9-b330-8868e5af8d94_bd767083-...` — PEC Assist is NOT a member
- **Successful execution 2565:** chatId `19:6902c06f-81ba-4813-b1d4-6061ce883e31_bd767083-...` — contains PEC Assist's own user ID, IS a member
- **Inner Graph error:** `AclCheckFailed - The initiator 8:orgid:6902c06f-81ba-4813-b1d4-6061ce883e31 is not a member of the roster`

### Cascade Effect

When Fetch Message gets 403, the "Handle Fetch Failure" node creates **fake fallback data** (`[Message content unavailable]`, sender: `Unknown Sender`). This fake data passes the bot check, gets classified by the LLM as `general_inquiry`, and then the Responder tries to reply to the same inaccessible chat — which also fails with 403.

---

## Fix 1: Correct the Subscription Resource

**Workflow:** Auto Subscription Lifecycle Manager
**Workflow ID:** `aRY0HcvD0wctDjuB`

### Step 1A: Update "Find Our Subscription" node (id: `find-sub`)

**Current code** (line to change):
```js
const ourSub = subscriptions.find(sub => 
    sub.notificationUrl === ourWebhookUrl && 
    sub.resource === '/me/chats/getAllMessages'
);
```

**New code:**
```js
const ourSub = subscriptions.find(sub => 
    sub.notificationUrl === ourWebhookUrl && 
    sub.resource === '/me/chats/allMessages'
);
```

### Step 1B: Update "Create New Subscription" node (id: `create-sub`)

**Current JSON body:**
```json
{
  "changeType": "created",
  "notificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",
  "lifecycleNotificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",
  "resource": "/me/chats/getAllMessages",
  "expirationDateTime": "{{ $json.newExpiration }}",
  "clientState": "pec-assist-webhook-secret"
}
```

**New JSON body:**
```json
{
  "changeType": "created",
  "notificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",
  "lifecycleNotificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",
  "resource": "/me/chats/allMessages",
  "expirationDateTime": "{{ $json.newExpiration }}",
  "clientState": "pec-assist-webhook-secret"
}
```

### Step 1C: Delete old subscription and create new one

After updating the workflow, the old subscription (with wrong resource) must be deleted so a new one gets created with the correct resource.

**Option A — Via n8n MCP:**
1. Use `mcp__n8n-mcp-full__n8n_update_partial_workflow` to update both nodes
2. Manually trigger the lifecycle manager — it won't find a sub matching `/me/chats/allMessages`, so it will create a new one
3. The old `/me/chats/getAllMessages` subscription will expire on its own (max 3 days)

**Option B — Force delete old sub first:**
1. List current subscriptions via Graph API (run the lifecycle manager manually, check "List Subscriptions" output)
2. Note the subscription ID for the old `/me/chats/getAllMessages` sub
3. Delete it: `DELETE https://graph.microsoft.com/v1.0/subscriptions/{subscriptionId}`
4. Then trigger lifecycle manager to create fresh

### MCP command to update the Lifecycle Manager workflow

Use `mcp__n8n-mcp-full__n8n_update_partial_workflow` with workflow ID `aRY0HcvD0wctDjuB`.

Update the "Find Our Subscription" node `find-sub` with this full jsCode:

```js
// Find subscription for our webhook URL
const subscriptions = $input.first().json.value || [];
const ourWebhookUrl = 'https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events';

// Calculate expiration date (+3 days from now)
const newExpiration = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();

const ourSub = subscriptions.find(sub => 
    sub.notificationUrl === ourWebhookUrl && 
    sub.resource === '/me/chats/allMessages'
);

if (ourSub) {
    // Check if expiring within 2 hours
    const expiration = new Date(ourSub.expirationDateTime);
    const twoHoursFromNow = new Date(Date.now() + 2 * 60 * 60 * 1000);
    
    return [{
        json: {
            found: true,
            subscriptionId: ourSub.id,
            expirationDateTime: ourSub.expirationDateTime,
            newExpiration: newExpiration,
            needsRenewal: expiration < twoHoursFromNow,
            reason: expiration < twoHoursFromNow ? 'Expiring soon' : 'Valid'
        }
    }];
}

return [{
    json: {
        found: false,
        subscriptionId: null,
        expirationDateTime: null,
        newExpiration: newExpiration,
        needsRenewal: true,
        reason: 'No subscription found'
    }
}];
```

Update the "Create New Subscription" node `create-sub` jsonBody to:
```
={\n  "changeType": "created",\n  "notificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",\n  "lifecycleNotificationUrl": "https://pecn8n.westus2.cloudapp.azure.com:9443/webhook/teams-events",\n  "resource": "/me/chats/allMessages",\n  "expirationDateTime": "{{ $json.newExpiration }}",\n  "clientState": "pec-assist-webhook-secret"\n}
```

---

## Fix 2: Stop Cascade on Fetch Failure

**Workflow:** PEC-Classifier
**Workflow ID:** `zHSGTpk1RJGPD9MY`
**Node:** "Handle Fetch Failure" (id: `handle-fail`)

### Current code (BROKEN — masks errors with fake data):
```js
const input = $input.first().json;
if (input && input.from && input.body && input.body.content) {
  return [{ json: input }];
}
return [{
  json: {
    id: "unknown",
    from: { user: { id: "unknown-sender", displayName: "Unknown Sender" } },
    body: { content: "[Message content unavailable]" },
    createdDateTime: new Date().toISOString(),
    webUrl: ""
  }
}];
```

### New code (stops processing on errors):
```js
const input = $input.first().json;

// If the Graph API returned an error response, stop processing entirely
if (input.error) {
  // Return empty to halt this branch — no classification, no reply
  return [];
}

// Valid message with expected structure
if (input && input.from && input.body && input.body.content) {
  return [{ json: input }];
}

// Unexpected structure but not an error — also stop to be safe
return [];
```

Returning `[]` (empty array) stops the workflow branch at this node. No downstream nodes (bot check, LLM, classification update, responder) will execute.

### MCP command

Use `mcp__n8n-mcp-full__n8n_update_partial_workflow` with workflow ID `zHSGTpk1RJGPD9MY`.

Update node `handle-fail` jsCode to the new code above.

---

## Fix 3 (Optional): Defense-in-Depth Chat Filter in Intake

**Workflow:** PEC-Intake
**Workflow ID:** `3CpsxZLMLHAXPnFz`
**Node:** "Parse Resource" (id: `parse-resource`)

Add a filter to skip notifications for chats where PEC Assist is not a participant. For 1:1 chats, the chatId format is `19:{userId1}_{userId2}@unq.gbl.spaces`, so we can check if PEC Assist's user ID is in the chatId.

### Updated Parse Resource code:
```js
const input = $input.first().json;
let body = input.body;
if (typeof body === 'string') {
  try { body = JSON.parse(body); } catch (e) { body = null; }
}
if (!body) body = input;
const notifications = body.value || [];
const results = [];

const PEC_ASSIST_USER_ID = '6902c06f-81ba-4813-b1d4-6061ce883e31';

for (const notification of notifications) {
  const resource = notification.resource || '';
  let match = resource.match(/chats\/([^\/]+)\/messages\/([^\/]+)/);
  if (!match) { match = resource.match(/chats\('([^']+)'\)\/messages\('([^']+)'\)/); }
  if (match) {
    const chatId = match[1];
    const messageId = match[2];
    
    // Skip chats where PEC Assist is not a participant
    // For 1:1 chats, the chatId contains both user IDs
    // For group chats, this check won't filter (handled by Fix 1 subscription scope)
    if (!chatId.includes(PEC_ASSIST_USER_ID)) {
      continue;
    }
    
    results.push({
      json: {
        chatId: chatId,
        messageId: messageId,
        resource: resource,
        subscriptionId: notification.subscriptionId || '',
        clientState: notification.clientState || ''
      }
    });
  }
}
if (results.length === 0) {
  return [{ json: { chatId: '', messageId: '', error: 'Could not parse resource or no valid chats' }}];
}
return results;
```

**Note:** This is a safety net. Fix 1 is the primary solution. This filter only works reliably for 1:1 chats. Once the subscription resource is corrected, this filter becomes redundant but harmless.

---

## Azure AD Prerequisite Check

Before applying Fix 1, verify the "PEC Assist" app registration in Azure AD has the correct **delegated** permissions:

1. Go to Azure Portal > App Registrations > find the app for "PEC Assist"
2. Check API Permissions:
   - **Required (delegated):** `Chat.Read` or `Chat.ReadWrite`
   - The `/me/chats/allMessages` subscription resource requires delegated `Chat.Read` at minimum
3. If only application permissions (`Chat.ReadWrite.All`) are granted, you need to add the delegated permission and re-consent

---

## Execution Order

1. **Check Azure AD permissions** (prerequisite)
2. **Apply Fix 1** — Update subscription resource in Lifecycle Manager
3. **Apply Fix 2** — Update Handle Fetch Failure in Classifier
4. **Apply Fix 3** (optional) — Add chat filter in Intake
5. **Delete old subscription** — Trigger lifecycle manager manually to create new sub
6. **Verify** — Send test message to PEC Assist in Teams

---

## Verification Steps

After applying all fixes:

1. **Check subscription was recreated:**
   - Manually trigger Auto Subscription Lifecycle Manager
   - Check execution output — "Create New Subscription" should fire with resource `/me/chats/allMessages`

2. **Send a test message:**
   - Open Teams, send a direct message to PEC Assist
   - Wait for the workflow to trigger

3. **Check PEC-Intake execution:**
   - Should show the webhook firing and passing to Classifier

4. **Check PEC-Classifier execution:**
   - "Fetch Message" should return 200 with actual message content
   - "Is From Bot?" should route to the correct branch
   - "LLM Analysis" should classify with real content (not "Message content unavailable")
   - "Update Classification" should write proper intent/urgency to Supabase

5. **Check PEC-Responder execution:**
   - "Send Reply" should return 200/201
   - Reply should appear in the Teams chat

6. **Verify no more phantom errors:**
   - Wait 10-15 minutes
   - Check PEC-Classifier executions — should no longer see 403 errors for foreign chats

7. **Check Supabase `processed_messages`:**
   - New entries should have: `status: 'classified'` or `'replied'`, proper `intent`, `sender_name`, `summary`
   - No more entries with `intent: null`, `sender_name: null`, `summary: null`

---

## Workflow IDs Quick Reference

| Workflow | ID | Role |
|----------|-----|------|
| PEC-Intake | `3CpsxZLMLHAXPnFz` | Webhook receiver, dedup, routes to Classifier |
| PEC-Classifier | `zHSGTpk1RJGPD9MY` | Fetches message, classifies with LLM, routes to Responder |
| PEC-Responder | `HJ9NigH9QU1bORGE` | Sends reply to Teams chat, updates Supabase |
| Auto Subscription Lifecycle Manager | `aRY0HcvD0wctDjuB` | Creates/renews Graph subscriptions every 30min |
| PEC-Error-Handler | `gZxrCH09fh6NK7CU` | Error workflow for all PEC workflows |

## Key Node IDs

| Workflow | Node Name | Node ID |
|----------|-----------|---------|
| Lifecycle Manager | Find Our Subscription | `find-sub` |
| Lifecycle Manager | Create New Subscription | `create-sub` |
| PEC-Classifier | Handle Fetch Failure | `handle-fail` |
| PEC-Intake | Parse Resource | `parse-resource` |

## Credential Reference

| Name | ID | Type |
|------|-----|------|
| PEC Assist | `g9tTmjF1O6MEthKF` | Microsoft OAuth2 API |
| Supabase account | `XZskHGgg0vTwDZFS` | Supabase API |
| OpenAi account | `MtOetnPgnOreJI9x` | OpenAI API |

## PEC Assist User ID

`6902c06f-81ba-4813-b1d4-6061ce883e31`
