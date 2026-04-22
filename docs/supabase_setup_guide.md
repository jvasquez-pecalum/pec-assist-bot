# Supabase Deduplication Setup Guide

This guide walks you through setting up native Supabase nodes in n8n for message deduplication.

## Overview

The deduplication system prevents duplicate auto-replies when Microsoft Graph sends multiple webhooks for the same message. It uses two native Supabase nodes plus a safeguard Code node:

1. **Check Supabase** - Queries if message was already processed
2. **Normalize Check** - Safeguards against empty results, errors, and edge cases
3. **Is Duplicate?** - Routes based on normalized check results
4. **Mark as Processed** - Inserts message record after processing

## Prerequisites

- Supabase project with `processed_messages` table created
- Supabase credential configured in n8n (type: `supabaseApi`)
- Workflow: PoC-Teams-Webhooks

## Step 1: Verify Supabase Table

Ensure your `processed_messages` table exists with this schema:

```sql
CREATE TABLE IF NOT EXISTS processed_messages (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    intent VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_message_id ON processed_messages(message_id);
```

## Step 2: Configure "Check Supabase" Node

### Add the Node

1. In the n8n workflow editor, add a **Supabase** node after "Parse Resource"
2. Rename it to **"Check Supabase"**

### Node Configuration

| Setting | Value |
|---------|-------|
| **Operation** | Get Many |
| **Table Name or ID** | `processed_messages` |
| **Return All** | `false` |
| **Limit** | `1` |
| **On Error** | Continue (from error output) |

### Filters Section

Add a filter condition (Filter Type = Build Manually):

| Field Name | Condition | Value |
|------------|-----------|-------|
| `message_id` | `Equals` | `{{ $json.messageId }}` |

**Important:** The Supabase node returns `[{}]` (array with one empty object) when no records are found, not an empty array. The "Normalize Check" Code node handles this.

## Step 3: Configure "Normalize Check" Code Node

This is a **critical safeguard** that handles all edge cases.

### Add the Node

1. Add a **Code** node after "Check Supabase"
2. Rename it to **"Normalize Check"**
3. Set **Mode** to "Run Once for All Items"

### JavaScript Code

```javascript
// Normalize Supabase check result
// Supabase returns [{}] when no records found, or [{message_id: '...'}] when found
// This code normalizes to: { isDuplicate: true/false, recordCount: 0/1, messageId: '...' }

const input = $input.all();
const messageId = $('Parse Resource').first().json.messageId;

console.log('Check Supabase input:', JSON.stringify(input));

// Handle various edge cases:
// 1. Empty array []
// 2. Array with empty object [{}]
// 3. Array with actual data [{message_id: '...'}]
// 4. Supabase error (caught by onError handler)

let isDuplicate = false;
let recordCount = 0;
let errorOccurred = false;
let errorMessage = '';

// Check if we have the expected input structure
if (!Array.isArray(input) || input.length === 0) {
    console.log('No input received from Check Supabase');
    // Treat as new message (not duplicate) to be safe
    isDuplicate = false;
    recordCount = 0;
} else {
    // Check the first item
    const firstItem = input[0];
    
    // Check if Supabase returned an error (in error output path)
    if (firstItem.error) {
        console.log('Supabase error:', firstItem.error);
        errorOccurred = true;
        errorMessage = firstItem.error.message || 'Supabase query failed';
        // On error, proceed as if not duplicate (fail open - better to process twice than not at all)
        isDuplicate = false;
        recordCount = 0;
    } 
    // Check if we got an empty object (no matching record)
    else if (Object.keys(firstItem.json || {}).length === 0) {
        console.log('Empty result - message not found in database');
        isDuplicate = false;
        recordCount = 0;
    }
    // Check if we have actual data (message exists)
    else if (firstItem.json && firstItem.json.message_id) {
        console.log('Found existing message:', firstItem.json.message_id);
        isDuplicate = true;
        recordCount = 1;
    }
    // Fallback for any other unexpected format
    else {
        console.log('Unexpected format, treating as not duplicate:', JSON.stringify(firstItem.json));
        isDuplicate = false;
        recordCount = 0;
    }
}

const result = {
    isDuplicate: isDuplicate,
    recordCount: recordCount,
    messageId: messageId,
    errorOccurred: errorOccurred,
    errorMessage: errorMessage,
    rawInput: input
};

console.log('Normalized result:', JSON.stringify(result));
return [{ json: result }];
```

**What this safeguards against:**
- ✅ Empty table (no records)
- ✅ Record not found (returns `[{}]`)
- ✅ Supabase connection errors
- ✅ Network timeouts
- ✅ Unexpected data formats
- ✅ Empty input array

**Fail-Open Strategy:** If anything goes wrong with the Supabase check, the workflow treats it as a new message (not duplicate). This is safer than blocking legitimate messages.

## Step 4: Configure "Is Duplicate?" IF Node

Add an **IF** node after "Normalize Check"

### Conditions

| Setting | Value |
|---------|-------|
| **Left Value** | `{{ $json.isDuplicate }}` |
| **Operator** | `Is True` |

**Logic:**
- If `isDuplicate = true` → message exists → Route to **"Skip Duplicate"**
- If `isDuplicate = false` → new message → Continue to **"Has Valid Data?"**

### Connections

- **True** (is duplicate) → Connect to "Skip Duplicate" (NoOp node)
- **False** (not duplicate) → Connect to "Has Valid Data?"

## Step 5: Configure "Mark as Processed" Node

Add a **Supabase** node after "Parse LLM JSON"

