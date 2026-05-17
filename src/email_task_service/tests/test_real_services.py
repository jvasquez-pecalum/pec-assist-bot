"""
Real-service integration tests — all mocks disabled.

Run with:
    pytest -m real_services -v

Requires the production .env to be present with:
    MOCK_OPENAI=false  MOCK_ASANA=false  MOCK_SMTP=false
"""

import os
import pytest
import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import (
    OpenAIClassifier,
    AsanaTaskClient,
    SMTPEmailSender,
    build_asana_task_payload,
)

VALID_INTENTS = {
    "password_reset", "software_issue", "hardware_issue", "access_request",
    "general_support", "other",
    "data_engineering", "business_reports", "business_intelligence",
    "ai_initiatives", "general_inquiry",
}
VALID_URGENCIES = {"low", "medium", "high", "critical"}


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

@pytest.mark.real_services
async def test_openai_classifier_returns_valid_classification():
    """OpenAI GPT-4o-mini returns a well-formed classification for a real email."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    classifier = OpenAIClassifier(api_key=api_key, mock=False)
    result = await classifier.classify(
        subject="Forgot my password and can't log in",
        body="Hi, I cannot access my account since this morning. My password stopped working after the weekend. Please help.",
        from_name="Test User",
        from_email="testuser@pecalum.com",
    )

    assert isinstance(result, dict), "Response must be a dict"
    assert result.get("intent") in VALID_INTENTS, f"Unexpected intent: {result.get('intent')}"
    assert result.get("urgency") in VALID_URGENCIES, f"Unexpected urgency: {result.get('urgency')}"
    assert isinstance(result.get("requires_task"), bool), "requires_task must be a bool"
    assert isinstance(result.get("summary"), str) and result["summary"], "summary must be a non-empty string"
    assert result.get("response_tone") in {"professional", "friendly", "urgent"}, \
        f"Unexpected tone: {result.get('response_tone')}"


# ---------------------------------------------------------------------------
# Asana
# ---------------------------------------------------------------------------

@pytest.mark.real_services
async def test_asana_task_client_creates_task():
    """AsanaTaskClient POSTs to the real asana-task service and gets a task_id back."""
    service_url = os.getenv("ASANA_SERVICE_URL", "http://asana-task:8000")

    # Try configured URL first, then localhost fallback for local development
    async with httpx.AsyncClient(timeout=5.0) as probe:
        try:
            await probe.get(f"{service_url}/health")
        except (httpx.ConnectError, httpx.TimeoutException):
            # Fallback to localhost if Docker hostname doesn't resolve
            if "asana-task" in service_url:
                service_url = service_url.replace("asana-task", "localhost")
                try:
                    await probe.get(f"{service_url}/health")
                except (httpx.ConnectError, httpx.TimeoutException):
                    pytest.skip(f"Asana service unreachable at configured and fallback URLs")

    client = AsanaTaskClient(service_url=service_url, mock=False)
    payload = build_asana_task_payload(
        subject="[REAL-SVC-TEST] Monitor not turning on",
        body="My monitor is black since this morning.",
        from_name="Real Test",
        from_email="realtest@pecalum.com",
        classification={
            "intent": "hardware_issue",
            "urgency": "medium",
            "summary": "Monitor not turning on — real service test",
        },
        message_id="real-svc-test-001",
    )

    result = await client.create_task(payload)

    assert result.get("success") is True, f"Expected success=True, got: {result}"
    assert result.get("task_id"), "task_id must be present and non-empty"
    assert result.get("task_url"), "task_url must be present"


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

@pytest.mark.real_services
async def test_smtp_sender_delivers_email():
    """SMTPEmailSender sends a real email via Office 365 and reports 'Sent via SMTP'."""
    password = os.getenv("IMAP_PASSWORD")
    if not password:
        pytest.skip("IMAP_PASSWORD not set — SMTP auth requires it")

    sender = SMTPEmailSender(mock=False)
    recipient = os.getenv("SENDER_ADDRESS", "pec.assist@pecalum.com")

    result = await sender.send_reply(
        to_email=recipient,
        subject="[REAL-SVC-TEST] Email Task Service SMTP check",
        text_body=(
            "This is an automated real-service test sent by test_real_services.py.\n"
            "MOCK_SMTP=false was confirmed working if you are reading this."
        ),
    )

    assert result.get("status") == "Sent via SMTP", f"Unexpected status: {result}"
    assert result.get("message_id", "").startswith("smtp-"), \
        f"message_id format unexpected: {result.get('message_id')}"
