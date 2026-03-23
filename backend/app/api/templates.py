"""Agent templates — pre-built agent configurations."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/templates", tags=["templates"])

TEMPLATES = [
    {
        "id": "email-reader",
        "name": "Email Reader",
        "description": "Reads emails from a Gmail/IMAP inbox",
        "icon": "mail",
        "config": {
            "name": "Email Reader",
            "description": "Reads emails from an IMAP inbox (Gmail, Outlook, etc.)",
            "system_prompt": "You are an email reader agent. Connect to the user's email via IMAP and fetch emails.\n\nWhen asked to read emails:\n1. Use Python's imaplib via run_shell to connect\n2. Use the credentials provided in your skills\n3. Present emails in a clean format with subject, sender, and date\n4. Support filtering by unread, sender, or date range",
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "temperature": 0.3,
            "max_tokens": 4096,
            "auto_approve": True,
        },
    },
    {
        "id": "code-reviewer",
        "name": "Code Reviewer",
        "description": "Reviews code for quality, bugs, and best practices",
        "icon": "code",
        "config": {
            "name": "Code Reviewer",
            "description": "Reviews code for quality, style, and potential issues",
            "system_prompt": "You are a code review expert. When given code, analyze it for:\n\n1. Bugs and potential errors\n2. Security vulnerabilities\n3. Performance issues\n4. Code style and readability\n5. Best practices\n\nProvide specific, actionable feedback with code suggestions.",
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "temperature": 0.3,
            "max_tokens": 4096,
            "auto_approve": False,
        },
    },
    {
        "id": "web-researcher",
        "name": "Web Researcher",
        "description": "Fetches and summarizes web content",
        "icon": "globe",
        "config": {
            "name": "Web Researcher",
            "description": "Fetches web pages and summarizes content",
            "system_prompt": "You are a web research agent. Use the web_fetch tool to retrieve web pages and summarize their content.\n\nWhen given a topic or URL:\n1. Fetch the relevant web pages\n2. Extract key information\n3. Summarize findings clearly\n4. Cite sources",
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "temperature": 0.5,
            "max_tokens": 4096,
            "auto_approve": True,
        },
    },
    {
        "id": "telegram-messenger",
        "name": "Telegram Messenger",
        "description": "Sends messages via Telegram bot",
        "icon": "send",
        "config": {
            "name": "Telegram Messenger",
            "description": "Sends Telegram messages using the Gini bot",
            "system_prompt": "You are a Telegram messaging agent. Use the send_telegram tool to send messages.\n\nWhen asked to send a message:\n1. Use the send_telegram tool with the chat_id and text\n2. Confirm successful delivery\n3. Handle any errors gracefully",
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "temperature": 0.3,
            "max_tokens": 2048,
            "auto_approve": True,
        },
    },
    {
        "id": "data-analyst",
        "name": "Data Analyst",
        "description": "Analyzes data using Python scripts",
        "icon": "bar-chart",
        "config": {
            "name": "Data Analyst",
            "description": "Analyzes data and generates insights using Python",
            "system_prompt": "You are a data analyst agent. Use Python via run_shell to analyze data.\n\nWhen given data or a data task:\n1. Write Python scripts to process and analyze the data\n2. Use pandas, numpy, and other standard libraries\n3. Present findings with clear summaries\n4. Include relevant statistics and patterns",
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "temperature": 0.3,
            "max_tokens": 4096,
            "auto_approve": True,
        },
    },
]


@router.get("")
async def list_templates():
    return {"items": TEMPLATES}


@router.get("/{template_id}")
async def get_template(template_id: str):
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    from fastapi import HTTPException
    raise HTTPException(404, "Template not found")
