# PEC Assist — Infrastructure Architecture

> **Last Updated:** April 30, 2026  
> **Applies to:** `vm-pec-n8n` (`pecn8n.westus2.cloudapp.azure.com`)  
> **Scope:** PEC Assist Docker containers only (n8n, asana-task, frontend, iic, pdf-splitter, caddy)

> 🟢 **Production:** n8n workflows + `asana-task` FastAPI service  
> ⚪ **Out of scope:** `invoice-api`, `invoice-dashboard`, `acs-email` — separate projects on the same VM

---

## Table of Contents

1. [Overview](#overview)
2. [Docker Network Topology](#docker-network-topology)
3. [Caddy Routing & Port Mapping](#caddy-routing--port-mapping)
4. [Teams Channel — Request Flow](#teams-channel--request-flow)
5. [Shared Services](#shared-services)
7. [External Services Dependency Map](#external-services-dependency-map)
8. [Database & Persistence](#database--persistence)
9. [Environment Variables Reference](#environment-variables-reference)
10. [Deployment Layout on VM](#deployment-layout-on-vm)

---

## Overview

PEC Assist runs as a **Docker Compose stack** on a single Azure VM. All containers share a private bridge network (`ai-network`). A **Caddy reverse proxy** is the only container that exposes ports to the internet. Every other service is reached through Caddy's path-based routing.

The **Teams** channel is the primary intake. All workflow orchestration runs inside n8n.

```mermaid
graph TB
    subgraph "Internet"
        USER_TEAMS["Teams User"]
        ASANA["Asana API"]
        OPENAI["OpenAI API"]
        GRAPH["Microsoft Graph API"]
        SB["Supabase Postgres"]
    end

    subgraph "Azure VM — pecn8nvm@vm-pec-n8n"
        subgraph "Docker — ai-network"
            CADDY["Caddy<br/>Reverse Proxy"]
            N8N["n8n<br/>Workflow Engine"]
            ASANA_TASK["asana-task<br/>FastAPI :8000"]
            FRONTEND["frontend<br/>Web UI"]
            IIC["iic<br/>Streamlit :8501"]
            PDF["pdf-splitter"]

        end
    end

    USER_TEAMS -->|"Chat Message"| GRAPH
    GRAPH -->|"Webhook POST"| CADDY
    CADDY -->|"/webhook/*"| N8N
    N8N -->|"POST /tasks"| ASANA_TASK
    ASANA_TASK -->|"Create Task"| ASANA
    N8N -->|"Teams DM"| GRAPH
    N8N -->|"Read/Write"| SB

    CADDY -->|"/asana/*"| ASANA_TASK
    CADDY -->|"/"| N8N
    CADDY -->|"/"| FRONTEND
    CADDY -->|"/"| IIC

    style CADDY fill:#FFCC00,stroke:#111111,stroke-width:3px
    style N8N fill:#e0e0e0,stroke:#111111
    style ASANA_TASK fill:#e0e0e0,stroke:#111111
```

---

## Docker Network Topology

All containers connect to a single Docker bridge network called `ai-network`. No container except Caddy binds to host ports. Internal services communicate using container names as DNS hostnames.

```mermaid
graph LR
    subgraph "Host Network (pecn8n.westus2.cloudapp.azure.com)"
        subgraph "ai-network (bridge)"
            CADDY["🌐 Caddy<br/>container_name: caddy<br/>image: caddy:2-alpine<br/>ports: 80, 443, 8080, 8081, 9443"]
            N8N["⚙️ n8n<br/>container_name: n8n<br/>port: 5678<br/>build: Dockerfile.n8n"]
            ASANA_TASK["📝 asana-task<br/>container_name: asana-task<br/>port: 8000<br/>build: pec-assist-bot/asana_task_service"]
            FRONTEND["🖥️ frontend<br/>container_name: frontend<br/>port: 8080<br/>build: /opt/deployment/code/frontend"]
            IIC["📊 iic<br/>container_name: iic<br/>port: 8501<br/>build: /opt/deployment/code/iic"]
            PDF["📄 pdf-splitter<br/>container_name: pdf-splitter<br/>internal only"]
        end
    end

    CADDY -->|"proxy"| N8N
    CADDY -->|"proxy"| ASANA_TASK
    CADDY -->|"proxy"| FRONTEND
    CADDY -->|"proxy"| IIC
    N8N -->|"depends_on"| PDF

    style CADDY fill:#FFCC00,stroke:#111111,stroke-width:3px
```

### Container Responsibilities

| Container | Internal Port | Purpose | Reaches Out To |
|-----------|--------------|---------|---------------|
| `caddy` | 80, 443, 8080, 8081, 9443 | Reverse proxy + TLS termination | Nothing (only receives) |
| `n8n` | 5678 | Workflow automation engine (PEC-Intake, PEC-Classifier, PEC-Responder, Asana-Poller) | Asana API, Microsoft Graph, OpenAI, Supabase |
| `asana-task` | 8000 | FastAPI microservice — creates Asana tasks | Asana API |
| `frontend` | 8080 | Web UI | Nothing (served via Caddy) |
| `iic` | 8501 | Streamlit interface | Nothing (served via Caddy) |
| `pdf-splitter` | — | PDF processing utility | Nothing (called by n8n) |

---

## Caddy Routing & Port Mapping

Caddy is the **single point of entry** from the internet. It handles TLS (HTTPS) and routes requests by path.

### External → Internal Routing Table

| External URL | Caddy Port | Path Match | Internal Destination | Purpose |
|-------------|-----------|-----------|---------------------|---------|
| `https://pecn8n.westus2.cloudapp.azure.com:9443/` | 9443 | `/` | `n8n:5678` | n8n Editor + Webhooks |
| `https://pecn8n.westus2.cloudapp.azure.com:9443/asana/*` | 9443 | `/asana/*` | `asana-task:8000` | Asana Task Service API |
| `https://pecn8n.westus2.cloudapp.azure.com:8080/` | 8080 | `/` | `frontend` | Web Frontend |
| `https://pecn8n.westus2.cloudapp.azure.com:8081/` | 8081 | `/` | `iic:8501` | Streamlit IIC Interface |

### Caddyfile Snippet

```caddy
pecn8n.westus2.cloudapp.azure.com:9443 {
    handle_path /asana/* {
        reverse_proxy asana-task:8000
    }
    reverse_proxy n8n:5678
}
```

> **Key Point:** `asana-task` is **never exposed directly** to the internet. All traffic goes through Caddy on port 9443.

---

## Teams Channel — Request Flow

This is the original path. It is fully orchestrated by n8n workflows.

```mermaid
sequenceDiagram
    autonumber
    participant U as Teams User
    participant MG as Microsoft Graph
    participant C as Caddy :9443
    participant N as n8n
    participant SB as Supabase
    participant O as OpenAI
    participant A as Asana API
    participant ATS as asana-task

    U->>MG: Send message to PEC Assist
    MG->>C: POST /webhook/teams-events
    C->>N: Forward to PEC-Intake workflow

    N->>SB: Check channel_config.teams.is_active
    alt teams is INACTIVE
        N->>MG: Send maintenance DM
        MG->>U: "Please email pec.assist@pecalum.com"
    else teams is ACTIVE
        N->>SB: Atomic claim (INSERT processed_messages)
        alt Already claimed
            N-->>N: Drop (duplicate webhook)
        else New message
            N->>MG: GET /chats/{chatId}/messages/{messageId}
            MG-->>N: Message content + sender info
            N->>O: LLM Classification (intent, urgency, summary)
            O-->>N: JSON classification result
            alt requires_task = true
                N->>ATS: POST /tasks (via Caddy /asana/tasks)
                ATS->>A: Create Asana task
                A-->>ATS: task_id + task_url
                ATS-->>N: Task response
            end
            N->>MG: POST auto-reply to chat
            MG->>U: Teams DM with ticket reference
        end
    end
```

### Active n8n Workflows (Teams Path)

| Workflow | ID | Trigger | Purpose | Active |
|----------|-----|---------|---------|--------|
| **PEC-Intake** | `3CpsxZLMLHAXPnFz` | Webhook (`/webhook/teams-events`) | Entry point — validates webhook, checks channel toggle, atomic claim | ✅ |
| **PEC-Classifier** | `zHSGTpk1RJGPD9MY` | Called by PEC-Intake | Fetches message, runs LLM, creates Asana task, calls Responder | ✅ |
| **PEC-Responder** | `HJ9NigH9QU1bORGE` | Called by PEC-Classifier | Sends Teams DM reply to user | ✅ |
| **Asana-Poller** | `bi8LtU1JETJwjZQq` | Schedule (every 5 min) | Polls Asana for task updates, sends Teams DM notifications | ✅ |
| **Auto Subscription Lifecycle Manager** | `aRY0HcvD0wctDjuB` | Schedule | Manages Microsoft Graph webhook subscription renewal | ✅ |
| **PEC-Error-Handler** | `gZxrCH09fh6NK7CU` | Error trigger | Handles n8n execution errors, sends alerts | ✅ |

---

## Shared Services

Both channels converge on the same **Asana Task Service** and read from the same **Supabase toggle**.

```mermaid
graph TB
    subgraph "Intake Channel"
        T["Teams Channel<br/>(n8n workflows)"]
    end

    subgraph "Shared Services"
        ATS["asana-task :8000<br/>FastAPI — Creates Asana tickets"]
        SB["Supabase Postgres<br/>channel_config | email_requests | processed_messages"]
    end

    subgraph "External APIs"
        ASANA["Asana API"]
        OPENAI["OpenAI GPT-4o-mini"]
        MG["Microsoft Graph"]
    end

    T -->|"POST /tasks"| ATS
    T -->|"Read/Write"| SB
    ATS -->|"Create task"| ASANA
    T -->|"Send DM"| MG
    T -->|"Classify"| OPENAI

    style ATS fill:#FFCC00,stroke:#111111,stroke-width:2px
    style SB fill:#e0e0e0,stroke:#111111,stroke-width:2px
```

### Mutual Exclusivity (The Toggle)

The `channel_config` table tracks channel state. Currently only the Teams channel is active:

```sql
SELECT * FROM channel_config;
-- teams  | true  | 2026-04-30T12:00:00Z
```

---

## External Services Dependency Map

```mermaid
graph LR
    subgraph "Our Stack"
        N8N["n8n"]
        ATS["asana-task"]
    end

    subgraph "External SaaS"
        ASANA["Asana API<br/>app.asana.com"]
        OPENAI["OpenAI API<br/>api.openai.com"]
        GRAPH["Microsoft Graph<br/>graph.microsoft.com"]
        SB["Supabase<br/>*.supabase.co"]
    end

    N8N -->|"Create tasks"| ASANA
    N8N -->|"Classify"| OPENAI
    N8N -->|"Fetch messages / Send DMs"| GRAPH
    N8N -->|"Read/Write"| SB

    ATS -->|"Create tasks"| ASANA
```

### Service Account / Credential Requirements

| External Service | Credential Type | Stored In | Used By |
|-----------------|----------------|-----------|---------|
| Asana API | Personal Access Token | `.env` → `ASANA_TOKEN` | `asana-task`, `n8n` |
| OpenAI API | API Key | `.env` → `OPENAI_API_KEY` | `n8n` |
| Microsoft Graph | OAuth2 (n8n credential) | n8n credential store | `n8n` |
| Supabase | Service Key | `.env` → `SUPABASE_SERVICE_KEY` | `n8n` |

---

## Database & Persistence

All persistent state lives in a single **Supabase Postgres** project.

```mermaid
erDiagram
    channel_config {
        varchar channel_type PK "teams | email"
        boolean is_active "mutual exclusivity"
        timestamptz updated_at
    }

    email_requests {
        serial id PK
        varchar message_id UK "IMAP UID"
        varchar from_email
        varchar from_name
        text subject
        varchar intent
        varchar urgency
        text summary
        boolean requires_task
        varchar asana_task_id
        text asana_task_url
        timestamptz replied_at
        timestamptz created_at
    }

    processed_messages {
        varchar message_id PK "Teams message ID"
        varchar chat_id
        text intent
        varchar urgency
        timestamptz processed_at
    }

    error_log {
        serial id PK
        text error_message
        text workflow_name
        json payload
        timestamptz created_at
    }

    channel_config ||--o{ processed_messages : "read by n8n"
```

### Table Responsibilities

| Table | Written By | Read By | Purpose |
|-------|-----------|---------|---------|
| `channel_config` | `n8n` | `n8n` | Channel toggle state |
| `processed_messages` | `n8n` (PEC-Intake) | `n8n` (atomic claim check) | Deduplication of Teams webhooks |
| `error_log` | `n8n` (PEC-Error-Handler) | Operators | Centralized error tracking |

---

## Environment Variables Reference

### Global `.env` file on VM (`~/ai-initiative/.env`)

```bash
# ── Asana (shared by n8n + asana-task) ──
ASANA_TOKEN=your_asana_token
ASANA_PROJECT_ID=your_project_id
ASANA_WORKSPACE_ID=your_workspace_id

# ── OpenAI (n8n) ──
OPENAI_API_KEY=sk-...

# ── Supabase (n8n) ──
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# ── Internal Service Discovery ──
ASANA_SERVICE_URL=http://asana-task:8000

# ── n8n ──
DASHSCOPE_API_KEY=...
```

### Which Service Needs What

| Variable | n8n | asana-task | Caddy | frontend | iic |
|----------|-----|-----------|-------|---------|-----|
| `ASANA_TOKEN` | ✅ | ✅ | — | — | — |
| `ASANA_PROJECT_ID` | ✅ | ✅ | — | — | — |
| `OPENAI_API_KEY` | ✅ | — | — | — | — |
| `SUPABASE_URL` | ✅ | — | — | — | — |
| `SUPABASE_SERVICE_KEY` | ✅ | — | — | — | — |
| `DASHSCOPE_API_KEY` | ✅ | — | — | — | — |

---

## Deployment Layout on VM

```
~/ai-initiative/
├── docker-compose.yml          # All services defined here
├── Caddyfile                   # Reverse proxy rules
├── .env                        # All secrets and config
├── n8n_data/                   # n8n workflow + credential persistence
├── pec-assist-bot/             # Git repo (PEC Assist)
│   ├── src/
│   │   └── asana_task_service/ # FastAPI — Asana task creation
│   └── ...
├── pdf-splitter/               # PDF utility (n8n dependency)
├── acs-email-service/          # Legacy Node.js email service (out of scope)
├── frontend/                   # Web UI (external build)
├── iic/                        # Streamlit app (external build)

├── caddy_data/                 # TLS certificates
└── caddy_config/               # Caddy runtime config
```

### Start / Stop / Restart Commands

```bash
# Full stack
cd ~/ai-initiative
docker-compose up -d
docker-compose down

# Individual services
docker-compose restart caddy
docker-compose logs -f asana-task
```

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-04-06 | Initial Teams-only architecture | PEC Dev |
| 2026-04-09 | Added Asana-Poller workflow | PEC Dev |
| 2026-05-03 | Removed email-task service (out of scope) | PEC Dev |
