"""
Email Task Service — FastAPI application.
Email-channel logic: LLM classification, Asana task creation, and SMTP auto-replies.
Triggered externally (e.g. by n8n) via /email/simulate — no background IMAP polling.
"""

import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from models import (
    EmailTaskRequest,
    HealthResponse,
    ChannelConfig,
    ToggleRequest,
    SimulationRequest,
    SimulationResponse,
    DiagnosticsResponse,
)
import httpx
from services import (
    Config,
    EmailPipeline,
    OpenAIClassifier,
    AsanaTaskClient,
    SMTPEmailSender,
    SupabaseConfigManager,
    build_asana_task_payload,
    format_auto_reply,
    ring_handler,
    logger as svc_logger,
    get_logger,
)

# ---------------------------------------------------------------------------
# App config & logging
# ---------------------------------------------------------------------------

config = Config()
logger = get_logger(__name__)

# Shared pipeline instance (injectable for tests)
pipeline: Optional[EmailPipeline] = None

# Runtime stats
_stats = {
    "last_poll_at": None,
    "emails_processed_1h": 0,
    "last_errors": [],
    "last_processed": [],
}


def _record_processed(email: dict, result: dict, correlation_id: str):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "from_email": email.get("from_email"),
        "subject": email.get("subject"),
        "intent": result.get("classification", {}).get("intent") if result.get("classification") else None,
        "requires_task": result.get("classification", {}).get("requires_task") if result.get("classification") else None,
        "asana_task_id": result.get("asana_response", {}).get("task_id") if result.get("asana_response") else None,
        "reply_sent": result.get("reply_sent"),
        "error": result.get("error"),
    }
    _stats["last_processed"].append(entry)
    if len(_stats["last_processed"]) > 20:
        _stats["last_processed"].pop(0)
    _stats["emails_processed_1h"] += 1


def _record_error(error: str, correlation_id: Optional[str] = None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "error": error,
    }
    _stats["last_errors"].append(entry)
    if len(_stats["last_errors"]) > 20:
        _stats["last_errors"].pop(0)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline

    logger.info("Starting Email Task Service (queue-driven, no IMAP poll)")

    # Build injectable services
    classifier = OpenAIClassifier(mock=config.mock_openai)
    asana_client = AsanaTaskClient(mock=config.mock_asana)
    email_sender = SMTPEmailSender(mock=config.mock_smtp)
    config_manager = SupabaseConfigManager()

    pipeline = EmailPipeline(
        classifier=classifier,
        asana_client=asana_client,
        email_sender=email_sender,
        config_manager=config_manager,
        imap_client=None,
    )

    yield

    logger.info("Shutting down Email Task Service")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PEC Assist — Email Task Service",
    description="FastAPI service for email-based Asana ticket creation (queue-driven)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/email/health", response_model=HealthResponse)
async def health_check():
    """Health check with runtime stats."""
    active_channel = "teams"
    try:
        cfg = await pipeline.config_manager.get_config()
        active_channel = "email" if cfg.get("email") else "teams"
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_channel=active_channel,
        imap_connected=False,
        last_poll_at=_stats.get("last_poll_at"),
        emails_processed_1h=_stats.get("emails_processed_1h", 0),
    )


