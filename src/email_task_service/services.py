"""
Business logic for the Email Task Service.
All external dependencies are injectable for testability.
"""

import os
import uuid
import json
import asyncio
import logging
import urllib.parse
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
    _level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logger.setLevel(_level)
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
9. general_support: General IT help, troubleshooting, how-to requests
10. general_inquiry: Questions about policies, greetings, non-IT topics
11. other: Anything that does not fit the above categories

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


def _logo_inline_images() -> dict[str, str]:
    """Return {cid: path} for the PEC logo.

    Looks in the service-local assets/ first (production / Docker), then falls
    back to the repo-root assets/ (local dev when running uvicorn from src/).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "assets", "pec-logo.png"),
        os.path.abspath(os.path.join(here, "..", "..", "assets", "pec-logo.png")),
    ]
    for path in candidates:
        if os.path.exists(path):
            return {"peclogo": path}
    return {}


_URGENCY_STYLE = {
    "critical": {"bg": "#dc2626", "fg": "#ffffff", "label": "CRITICAL"},
    "high":     {"bg": "#FFCC00", "fg": "#111111", "label": "HIGH"},
    "medium":   {"bg": "#F0F0F0", "fg": "#111111", "label": "MEDIUM"},
    "low":      {"bg": "#16a34a", "fg": "#ffffff", "label": "LOW"},
}


def _first_name(name: Optional[str]) -> Optional[str]:
    """Return the first token of a display name, or None if empty/missing."""
    if not name:
        return None
    token = name.strip().split()[0] if name.strip() else ""
    return token or None


def _format_eta(due_on: Optional[str], due_at: Optional[str]) -> Optional[str]:
    """Friendly ETA string matching what was committed to the Asana ticket."""
    if due_at:
        try:
            dt_utc = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        try:
            from zoneinfo import ZoneInfo
            tz_name = os.getenv("BUSINESS_TIMEZONE", "America/Los_Angeles")
            local = dt_utc.astimezone(ZoneInfo(tz_name))
            tz_abbrev = local.strftime("%Z") or "PT"
            hour_12 = local.strftime("%I").lstrip("0") or "12"
            time_str = f"{hour_12}:{local.strftime('%M %p')}"
            return f"Within 4 business hours (by {local.strftime('%a, %b %d')} · {time_str} {tz_abbrev})"
        except Exception:
            return f"Within 4 business hours (by {dt_utc.strftime('%a, %b %d %H:%M UTC')})"
    if due_on:
        try:
            d = datetime.strptime(due_on, "%Y-%m-%d").date()
        except ValueError:
            return None
        return f"By {d.strftime('%a, %b %d')}"
    return None


def format_auto_reply(
    classification: dict,
    from_name: Optional[str],
    ticket_id: Optional[str],
    task_name: Optional[str],
    due_on: Optional[str],
    due_at: Optional[str],
) -> tuple[str, str]:
    """Format the auto-reply as (text_body, html_body).

    `ticket_id` is the user-facing ID (e.g. "ID-49") returned by the Asana service.
    """
    intent_raw = classification.get("intent", "general_inquiry")
    intent_display = intent_raw.replace("_", " ").upper()
    urgency_raw = (classification.get("urgency") or "medium").lower()
    urgency_style = _URGENCY_STYLE.get(urgency_raw, _URGENCY_STYLE["medium"])
    summary = classification.get("summary", "Your request has been received.")

    first = _first_name(from_name)
    greeting = f"Hello {first}," if first else "Hello,"
    eta = _format_eta(due_on, due_at)

    text_lines = [
        greeting,
        "",
        f"Thank you for contacting PEC Assist. We have received your {intent_display.title()}.",
        "",
        f"Summary: {summary}",
        f"Priority: {urgency_style['label']}",
    ]
    if ticket_id:
        text_lines += ["", "Ticket:", f"  ID:    {ticket_id}", f"  Title: {task_name or '(unnamed)'}"]
    else:
        text_lines += ["", "Your request does not require a ticket; our team will review it."]
    if eta:
        text_lines += ["", f"Target response: {eta}"]
    text_lines += ["", "---", "This is an automated response from PEC Assist."]
    text_body = "\n".join(text_lines)

    html_body = _render_html_reply(
        greeting=greeting,
        intent_display=intent_display,
        urgency_style=urgency_style,
        summary=summary,
        ticket_id=ticket_id,
        task_name=task_name,
        eta=eta,
    )
    return text_body, html_body


def _esc(s: Optional[str]) -> str:
    """Minimal HTML escaping for text inserted into the template."""
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _render_html_reply(
    greeting: str,
    intent_display: str,
    urgency_style: dict,
    summary: str,
    ticket_id: Optional[str],
    task_name: Optional[str],
    eta: Optional[str],
) -> str:
    """Render the branded HTML auto-reply (table-based, inline CSS, email-safe)."""
    pe_black = "#111111"
    pe_yellow = "#FFCC00"
    pe_gray = "#F0F0F0"
    pe_darkgray = "#222222"
    font_stack = "Inter, -apple-system, 'Segoe UI', Arial, sans-serif"

    badge_bg = urgency_style["bg"]
    badge_fg = urgency_style["fg"]
    badge_label = urgency_style["label"]

    ticket_block = ""
    if ticket_id:
        ticket_block = f"""
        <tr>
          <td style="padding:0 32px 24px 32px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
                   style="border:3px solid {pe_black}; background-color:#ffffff;">
              <tr>
                <td style="padding:12px 16px; border-bottom:3px solid {pe_black}; background-color:{pe_yellow};
                           font-family:{font_stack}; font-size:12px; font-weight:900; letter-spacing:0.1em;
                           color:{pe_black}; text-transform:uppercase;">
                  Ticket
                </td>
              </tr>
              <tr>
                <td style="padding:16px;">
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="font-family:{font_stack}; font-size:11px; font-weight:900; letter-spacing:0.1em;
                                 text-transform:uppercase; color:{pe_darkgray}; padding:0 12px 4px 0; vertical-align:top;">
                        ID
                      </td>
                      <td style="font-family:'JetBrains Mono', Consolas, monospace; font-size:14px; font-weight:600;
                                 color:{pe_black}; padding:0 0 4px 0;">
                        {_esc(ticket_id)}
                      </td>
                    </tr>
                    <tr>
                      <td style="font-family:{font_stack}; font-size:11px; font-weight:900; letter-spacing:0.1em;
                                 text-transform:uppercase; color:{pe_darkgray}; padding:4px 12px 0 0; vertical-align:top;">
                        Title
                      </td>
                      <td style="font-family:{font_stack}; font-size:14px; font-weight:600; color:{pe_black}; padding:4px 0 0 0;">
                        {_esc(task_name) or '(unnamed)'}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """
    else:
        ticket_block = f"""
        <tr>
          <td style="padding:0 32px 24px 32px; font-family:{font_stack}; font-size:14px; color:{pe_darkgray};">
            Your request does not require a ticket; our team will review it.
          </td>
        </tr>
        """

    eta_block = ""
    if eta:
        eta_block = f"""
        <tr>
          <td style="padding:0 32px 24px 32px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-family:{font_stack}; font-size:11px; font-weight:900; letter-spacing:0.1em;
                           text-transform:uppercase; color:{pe_darkgray}; padding-bottom:6px;">
                  ⏱ Target Response
                </td>
              </tr>
              <tr>
                <td style="font-family:{font_stack}; font-size:16px; font-weight:600; color:{pe_black};">
                  {_esc(eta)}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PEC Assist</title>
