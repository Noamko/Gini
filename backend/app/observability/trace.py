"""Trace builder — creates execution logs for agent steps."""
import time
import uuid
from contextlib import asynccontextmanager

import structlog

from app.dependencies import async_session
from app.models.execution_log import ExecutionLog

logger = structlog.get_logger("trace")


class TraceBuilder:
    """Collects execution steps for a single trace (one user message -> response cycle)."""

    def __init__(self, conversation_id: str | None = None, agent_id: str | None = None, agent_name: str | None = None):
        self.trace_id = str(uuid.uuid4())
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._step_counter = 0

    @asynccontextmanager
    async def step(self, step_type: str, step_name: str | None = None, input_data: dict | None = None):
        """Context manager that times a step and persists the log entry."""
        self._step_counter += 1
        order = self._step_counter
        start = time.perf_counter()

        result = StepResult()
        try:
            yield result
        except Exception as e:
            result.error = str(e)
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            log = ExecutionLog(
                trace_id=self.trace_id,
                conversation_id=self.conversation_id,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                step_type=step_type,
                step_name=step_name,
                step_order=order,
                input_data=_truncate_data(input_data),
                output_data=_truncate_data(result.output_data),
                error=result.error,
                duration_ms=duration_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                model=result.model,
                metadata_=result.metadata,
            )

            try:
                async with async_session() as db:
                    db.add(log)
                    await db.commit()
            except Exception as e:
                await logger.awarning("trace_persist_error", error=str(e), trace_id=self.trace_id)


class StepResult:
    """Mutable container for step output, populated inside the `async with` block."""

    def __init__(self):
        self.output_data: dict | None = None
        self.error: str | None = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost_usd: float = 0
        self.model: str | None = None
        self.metadata: dict = {}


def _truncate_data(data: dict | None, max_str_len: int = 2000) -> dict | None:
    """Truncate long string values in dicts to keep logs manageable."""
    if data is None:
        return None
    out = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > max_str_len:
            out[k] = v[:max_str_len] + f"... (truncated, {len(v)} chars)"
        elif isinstance(v, dict):
            out[k] = _truncate_data(v, max_str_len)
        else:
            out[k] = v
    return out
