"""Event type constants."""


class EventTypes:
    # HITL
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"

    # Tool execution
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # Agent lifecycle (for future use in Step 12)
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_MESSAGE = "agent.message"
    AGENT_TASK_DELEGATED = "agent.task_delegated"
