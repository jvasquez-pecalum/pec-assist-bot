"""
Unit tests for Email Task Service business logic.
"""

import pytest
from services import (
    build_asana_task_payload,
    format_auto_reply,
    parse_classification_response,
    build_classification_prompt,
    OpenAIClassifier,
    AsanaTaskClient,
    SMTPEmailSender,
    SupabaseConfigManager,
)


class TestParseClassificationResponse:
    def test_clean_json(self):
        raw = '{"intent": "password_reset", "urgency": "high", "summary": "test", "requires_task": true, "response_tone": "urgent"}'
        result = parse_classification_response(raw)
        assert result["intent"] == "password_reset"
        assert result["urgency"] == "high"

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"intent": "general_inquiry", "urgency": "low", "summary": "test", "requires_task": false, "response_tone": "friendly"}\n```'
        result = parse_classification_response(raw)
        assert result["intent"] == "general_inquiry"
        assert result["requires_task"] is False

    def test_malformed_fallback(self):
        raw = 'Some text before {"intent": "software_issue", "urgency": "medium", "summary": "test", "requires_task": true, "response_tone": "professional"} some text after'
        result = parse_classification_response(raw)
        assert result["intent"] == "software_issue"


class TestFormatAutoReply:
    def test_with_task(self):
        classification = {
            "intent": "password_reset",
            "urgency": "high",
            "summary": "Forgot my password",
        }
        reply = format_auto_reply(classification, "https://app.asana.com/0/123/456")
        assert "Password Reset" in reply
        assert "HIGH" in reply
        assert "https://app.asana.com/0/123/456" in reply

    def test_without_task(self):
        classification = {
            "intent": "general_inquiry",
            "urgency": "low",
            "summary": "Just saying hello",
        }
        reply = format_auto_reply(classification, None)
        assert "General Inquiry" in reply
        assert "does not require a ticket" in reply


class TestBuildAsanaTaskPayload:
    def test_payload_structure(self):
        classification = {
            "intent": "hardware_issue",
            "urgency": "critical",
            "summary": "Monitor won't turn on",
        }
        payload = build_asana_task_payload(
            subject="Monitor broken",
            body="My monitor is black",
            from_name="Alice",
            from_email="alice@example.com",
            classification=classification,
            message_id="msg-123",
        )
        assert payload["title"] == "Monitor broken"
        assert payload["intent"] == "hardware_issue"
        assert payload["urgency"] == "critical"
        assert payload["sender_email"] == "alice@example.com"
        assert payload["message_id"] == "msg-123"
        assert payload["chat_id"] is None


class TestMockServices:
    def test_mock_classifier(self):
        classifier = OpenAIClassifier(mock=True)
        result = pytest.anyio.run(classifier.classify("test", "body", "Name", "email@test.com"))
        assert result["intent"] == "general_inquiry"
        assert result["requires_task"] is True

    def test_mock_asana_client(self):
        client = AsanaTaskClient(mock=True)
        result = pytest.anyio.run(client.create_task({"title": "test"}))
        assert result["success"] is True
        assert "mock-task" in result["task_id"]

    def test_mock_smtp_sender(self):
        sender = SMTPEmailSender(mock=True)
        result = pytest.anyio.run(sender.send_reply("to@test.com", "Subject", "Body"))
        assert result["status"] == "Mock sent"
