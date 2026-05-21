"""
FastAPI service to create Asana tasks from n8n/Teams bot integration.
Receives task data from n8n and creates corresponding tasks in Asana.
"""

import os
import re
import asyncio
import logging
from typing import Optional, Literal
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

import httpx
from fastapi import FastAPI, HTTPException, status, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field, EmailStr, field_validator

from due_date import resolve_due_date

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ASANA_API_BASE = "https://app.asana.com/api/1.0"
ASANA_TOKEN = os.getenv("ASANA_TOKEN")
ASANA_PROJECT_ID = os.getenv("ASANA_PROJECT_ID")
ASANA_WORKSPACE_ID = os.getenv("ASANA_WORKSPACE_ID")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")
APP_ENV = os.getenv("APP_ENV", "development")

if not ASANA_TOKEN:
    logger.warning("ASANA_TOKEN not set. Asana task creation will fail.")
if not ASANA_PROJECT_ID:
    logger.warning("ASANA_PROJECT_ID not set. Tasks may not be assigned to a project.")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: Optional[str] = Security(_api_key_header)) -> str:
    if not SERVICE_API_KEY:
        if APP_ENV == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Service misconfigured: SERVICE_API_KEY not set",
            )
        return ""
    if api_key != SERVICE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TaskRequest(BaseModel):
    """Task creation request from n8n"""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=50000)
    intent: Literal[
        "password_reset", "software_issue", "hardware_issue", "access_request",
        "general_support", "other",
        "data_engineering", "business_reports", "business_intelligence",
        "ai_initiatives", "general_inquiry",
    ] = Field(...)
    urgency: Literal["low", "medium", "high", "critical"] = Field(...)
    summary: Optional[str] = Field(None, max_length=5000)
    sender_name: Optional[str] = Field(None, max_length=200)
    sender_email: Optional[EmailStr] = Field(None)
    message_id: Optional[str] = Field(None, max_length=500)
    chat_id: Optional[str] = Field(None, max_length=500)
    assignee: Optional[str] = Field(None)
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    tags: Optional[list[str]] = Field(default_factory=list)

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("due_date must be YYYY-MM-DD")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("due_date is not a valid calendar date")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Password Reset Request - John Doe",
                "description": "User cannot access their account and needs password reset",
                "intent": "password_reset",
                "urgency": "high",
                "summary": "User locked out of account, needs immediate assistance",
                "sender_name": "John Doe",
                "sender_email": "john.doe@pecaluminum.com",
                "message_id": "123456789",
                "chat_id": "19:abc123@thread.v2",
            }
        }


class TaskResponse(BaseModel):
    """Task creation response"""
    success: bool
    task_id: Optional[str] = None
    task_url: Optional[str] = None
    task_name: Optional[str] = None
    friendly_id: Optional[str] = None  # User-facing ticket ID from Asana "ID" custom field (e.g. "ID-49")
    due_on: Optional[str] = None
    due_at: Optional[str] = None
    message: str
    created_at: str


# Asana custom field whose display_value is the user-facing ticket ID (e.g. "ID-49").
# Configurable via env in case the field is renamed.
FRIENDLY_ID_FIELD_NAME = os.getenv("ASANA_FRIENDLY_ID_FIELD", "ID")


def _extract_friendly_id(custom_fields: list[dict]) -> Optional[str]:
    """Pull the user-facing ticket ID (display_value) from the named custom field."""
    if not custom_fields:
        return None
    for field in custom_fields:
        if field.get("name") == FRIENDLY_ID_FIELD_NAME:
            value = field.get("display_value")
            if value:
                return str(value)
    return None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    asana_configured: bool
    version: str = "1.0.0"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Asana Task Service")
    yield
    logger.info("Shutting down Asana Task Service")


_docs_url = None if APP_ENV == "production" else "/docs"
_redoc_url = None if APP_ENV == "production" else "/redoc"

app = FastAPI(
    title="PEC Assist - Asana Task Service",
    description="FastAPI service to create Asana tasks from Teams/n8n integration",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

# CORS — backend-to-backend; default is no browser origins
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=bool(ALLOWED_ORIGINS),
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_urgency_emoji(urgency: str) -> str:
    urgency_map = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }
    return urgency_map.get(urgency.lower(), "⚪")


def _format_task_name(task: TaskRequest) -> str:
    emoji = _get_urgency_emoji(task.urgency)
    intent_display = task.intent.replace("_", " ").title()
    name = f"{emoji} [{intent_display}] {task.title}"

    if task.summary and task.summary not in task.title:
        max_len = 500
        suffix = f" | {task.summary}"
        if len(name) + len(suffix) > max_len:
            available = max_len - len(name) - 3
            suffix = f" | {task.summary[:available]}..."
        name += suffix

    return name