### Node Configuration

| Setting | Value |
|---------|-------|
| **Operation** | Create |
| **Table Name or ID** | `processed_messages` |
| **Data to Send** | Define Below for Each Column |
| **On Error** | Continue (from error output) |

### Fields to Send Section

Add two fields:

| Field Name | Value |
|------------|-------|
| `message_id` | `{{ $('Parse Resource').first().json.messageId }}` |
| `intent` | `{{ $json.intent }}` |

**Note:** The `processed_at` and `created_at` fields auto-populate via default values in the database.

**Error Handling:** Even if the insert fails (e.g., duplicate key), the workflow continues to send the reply. This ensures users get a response even if there's a database issue.

## Step 6: Update Workflow Connections

Ensure these connections exist:

```
Parse Resource → Check Supabase
Check Supabase → Normalize Check (both outputs)
Normalize Check → Is Duplicate?
Is Duplicate? → [True] Skip Duplicate
Is Duplicate? → [False] Has Valid Data?
...
Parse LLM JSON → Mark as Processed (both outputs)
Mark as Processed → Send Reply
```

## Testing

### Test 1: First Message (New)

1. Open the workflow in n8n
2. Click **"Execute Workflow"**
3. Send a test message in Teams
4. Check execution:
   - "Check Supabase" returns `[{}]` (empty record)
   - "Normalize Check" outputs `{ isDuplicate: false, ... }`
   - "Is Duplicate?" routes to "Has Valid Data?"
   - "Mark as Processed" inserts record

### Test 2: Duplicate Message

1. Trigger another execution with the same message
2. "Check Supabase" returns `[{message_id: '...'}]`
3. "Normalize Check" outputs `{ isDuplicate: true, ... }`
4. "Is Duplicate?" routes to "Skip Duplicate"

### Test 3: Supabase Error Handling

1. Temporarily disable the Supabase table or credential
2. Send a message
3. Workflow should continue (fail open) and process the message
4. Check logs for error messages in "Normalize Check"

### Check Supabase Data

Run this SQL in Supabase SQL Editor:

```sql
SELECT * FROM processed_messages ORDER BY processed_at DESC LIMIT 10;
```

You should see records with:
- `message_id` - Teams message ID
- `intent` - Classified intent (password_reset, hardware_issue, etc.)
- `processed_at` - Timestamp

## Troubleshooting

### "Check Supabase" returns error

**Problem:** Table doesn't exist or credential misconfigured

**Solution:**
1. Verify table exists: `SELECT * FROM processed_messages LIMIT 1;`
2. Check Supabase credential uses correct URL and Service Role Key
3. The "Normalize Check" node handles errors gracefully

### "Mark as Processed" fails

**Problem:** Duplicate key violation (message already exists)

**Solution:** 
- The node has `onError: continueRegularOutput` so it won't stop the workflow
- This can happen if two webhooks arrive simultaneously (race condition)
- The duplicate detection in "Check Supabase" handles most cases

### Filter not working

**Problem:** Expression `{{ $json.messageId }}` not resolving

**Solution:** 
- Make sure you're using the correct expression syntax
- In "Check Supabase", the filter value should be: `{{ $json.messageId }}`
- Test the expression in the expression editor

### Permission Denied errors

**Problem:** Supabase RLS policies blocking inserts

**Solution:** Run this in Supabase SQL Editor:

```sql
-- Disable RLS on the table (simplest for internal use)
ALTER TABLE processed_messages DISABLE ROW LEVEL SECURITY;

-- OR create a permissive policy
CREATE POLICY "Allow all operations" ON processed_messages
    FOR ALL USING (true) WITH CHECK (true);
```

### "Normalize Check" shows unexpected input

**Problem:** Supabase node output format changed

**Solution:**
- Check the execution logs for the raw input
- The Code node has fallback logic for various formats
- Update the node logic if Supabase behavior changes

## How It Works

### Success Flow (New Message)

1. **Incoming Webhook**: Microsoft Graph sends notification
2. **Parse Resource**: Extract chatId and messageId
3. **Check Supabase**: Query for existing message → returns `[{}]`
4. **Normalize Check**: Detects empty object → `{ isDuplicate: false }`
5. **Is Duplicate?**: Routes to processing (false branch)
6. **Fetch Message**: Get message details from Graph API
7. **Is From Bot?**: Check if auto-reply (loop prevention)
8. **LLM Analysis**: Classify intent with OpenAI
9. **Parse LLM JSON**: Extract structured data
10. **Mark as Processed**: Insert into Supabase
11. **Send Reply**: Send auto-reply to Teams

### Duplicate Flow

1-4. Same as above
5. **Is Duplicate?**: Detects `{ isDuplicate: true }` → Routes to Skip Duplicate
6. Workflow ends (no reply sent)

### Error Flow (Fail-Open)

1-3. Same as above, but Check Supabase fails
4. **Normalize Check**: Detects error → `{ isDuplicate: false, errorOccurred: true }`
5. **Is Duplicate?**: Routes to processing (fail open)
6. Workflow continues normally, message is processed
7. Error is logged for debugging

## Race Condition Handling

If two identical webhooks arrive simultaneously:

1. Both pass "Check Supabase" (neither exists yet)
2. Both process through LLM
3. First one inserts successfully in "Mark as Processed"
4. Second one fails to insert (duplicate key), but continues to send reply

**Result:** User might receive two replies, but database stays consistent.

To minimize this, the "Check Supabase" → "Normalize Check" → "Is Duplicate?" path is as fast as possible, minimizing the window for race conditions.
