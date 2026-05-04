"""
Business logic for the Email Task Service.
All external dependencies are injectable for testability.
"""

import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

import httpx
import msal
from imap_tools import MailBox, AND

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """JSON-structured log formatter with correlation_id support."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        if hasattr(record, "extra"):
            log_obj["extra"] = record.extra
        return json.dumps(log_obj, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable console formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        corr = getattr(record, "correlation_id", None)
        corr_str = f" | corr={corr}" if corr else ""
        return f"[{ts}] {record.levelname:8s} {record.name:20s} | {record.getMessage()}{corr_str}"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        if os.getenv("LOG_FORMAT", "").lower() == "text":
            handler.setFormatter(TextFormatter())
        else:
            handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Ring-buffer log handler for /email/logs endpoint
# ---------------------------------------------------------------------------


class RingBufferHandler(logging.Handler):
    """In-memory ring buffer of the last N log records."""

    def __init__(self, capacity: int = 500):
        super().__init__()
        self.capacity = capacity
        self._buffer: list[logging.LogRecord] = []
        import threading
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) > self.capacity:
                self._buffer.pop(0)

    def get_lines(self, count: int, fmt: str = "json") -> list[str]:
        with self._lock:
            records = self._buffer[-count:]
        if fmt == "text":
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            return [formatter.format(r) for r in records]
        formatter = JsonFormatter()
        return [formatter.format(r) for r in records]


ring_handler = RingBufferHandler(capacity=500)
root_logger = logging.getLogger()
root_logger.addHandler(ring_handler)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment."""
    asana_service_url: str = os.getenv("ASANA_SERVICE_URL", "http://asana-task:8000")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    sender_address: str = os.getenv("SENDER_ADDRESS", "pec.assist@pecalum.com")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.office365.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    imap_host: str = os.getenv("IMAP_HOST", "outlook.office365.com")
    imap_port: int = int(os.getenv("IMAP_PORT", "993"))
    imap_user: str = os.getenv("IMAP_USER", "pec.assist@pecalum.com")
    imap_password: Optional[str] = os.getenv("IMAP_PASSWORD")
    poll_interval_seconds: int = int(os.getenv("IMAP_POLL_INTERVAL_SECONDS", "60"))
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_service_key: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY")
    test_mode: bool = os.getenv("TEST_MODE", "").lower() in ("true", "1", "yes")
    mock_openai: bool = os.getenv("MOCK_OPENAI", "").lower() in ("true", "1", "yes")
    mock_smtp: bool = os.getenv("MOCK_SMTP", "").lower() in ("true", "1", "yes")
    mock_asana: bool = os.getenv("MOCK_ASANA", "").lower() in ("true", "1", "yes")
    skip_channel_check: bool = os.getenv("SKIP_CHANNEL_CHECK", "").lower() in ("true", "1", "yes")
    # Microsoft Graph API credentials (alternative to IMAP for Office 365)
    graph_client_id: Optional[str] = os.getenv("GRAPH_CLIENT_ID")
    graph_client_secret: Optional[str] = os.getenv("GRAPH_CLIENT_SECRET")
    graph_tenant_id: Optional[str] = os.getenv("GRAPH_TENANT_ID")
    # Webhook security
    webhook_api_key: Optional[str] = os.getenv("WEBHOOK_API_KEY")

    @property
    def use_graph_api(self) -> bool:
        return bool(self.graph_client_id and self.graph_client_secret and self.graph_tenant_id)


# ---------------------------------------------------------------------------
# Classification prompt (same pattern as PEC-Classifier)
# ---------------------------------------------------------------------------

CLASSIFICATION_PROMPT = """You are an IT support classifier for PEC Aluminum. Analyze the email and classify it EXACTLY as follows:

EMAIL SUBJECT: {subject}
EMAIL BODY: {body}
SENDER: {from_name} <{from_email}>

CLASSIFICATION RULES:
1. password_reset: Forgotten passwords, can't login, password expired, account locked
2. software_issue: App crashes, errors, bugs, software not working
3. hardware_issue: Computer won't start, broken screen, mouse/keyboard not working
4. access_request: Need permissions, access to folders, new software license
5. data_engineering: ETL failures, data pipelines
6. business_reports: Report generation, scheduling
7. business_intelligence: Dashboard issues, KPI queries
8. ai_initiatives: AI/ML requests, automation
9. general_inquiry: Questions about policies, how-to, greetings

URGENCY RULES:
- critical: User cannot work at all
- high: Significant impact (meeting in <1 hour, urgent deadline)
- medium: Work impacted but workaround exists
- low: General questions, no immediate impact

Respond with ONLY this JSON format (no markdown):
{{"intent": "...", "urgency": "low|medium|high|critical", "summary": "...", "requires_task": true|false, "response_tone": "professional|friendly|urgent"}}
"""