</head>
<body style="margin:0; padding:0; background-color:{pe_gray};">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:{pe_gray};">
    <tr>
      <td align="center" style="padding:32px 16px;">

        <!-- Card: thick black border conveys the industrial design system in an email-safe way -->
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600"
               style="max-width:600px; background-color:#ffffff; border:3px solid {pe_black};">
          <tr>
            <td style="padding:0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
                     style="background-color:#ffffff;">

                <!-- Header / logo bar -->
                <tr>
                  <td style="padding:20px 32px; border-bottom:4px solid {pe_black}; background-color:#ffffff;">
                    <img src="cid:peclogo" alt="PEC" width="120" style="display:block; max-width:120px; height:auto; border:0;">
                  </td>
                </tr>

                <!-- Intent + urgency badge -->
                <tr>
                  <td style="padding:24px 32px 12px 32px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="font-family:{font_stack}; font-size:18px; font-weight:900; letter-spacing:-0.025em;
                                   text-transform:uppercase; color:{pe_black}; padding-right:12px;">
                          {_esc(intent_display)}
                        </td>
                        <td style="padding:0;">
                          <span style="display:inline-block; padding:4px 10px; border:2px solid {pe_black};
                                       background-color:{badge_bg}; color:{badge_fg};
                                       font-family:{font_stack}; font-size:11px; font-weight:900; letter-spacing:0.1em;
                                       text-transform:uppercase;">
                            {_esc(badge_label)}
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <!-- Greeting + intro -->
                <tr>
                  <td style="padding:0 32px 16px 32px; font-family:{font_stack}; font-size:16px; font-weight:500; color:{pe_black};">
                    {_esc(greeting)}
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 32px 24px 32px; font-family:{font_stack}; font-size:14px; font-weight:500;
                             color:{pe_darkgray}; line-height:1.5;">
                    Thank you for contacting PEC Assist. We've received your request and created a support ticket.
                  </td>
                </tr>

                <!-- Summary card -->
                <tr>
                  <td style="padding:0 32px 24px 32px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
                           style="border:3px solid {pe_black}; background-color:{pe_gray};">
                      <tr>
                        <td style="padding:12px 16px; border-bottom:3px solid {pe_black}; background-color:#ffffff;
                                   font-family:{font_stack}; font-size:12px; font-weight:900; letter-spacing:0.1em;
                                   color:{pe_black}; text-transform:uppercase;">
                          Summary
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:16px; font-family:{font_stack}; font-size:14px; font-weight:500;
                                   color:{pe_black}; line-height:1.5;">
                          {_esc(summary)}
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                {ticket_block}
                {eta_block}

                <!-- Footer -->
                <tr>
                  <td style="padding:20px 32px; border-top:3px solid {pe_black}; background-color:{pe_gray};
                             font-family:{font_stack}; font-size:12px; font-weight:600; letter-spacing:0.05em;
                             color:{pe_darkgray}; text-transform:uppercase;">
                    This is an automated response from PEC Assist<br>
                    <span style="font-family:'JetBrains Mono', Consolas, monospace; font-size:11px; text-transform:none; letter-spacing:0;">
                      pec.assist@pecalum.com
                    </span>
                  </td>
                </tr>

              </table>
            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""


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

        _api_key = os.getenv("ASANA_SERVICE_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if _api_key:
            headers["X-API-Key"] = _api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.service_url}/tasks",
                json=payload,
                headers=headers,
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

    async def send_reply(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
        inline_images: Optional[dict[str, str]] = None,
    ) -> dict:
        """Send a reply email.

        inline_images: mapping of Content-ID (e.g. "peclogo") -> local file path.
        When provided alongside html_body, the message is sent as multipart/related
        so the HTML can reference <img src="cid:peclogo">.
        """
        if self.mock:
            return {"message_id": "mock-smtp-reply", "status": "Mock sent"}

        if not self.password:
            raise RuntimeError("IMAP_PASSWORD not configured (required for SMTP auth)")

        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.image import MIMEImage
        from email.utils import formatdate, make_msgid
        import mimetypes
        import aiosmtplib

        text_part = MIMEText(text_body, "plain", "utf-8")

        if html_body is None:
            msg = text_part
        else:
            html_part = MIMEText(html_body, "html", "utf-8")
            alternative = MIMEMultipart("alternative")
            alternative.attach(text_part)
            alternative.attach(html_part)

            if inline_images:
                related = MIMEMultipart("related")
                related.attach(alternative)
                for cid, path in inline_images.items():
                    try:
                        with open(path, "rb") as f:
                            data = f.read()
                    except OSError as e:
                        logger.warning(f"Inline image '{cid}' at {path} unreadable: {e}")
                        continue
                    ctype, _ = mimetypes.guess_type(path)
                    subtype = ctype.split("/")[1] if ctype and ctype.startswith("image/") else "png"
                    img = MIMEImage(data, _subtype=subtype)
                    img.add_header("Content-ID", f"<{cid}>")
                    img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
                    related.attach(img)
                msg = related
            else:
                msg = alternative

        msg["Subject"] = f"Re: {subject}"
        msg["From"] = self.sender_address
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg["Reply-To"] = self.sender_address
        msg["Message-ID"] = make_msgid(domain=self.sender_address.split("@")[-1])

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

        encoded_id = urllib.parse.quote(message_id, safe="")
        url = f"{self.supabase_url}/rest/v1/email_requests?message_id=eq.{encoded_id}&select=*"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                logger.warning("Failed to query email request", extra={"status": response.status_code})
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
            ar = result["asana_response"] or {}
            text_body, html_body = format_auto_reply(
                classification=classification,
                from_name=email.get("from_name"),
                ticket_id=ar.get("friendly_id") or ar.get("task_id"),
                task_name=ar.get("task_name"),
                due_on=ar.get("due_on"),
                due_at=ar.get("due_at"),
            )
            await self.email_sender.send_reply(
                to_email=email["from_email"],
                subject=email["subject"],
                text_body=text_body,
                html_body=html_body,
                inline_images=_logo_inline_images(),
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
