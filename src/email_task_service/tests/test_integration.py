"""
Integration tests for the Email Task Service.
Run with: TEST_MODE=true MOCK_OPENAI=true MOCK_SMTP=true MOCK_ASANA=true pytest -m integration -v
"""

import pytest
from httpx import AsyncClient
from main import app


@pytest.mark.integration
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/email/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.integration
async def test_simulate_email():
    payload = {
        "subject": "Test integration",
        "body": "This is a test email for integration testing.",
        "from_name": "Integration Test",
        "from_email": "test@example.com",
        "message_id": "int-test-001",
    }
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/email/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["correlation_id"].startswith("sim-")
    assert data["classification"] is not None
    assert len(data["errors"]) == 0