# ---------------------------------------------------------------------------
# Pure functions (stateless, easily testable)
# ---------------------------------------------------------------------------


def build_classification_prompt(subject: str, body: Optional[str], from_name: Optional[str], from_email: str) -> str:
    return CLASSIFICATION_PROMPT.format(
        subject=subject,
        body=body or "",
        from_name=from_name or from_email,
        from_email=from_email,
    )


def parse_classification_response(raw: str) -> dict:
    """Extract JSON from OpenAI response, with graceful fallback."""
    text = raw.strip()
    # Remove markdown fences if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def format_auto_reply(classification: dict, asana_task_url: Optional[str]) -> str:
    """Format the auto-reply email body."""
    intent_display = classification.get("intent", "request").replace("_", " ").title()
    urgency = classification.get("urgency", "medium").upper()
    summary = classification.get("summary", "Your request has been received.")

    lines = [
        f"Hello,",
        "",
        f"Thank you for contacting PEC Assist. We have received your {intent_display} request.",
        "",
        f"Summary: {summary}",
        f"Priority: {urgency}",
    ]

    if asana_task_url:
        lines.extend([
            "",
            f"Ticket: {asana_task_url}",
        ])
    else:
        lines.extend([
            "",
            "Your request does not require a ticket at this time, but our team will review it.",
        ])

    lines.extend([
        "",
        "---",
        "This is an automated response from PEC Assist.",
    ])

    return "\n".join(lines)


def build_asana_task_payload(
    subject: str,
    body: Optional[str],
    from_name: Optional[str],
    from_email: str,
    classification: dict,
    message_id: str,
) -> dict:
    """Build the payload for the existing Asana Task Service."""
    intent = classification.get("intent", "general_inquiry")
    urgency = classification.get("urgency", "medium")
    summary = classification.get("summary", "")

    return {
        "title": subject,
        "description": body,
        "intent": intent,
        "urgency": urgency,
        "summary": summary,
        "sender_name": from_name or from_email,
        "sender_email": from_email,
        "message_id": message_id,
        "chat_id": None,  # Not applicable for email channel
    }


# ---------------------------------------------------------------------------
# Injectable service classes
# ---------------------------------------------------------------------------


class OpenAIClassifier:
    """Classifies emails using OpenAI GPT-4o-mini."""

    def __init__(self, api_key: Optional[str] = None, mock: bool = False):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.mock = mock
        self.base_url = "https://api.openai.com/v1/chat/completions"

    async def classify(self, subject: str, body: Optional[str], from_name: Optional[str], from_email: str) -> dict:
        if self.mock:
            return {
                "intent": "general_inquiry",
                "urgency": "medium",
                "summary": "Mock classification result",
                "requires_task": True,
                "response_tone": "professional",
            }

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")

        prompt = build_classification_prompt(subject, body, from_name, from_email)
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are an IT support classifier."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 300,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            return parse_classification_response(raw_content)


class AsanaTaskClient:
    """Client for the existing Asana Task Service."""

    def __init__(self, service_url: Optional[str] = None, mock: bool = False):
        self.service_url = service_url or os.getenv("ASANA_SERVICE_URL", "http://asana-task:8000")
        self.mock = mock

    async def create_task(self, payload: dict) -> dict:
        if self.mock:
            return {
                "success": True,
                "task_id": "mock-task-123",
                "task_url": "https://app.asana.com/0/mock/123",
                "message": "Mock task created",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.service_url}/tasks",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()


