# Azure VM Deployment Guide

Deploy the Asana Task Service to your existing Azure VM running n8n.

## Prerequisites

- SSH access to `pecn8nvm@vm-pec-n8n`
- Docker and Docker Compose installed (already present)
- Caddy reverse proxy configured

## Files

| File | Purpose |
|------|---------|
| `docker-compose-addition.yml` | Snippet to add to your existing docker-compose.yml |
| `docker-compose-updated.yml` | Complete updated docker-compose.yml (reference) |
| `Caddyfile-addition` | Caddy route configuration for the Asana service |

## Deployment Steps

### 1. Clone/Copy Repository to VM

```bash
# On your VM
ssh pecn8nvm@vm-pec-n8n
cd ~/ai-initiative

# Option A: Git clone (if you push to GitHub/Azure DevOps)
git clone <your-repo-url> pec-assist-bot
cp -r pec-assist-bot/src/asana_task_service ./

# Option B: Copy files via SCP from your local machine
# scp -r src/asana_task_service pecn8nvm@vm-pec-n8n:~/ai-initiative/
```

### 2. Create Environment File

```bash
cd ~/ai-initiative
nano .env
```

Add (if not already present):
```bash
ASANA_TOKEN=your_token_here
ASANA_PROJECT_ID=your_project_id_here
```

### 3. Update docker-compose.yml

Edit `~/ai-initiative/docker-compose.yml` and add the `asana-task` service:

```yaml
  asana-task:
    build: ./src/asana_task_service
    container_name: asana-task
    restart: unless-stopped
    environment:
      - ASANA_TOKEN=${ASANA_TOKEN}
      - ASANA_PROJECT_ID=${ASANA_PROJECT_ID}
      - ASANA_WORKSPACE_ID=${ASANA_WORKSPACE_ID:-}
    networks:
      - ai-network
```

Also add `asana-task` to Caddy's `depends_on`:
```yaml
    depends_on:
      - n8n
      - frontend
      - iic
      - asana-task  # ADD THIS
```

### 4. Update Caddyfile

Edit `~/ai-initiative/Caddyfile` and add before the final `reverse_proxy` or in the appropriate server block:

```
handle_path /asana/* {
    reverse_proxy asana-task:8000
}
```

### 5. Deploy

```bash
cd ~/ai-initiative

# Build and start the new service
docker-compose up -d --build asana-task

# Restart Caddy to pick up new routes
docker-compose restart caddy

# Verify all services are running
docker-compose ps

# Check logs
docker-compose logs -f asana-task
```

### 6. Test

```bash
# Test health endpoint
curl https://pecn8n.westus2.cloudapp.azure.com:9443/asana/health

# Expected response:
# {"status": "healthy", "asana_configured": true, ...}
```

### 7. Update n8n Workflow

In your n8n HTTP Request node for task creation:

| Setting | Value |
|---------|-------|
| Method | POST |
| URL | `https://pecn8n.westus2.cloudapp.azure.com:9443/asana/tasks` |
| Content Type | JSON |

## Updating the Service

When you have new code:

```bash
cd ~/ai-initiative

# Pull latest changes (if using git)
cd pec-assist-bot && git pull && cd ..
cp -r pec-assist-bot/src/asana_task_service/* ./asana_task_service/

# Rebuild and restart
docker-compose up -d --build asana-task
docker-compose restart caddy
```

## Troubleshooting

### Service not accessible
```bash
# Check if container is running
docker-compose ps

# Check logs
docker-compose logs asana-task

# Test internal network
docker-compose exec caddy wget -qO- http://asana-task:8000/health
```

### Caddy routing issues
```bash
# Verify Caddy config
docker-compose exec caddy caddy validate --config /etc/caddy/Caddyfile

# Reload Caddy
docker-compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## Directory Structure on VM

```
~/ai-initiative/
├── docker-compose.yml      # Updated with asana-task service
├── Caddyfile               # Updated with /asana route
├── .env                    # Contains ASANA_TOKEN, ASANA_PROJECT_ID
├── asana_task_service/     # This repo's service folder
│   ├── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ...
└── pec-assist-bot/         # Git repo (optional, for updates)
    └── ...
```
