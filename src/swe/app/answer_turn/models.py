# -*- coding: utf-8 -*-
"""Value objects for the Console answer-turn lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar


class TurnStatus(str, Enum):
    ADMITTING = "admitting"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_STATUSES = frozenset(
    {TurnStatus.COMPLETED, TurnStatus.CANCELLED, TurnStatus.FAILED},
)


@dataclass(frozen=True, slots=True)
class TurnIdentity:
    chat_id: str
    msgid: str
    turn_id: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (self.chat_id, self.msgid, self.turn_id)
        ) or not self.turn_id.startswith("turn-"):
            raise ValueError("chat_id, msgid, and turn_id are required")

    @classmethod
    def create(cls, *, chat_id: str, msgid: str) -> "TurnIdentity":
        from uuid import uuid4

        if not chat_id or not msgid:
            raise ValueError("chat_id and msgid are required")
        return cls(chat_id, msgid, f"turn-{uuid4().hex}")


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    identity: TurnIdentity
    status: TurnStatus
    reason: str | None = None
    result: Any = None
    error: BaseException | str | None = None
    assistant_text: str | None = None

    _TERMINAL: ClassVar[frozenset[TurnStatus]] = TERMINAL_STATUSES

    def __post_init__(self) -> None:
        if not isinstance(self.identity, TurnIdentity):
            raise TypeError("outcome identity must be a TurnIdentity")
        status = self.status
        if not isinstance(status, TurnStatus):
            object.__setattr__(self, "status", TurnStatus(status))
        if self.status not in self._TERMINAL:
            raise ValueError(f"outcome must be terminal, got {self.status}")

    @classmethod
    def completed(
        cls,
        identity: TurnIdentity,
        *,
        assistant_text: str | None = None,
        result: Any = None,
    ) -> "TurnOutcome":
        return cls(
            identity,
            TurnStatus.COMPLETED,
            result=result,
            assistant_text=assistant_text,
        )

    @classmethod
    def cancelled(
        cls,
        identity: TurnIdentity,
        *,
        result: Any = None,
    ) -> "TurnOutcome":
        return cls(identity, TurnStatus.CANCELLED, result=result)

    @classmethod
    def failed(
        cls,
        identity: TurnIdentity,
        error: BaseException | str,
    ) -> "TurnOutcome":
        return cls(identity, TurnStatus.FAILED, error=error)


@dataclass(frozen=True, slots=True)
class TurnLease:
    identity: TurnIdentity
    queue: Any
    is_new_run: bool


@dataclass(frozen=True, slots=True)
class StopClaim:
    accepted: bool
    identity: TurnIdentity | None = None
    status: TurnStatus | None = None
