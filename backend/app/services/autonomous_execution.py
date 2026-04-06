"""Shared autonomous agent execution helpers.

This module centralizes the non-interactive LLM/tool loop used by background
runs, delegated sub-agents, and Telegram chat handling.
"""
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field

from app.models.agent import Agent
from app.services.execution_prep import ExecutionResources
from app.services.llm_gateway import LLMResponse, llm_gateway
from app.services.tool_catalog import ToolPolicy
from app.services.tool_runner import execute_tool


ToolRoundPersistHook = Callable[[str | None, list[dict]], Awaitable[None]]
ToolResultHook = Callable[[str, dict, str, bool, str | None], Awaitable[None]]
DelegateTaskRunner = Callable[[str, str], Awaitable[dict]]
PhaseHook = Callable[[], Awaitable[None]]
ToolHandler = Callable[[dict, ToolPolicy | None], Awaitable["ToolExecutionResult"]]
ApprovalRequester = Callable[[dict, ToolPolicy | None], Awaitable[tuple[bool, str | None]]]


@dataclass
class AutonomousContext:
    messages: list[dict]
    steps: list[dict] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


@dataclass
class AutonomousRoundResult:
    done: bool
    response: LLMResponse
    final_content: str | None = None


@dataclass
class ToolExecutionResult:
    output: str
    success: bool
    error: str | None = None
    extra_cost_usd: float = 0.0


def build_assistant_tool_content(response: LLMResponse) -> list[dict]:
    assistant_content = []
    if response.content:
        assistant_content.append({"type": "text", "text": response.content})
    for tc in response.tool_calls:
        assistant_content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["name"],
            "input": tc["arguments"],
        })
    return assistant_content


async def process_tool_response(
    *,
    response: LLMResponse,
    context: AutonomousContext,
    tool_policy_by_name: dict[str, ToolPolicy],
    tool_handler: ToolHandler,
    on_tool_round_persist: ToolRoundPersistHook | None = None,
    on_tool_result: ToolResultHook | None = None,
    on_before_tools: PhaseHook | None = None,
) -> None:
    if on_before_tools:
        await on_before_tools()

    assistant_content = build_assistant_tool_content(response)
    context.messages.append({"role": "assistant", "content": assistant_content})
    if on_tool_round_persist:
        await on_tool_round_persist(response.content, deepcopy(assistant_content))

    tool_results_content = []
    for tc in response.tool_calls:
        tool_name = tc["name"]
        tool_policy = tool_policy_by_name.get(tool_name)
        execution = await tool_handler(tc, tool_policy)

        context.total_cost_usd += execution.extra_cost_usd
        tool_results_content.append({
            "type": "tool_result",
            "tool_use_id": tc["id"],
            "content": execution.output[:10000],
        })
        context.steps.append({
            "type": "tool_call",
            "tool": tool_name,
            "arguments": tc["arguments"],
            "success": execution.success,
            "output": execution.output[:2000],
            "error": execution.error,
        })
        if on_tool_result:
            await on_tool_result(tool_name, tc, execution.output[:10000], execution.success, execution.error)

    context.messages.append({"role": "user", "content": tool_results_content})


async def run_autonomous_round(
    *,
    agent: Agent,
    resources: ExecutionResources,
    context: AutonomousContext,
    round_num: int,
    delegate_task_runner: DelegateTaskRunner | None = None,
    request_tool_approval: ApprovalRequester | None = None,
    on_tool_round_persist: ToolRoundPersistHook | None = None,
    on_tool_result: ToolResultHook | None = None,
    on_before_tools: PhaseHook | None = None,
) -> AutonomousRoundResult:
    response: LLMResponse = await llm_gateway.call_with_tools(
        messages=context.messages,
        system_prompt=resources.system_prompt,
        tools=resources.tool_specs if resources.tool_specs else None,
        provider=agent.llm_provider,
        model=agent.llm_model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
    )

    context.total_input_tokens += response.input_tokens
    context.total_output_tokens += response.output_tokens
    context.total_cost_usd += response.cost_usd

    context.steps.append({
        "type": "llm_call",
        "round": round_num,
        "content": (response.content or "")[:1000],
        "tool_calls": len(response.tool_calls) if response.tool_calls else 0,
        "tokens": response.input_tokens + response.output_tokens,
    })

    if not response.tool_calls:
        return AutonomousRoundResult(done=True, response=response, final_content=response.content)

    async def autonomous_tool_handler(tc: dict, tool_policy: ToolPolicy | None) -> ToolExecutionResult:
        tool_name = tc["name"]
        tool_args = tc["arguments"]
        approved_via_hitl = False
        if tool_policy and tool_policy.requires_approval and not agent.auto_approve:
            if not request_tool_approval:
                return ToolExecutionResult(
                    output=f"Error: Tool '{tool_name}' requires approval and is unavailable in this autonomous context.",
                    success=False,
                    error="Approval required",
                )
            approved, reason = await request_tool_approval(tc, tool_policy)
            if not approved:
                reject_reason = reason or "User rejected"
                return ToolExecutionResult(
                    output=f"Error: Tool execution was rejected by the user. Reason: {reject_reason}",
                    success=False,
                    error=f"Rejected: {reject_reason}",
                )
            approved_via_hitl = True
        if tool_name == "delegate_task":
            if not delegate_task_runner:
                return ToolExecutionResult(
                    output="Error: delegate_task is not configured for this execution context.",
                    success=False,
                    error="Error: delegate_task is not configured for this execution context.",
                )
            sub_agent_name = tool_args.get("agent_name", "")
            task = tool_args.get("task", "")
            delegation_result = await delegate_task_runner(sub_agent_name, task)
            tool_output = delegation_result.get("content", "No result")
            tool_success = delegation_result.get("success", False)
            tool_error = None if tool_success else tool_output
            return ToolExecutionResult(
                output=tool_output,
                success=tool_success,
                error=tool_error,
                extra_cost_usd=delegation_result.get("cost_usd", 0.0),
            )
        result = await execute_tool(
            tool_name,
            tool_args,
            use_sandbox=tool_policy.requires_sandbox if tool_policy else True,
            allow_network=agent.auto_approve or approved_via_hitl,
            credential_values=resources.credentials,
        )
        return ToolExecutionResult(
            output=result.output if result.success else f"Error: {result.error}",
            success=result.success,
            error=result.error,
        )

    await process_tool_response(
        response=response,
        context=context,
        tool_policy_by_name=resources.tool_policy_by_name,
        tool_handler=autonomous_tool_handler,
        on_tool_round_persist=on_tool_round_persist,
        on_tool_result=on_tool_result,
        on_before_tools=on_before_tools,
    )
    return AutonomousRoundResult(done=False, response=response)
