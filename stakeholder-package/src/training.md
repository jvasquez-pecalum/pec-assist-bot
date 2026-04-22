# PEC Assist — Training Guide

**Audience:** Business stakeholders, team leads, power users.
**Goal:** After reading this, you can explain PEC Assist to anyone at PEC Aluminum and run through the UAT checklist in Appendix A.

> **Verified:** n8n workflow inventory current as of 2026-04-21.

---

## 1. System overview

PEC Assist turns natural-language Microsoft Teams messages into structured, tracked IT tickets in Asana, without any forms or friction for the end user.

**End-to-end flow:**

```
  ┌────────────┐    webhook    ┌─────────────┐    executes    ┌────────────────┐
  │ MS Teams   │ ────────────▶ │ PEC-Intake  │ ─────────────▶ │ PEC-Classifier │
  │ chat       │               │ (n8n)       │                │ (n8n + OpenAI) │
  └────────────┘               └─────────────┘                └────────┬───────┘
                                                                        │
                                                        requires_task?  │
                                                                        ▼
                                                            ┌───────────────────────┐
                                                            │ asana_task_service    │
                                                            │ (FastAPI, POST /tasks)│
                                                            └───────────┬───────────┘
                                                                        ▼
                                                            ┌─────────────────────┐
                                                            │ Asana task created  │
                                                            └───────────┬─────────┘
                                                                        ▼
                                                            ┌─────────────────────┐
                                                            │ PEC-Responder (n8n) │
                                                            │ Teams auto-reply    │
                                                            │ + Asana comment     │
                                                            └─────────────────────┘

  side branches:
    • Asana-Poller           — watches Asana for status changes, triggers notifications
    • Asana-Teams Notifier   — posts Asana task updates back into Teams
    • PEC-Error-Handler      — catches and reports workflow failures
    • Auto Subscription Lifecycle Manager — keeps the MS Graph webhook alive
```

Every box above is real and currently active in production.

---

## 2. The 7 active workflows that matter

Live inventory (verified via n8n API, 2026-04-19):

| Workflow | Nodes | Trigger | What it does in one line |
|---|---:|---|---|
| **PEC-Intake** | 10 | Webhook (MS Graph) | Receives every Teams message notification, deduplicates, hands off to Classifier. |
| **PEC-Classifier** | 34 | Execute Workflow | Fetches the full message, detects bots, asks OpenAI to classify intent + urgency, decides whether to create/update an Asana task, routes to Responder. |
| **PEC-Responder** | 5 | Execute Workflow | Builds the Teams auto-reply, sends it, posts a matching comment on the Asana task, marks the thread as replied. |
| **PEC-Error-Handler** | 5 | Error trigger | Catches any workflow failure and writes a diagnosable error record. |
| **Asana-Poller** | 11 | Schedule | Polls Asana for task status changes (assignee, completion, custom fields). |
| **Asana-Teams Notifier** | 3 | Webhook from Poller | Posts notifications back into the relevant Teams chat when Asana tasks change. |
| **Auto Subscription Lifecycle Manager** | 10 | Schedule | Renews the Microsoft Graph subscription so the Intake webhook keeps receiving events. |

Ancillary workflows (not core to the user-facing flow): POC-OCR-SB, PoC-acs-events ServiceValidation, AI Agent Conversation, SCRAP BIN Clean Up.

---

## 3. End-to-end walkthrough

**Scenario:** User Jane Doe posts in the PEC Assist Teams chat: *"Outlook keeps crashing when I open meeting invites — I have a client call in 30 minutes."*

