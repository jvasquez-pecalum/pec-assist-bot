# PEC Assist — UAT Checklist

**Purpose:** Hand this to a business stakeholder; they can validate PEC Assist end-to-end with no engineering help.
**How long:** About 30 minutes if production is healthy.
**Pre-req:** You must (a) be a member of the monitored PEC Assist Teams chat, and (b) have read access to the PEC Assist Asana project.

> For each row, post the sample message in the Teams chat, wait for the auto-reply (max ~15 seconds), then open the linked Asana task and verify the expected fields. Check the box when all expected outcomes match.

---

## A. Intent classification

One test per intent category. Verify the classifier picks the right label.

| # | Test message | Expected intent | Expected in Asana |
|---:|---|---|---|
| A1 | ☐ "please reset my password" | `password_reset` | Title starts with emoji + `[Password Reset]` |
| A2 | ☐ "Outlook keeps crashing when I open meeting invites" | `software_issue` | Title starts with `[Software Issue]` |
| A3 | ☐ "my laptop won't boot this morning" | `hardware_issue` | Title starts with `[Hardware Issue]` |
| A4 | ☐ "I need access to the Finance SharePoint site" | `access_request` | Title starts with `[Access Request]` |
| A5 | ☐ "what are the office hours?" | `general_inquiry` | May receive reply only — `requires_task` is often `false` for pure info questions. If no Asana task appears, that's expected behavior for this intent. |

---

## B. Urgency mapping

Urgency is inferred from language cues. Verify the emoji prefix and the auto-calculated due date.

| # | Test message | Expected urgency | Expected emoji | Expected Asana due date |
|---:|---|---|:---:|---|
| B1 | ☐ "Production is down, nobody can work" | `critical` | 🔴 | Same day (today) |
| B2 | ☐ "Need this before my 3pm meeting — ASAP" | `high` | 🟠 | Tomorrow (+1 day) |
| B3 | ☐ "Outlook is slow but I can still work" | `medium` | 🟡 | +3 days |
| B4 | ☐ "Not urgent, whenever you get a chance" | `low` | 🟢 | +7 days |

---

## C. Happy path

Validate the full end-to-end loop behaves as expected for a normal ticket.

| # | Check | Pass criteria |
|---:|---|---|
| C1 | ☐ Auto-reply arrives in Teams | Within ~15 seconds of posting a fresh test message. |
| C2 | ☐ Asana task has correct title | Format: `{emoji} [Intent] {title} \| {summary}` |
| C3 | ☐ Asana task has correct notes | Contains Summary, Original Request, and Details block (Intent, Urgency, Reported by, Email, Message ID, Chat ID, Created timestamp). |
| C4 | ☐ Asana task has correct due date | Matches the urgency → due-date mapping from section B. |
| C5 | ☐ Asana-Teams Notifier posts updates | Change the Asana task assignee or mark it complete — a notification should appear in the Teams chat shortly after. |

---

## D. Robustness

The tricky edge cases. These are what separate a PoC from a production system.

| # | Check | Pass criteria |
|---:|---|---|
| D1 | ☐ Duplicate message produces one task | Post the exact same message twice within 60 seconds. Exactly **one** Asana task should exist (deduplication via atomic claim). |
| D2 | ☐ Bot-style message is ignored | Post an auto-reply-style message containing text like "Thanks, your request has been received." No Asana task should be created. |
| D3 | ☐ Ambiguous message triggers clarification | Post "I'm having a problem" — the assistant should ask a clarifying question *instead of* creating a task. |
| D4 | ☐ Clarification is resolved | Answer D3's clarifying question. The assistant should then create a task that references the clarified intent/urgency. |
| D5 | ☐ Multi-turn reference is tracked | Open a ticket (e.g., "my monitor is broken"), then reply a few minutes later "still not working, is there an update?" — the assistant should recognize this as a follow-up, not open a fresh ticket. |

---

## E. Sign-off

| Field | Value |
|---|---|
| Stakeholder name | _________________________________ |
| Role / Team | _________________________________ |
| Date | _________________________________ |
| Overall result | ☐ Pass &nbsp;&nbsp; ☐ Pass-with-notes &nbsp;&nbsp; ☐ Fail |
| Tests failed (IDs, e.g., B2, D1) | _________________________________ |
| Notes / observations | _________________________________ |
| | _________________________________ |
| | _________________________________ |
| Approved for rollout | ☐ Yes &nbsp;&nbsp; ☐ Yes with conditions &nbsp;&nbsp; ☐ No |
| Signature | _________________________________ |

---

## Interpreting results

- **All 14 core rows (A1–C5 + D1) pass:** Production is healthy. Proceed with rollout.
- **Any B-row fails:** Classifier urgency heuristic needs tuning. Log which phrases the LLM mis-graded; pass to the PM.
- **D1 fails (duplicates created):** Stop rollout. The atomic-claim dedup path in PEC-Intake is broken — engineering issue.
- **D2 fails (bot loop):** The assistant is replying to its own messages. Stop rollout — risk of runaway reply loops.
- **D3/D4 fail:** Clarification flow is broken. Degrades experience but doesn't block rollout; flag to PM.
- **C1 fails (no reply at all):** Likely an expired MS Graph subscription or downstream service outage. Escalate to IT immediately.

*Escalations: PEC Assist PM for content/classifier issues · IT Support for infrastructure (n8n, Graph, Asana API, Supabase) issues.*
