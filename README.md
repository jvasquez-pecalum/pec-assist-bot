# PEC Assist - Teams AI Bot

AI-powered IT support assistant for Microsoft Teams with Asana task integration.

## Components

| Component | Description | Location |
|-----------|-------------|----------|
| **Asana Task Service** | FastAPI microservice for creating Asana tasks | `src/asana_task_service/` |
| **Documentation** | Setup guides and architecture docs | `docs/` |
| **Stakeholder Overview** | Consolidated HTML5 overview (user guide + training + cheat sheet) | `artifacts/pec-teams-ai-bot-overview.html` |

## Quick Start

### Asana Task Service

```bash
cd src/asana_task_service
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Asana credentials
uvicorn main:app --reload
```

## Architecture

```
Microsoft Teams → Microsoft Graph → n8n → FastAPI → Asana
```

## Deployment

### Docker Compose (Recommended)

The service is designed to run alongside your existing n8n setup:

```bash
# On your Azure VM
cd ~/ai-initiative
docker-compose up -d --build asana-task
```

See `src/asana_task_service/README.md` for detailed deployment instructions.

## Environment Variables

Create a `.env` file in `src/asana_task_service/`:

```bash
ASANA_TOKEN=your_asana_personal_access_token
ASANA_PROJECT_ID=your_project_id
```

## License

Internal use only - PEC Aluminum
