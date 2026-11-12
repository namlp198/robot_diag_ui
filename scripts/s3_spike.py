"""Spike S3: Claude Agent SDK (Python) from the daemon's point of view. No hardware involved.

Checks: (1) login reused, (2) structured event stream, (3) in-process tool, (4) permission callback for a
"write" tool, (5) resume of a session. Built-in tools are off and user/project settings are not loaded.
Usage: python -I scripts/s3_spike.py
"""
from __future__ import annotations

import asyncio
import json
import sys

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, PermissionResultAllow, PermissionResultDeny,
    ResultMessage, StreamEvent, SystemMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage,
    create_sdk_mcp_server, tool,
)

MODEL = "claude-haiku-5-5"
asked: list[str] = []


@tool("read_counter", "Read a demo counter (read-only).", {"name": str})
async def read_counter(args):
    return {"content": [{"type": "text", "text": json.dumps({"name": args["name"], "value": 4242})}]}


@tool("write_counter", "Write a demo counter (needs approval).", {"name": str, "value": int})
async def write_counter(args):
    return {"content": [{"type": "text", "text": "written"}]}  # must never run in this spike


async def can_use_tool(tool_name, tool_input, ctx):
    asked.append(tool_name)
    if tool_name.endswith("write_counter"):
        return PermissionResultDeny(message="writes are refused in the spike", interrupt=False)
    return PermissionResultAllow()


def options(resume: str | None = None) -> ClaudeAgentOptions:
    srv = create_sdk_mcp_server("rdt", tools=[read_counter, write_counter])
    return ClaudeAgentOptions(
        model=MODEL, tools=[], mcp_servers={"rdt": srv},
        allowed_tools=["mcp__rdt__read_counter"],  # write_counter is not pre-approved -> can_use_tool decides
        can_use_tool=can_use_tool, setting_sources=[], max_turns=6, max_budget_usd=0.25,
        include_partial_messages=True, resume=resume,
        system_prompt="You are a test agent. Use the tools you are given. Answer in one short sentence.",
    )


async def run(prompt: str, resume: str | None = None) -> str | None:
    sid = None
    kinds: list[str] = []
    async with ClaudeSDKClient(options=options(resume)) as c:
        await c.query(prompt)
        async for m in c.receive_response():
            k = type(m).__name__
            if isinstance(m, StreamEvent):
                k = "stream:" + str(m.event.get("type"))
            if not kinds or kinds[-1] != k:
                kinds.append(k)
            if isinstance(m, SystemMessage) and getattr(m, "subtype", "") == "init":
                sid = m.data.get("session_id", sid)
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        print("  tool_use:", b.name, b.input)
                    elif isinstance(b, TextBlock):
                        print("  text:", b.text[:200])
            elif isinstance(m, UserMessage) and isinstance(m.content, list):
                for b in m.content:
                    if isinstance(b, ToolResultBlock):
                        print("  tool_result:", str(b.content)[:120], "is_error=", b.is_error)
            elif isinstance(m, ResultMessage):
                sid = m.session_id
                print(f"  result: subtype={m.subtype} turns={m.num_turns} cost=${m.total_cost_usd} error={m.is_error}")
    print("  event kinds:", " > ".join(kinds))
    return sid


async def main():
    print("1) read tool via in-process MCP + event stream")
    sid = await run("Read the counter named 'frames' and tell me its value.")
    print("2) write tool must reach the permission callback and be denied")
    await run("Set the counter named 'frames' to 1 using write_counter, then say what happened.", resume=None)
    print("permission callback saw:", asked)
    print("3) resume session", sid)
    if sid:
        await run("What counter value did you read earlier?", resume=sid)


if __name__ == "__main__":
    asyncio.run(main())
