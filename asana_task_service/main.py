"""
FastAPI service to create Asana tasks from n8n/Teams bot integration.
Receives task data from n8n and creates corresponding tasks in Asana.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
ASANA_API_BASE = "https://app.asana.com/api/1.0"
ASANA_TOKEN = os.getenv("ASANA_TOKEN")
ASANA_PROJECT_ID = os.getenv("ASANA_PROJECT_ID")
ASANA_WORKSPACE_ID = os.getenv("ASANA_WORKSPACE_ID")

if not ASANA_TOKEN:
    logger.warning("ASANA_TOKEN not set. Asana task creation will fail.")
if not ASANA_PROJECT_ID:
    logger.warning("ASANA_PROJECT_ID not set. Tasks may not be assigned to a project.")


# Pydantic models for request/response
class TaskRequest(BaseModel):
    """Task creation request from n8n"""
    title: str = Field(..., min_length=1, max_length=500, description="Task title")
    description: Optional[str] = Field(None, max_length=50000, description="Task description/notes")
    intent: str = Field(..., description="Classified intent: password_reset, software_issue, hardware_issue, access_request, general_inquiry")
    urgency: str = Field(..., description="Urgency level: low, medium, high, critical")
    summary: Optional[str] = Field(None, description="LLM-generated summary of the request")
    sender_name: Optional[str] = Field(None, description="Teams user who sent the message")
    sender_email: Optional[str] = Field(None, description="Teams user's email")
    message_id: Optional[str] = Field(None, description="Teams message ID for reference")
    chat_id: Optional[str] = Field(None, description="Teams chat ID for reference")
    assignee: Optional[str] = Field(None, description="Asana user GID to assign the task to")
    due_date: Optional[str] = Field(None, description="Due date in YYYY-MM-DD format")
    tags: Optional[list[str]] = Field(default_factory=list, description="List of tag names to apply")

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
                "chat_id": "19:abc123@thread.v2"
            }
        }


class TaskResponse(BaseModel):
    """Task creation response"""
    success: bool
    task_id: Optional[str] = None
    task_url: Optional[str] = None
    message: str
    created_at: str
    asana_response: Optional[dict] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    asana_configured: bool
    version: str = "1.0.0"


# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Asana Task Service")
    yield
    logger.info("Shutting down Asana Task Service")


app = FastAPI(
    title="PEC Assist - Asana Task Service",
    description="FastAPI service to create Asana tasks from Teams/n8n integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# Helper functions
def _get_urgency_emoji(urgency: str) -> str:
    """Get emoji prefix based on urgency"""
    urgency_map = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢"
    }
    return urgency_map.get(urgency.lower(), "⚪")


def _format_task_name(task: TaskRequest) -> str:
    """Format task name with urgency and intent"""
    emoji = _get_urgency_emoji(task.urgency)
    intent_display = task.intent.replace("_", " ").title()
    return f"{emoji} [{intent_display}] {task.title}"


def _format_task_notes(task: TaskRequest) -> str:
    """Format rich task description/notes"""
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
    
    lines.append(f"- **Created:** {datetime.utcnow().isoformat()}Z")
    
    return "\n".join(lines)


def _get_due_date_from_urgency(urgency: str) -> Optional[str]:
    """Calculate due date based on urgency"""
    urgency_days = {
        "critical": 0,  # Same day
        "high": 1,      # Next day
        "medium": 3,    # 3 days
        "low": 7        # 1 week
    }
    
    days = urgency_days.get(urgency.lower())
    if days is not None:
        due = datetime.utcnow() + timedelta(days=days)
        return due.strftime("%Y-%m-%d")
    return None


# API endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        asana_configured=bool(ASANA_TOKEN and ASANA_PROJECT_ID)
    )


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskRequest):
    """
    Create a new task in Asana.
    
    This endpoint receives task data from n8n and creates a corresponding
    task in Asana with appropriate prioritization and metadata.
    """
    if not ASANA_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asana integration not configured. ASANA_TOKEN missing."
        )
    
    # Prepare task data
    task_name = _format_task_name(task)
    task_notes = _format_task_notes(task)
    
    # Build Asana task payload
    asana_task = {
        "data": {
            "name": task_name,
            "notes": task_notes,
            "projects": [ASANA_PROJECT_ID] if ASANA_PROJECT_ID else [],
        }
    }
    
    # Add workspace if project not specified
    if ASANA_WORKSPACE_ID and not ASANA_PROJECT_ID:
        asana_task["data"]["workspace"] = ASANA_WORKSPACE_ID
    
    # Add assignee if provided
    if task.assignee:
        asana_task["data"]["assignee"] = task.assignee
    
    # Add due date (from request or calculated from urgency)
    due_date = task.due_date or _get_due_date_from_urgency(task.urgency)
    if due_date:
        asana_task["data"]["due_on"] = due_date
    
    # Add tags (optional - will be created if they don't exist, or skip if API fails)
    # Note: Asana requires tag GIDs, not names. For now, we skip auto-tagging.
    # You can manually create tags in Asana: password_reset, software_issue, hardware_issue, 
    # access_request, urgency_low, urgency_medium, urgency_high, urgency_critical
    tags = task.tags or []
    if tags:
        # Only add tags if explicitly provided (must be valid tag GIDs)
        asana_task["data"]["tags"] = tags
    
    logger.info(f"Creating Asana task: {task_name}")
    logger.debug(f"Asana payload: {asana_task}")
    
    # Call Asana API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ASANA_API_BASE}/tasks",
                headers={
                    "Authorization": f"Bearer {ASANA_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json=asana_task,
                timeout=30.0
            )
            
            response.raise_for_status()
            asana_data = response.json()

            task_id = asana_data.get("data", {}).get("gid")
            task_url = f"https://app.asana.com/0/{ASANA_PROJECT_ID}/{task_id}" if ASANA_PROJECT_ID else None

            # Re-fetch the task to get auto-populated custom fields (e.g. ID auto-number)
            if task_id:
                try:
                    refetch = await client.get(
                        f"{ASANA_API_BASE}/tasks/{task_id}?opt_fields=custom_fields,custom_fields.display_value,custom_fields.name",
                        headers={
                            "Authorization": f"Bearer {ASANA_TOKEN}",
                            "Accept": "application/json"
                        },
                        timeout=10.0
                    )
                    refetch.raise_for_status()
                    refetch_data = refetch.json()
                    # Merge updated custom_fields into original response
                    if "data" in refetch_data and "custom_fields" in refetch_data["data"]:
                        asana_data["data"]["custom_fields"] = refetch_data["data"]["custom_fields"]
                except Exception as e:
                    logger.warning(f"Failed to re-fetch task custom fields: {e}")

            logger.info(f"Task created successfully: {task_id}")

            return TaskResponse(
                success=True,
                task_id=task_id,
                task_url=task_url,
                message="Task created successfully in Asana",
                created_at=datetime.utcnow().isoformat() + "Z",
                asana_response=asana_data
            )
            
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            logger.error(f"Asana API error: {e.response.status_code} - {error_detail}")
            
            # Try to parse Asana error
            try:
                error_json = e.response.json()
                if "errors" in error_json:
                    error_messages = [err.get("message", "Unknown error") for err in error_json["errors"]]
                    error_detail = "; ".join(error_messages)
            except:
                pass
            
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Asana API error: {error_detail}"
            )
            
        except httpx.RequestError as e:
            logger.error(f"Network error calling Asana API: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Network error communicating with Asana: {str(e)}"
            )


@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "PEC Assist - Asana Task Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "create_task": "POST /tasks"
        },
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
