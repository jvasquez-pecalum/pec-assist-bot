# PEC Assist — Cheat Sheet

One-page quick reference. Print-friendly.

---

## How to use it

Post a plain-English message in the **PEC Assist Teams chat**. That's it. No forms, no @-mentions, no tickets to open. The assistant replies within seconds and opens an Asana task automatically.

---

## Intent categories — what to say

| Intent | Say something like… |
|---|---|
| **Password reset** | "I forgot my password" · "I'm locked out of my account" · "Can't log into Windows" |
| **Software issue** | "Outlook keeps crashing" · "Excel is frozen" · "Teams won't load" |
| **Hardware issue** | "My laptop won't turn on" · "Monitor has no signal" · "Keyboard is dead" |
| **Access request** | "Need access to Finance SharePoint" · "Please grant me a Visio license" · "Add me to the Engineering folder" |
| **General inquiry** | "What are office hours?" · "How do I book PTO?" · "Where do I find the VPN guide?" |

---

## Urgency — what gets you prioritized

| Urgency | Emoji | Say something like… | Asana due date |
|---|:---:|---|---|
| **Critical** | 🔴 | "production down", "can't work at all", "blocking everything" | Same day |
| **High** | 🟠 | "ASAP", "meeting in 30 min", "urgent deadline today" | Next day |
| **Medium** | 🟡 | *default* — work impacted but you have a workaround | 3 days |
| **Low** | 🟢 | "no rush", "whenever you get a chance", "FYI" | 1 week |

---

## What you'll see

**In Teams (auto-reply):**
> Thanks, {name} — I've got this one tagged as *{Intent}* with *{urgency}* urgency and opened a ticket. I'll keep you posted here.

**In Asana (task):**
- **Title:** `🟠 [Software Issue] Outlook keeps crashing | User unable to open meeting invites`
- **Notes:** Summary · Original request · Intent · Urgency · Reported by · Email · Message ID · Created timestamp
- **Due date:** auto-set from urgency

---

## Common issues → quick fixes

| Symptom | Quick fix |
|---|---|
| No reply within 1 min | Report to IT Support — webhook or subscription may be down |
| Duplicate auto-reply | Ignore — only one Asana task is created (deduplication works) |
| Wrong intent category | Reply "this is actually a {correct category}" — assistant will re-classify |
| Assistant asks a question | Answer in chat — it's resolving ambiguity and remembers context |
| Assistant ignored me | Rephrase and re-post; it may have flagged you as a bot in error |

---

## Contact matrix

| Need | Who | How |
|---|---|---|
| Assistant not working | IT Support | IT Support Teams channel · ithelp@pecaluminum.com |
| Feature request / feedback | PEC Assist PM | direct message |
| Critical outage (bypass) | IT Hotline | phone, don't rely on Teams |

---

*Print and pin near your desk. Covers 95% of daily use. For the full overview, see `pec-teams-ai-bot-overview.html` in the project root.*