| # | Stage | What happens | Observable where |
|---:|---|---|---|
| 1 | MS Graph | Teams fires a change notification to the Intake webhook. | Not user-visible. |
| 2 | PEC-Intake → Webhook | Receives payload. Checks if it's a validation token (if so, echoes it back; otherwise continues). | n8n execution log. |
| 3 | PEC-Intake → Parse Resource | Extracts `chatId` and `messageId` from the resource URL. | n8n log. |
| 4 | PEC-Intake → Atomic Claim | Inserts a claim row into Supabase (`processed_messages`). If the row already exists, the "If: Claimed?" node routes to **Stop: Duplicate**. This is the deduplication guard. | Supabase `processed_messages` table. |
| 5 | PEC-Intake → Execute PEC-Classifier | Passes control to the Classifier sub-workflow. | n8n log. |
| 6 | PEC-Classifier → Fetch Message | GETs the full message body from Microsoft Graph. | n8n log. |
| 7 | PEC-Classifier → Is From Bot? | Bot-detection node. If true, updates status to "bot skip" and stops. | Supabase row status. |
| 8 | PEC-Classifier → Is New Command? / Clarification nodes | Checks if the message is a new ticket, a reply to an open ticket, or an answer to a pending clarification. | Supabase. |
| 9 | PEC-Classifier → Strip HTML → LLM Analysis | OpenAI (gpt-4o-mini, temperature 0.1) classifies: `{intent, urgency, summary, requires_task, response_tone}`. | LLM Analysis node output. |
| 10 | PEC-Classifier → Update Classification | Writes the classification back to Supabase. | `processed_messages` row. |
| 11 | PEC-Classifier → Check Open Task → Is Ambiguous? | If ambiguous, builds a clarification reply and sets pending-clarification state. Otherwise continues. | Supabase. |
| 12 | PEC-Classifier → Requires Task? | If `requires_task=true`, builds an Asana payload. | n8n log. |
| 13 | PEC-Classifier → Create Asana Task (HTTP) | POSTs to the **asana_task_service** `/tasks` endpoint. | FastAPI logs; Asana. |
| 14 | asana_task_service → Asana API | FastAPI formats the title (`🟠 [Software Issue] Outlook keeps crashing \| Meeting invite crash`), computes due date (urgency=high → next day), calls Asana API, re-fetches for custom fields. | Asana task appears. |
| 15 | PEC-Classifier → Build Responder Data + Update Asana Reference | Passes the Asana task ID and reply context to PEC-Responder. Writes the Asana reference back to Supabase. | Supabase. |
| 16 | PEC-Responder → Build Reply Message → Send Reply | Formats and sends the Teams auto-reply. | Teams chat. |
| 17 | PEC-Responder → Post Comment to Asana | Adds the reply text as a comment on the Asana task. | Asana activity feed. |
| 18 | PEC-Responder → Update Status: Replied | Marks the Supabase row as replied. End of the happy path. | Supabase. |

Typical end-to-end latency: a few seconds up to ~15 seconds (dominated by the OpenAI call and two Asana API round-trips).

---

## 4. Reading an Asana task

An Asana task created by PEC Assist always looks like this:

```
🟠 [Software Issue] Outlook keeps crashing | User unable to open meeting invites

## Summary
User unable to open meeting invites

## Original Request
My Outlook keeps crashing when I open a meeting invite — I have a client call in 30 minutes.

## Details
- **Intent:** software_issue
- **Urgency:** HIGH
- **Reported by:** Jane Doe
- **Email:** jane.doe@pecaluminum.com
- **Message ID:** 1745000000000
- **Chat ID:** 19:abc123@thread.v2
- **Created:** 2026-04-19T14:03:22.101Z
```

- **Emoji prefix** — urgency at a glance. 🔴 critical · 🟠 high · 🟡 medium · 🟢 low.
- **[Bracketed] tag** — the intent category, human-readable.
- **Title body** — the user's original title, optionally followed by the AI-generated summary.
- **Notes (markdown)** — summary, original request, and metadata block.
- **Due date** — auto-set from urgency (critical=today, high=+1 day, medium=+3 days, low=+7 days).
- **Custom fields** — auto-populated after creation (e.g., ID number); visible in the Asana project board.

---

## 5. Knowing the system is healthy (the 3 signals)

A business stakeholder can confirm PEC Assist is working **without opening n8n or Supabase** by checking three things:

1. **Auto-reply arrives in Teams** within ~15 seconds of posting a test message.
2. **A new Asana task appears** in the PEC Assist project with an emoji-prefixed title.
3. **No duplicate Asana tasks** when the same message happens to fire multiple Graph notifications (common — the dedup claim should prevent duplicates).

If any of those three fails, escalate to IT Support with the time of your test message and your Teams display name. They can pull the execution from n8n in seconds.

---

## 6. Glossary

| Term | Plain-English meaning |
|---|---|
| **Webhook** | A URL that an external service (MS Graph) calls when something happens (a Teams message is posted). |
| **Intake** | The n8n workflow that receives the webhook and decides whether to process or stop. |
| **Classifier** | The n8n workflow that uses OpenAI to decide intent + urgency and builds the Asana payload. |
| **Responder** | The n8n workflow that sends the Teams auto-reply and posts an Asana comment. |
| **Dedup (Atomic Claim)** | The database-backed guard that prevents the same Teams message from creating two Asana tasks. |
| **Subscription** | The MS Graph registration that tells Microsoft to send us Teams message events. It expires and is auto-renewed by the Lifecycle Manager. |
| **Clarification** | When the Classifier is unsure, it asks the user a follow-up question and remembers the pending state. |
| **Requires Task** | A boolean the LLM sets — `false` for quick informational replies that don't need an Asana ticket. |

