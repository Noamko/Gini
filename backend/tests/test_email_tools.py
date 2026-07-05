"""Tests for IMAP/SMTP email tools (credentials arrive via the bound ``password`` slot)."""

import pytest

from app.tools.email_tools import ReadEmailIMAPTool, SendEmailSMTPTool


@pytest.mark.asyncio
async def test_imap_missing_credential_returns_error():
    tool = ReadEmailIMAPTool()
    result = await tool.execute(
        email_address="user@example.com",
        credential_values={},
    )
    assert result.success is False
    assert "password" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_smtp_missing_credential_returns_error():
    tool = SendEmailSMTPTool()
    result = await tool.execute(
        email_address="user@example.com",
        to="dest@example.com",
        subject="hi",
        body="hello",
        credential_values={},
    )
    assert result.success is False
    assert "password" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_smtp_requires_recipients():
    tool = SendEmailSMTPTool()
    result = await tool.execute(
        email_address="user@example.com",
        to="",
        subject="hi",
        body="hello",
        credential_values={"password": "secret"},
    )
    assert result.success is False
    assert "recipient" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_imap_reads_password_slot_then_fails_on_connect():
    # With the slot bound, it proceeds past the credential check and fails at connect.
    tool = ReadEmailIMAPTool()
    result = await tool.execute(
        email_address="user@example.com",
        credential_values={"password": "secret"},
        imap_server="127.0.0.1",
        imap_port=1,
    )
    assert result.success is False
    assert "password" not in (result.error or "").lower()
