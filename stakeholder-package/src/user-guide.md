# PEC Assist — User Guide

**Audience:** Everyone at PEC Aluminum who uses Microsoft Teams for IT support.
**Version:** 1.0 (April 2026)

---

## 1. What PEC Assist does

PEC Assist is an AI-powered IT support assistant that lives inside Microsoft Teams. When you post a message in the monitored Teams chat, PEC Assist reads it, understands what you need, opens a tracked ticket in Asana, and replies to you in Teams with a confirmation. You do not need to fill out a form, email anyone, or open a separate ticketing app — just chat normally.

Behind the scenes, PEC Assist is a set of automations (n8n workflows) plus an AI classifier (OpenAI GPT-4o-mini) plus an Asana task service. You don't need to know the internals — just keep reading.

## 2. How to submit a request

1. Open the designated **PEC Assist** Teams chat.
2. Post a message describing what you need, in plain English. Example: *"My Outlook keeps crashing when I open a meeting invite — I have a client call in 30 minutes."*
3. That's it. PEC Assist will respond within seconds.

**Tips to get the best result:**

- **Say what's broken and how it affects your work.** The assistant uses urgency cues ("production down", "ASAP", "meeting in an hour") to prioritize.
- **One issue per message.** If you have two unrelated problems, post them separately.
- **Don't @-mention a bot or person.** The assistant watches the whole chat — mentions aren't required.
- **If you're following up on an existing ticket**, reference it naturally ("still having the same Outlook issue from earlier") — the assistant tracks open tasks.

## 3. What happens next

```
You post in Teams
      ↓
PEC Assist reads the message (seconds)
      ↓
AI classifies it: category + urgency + summary
      ↓
Asana ticket created (if the issue needs tracking)
      ↓
Teams auto-reply to you with confirmation
```

You will see:

- An **auto-reply in the Teams chat** acknowledging your request.
- A **new task in the Asana project** you have access to, titled with an emoji that matches the urgency.
- If your message is a quick question or doesn't need a ticket (like "what are the office hours?"), you may get a reply without an Asana task being created.

## 4. The 5 intent categories

Every message is classified into exactly one of these:

| Category | What it means | Example phrases |
|---|---|---|
| **Password reset** | You can't log in, password expired, account locked. | "I forgot my password", "account locked out" |
| **Software issue** | An app is crashing, throwing errors, or misbehaving. | "Outlook keeps crashing", "Excel froze" |
| **Hardware issue** | Physical device problem — laptop, monitor, keyboard, etc. | "My laptop won't boot", "mouse not working" |
| **Access request** | You need permission to a folder, app, SharePoint site, license, etc. | "Need access to the Finance SharePoint", "please grant me a Visio license" |
| **General inquiry** | Questions about policies, how-tos, or anything not above. | "What are office hours?", "How do I request PTO?" |

If your message is ambiguous (could fit two categories), PEC Assist will ask you a clarifying question before creating a task.

## 5. Urgency levels & expected response

The assistant reads urgency cues from your message and sets one of four levels. Each level has a different Asana due date target.

| Urgency | Emoji | When it's used | Asana due date |
|---|---|---|---|
| Critical | 🔴 | You can't work at all — system down, account locked, production halted. | Same day |
| High | 🟠 | Significant impact — meeting soon, urgent deadline, "ASAP". | Next day |
| Medium | 🟡 | Work impacted but you have a workaround. This is the default. | 3 days |
| Low | 🟢 | General question, no time pressure ("whenever you get a chance"). | 1 week |

You will see the matching emoji prefix on the Asana task title, so IT support can triage at a glance.

## 6. Where to see my request

- **In Teams:** The auto-reply will confirm your request was received. The reply mentions intent and urgency so you can verify the classifier got it right.
- **In Asana:** Open the PEC Assist project in Asana. Your task will appear with title format:
  `🟠 [Software Issue] <your title> | <AI summary>`
  The task notes contain your original message, your name/email, Teams message ID, and urgency.

If the classifier got it wrong (e.g., labeled your hardware issue as "general inquiry"), reply in the Teams chat with a correction — the assistant can re-classify or ask for clarification.

## 7. When things go wrong

| Symptom | What it probably means | What to do |
|---|---|---|
| No auto-reply in Teams after 1 minute | Graph subscription may have expired, or the webhook is down. | Notify IT support (channel in section 8). |
| Your message got two replies | Microsoft Graph occasionally sends duplicate webhook events. Cosmetic; the Asana task is deduped. | Ignore — only one Asana task will exist. |
| Asana task has wrong category | AI classifier made a bad call (rare but possible). | Reply in Teams with a correction, or edit the Asana task directly. |
| Assistant ignores your message | You may have been misidentified as a bot (very rare). | Re-post, rewording the message. |
| Assistant asks a clarifying question | Your message was ambiguous. | Answer it in the chat — the assistant remembers the context. |

## 8. Who to contact

- **Operational issues** (assistant not responding, Asana board broken): **IT Support** — post in the IT Support channel or email ithelp@pecaluminum.com.
- **Feedback / feature requests** (new intent categories, different response wording): **Project Manager** for PEC Assist.
- **Urgent outage** (assistant down and you have a critical issue): call the IT hotline and bypass the assistant entirely.

---

*PEC Assist is in active rollout. Expect small improvements week-to-week. Feedback shapes the roadmap — tell us what works and what doesn't.*

*For a consolidated technical and user overview, see `pec-teams-ai-bot-overview.html` in the project root.*