@app.get("/email/config")
async def get_config():
    """Get current channel toggle state."""
    try:
        cfg = await pipeline.config_manager.get_config()
        return {
            "teams": cfg.get("teams", False),
            "email": cfg.get("email", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to read config: {e}",
        )


@app.post("/email/config/toggle")
async def toggle_channel(req: ToggleRequest):
    """Toggle active channel. Enforces mutual exclusivity."""
    try:
        result = await pipeline.config_manager.toggle(req.channel)
        return {
            "success": True,
            "config": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Toggle failed: {e}",
        )


@app.get("/email/logs")
async def get_logs(
    lines: int = Query(default=100, ge=1, le=500),
    fmt: str = Query(default="json", pattern="^(json|text)$"),
):
    """Return last N log lines from the in-memory ring buffer."""
    log_lines = ring_handler.get_lines(lines, fmt)
    return {"lines": log_lines, "count": len(log_lines)}


@app.get("/email/diagnostics")
async def get_diagnostics():
    """Full diagnostic snapshot."""
    now = datetime.now(timezone.utc).isoformat()

    # Env sanity (redact secrets)
    env_sanity = {
        "ASANA_SERVICE_URL_set": bool(config.asana_service_url),
        "OPENAI_API_KEY_set": bool(config.openai_api_key),
        "SMTP_HOST": config.smtp_host,
        "SMTP_PORT": config.smtp_port,
        "EMAIL_SOURCE": "queue-driven (no IMAP poll)",
        "IMAP_HOST": config.imap_host,
        "IMAP_USER": config.imap_user,
        "IMAP_PASSWORD_set": bool(config.imap_password),
        "GRAPH_CLIENT_ID_set": bool(config.graph_client_id),
        "SUPABASE_URL_set": bool(config.supabase_url),
        "SUPABASE_KEY_set": bool(config.supabase_service_key),
        "TEST_MODE": config.test_mode,
        "SKIP_CHANNEL_CHECK": config.skip_channel_check,
    }

    # Ping Supabase
    supabase_ping = {"ok": False, "latency_ms": None}
    try:
        start = datetime.now(timezone.utc)
        await pipeline.config_manager.get_config()
        supabase_ping = {"ok": True, "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000)}
    except Exception as e:
        supabase_ping["error"] = str(e)

    # Ping Asana service
    asana_ping = {"ok": False, "latency_ms": None}
    try:
        start = datetime.now(timezone.utc)
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{config.asana_service_url}/health")
            asana_ping = {"ok": r.status_code == 200, "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000)}
    except Exception as e:
        asana_ping["error"] = str(e)

    # Ping SMTP (lightweight: just check config)
    smtp_ping = {"ok": False}
    try:
        if config.smtp_host and config.imap_password:
            smtp_ping = {"ok": True}
        else:
            smtp_ping["error"] = "SMTP_HOST or IMAP_PASSWORD not configured"
    except Exception as e:
        smtp_ping["error"] = str(e)

    return DiagnosticsResponse(
        service="email-task",
        timestamp=now,
        version="1.0.0",
        env_sanity=env_sanity,
        imap_state={
            "connected": False,
            "last_poll": _stats.get("last_poll_at"),
            "host": config.imap_host,
            "user": config.imap_user,
        },
        supabase_ping=supabase_ping,
        asana_service_ping=asana_ping,
        smtp_ping=smtp_ping,
        last_processed_emails=_stats.get("last_processed", [])[-5:],
        last_errors=_stats.get("last_errors", [])[-5:],
    )


@app.post("/email/simulate", response_model=SimulationResponse)
async def simulate_email(req: SimulationRequest):
    """Run a test email through the full pipeline without IMAP."""
    import time
    start_time = time.time()
    corr_id = f"sim-{uuid.uuid4().hex[:8]}"

    email = {
        "subject": req.subject,
        "body": req.body,
        "from_name": req.from_name,
        "from_email": req.from_email,
        "message_id": req.message_id,
    }

    errors = []
    classification = None
    asana_payload = None
    asana_response = None
    reply_body = None

    try:
        classification = await pipeline.classifier.classify(
            subject=email["subject"],
            body=email.get("body"),
            from_name=email.get("from_name"),
            from_email=email["from_email"],
        )
    except Exception as e:
        errors.append(f"Classification: {e}")

    if classification and classification.get("requires_task", True):
        asana_payload = build_asana_task_payload(
            subject=email["subject"],
            body=email.get("body"),
            from_name=email.get("from_name"),
            from_email=email["from_email"],
            classification=classification,
            message_id=email["message_id"],
        )
        try:
            asana_response = await pipeline.asana_client.create_task(asana_payload)
        except Exception as e:
            errors.append(f"Asana: {e}")

    if classification:
        asana_url = asana_response.get("task_url") if asana_response else None
        reply_body = format_auto_reply(classification, asana_url)
        try:
            await pipeline.email_sender.send_reply(
                to_email=email["from_email"],
                subject=email["subject"],
                body=reply_body,
            )
        except Exception as e:
            errors.append(f"Reply: {e}")

    duration_ms = int((time.time() - start_time) * 1000)

    return SimulationResponse(
        correlation_id=corr_id,
        classification=classification,
        asana_payload=asana_payload,
        asana_response=asana_response,
        reply_body=reply_body,
        errors=errors,
        duration_ms=duration_ms,
    )


@app.get("/")
async def root():
    return {
        "service": "PEC Assist — Email Task Service",
        "version": "1.0.0",
        "mode": "queue-driven (no IMAP poll)",
        "endpoints": {
            "health": "GET /email/health",
            "config": "GET /email/config",
            "toggle": "POST /email/config/toggle",
            "logs": "GET /email/logs",
            "diagnostics": "GET /email/diagnostics",
            "simulate": "POST /email/simulate",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("EMAIL_SERVICE_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