class SMTPEmailSender:
    """Sends emails via SMTP (self-contained, no external SaaS)."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        sender_address: Optional[str] = None,
        mock: bool = False,
    ):
        self.host = host or os.getenv("SMTP_HOST", "smtp.office365.com")
        self.port = port or int(os.getenv("SMTP_PORT", "587"))
        self.user = user or os.getenv("IMAP_USER", "pec.assist@pecalum.com")
        self.password = password or os.getenv("IMAP_PASSWORD")
        self.sender_address = sender_address or os.getenv("SENDER_ADDRESS", self.user or "pec.assist@pecalum.com")
        self.mock = mock

    async def send_reply(self, to_email: str, subject: str, body: str) -> dict:
        if self.mock:
            return {"message_id": "mock-smtp-reply", "status": "Mock sent"}

        if not self.password:
            raise RuntimeError("IMAP_PASSWORD not configured (required for SMTP auth)")

        from email.mime.text import MIMEText
        from email.utils import formatdate
        import aiosmtplib

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"Re: {subject}"
        msg["From"] = self.sender_address
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg["Reply-To"] = self.sender_address

        await aiosmtplib.send(
            msg,
            hostname=self.host,
            port=self.port,
            start_tls=True,
            username=self.user,
            password=self.password,
            timeout=30,
        )

        return {"message_id": f"smtp-{datetime.now(timezone.utc).isoformat()}", "status": "Sent via SMTP"}


class SupabaseConfigManager:
    """Manages channel toggle state in Supabase."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY")
        self.headers = {}
        if self.supabase_key:
            self.headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }

    async def get_config(self) -> dict:
        if not self.supabase_url or not self.supabase_key:
            logger.info("Supabase not configured — using fallback channel config (teams=true, email=false)")
            return {"teams": True, "email": False}

        url = f"{self.supabase_url}/rest/v1/channel_config?select=*"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
            except httpx.ConnectError as e:
                logger.error(f"Supabase connection failed — cannot reach {self.supabase_url}. "
                             f"Check SUPABASE_URL or set SKIP_CHANNEL_CHECK=true for local testing. Error: {e}")
                return {"teams": True, "email": False}
            except httpx.HTTPStatusError as e:
                logger.error(f"Supabase returned error {e.response.status_code}. "
                             f"Check SUPABASE_SERVICE_KEY is correct.")
                return {"teams": True, "email": False}

            rows = response.json()
            result = {}
            for row in rows:
                result[row.get("channel_type")] = row.get("is_active", False)
            return result

    async def is_channel_active(self, channel: str) -> bool:
        config = await self.get_config()
        return config.get(channel, False)

    async def toggle(self, target_channel: str) -> dict:
        if target_channel not in ("teams", "email"):
            raise ValueError("channel must be 'teams' or 'email'")

        if not self.supabase_url or not self.supabase_key:
            raise RuntimeError("Supabase not configured")

        # Update target to true, other to false (mutual exclusivity)
        other = "email" if target_channel == "teams" else "teams"
        updates = [
            {"channel_type": target_channel, "is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()},
            {"channel_type": other, "is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()},
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            for upd in updates:
                url = f"{self.supabase_url}/rest/v1/channel_config?channel_type=eq.{upd['channel_type']}"
                response = await client.patch(url, headers=self.headers, json=upd)
                response.raise_for_status()

        return await self.get_config()

    async def get_email_request(self, message_id: str) -> Optional[dict]:
        """Check if an email has already been processed by message_id."""
        if not self.supabase_url or not self.supabase_key:
            return None

        url = f"{self.supabase_url}/rest/v1/email_requests?message_id=eq.{message_id}&select=*"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                logger.warning("Failed to query email request", extra={"status": response.status_code, "body": response.text})
                return None
            rows = response.json()
            return rows[0] if rows else None

    async def record_email_request(self, data: dict) -> None:
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase not configured, skipping email request logging")
            return

        # Upsert on message_id to avoid unique-constraint failures on re-processing
        url = f"{self.supabase_url}/rest/v1/email_requests?on_conflict=message_id"
        upsert_headers = {**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=upsert_headers, json=data)
            if response.status_code >= 400:
                logger.error("Failed to log email request", extra={"status": response.status_code, "body": response.text})


class IMAPClient:
    """Polls an IMAP inbox for unread emails."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host or os.getenv("IMAP_HOST", "outlook.office365.com")
        self.port = port or int(os.getenv("IMAP_PORT", "993"))
        self.user = user or os.getenv("IMAP_USER", "pec.assist@pecalum.com")
        self.password = password or os.getenv("IMAP_PASSWORD")

    def fetch_unread(self):
        """Generator yielding unread email dicts."""
        if not self.password:
            raise RuntimeError("IMAP_PASSWORD not configured")

        logger.info(f"Connecting to IMAP {self.host}:{self.port} as {self.user}...")
        with MailBox(self.host, port=self.port).login(self.user, self.password) as mailbox:
            for msg in mailbox.fetch(AND(seen=False), mark_seen=False):
                # imap_tools provides parsed from_values; fall back to raw from_ if unavailable
                from_name = msg.from_values.name if msg.from_values else (msg.from_ or "")
                from_email = msg.from_values.email if msg.from_values else (msg.from_ or "")
                yield {
                    "subject": msg.subject or "",
                    "body": msg.text or "",
                    "from_name": from_name,
                    "from_email": from_email,
                    "message_id": msg.uid or str(uuid.uuid4()),
                    "received_at": msg.date.isoformat() if msg.date else datetime.now(timezone.utc).isoformat(),
                }

    def mark_seen(self, message_id: str) -> None:
        """Mark a specific email as seen by UID."""
        if not self.password:
            return
        with MailBox(self.host, port=self.port).login(self.user, self.password) as mailbox:
            # imap_tools uses UIDs; message_id in our context is the UID
            mailbox.client.uid("STORE", message_id, "+FLAGS", "(\\Seen)")


class GraphEmailClient:
    """Reads emails via Microsoft Graph API instead of IMAP.

    Uses client-credentials flow (application permissions) to access
    a specific user's mailbox. Requires admin consent for Mail.Read.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_email: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("GRAPH_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("GRAPH_CLIENT_SECRET", "")
        self.tenant_id = tenant_id or os.getenv("GRAPH_TENANT_ID", "")
        self.user_email = user_email or os.getenv("IMAP_USER", "pec.assist@pecalum.com")
        self.password = password or os.getenv("IMAP_PASSWORD", "")
        self.scopes = ["https://graph.microsoft.com/Mail.Read"]

        if not all([self.client_id, self.client_secret, self.tenant_id, self.user_email, self.password]):
            raise RuntimeError(
                "GraphEmailClient requires GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID, IMAP_USER, and IMAP_PASSWORD"
            )

        self._app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )

    def _get_token(self) -> str:
        """Acquire or reuse an access token for Graph API via ROPC."""
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(self.scopes, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]

        result = self._app.acquire_token_by_username_password(
            username=self.user_email,
            password=self.password,
            scopes=self.scopes,
        )
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "unknown"))
            raise RuntimeError(f"Graph token acquisition failed: {error}")
        return result["access_token"]

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Minimal HTML-to-text conversion for email bodies."""
        import re
        text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse multiple blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def fetch_unread(self):
        """Generator yielding unread email dicts from Graph API."""
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "outlook.body-content-type=text",
        }
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/messages"
        params = {
            "$filter": "isRead eq false",
            "$select": "id,subject,body,from,sender,receivedDateTime,internetMessageId",
            "$top": 50,
            "$orderby": "receivedDateTime desc",
        }

        logger.info(f"Graph API: fetching unread messages for {self.user_email}")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            messages = data.get("value", [])
            logger.info(f"Graph API: found {len(messages)} unread message(s)")

            for msg in messages:
                from_name = ""
                from_email = ""
                if msg.get("from") and msg["from"].get("emailAddress"):
                    from_name = msg["from"]["emailAddress"].get("name", "")
                    from_email = msg["from"]["emailAddress"].get("address", "")

                body = ""
                if msg.get("body"):
                    content = msg["body"].get("content", "")
                    if msg["body"].get("contentType") == "html":
                        body = self._html_to_text(content)
                    else:
                        body = content

                yield {
                    "subject": msg.get("subject", ""),
                    "body": body,
                    "from_name": from_name,
                    "from_email": from_email,
                    "message_id": msg.get("id"),  # Graph message ID
                    "received_at": msg.get("receivedDateTime", datetime.now(timezone.utc).isoformat()),
                }

    def mark_seen(self, message_id: str) -> None:
        """Mark a specific email as read via Graph API."""
        if not message_id:
            return
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = (
            f"https://graph.microsoft.com/v1.0/users/{self.user_email}"
            f"/messages/{message_id}"
        )
        logger.info(f"Graph API: marking message {message_id} as read")
        with httpx.Client(timeout=30.0) as client:
            response = client.patch(url, headers=headers, json={"isRead": True})
            response.raise_for_status()


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class EmailPipeline:
    """Orchestrates the full email → classification → Asana → reply flow."""

    def __init__(
        self,
        classifier: Optional[OpenAIClassifier] = None,
        asana_client: Optional[AsanaTaskClient] = None,
        email_sender: Optional[SMTPEmailSender] = None,
        config_manager: Optional[SupabaseConfigManager] = None,
        imap_client: Optional[IMAPClient] = None,
    ):
        self.classifier = classifier or OpenAIClassifier()
        self.asana_client = asana_client or AsanaTaskClient()
        self.email_sender = email_sender or SMTPEmailSender()
        self.config_manager = config_manager or SupabaseConfigManager()
        # Accepts IMAPClient or GraphEmailClient (duck-typed interface)
        self.imap_client = imap_client

    async def process_email(self, email: dict, correlation_id: str) -> dict:
        """Process a single email through the full pipeline."""
        result = {
            "correlation_id": correlation_id,
            "classification": None,
            "asana_response": None,
            "reply_sent": False,
            "error": None,
            "marked_seen": False,
        }

        # 0. Deduplication: skip if already processed
        try:
            existing = await self.config_manager.get_email_request(email["message_id"])
            if existing:
                logger.info("Email already processed, skipping", extra={"correlation_id": correlation_id, "message_id": email["message_id"]})
                result["error"] = "Already processed"
                return result
        except Exception as e:
            logger.warning("Dedup check failed, continuing", extra={"correlation_id": correlation_id, "error": str(e)})

        # 1. Check channel is active (skip if SKIP_CHANNEL_CHECK=true for local testing)
        if not await self.config_manager.is_channel_active("email"):
            if not os.getenv("SKIP_CHANNEL_CHECK", "").lower() in ("true", "1", "yes"):
                logger.info("Email channel inactive, skipping", extra={"correlation_id": correlation_id})
                result["error"] = "Channel inactive"
                return result
            logger.info("Email channel inactive, but SKIP_CHANNEL_CHECK is enabled — continuing", extra={"correlation_id": correlation_id})

        # 2. Classify
        try:
            classification = await self.classifier.classify(
                subject=email["subject"],
                body=email.get("body"),
                from_name=email.get("from_name"),
                from_email=email["from_email"],
            )
            result["classification"] = classification
            logger.info(
                "Classification complete",
                extra={"correlation_id": correlation_id, "intent": classification.get("intent"), "urgency": classification.get("urgency")},
            )
        except Exception as e:
            logger.error("Classification failed", extra={"correlation_id": correlation_id, "error": str(e)})
            result["error"] = f"Classification failed: {e}"
            return result

        # 3. Create Asana task if required
        asana_task_url = None
        if classification.get("requires_task", True):
            try:
                payload = build_asana_task_payload(
                    subject=email["subject"],
                    body=email.get("body"),
                    from_name=email.get("from_name"),
                    from_email=email["from_email"],
                    classification=classification,
                    message_id=email["message_id"],
                )
                asana_response = await self.asana_client.create_task(payload)
                result["asana_response"] = asana_response
                asana_task_url = asana_response.get("task_url")
                logger.info(
                    "Asana task created",
                    extra={"correlation_id": correlation_id, "task_id": asana_response.get("task_id")},
                )
            except Exception as e:
                logger.error("Asana task creation failed", extra={"correlation_id": correlation_id, "error": str(e)})
                result["error"] = f"Asana task creation failed: {e}"
                # Continue to send reply even if Asana fails

        # 4. Send auto-reply
        try:
            reply_body = format_auto_reply(classification, asana_task_url)
            await self.email_sender.send_reply(
                to_email=email["from_email"],
                subject=email["subject"],
                body=reply_body,
            )
            result["reply_sent"] = True
            logger.info("Auto-reply sent", extra={"correlation_id": correlation_id})
        except Exception as e:
            logger.error("Auto-reply failed", extra={"correlation_id": correlation_id, "error": str(e)})
            result["error"] = f"Auto-reply failed: {e}"

        # 5. Log to Supabase
        try:
            await self.config_manager.record_email_request({
                "message_id": email["message_id"],
                "from_email": email.get("from_email"),
                "from_name": email.get("from_name"),
                "subject": email["subject"],
                "intent": classification.get("intent"),
                "urgency": classification.get("urgency"),
                "summary": classification.get("summary"),
                "requires_task": classification.get("requires_task"),
                "asana_task_id": result["asana_response"].get("task_id") if result["asana_response"] else None,
                "asana_task_url": asana_task_url,
                "replied_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error("Failed to log email request", extra={"correlation_id": correlation_id, "error": str(e)})

        # 6. Mark email as seen so it is not re-processed
        if self.imap_client:
            try:
                self.imap_client.mark_seen(email["message_id"])
                result["marked_seen"] = True
                logger.info("Email marked as seen", extra={"correlation_id": correlation_id, "message_id": email["message_id"]})
            except Exception as e:
                logger.error("Failed to mark email as seen", extra={"correlation_id": correlation_id, "message_id": email["message_id"], "error": str(e)})

        return result
