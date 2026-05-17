"""
Unit tests for Email Task Service business logic.
"""

import asyncio
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
        text, html = format_auto_reply(
            classification=classification,
            from_name="Alice Smith",
            ticket_id="ID-49",
            task_name="🟠 [Password Reset] Reset for Alice",
            due_on="2026-05-20",
            due_at=None,
        )
        assert "Password Reset" in text
        assert "HIGH" in text
        assert "ID-49" in text
        assert "Hello Alice," in text
        assert "<html" in html.lower()
        assert "ID-49" in html
        assert "cid:peclogo" in html

    def test_without_task(self):
        classification = {
            "intent": "general_inquiry",
            "urgency": "low",
            "summary": "Just saying hello",
        }
        text, html = format_auto_reply(
            classification=classification,
            from_name=None,
            ticket_id=None,
            task_name=None,
            due_on=None,
            due_at=None,
        )
        assert "General Inquiry" in text
        assert "does not require a ticket" in text
        assert "Hello," in text  # no first name → generic greeting
        assert "does not require a ticket" in html


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
        result = asyncio.run(classifier.classify("test", "body", "Name", "email@test.com"))
        assert result["intent"] == "general_inquiry"
        assert result["requires_task"] is True

    def test_mock_asana_client(self):
        client = AsanaTaskClient(mock=True)
        result = asyncio.run(client.create_task({"title": "test"}))
        assert result["success"] is True
        assert "mock-task" in result["task_id"]

    def test_mock_smtp_sender(self):
        sender = SMTPEmailSender(mock=True)
        result = asyncio.run(sender.send_reply("to@test.com", "Subject", text_body="Body"))
        assert result["status"] == "Mock sent"