---

## 7. FAQ

**Q: Does it read all Teams messages across the company?**
No. Only messages in the explicitly monitored PEC Assist chat / channel(s). The MS Graph subscription is scoped there.

**Q: What AI model is used?**
OpenAI `gpt-4o-mini` with `temperature=0.1` (low, for consistent classification). The classifier prompt is tuned for PEC Aluminum IT support categories.

**Q: What if the AI gets the intent wrong?**
The user can reply with a correction ("this is actually a hardware issue") and the Classifier will reprocess. Or IT can edit the Asana task directly.

**Q: Can it create duplicate Asana tasks for the same message?**
No, not under normal operation. PEC-Intake runs an atomic claim against Supabase before handing off. Duplicate Graph notifications short-circuit to a **Stop: Duplicate** node.

**Q: What happens if the asana_task_service is down?**
The HTTP call in the Classifier will fail. PEC-Error-Handler captures the failure. The Teams user does **not** get an auto-reply in that case, which is a visible signal.

**Q: How does the system know a message came from a bot (to skip it)?**
The Classifier's *Is From Bot?* node inspects the message source and known auto-reply text, then routes bot-authored messages to a no-op to avoid reply loops.

**Q: What about multi-turn conversations?**
The Classifier tracks an **Agent Memory** node and a pending-clarification flag in Supabase. If the user is answering a clarification the assistant asked earlier, it resumes that ticket instead of opening a new one.

**Q: How do I add a new intent category?**
Requires a change to the OpenAI classifier prompt, the Structured Output Parser schema, and optionally the asana_task_service intent field docstring. Talk to the PEC Assist PM.

**Q: Can I trigger the flow from outside Teams (e.g., email)?**
Not today. The only Intake is the MS Graph Teams webhook. Extending to email would be a future workflow.

**Q: Who sees the Asana tasks?**
Anyone with access to the PEC Assist Asana project. The Teams reply is visible only to the originating chat.

---

## Appendix A — UAT Checklist

See [uat-checklist.md](uat-checklist.md) for the standalone version with tickbox formatting.

### A. Intent classification (5 tests — one per intent)

- [ ] Submit "please reset my password" → Asana task created with intent=**password_reset**, urgency ≥ medium.
- [ ] Submit "Outlook keeps crashing" → intent=**software_issue**.
- [ ] Submit "my laptop won't boot" → intent=**hardware_issue**.
- [ ] Submit "I need access to the Finance SharePoint" → intent=**access_request**.
- [ ] Submit "what are the office hours" → intent=**general_inquiry**. Note: `requires_task` may be `false` for pure info questions.

### B. Urgency mapping (4 tests)

- [ ] "Production is down, nobody can work" → urgency=**critical**, 🔴 prefix, due date **today**.
- [ ] "Need this before my 3pm meeting — ASAP" → urgency=**high**, 🟠 prefix, due **tomorrow**.
- [ ] "Outlook is slow but I can work" (neutral) → urgency=**medium**, 🟡 prefix, due **+3 days**.
- [ ] "Not urgent, whenever you get a chance" → urgency=**low**, 🟢 prefix, due **+7 days**.

### C. Happy path

- [ ] Auto-reply arrives in Teams within ~15 seconds of posting.
- [ ] Asana task URL opens and shows correct title, notes (summary / original request / details block), urgency field.
- [ ] Asana-Teams Notifier posts a message to Teams when the assignee changes or the task is completed.

### D. Robustness

- [ ] Repeat the *same* message twice within 60 seconds → **only one** Asana task exists.
- [ ] Post an auto-reply-style message ("Thanks, your request has been received…") → the assistant ignores it (bot-skip branch).
- [ ] Ask an ambiguous question ("I'm having a problem") → the assistant responds with a clarifying question, not an immediate task.

### E. Sign-off

| Field | |
|---|---|
| Stakeholder name | |
| Date | |
| Overall result | ☐ Pass ☐ Pass-with-notes ☐ Fail |
| Notes / issues found | |
| Approved by | |

---

*This document is the single source of truth for the rollout. For a consolidated view, see `pec-teams-ai-bot-overview.html` in the project root.*
