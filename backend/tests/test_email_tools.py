"""Tests for built-in email tools."""
from email.message import EmailMessage
from unittest.mock import patch

from app.tools.email_tools import ReadEmailIMAPTool, SendEmailSMTPTool


class FakeIMAP4SSL:
    def __init__(self, host, port, ssl_context=None):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, email_address, password):
        self.email_address = email_address
        self.password = password
        return "OK", []

    def select(self, folder):
        self.folder = folder
        return "OK", [b""]

    def search(self, charset, *criteria):
        self.criteria = criteria
        return "OK", [b"1 2"]

    def fetch(self, msg_id, _parts):
        message = EmailMessage()
        message["Subject"] = f"Test {msg_id.decode()}"
        message["From"] = "sender@example.com"
        message["Date"] = "Mon, 06 Apr 2026 12:00:00 +0000"
        message.set_content(f"Body for {msg_id.decode()}")
        return "OK", [(None, message.as_bytes())]


class FakeSMTPSSL:
    def __init__(self, host, port, context=None):
        self.host = host
        self.port = port
        self.context = context
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, email_address, password):
        self.email_address = email_address
        self.password = password

    def send_message(self, message, from_addr, to_addrs):
        self.sent.append((message, from_addr, to_addrs))


async def test_read_email_imap_reads_messages_with_filters():
    tool = ReadEmailIMAPTool()

    with patch("app.tools.email_tools.imaplib.IMAP4_SSL", FakeIMAP4SSL):
        result = await tool.execute(
            email_address="noamko25@gmail.com",
            credential_name="gmail app password",
            sender_filter="alerts@example.com",
            subject_filter="Deploy",
            limit=2,
            credential_values={"gmail app password": "secret"},
        )

    assert result.success is True
    assert "Subject: Test 2" in result.output
    assert "sender@example.com" in result.output
    assert result.metadata["count"] == 2


async def test_send_email_smtp_sends_message():
    tool = SendEmailSMTPTool()
    fake_smtp = FakeSMTPSSL("smtp.gmail.com", 465)

    with patch("app.tools.email_tools.smtplib.SMTP_SSL", lambda *args, **kwargs: fake_smtp):
        result = await tool.execute(
            email_address="noamko25@gmail.com",
            credential_name="gmail app password",
            to=["friend@example.com"],
            subject="Hello",
            body="Hi there",
            credential_values={"gmail app password": "secret"},
        )

    assert result.success is True
    assert fake_smtp.sent
    sent_message, from_addr, to_addrs = fake_smtp.sent[0]
    assert from_addr == "noamko25@gmail.com"
    assert to_addrs == ["friend@example.com"]
    assert sent_message["Subject"] == "Hello"


async def test_send_email_smtp_accepts_single_string_recipient():
    tool = SendEmailSMTPTool()
    fake_smtp = FakeSMTPSSL("smtp.gmail.com", 465)

    with patch("app.tools.email_tools.smtplib.SMTP_SSL", lambda *args, **kwargs: fake_smtp):
        result = await tool.execute(
            email_address="noamko25@gmail.com",
            credential_name="gmail app password",
            to="friend@example.com",
            cc="copy@example.com",
            bcc="blind@example.com",
            subject="Hello",
            body="Hi there",
            credential_values={"gmail app password": "secret"},
        )

    assert result.success is True
    assert fake_smtp.sent
    sent_message, _from_addr, to_addrs = fake_smtp.sent[0]
    assert to_addrs == ["friend@example.com", "copy@example.com", "blind@example.com"]
    assert sent_message["To"] == "friend@example.com"
    assert sent_message["Cc"] == "copy@example.com"


async def test_send_email_smtp_requires_known_credential():
    tool = SendEmailSMTPTool()
    result = await tool.execute(
        email_address="noamko25@gmail.com",
        credential_name="missing",
        to=["friend@example.com"],
        subject="Hello",
        body="Hi there",
        credential_values={},
    )

    assert result.success is False
    assert "Credential 'missing' is not available" in result.error
