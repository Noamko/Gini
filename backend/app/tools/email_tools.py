"""Email tools for reading inbox messages and sending outbound mail."""
from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate, parsedate_to_datetime
from typing import Any

from app.tools.base import BaseTool, ToolResult


def _require_credential(
    credential_name: str,
    credential_values: dict[str, str] | None,
) -> str:
    if not credential_name:
        raise ValueError("credential_name is required")
    if not credential_values or credential_name not in credential_values:
        raise ValueError(f"Credential '{credential_name}' is not available")
    return credential_values[credential_name]


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    decoded = email.header.decode_header(value)
    parts: list[str] = []
    for chunk, encoding in decoded:
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _extract_text_body(message: email.message.Message, max_chars: int) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition or content_type != "text/plain":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = message.get_payload(decode=True)
        if payload:
            charset = message.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))

    body = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if len(body) > max_chars:
        return body[:max_chars] + f"... [truncated to {max_chars} chars]"
    return body


def _normalize_recipients(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [item.strip() for item in value.replace(";", ",").split(",")]
        return [item for item in parts if item]
    return [item.strip() for item in value if item and item.strip()]


class ReadEmailIMAPTool(BaseTool):
    name = "read_email_imap"
    description = "Read messages from an IMAP inbox using a credential handle managed by Gini."
    parameters_schema = {
        "type": "object",
        "properties": {
            "email_address": {
                "type": "string",
                "description": "Mailbox username or email address to authenticate as.",
            },
            "credential_name": {
                "type": "string",
                "description": "Credential handle containing the mailbox password or app password.",
            },
            "imap_server": {
                "type": "string",
                "description": "IMAP server host.",
                "default": "imap.gmail.com",
            },
            "imap_port": {
                "type": "integer",
                "description": "IMAP SSL port.",
                "default": 993,
            },
            "folder": {
                "type": "string",
                "description": "Mailbox folder to select.",
                "default": "INBOX",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to return.",
                "default": 5,
            },
            "unread_only": {
                "type": "boolean",
                "description": "If true, search only unread mail.",
                "default": True,
            },
            "sender_filter": {
                "type": "string",
                "description": "Optional FROM filter.",
            },
            "subject_filter": {
                "type": "string",
                "description": "Optional SUBJECT filter.",
            },
            "since": {
                "type": "string",
                "description": "Optional lower date bound in YYYY-MM-DD format.",
            },
            "include_body": {
                "type": "boolean",
                "description": "Include a body excerpt for each message.",
                "default": True,
            },
            "max_body_chars": {
                "type": "integer",
                "description": "Maximum body excerpt length per message.",
                "default": 800,
            },
        },
        "required": ["email_address", "credential_name"],
    }

    async def execute(
        self,
        email_address: str,
        credential_name: str,
        imap_server: str = "imap.gmail.com",
        imap_port: int = 993,
        folder: str = "INBOX",
        limit: int = 5,
        unread_only: bool = True,
        sender_filter: str | None = None,
        subject_filter: str | None = None,
        since: str | None = None,
        include_body: bool = True,
        max_body_chars: int = 800,
        credential_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            password = _require_credential(credential_name, credential_values)
            search_terms: list[str] = ["UNSEEN" if unread_only else "ALL"]
            if sender_filter:
                search_terms.extend(["FROM", f'"{sender_filter}"'])
            if subject_filter:
                search_terms.extend(["SUBJECT", f'"{subject_filter}"'])
            if since:
                since_dt = datetime.strptime(since, "%Y-%m-%d")
                search_terms.extend(["SINCE", since_dt.strftime("%d-%b-%Y")])

            with imaplib.IMAP4_SSL(imap_server, imap_port, ssl_context=ssl.create_default_context()) as mail:
                mail.login(email_address, password)
                status, _ = mail.select(folder)
                if status != "OK":
                    return ToolResult(success=False, error=f"Failed to open folder '{folder}'")

                status, data = mail.search(None, *search_terms)
                if status != "OK":
                    return ToolResult(success=False, error="IMAP search failed")

                message_ids = data[0].split()
                if not message_ids:
                    return ToolResult(output=f"No matching emails found in {folder}.")

                selected_ids = list(reversed(message_ids[-max(limit, 1):]))
                summaries: list[str] = []

                for index, msg_id in enumerate(selected_ids, start=1):
                    status, fetched = mail.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not fetched or not fetched[0]:
                        continue
                    raw_message = fetched[0][1]
                    parsed = email.message_from_bytes(raw_message)
                    subject = _decode_header_value(parsed.get("Subject"))
                    sender = _decode_header_value(parsed.get("From"))
                    date_raw = parsed.get("Date")
                    try:
                        date_value = parsedate_to_datetime(date_raw).astimezone(UTC).isoformat() if date_raw else ""
                    except Exception:
                        date_value = date_raw or ""

                    block = [
                        f"{index}. Subject: {subject or '(no subject)'}",
                        f"From: {sender or '(unknown sender)'}",
                        f"Date: {date_value or '(unknown date)'}",
                    ]
                    if include_body:
                        body_excerpt = _extract_text_body(parsed, max_body_chars)
                        if body_excerpt:
                            block.append(f"Body:\n{body_excerpt}")
                    summaries.append("\n".join(block))

                if not summaries:
                    return ToolResult(output=f"No readable emails found in {folder}.")

                return ToolResult(
                    output="\n\n---\n\n".join(summaries),
                    metadata={
                        "email_address": email_address,
                        "folder": folder,
                        "count": len(summaries),
                        "unread_only": unread_only,
                    },
                )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SendEmailSMTPTool(BaseTool):
    name = "send_email_smtp"
    description = "Send an outbound email using SMTP with a credential handle managed by Gini."
    requires_approval = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "email_address": {
                "type": "string",
                "description": "Mailbox username or sender email address.",
            },
            "credential_name": {
                "type": "string",
                "description": "Credential handle containing the mailbox password or app password.",
            },
            "to": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": "Primary recipients.",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
            },
            "body": {
                "type": "string",
                "description": "Plain-text message body.",
            },
            "cc": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": "Optional CC recipients.",
                "default": [],
            },
            "bcc": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": "Optional BCC recipients.",
                "default": [],
            },
            "reply_to": {
                "type": "string",
                "description": "Optional Reply-To address.",
            },
            "smtp_server": {
                "type": "string",
                "description": "SMTP server host.",
                "default": "smtp.gmail.com",
            },
            "smtp_port": {
                "type": "integer",
                "description": "SMTP SSL port.",
                "default": 465,
            },
        },
        "required": ["email_address", "credential_name", "to", "subject", "body"],
    }

    async def execute(
        self,
        email_address: str,
        credential_name: str,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        reply_to: str | None = None,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 465,
        credential_values: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            password = _require_credential(credential_name, credential_values)
            to_list = _normalize_recipients(to)
            cc_list = _normalize_recipients(cc)
            bcc_list = _normalize_recipients(bcc)
            recipients = [addr for addr in [*to_list, *cc_list, *bcc_list] if addr]
            if not recipients:
                return ToolResult(success=False, error="At least one recipient is required")

            message = EmailMessage()
            message["From"] = email_address
            message["To"] = ", ".join(to_list)
            if cc_list:
                message["Cc"] = ", ".join(cc_list)
            if reply_to:
                message["Reply-To"] = reply_to
            message["Subject"] = subject
            message["Date"] = formatdate(localtime=True)
            message.set_content(body)

            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=ssl.create_default_context()) as smtp:
                smtp.login(email_address, password)
                smtp.send_message(message, from_addr=email_address, to_addrs=recipients)

            return ToolResult(
                output=f"Email sent successfully to {', '.join(recipients)}",
                metadata={
                    "email_address": email_address,
                    "to": to_list,
                    "cc": cc_list,
                    "bcc_count": len(bcc_list),
                    "subject": subject,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