def _format_task_notes(task: TaskRequest) -> str:
    lines = []

    if task.summary:
        lines.append(f"## Summary\n{task.summary}\n")

    if task.description:
        lines.append(f"## Original Request\n{task.description}\n")

    lines.append("## Details")
    lines.append(f"- **Intent:** {task.intent}")
    lines.append(f"- **Urgency:** {task.urgency.upper()}")

    if task.sender_name:
        lines.append(f"- **Reported by:** {task.sender_name}")
    if task.sender_email:
        lines.append(f"- **Email:** {task.sender_email}")
    if task.message_id:
        lines.append(f"- **Message ID:** {task.message_id}")
    if task.chat_id:
        lines.append(f"- **Chat ID:** {task.chat_id}")

    lines.append(f"- **Created:** {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}")

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
@limiter.limit("120/minute")
async def health_check(request: Request):
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        asana_configured=bool(ASANA_TOKEN and ASANA_PROJECT_ID),
    )


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def create_task(request: Request, task: TaskRequest, _key: str = Security(require_api_key)):
    """
    Create a new task in Asana.

    Receives task data from n8n and creates a corresponding task in Asana
    with appropriate prioritization and metadata.
    """
    if not ASANA_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asana integration not configured. ASANA_TOKEN missing.",
        )

    task_name = _format_task_name(task)
    task_notes = _format_task_notes(task)

    asana_task = {
        "data": {
            "name": task_name,
            "notes": task_notes,
            "projects": [ASANA_PROJECT_ID] if ASANA_PROJECT_ID else [],
        }
    }

    if ASANA_WORKSPACE_ID and not ASANA_PROJECT_ID:
        asana_task["data"]["workspace"] = ASANA_WORKSPACE_ID

    if task.assignee:
        asana_task["data"]["assignee"] = task.assignee

    try:
        resolved = resolve_due_date(task.intent, task.urgency, task.due_date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    if resolved.due_on:
        asana_task["data"]["due_on"] = resolved.due_on
    elif resolved.due_at:
        asana_task["data"]["due_at"] = resolved.due_at

    tags = task.tags or []
    if tags:
        asana_task["data"]["tags"] = tags

    logger.info(f"Creating Asana task: {task_name}")
    logger.debug(f"Asana payload: {asana_task}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ASANA_API_BASE}/tasks",
                headers={
                    "Authorization": f"Bearer {ASANA_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=asana_task,
                timeout=30.0,
            )

            response.raise_for_status()
            asana_data = response.json()

            task_id = asana_data.get("data", {}).get("gid")
            task_url = f"https://app.asana.com/0/{ASANA_PROJECT_ID}/{task_id}" if ASANA_PROJECT_ID else None

            if task_id:
                for attempt, delay in enumerate([1, 2, 3], 1):
                    try:
                        await asyncio.sleep(delay)
                        refetch = await client.get(
                            f"{ASANA_API_BASE}/tasks/{task_id}?opt_fields=custom_fields,custom_fields.display_value,custom_fields.name",
                            headers={
                                "Authorization": f"Bearer {ASANA_TOKEN}",
                                "Accept": "application/json",
                            },
                            timeout=10.0,
                        )
                        refetch.raise_for_status()
                        refetch_data = refetch.json()
                        fields = refetch_data.get("data", {}).get("custom_fields", [])
                        if fields:
                            asana_data["data"]["custom_fields"] = fields
                        if _extract_friendly_id(fields):
                            break
                        logger.debug(f"friendly_id not populated yet (attempt {attempt}/3)")
                    except Exception as e:
                        logger.warning(f"Failed to re-fetch task custom fields (attempt {attempt}/3): {e}")

            friendly_id = _extract_friendly_id(asana_data.get("data", {}).get("custom_fields", []))
            if not friendly_id:
                logger.warning(f"friendly_id not found after retries for task {task_id}; using GID as fallback")
                friendly_id = task_id
            logger.info(f"Task created successfully: gid={task_id} friendly_id={friendly_id}")

            return TaskResponse(
                success=True,
                task_id=task_id,
                task_url=task_url,
                task_name=task_name,
                friendly_id=friendly_id,
                due_on=resolved.due_on,
                due_at=resolved.due_at,
                message="Task created successfully in Asana",
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Asana API error: {e.response.status_code} - {e.response.text}")
            sanitized = "Asana API returned an error"
            try:
                errs = e.response.json().get("errors", [])
                msgs = [err.get("message", "Unknown error") for err in errs]
                if msgs:
                    sanitized = "Asana API error: " + "; ".join(msgs)
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=sanitized)

        except httpx.RequestError as e:
            logger.error(f"Network error calling Asana API: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Network error communicating with Asana. Please try again later.",
            )


@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "PEC Assist - Asana Task Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "create_task": "POST /tasks",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
