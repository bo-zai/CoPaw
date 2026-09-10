# -*- coding: utf-8 -*-
"""Candidate assistant-response selection shared by completion paths."""

from __future__ import annotations

from typing import Any


def project_candidate_assistant_response(msg: Any) -> str | None:
    """Return visible text when a message is eligible for Stop."""
    if getattr(msg, "role", None) != "assistant" or _is_live_assistant_event(
        msg,
    ):
        return None
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content if content.strip() else None
    if not isinstance(content, list) or _has_tool_use_block(content):
        return None
    texts = [text for block in content if (text := _text_from_block(block))]
    response = "\n".join(texts)
    return response if response.strip() else None


def replace_candidate_assistant_response(msg: Any, response: str) -> bool:
    """Replace only visible text while retaining all non-text blocks."""
    if project_candidate_assistant_response(msg) is None:
        return False
    if isinstance(msg.content, str):
        msg.content = response
        return True
    text_blocks = [
        block for block in msg.content if _text_from_block(block) is not None
    ]
    if not text_blocks:
        return False
    _replace_block_text(text_blocks[0], response)
    for block in text_blocks[1:]:
        _replace_block_text(block, "")
    return True


def _is_live_assistant_event(msg: Any) -> bool:
    metadata = getattr(msg, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    values = " ".join(
        str(metadata.get(key, ""))
        for key in ("event_type", "message_type", "kind", "type")
    ).lower()
    return any(token in values for token in ("progress", "tool", "approval"))


def _has_tool_use_block(blocks: list[Any]) -> bool:
    return any(_block_type(block) == "tool_use" for block in blocks)


def _text_from_block(block: Any) -> str | None:
    if _block_type(block) != "text":
        return None
    value = (
        block.get("text")
        if isinstance(block, dict)
        else getattr(block, "text", None)
    )
    return value if isinstance(value, str) else None


def _block_type(block: Any) -> str | None:
    return (
        block.get("type")
        if isinstance(block, dict)
        else getattr(block, "type", None)
    )


def _replace_block_text(block: Any, response: str) -> None:
    if isinstance(block, dict):
        block["text"] = response
    else:
        block.text = response
