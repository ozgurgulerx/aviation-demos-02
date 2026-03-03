"""
Chat middleware that sanitizes orphaned tool_calls in conversation history.

Works around a bug in the Microsoft Agent Framework's streaming function
invocation wrapper (_tools.py) where hitting max_consecutive_errors causes
a `break` without yielding the final error tool result. The orphaned
assistant message with tool_calls (but no matching tool response) corrupts
the conversation history, causing Azure OpenAI to reject subsequent requests
with: "An assistant message with 'tool_calls' must be followed by tool
messages responding to each 'tool_call_id'."

This ChatMiddleware intercepts messages just before they're sent to the LLM
and injects synthetic error responses for any orphaned tool_call_ids.
"""

from agent_framework import ChatMessage, ChatMiddleware, Content
from agent_framework._middleware import ChatContext
import structlog

logger = structlog.get_logger()


class ToolCallSanitizer(ChatMiddleware):
    """Ensure every function_call in the conversation has a matching function_result."""

    async def process(self, context: ChatContext, next) -> None:
        _patch_orphaned_tool_calls(context.messages)
        await next(context)


def _patch_orphaned_tool_calls(messages) -> int:
    """Scan messages and inject synthetic tool results for orphaned function_calls.

    Returns the number of synthetic results injected.
    """
    # Collect all function_call call_ids and their positions
    pending_calls: dict[str, int] = {}  # call_id -> index of assistant msg
    patched = 0

    for i, msg in enumerate(messages):
        role = getattr(msg.role, "value", str(msg.role))

        if role == "assistant" and msg.contents:
            for content in msg.contents:
                if content.type == "function_call" and content.call_id:
                    pending_calls[content.call_id] = i

        elif role == "tool" and msg.contents:
            for content in msg.contents:
                if content.type == "function_result" and content.call_id:
                    pending_calls.pop(content.call_id, None)

    if not pending_calls:
        return 0

    # Group orphaned call_ids by their assistant message index so we inject
    # one synthetic tool message per assistant message (preserving order).
    by_msg_idx: dict[int, list[str]] = {}
    for call_id, msg_idx in pending_calls.items():
        by_msg_idx.setdefault(msg_idx, []).append(call_id)

    # Walk backwards so insertions don't shift later indices
    for msg_idx in sorted(by_msg_idx, reverse=True):
        call_ids = by_msg_idx[msg_idx]
        insert_at = msg_idx + 1
        # Skip past any existing tool messages that follow this assistant message
        while insert_at < len(messages):
            r = getattr(messages[insert_at].role, "value", str(messages[insert_at].role))
            if r != "tool":
                break
            insert_at += 1

        synthetic = ChatMessage(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id=cid,
                    result="[Error: tool call result was lost due to consecutive errors. "
                    "Please retry or use an alternative approach.]",
                )
                for cid in call_ids
            ],
        )
        messages.insert(insert_at, synthetic)
        patched += len(call_ids)

        logger.warning(
            "tool_call_sanitizer_patched",
            call_ids=call_ids,
            assistant_msg_idx=msg_idx,
            insert_idx=insert_at,
        )

    return patched
