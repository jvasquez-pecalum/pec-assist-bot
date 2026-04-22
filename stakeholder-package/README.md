# PEC Assist — Stakeholder Package

Self-contained documentation + UAT materials for rolling out the PEC Assist Teams AI Bot to business stakeholders.

## What's in here

```
stakeholder-package/
├── README.md                    ← you are here
├── src/                         ← markdown sources (editable)
│   ├── user-guide.md
│   ├── cheat-sheet.md
│   ├── training.md
│   └── uat-checklist.md
└── html/                        ← rendered, shareable pages (standalone, inline CSS)
    ├── user-guide.html
    ├── cheat-sheet.html
    └── training.html
```

Every `.html` file is **fully self-contained** — open it in a browser, email it as an attachment, or print it. No server, no shared CSS file, no JavaScript required.

## How to share this with stakeholders

| Deliverable | Best for | Format |
|---|---|---|
| **User Guide** (`user-guide.html`) | Everyday Teams users. "How do I submit a request?" | 8 sections, ~5 min read |
| **Cheat Sheet** (`cheat-sheet.html`) | Pin at desk or print. Quick reference only. | 1 page, print-friendly |
| **Training Guide** (`training.html`) | Stakeholders, team leads, anyone running UAT. Includes full walkthrough + UAT checklist. | ~20 min read |
| **UAT Checklist** (`src/uat-checklist.md`) | Executable acceptance tests. Also embedded as Appendix A in the Training HTML. | Markdown + HTML |

## How to run UAT this week

1. Share `html/training.html` with 1–2 stakeholders.
2. They work through **Appendix A** in that file, posting the sample test messages in the PEC Assist Teams chat and checking each box.
3. Target **A1–C5 + D1** (the 14 core rows) before end of week.
4. Stakeholder fills in Section **E. Sign-off** and returns.
5. Interpret results per the "Interpreting results" guidance at the bottom of the training page.

## How to edit

- **Content changes:** edit the `.md` in `src/`, then re-render the matching `.html` by copying content into the existing HTML structure (manual — no build step).
- **Style changes:** the `<style>` block is inline at the top of each HTML. Tokens (colors, fonts) are in `:root` CSS variables — change once per file.
- **Brand tokens in use:**
  - PE Yellow `#FFCC00` (primary accent)
  - PE Black `#111111` (text + dark backgrounds)
  - Inter (body) + JetBrains Mono (code) — loaded via Google Fonts `@import`
  - Urgency colors: 🔴 `#dc2626` · 🟠 `#ea580c` · 🟡 `#ca8a04` · 🟢 `#16a34a`

## Sources

Content distilled from the existing repo — do not edit these, they're the upstream of truth:

| Source | Used for |
|---|---|
| `asana_task_service/main.py` | Intent enum, urgency → emoji mapping, urgency → due-date mapping, task title/notes format |
| `pec_assist_poc.md` | Classifier prompt, LLM model + temperature, known-issues context |
| `PROJECT_DOCUMENTATION.md` | Architecture, services, infrastructure |
| Live n8n API (via MCP) | Workflow names, node counts, current connections (verified 2026-04-19) |
| `DESIGN_SYSTEM.md` | Brand colors, typography tokens |
| `pec_assist_task_report.html` | Visual structure reference |

## Verification done

- Intent list in docs matches the `TaskRequest.intent` literal in `main.py`.
- Urgency emoji mapping matches `_get_urgency_emoji` in `main.py` (🔴 critical, 🟠 high, 🟡 medium, 🟢 low).
- Urgency → due-date mapping matches `_get_due_date_from_urgency` (0 / 1 / 3 / 7 days).
- Workflow names + node counts in Training match live `n8n_list_workflows` output as of 2026-04-19.
- PEC-Classifier walkthrough reflects the actual node topology (`Is From Bot?`, `Is New Command?`, `Has Pending Clarification?`, `LLM Analysis`, `Requires Task?`, `Is Ambiguous?`, `Needs Continuation?`).
- PEC-Responder walkthrough reflects the actual 5-node flow (trigger → Build Reply → Send Reply → Post Comment to Asana → Update Status: Replied).

## Not in scope (deliberately)

- Automated pytest / n8n execution tests
- CI integration
- Hosting of HTML pages
- Operator / IT-support training (this package is end-user focused; a separate ops runbook would be needed for that audience)

---

Questions or content errors → PEC Assist PM.
