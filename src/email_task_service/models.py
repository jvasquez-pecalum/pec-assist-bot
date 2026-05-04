"""
Pydantic models for the Email Task Service.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class EmailTaskRequest(BaseModel):
    """Legacy model — kept for compatibility."""
    subject: str = Field(..., max_length=500)
    body: Optional[str] = Field(None, max_length=50000)
    from_name: Optional[str] = Field(None, max_length=200)
    from_email: str = Field(..., max_length=254)
    message_id: Optional[str] = Field(None, max_length=255)


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    active_channel: str = "teams"
    imap_connected: bool = False
    last_poll_at: Optional[str] = None
    emails_processed_1h: int = 0


class ChannelConfig(BaseModel):
    channel_type: str
    is_active: bool
    updated_at: Optional[str] = None


class ToggleRequest(BaseModel):
    channel: str = Field(..., pattern="^(teams|email)$")


class SimulationRequest(BaseModel):
    subject: str = Field(..., max_length=500)
    body: Optional[str] = Field(None, max_length=50000)
    from_name: Optional[str] = Field(None, max_length=200)
    from_email: str = Field(..., max_length=254)
    message_id: Optional[str] = Field(None, max_length=255)


class SimulationResponse(BaseModel):
    correlation_id: str
    classification: Optional[dict] = None
    asana_payload: Optional[dict] = None
    asana_response: Optional[dict] = None
    reply_body: Optional[str] = None
    errors: list[str] = []
    duration_ms: int = 0


class DiagnosticsResponse(BaseModel):
    service: str
    timestamp: str
    version: str
    env_sanity: dict
    imap_state: dict
    supabase_ping: dict
    asana_service_ping: dict
    smtp_ping: dict
    last_processed_emails: list[Any]
    last_errors: list[Any]
