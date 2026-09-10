# -*- coding: utf-8 -*-
"""Lifecycle service for one durable Goal without AgentRunner coupling."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4
from typing import Protocol

from .models import (
    GoalContract,
    GoalControlAction,
    GoalControlCommand,
    GoalCriterionStatus,
    GoalScope,
    GoalSteering,
    GoalSnapshot,
    GoalState,
    GoalTurnDecision,
    TERMINAL_GOAL_STATES,
    utc_now,
)
from .wakeup import notify_goal_wake

DEFAULT_GOAL_TURN_BUDGET = 12
logger = logging.getLogger(__name__)
_CONTROL_PRECEDENCE = {
    GoalControlAction.CANCEL: 4,
    GoalControlAction.EDIT: 3,
    GoalControlAction.PAUSE: 2,
    GoalControlAction.RESUME: 1,
}


class GoalConflictError(ValueError):
    """Raised when an operation conflicts with current Goal ownership."""


class GoalNotFoundError(ValueError):
    """Raised when the requested Goal does not exist."""


class GoalStore(Protocol):
    async def create(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        """Persist a new Goal snapshot."""

    async def get(self, goal_id: str) -> GoalSnapshot | None:
        """Return one persisted Goal snapshot."""

    async def save(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        """Replace one persisted Goal snapshot atomically."""

    async def latest_for_chat(self, chat_id: str) -> GoalSnapshot | None:
        """Return the most recent non-terminal Goal, otherwise latest Goal."""


class InMemoryGoalStore:
    """Test store with the same snapshot replacement semantics as MySQL."""

    def __init__(self) -> None:
        self._items: dict[str, GoalSnapshot] = {}

    async def create(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        self._items[snapshot.goal_id] = snapshot.model_copy(deep=True)
        return snapshot.model_copy(deep=True)

    async def get(self, goal_id: str) -> GoalSnapshot | None:
        item = self._items.get(goal_id)
        return item.model_copy(deep=True) if item is not None else None

    async def save(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        self._items[snapshot.goal_id] = snapshot.model_copy(deep=True)
        return snapshot.model_copy(deep=True)

    async def latest_for_chat(self, chat_id: str) -> GoalSnapshot | None:
        matching = [
            item
            for item in self._items.values()
            if item.scope.chat_id == chat_id
        ]
        if not matching:
            return None
        active = [item for item in matching if not item.is_terminal]
        chosen = max(active or matching, key=lambda item: item.created_at)
        return chosen.model_copy(deep=True)


class GoalService:
    """Apply deterministic lifecycle rules to Goal snapshots."""

    def __init__(
        self,
        store: GoalStore,
        *,
        turn_budget: int = DEFAULT_GOAL_TURN_BUDGET,
    ) -> None:
        if turn_budget <= 0:
            raise ValueError("turn_budget must be positive")
        self._store = store
        self._turn_budget = turn_budget
        self._create_locks: dict[str, asyncio.Lock] = {}
        self._review_claim_locks: dict[str, asyncio.Lock] = {}
        self._goal_locks: dict[str, asyncio.Lock] = {}
        self._active_turn_msgids: dict[str, str] = {}

    def _goal_lock(self, goal_id: str) -> asyncio.Lock:
        return self._goal_locks.setdefault(goal_id, asyncio.Lock())

    async def create_goal(
        self,
        *,
        scope: GoalScope,
        contract: GoalContract,
    ) -> GoalSnapshot:
        lock = self._create_locks.setdefault(scope.chat_id, asyncio.Lock())
        async with lock:
            current = await self._store.latest_for_chat(scope.chat_id)
            if current is not None and not current.is_terminal:
                raise GoalConflictError("chat already has a non-terminal goal")
            snapshot = GoalSnapshot(
                scope=scope,
                contract=contract,
                criteria=[
                    GoalCriterionStatus(
                        criterion_id=f"criterion-{index}",
                        criterion=criterion,
                    )
                    for index, criterion in enumerate(
                        contract.completion_criteria,
                        1,
                    )
                ],
                turn_budget=self._turn_budget,
            )
            return await self._store.create(snapshot)

    async def get(self, goal_id: str) -> GoalSnapshot:
        return await self._require_goal(goal_id)

    async def recent_for_chat(self, chat_id: str) -> GoalSnapshot | None:
        """Return the monitor-selected Goal for one Chat."""
        return await self._store.latest_for_chat(chat_id)

    async def persist(self, goal: GoalSnapshot) -> GoalSnapshot:
        """Persist a runtime-owned state transition after completion review."""
        return await self._save(goal)

    async def enqueue_steering(
        self,
        goal_id: str,
        content: str,
    ) -> GoalSnapshot:
        """Durably queue normal user input without changing the Contract."""
        goal = await self._require_goal(goal_id)
        if goal.state not in {GoalState.ACTIVE, GoalState.WAITING}:
            raise GoalConflictError("goal does not accept steering")
        text = content.strip()
        if not text:
            raise ValueError("steering must not be blank")
        goal.steering.append(
            GoalSteering(sequence_no=len(goal.steering) + 1, content=text),
        )
        woke = goal.state == GoalState.WAITING
        if woke:
            goal.state = GoalState.ACTIVE
            goal.state_reason = None
        saved = await self._save(goal)
        if woke:
            notify_goal_wake(goal_id)
        return saved

    async def has_pending_steering(self, goal_id: str) -> bool:
        """Check whether in-turn Steering should prevent a new wait state."""
        goal = await self._require_goal(goal_id)
        return any(not item.consumed for item in goal.steering)

    async def link_subagent(self, goal_id: str, run_id: str) -> GoalSnapshot:
        goal = await self._require_goal(goal_id)
        if goal.is_terminal:
            raise GoalConflictError("terminal goals cannot link a subagent")
        if run_id not in goal.subagent_run_ids:
            goal.subagent_run_ids.append(run_id)
        return await self._save(goal)

    async def wake(
        self,
        goal_id: str,
        reason: str = "Goal wake event",
    ) -> GoalSnapshot:
        goal = await self._require_goal(goal_id)
        if goal.state == GoalState.WAITING:
            goal.state = GoalState.ACTIVE
            goal.state_reason = None
            goal.next_focus = reason
            saved = await self._save(goal)
            notify_goal_wake(goal_id)
            return saved
        return goal

    async def consume_steering(
        self,
        goal_id: str,
    ) -> tuple[GoalSnapshot, list[str]]:
        """Claim pending Steering in arrival order for one next Goal turn."""
        goal = await self._require_goal(goal_id)
        pending = [item for item in goal.steering if not item.consumed]
        for item in pending:
            item.consumed = True
        saved = await self._save(goal)
        return saved, [item.content for item in pending]

    async def request_control(
        self,
        goal_id: str,
        action: GoalControlAction,
    ) -> GoalSnapshot:
        async with self._goal_lock(goal_id):
            return await self._request_control_unlocked(goal_id, action)

    async def _request_control_unlocked(
        self,
        goal_id: str,
        action: GoalControlAction,
    ) -> GoalSnapshot:
        if action == GoalControlAction.EDIT:
            raise ValueError("edit requires a complete contract")
        goal = await self._require_goal(goal_id)
        if goal.is_terminal:
            raise GoalConflictError("terminal goals cannot be controlled")
        goal.control_commands.append(GoalControlCommand(action=action))
        if not goal.turn_active:
            self._apply_pending_control(goal)
        saved = await self._save(goal)
        if not saved.turn_active:
            notify_goal_wake(goal_id)
        return saved

    async def request_edit(
        self,
        goal_id: str,
        contract: GoalContract,
    ) -> GoalSnapshot:
        goal = await self._require_goal(goal_id)
        if goal.is_terminal:
            raise GoalConflictError("terminal goals cannot be edited")
        goal.control_commands.append(
            GoalControlCommand(
                action=GoalControlAction.EDIT,
                contract=contract,
            ),
        )
        approval_ids = self._pending_review_approval_ids(goal)
        if not goal.turn_active:
            applied = self._apply_pending_control(goal)
        else:
            applied = None
        saved = await self._save(goal)
        if applied == GoalControlAction.EDIT:
            await self._supersede_review_approvals(saved.goal_id, approval_ids)
        if not saved.turn_active:
            notify_goal_wake(goal_id)
        return saved

    async def resume(self, goal_id: str) -> GoalSnapshot:
        goal = await self._require_goal(goal_id)
        if goal.is_terminal:
            raise GoalConflictError("terminal goals cannot be resumed")
        if goal.turn_active:
            goal.control_commands.append(
                GoalControlCommand(action=GoalControlAction.RESUME),
            )
            return await self._save(goal)
        if goal.state == GoalState.LIMITED:
            goal.budget_cycle += 1
            goal.turns_used = 0
        if goal.state not in TERMINAL_GOAL_STATES:
            goal.state = GoalState.ACTIVE
            goal.state_reason = None
        saved = await self._save(goal)
        notify_goal_wake(goal_id)
        return saved

    async def begin_turn(
        self,
        goal_id: str,
        msgid: str | None = None,
    ) -> GoalSnapshot:
        """Mark a running Main Agent turn so controls settle at its boundary."""
        goal = await self._require_goal(goal_id)
        if goal.state != GoalState.ACTIVE or goal.turn_active:
            raise GoalConflictError("goal cannot begin a turn")
        goal.turn_active = True
        if msgid:
            self._active_turn_msgids[goal_id] = msgid
        return await self._save(goal)

    async def abandon_turn(self, goal_id: str, reason: str) -> GoalSnapshot:
        """Release a begun turn when its host cannot produce a valid boundary."""
        goal = await self._require_goal(goal_id)
        if goal.turn_active:
            goal.turn_active = False
        self._active_turn_msgids.pop(goal_id, None)
        if goal.state == GoalState.ACTIVE:
            goal.state = GoalState.INTERRUPTED
            goal.state_reason = reason
        return await self._save(goal)

    async def active_turn_matches(self, goal_id: str, msgid: str) -> bool:
        """Check whether the current Goal turn owns the supplied message id."""
        if not goal_id or not msgid:
            return False
        goal = await self._require_goal(goal_id)
        return bool(
            goal.state in {GoalState.ACTIVE, GoalState.WAITING}
            and self._active_turn_msgids.get(goal_id) == msgid,
        )

    async def interrupt_turn_if_matches(
        self,
        goal_id: str,
        msgid: str,
        reason: str,
    ) -> GoalSnapshot | None:
        """Interrupt the exact Goal turn currently owned by a stopped Chat."""
        async with self._goal_lock(goal_id):
            if not goal_id or not msgid:
                return None
            goal = await self._require_goal(goal_id)
            if (
                goal.state not in {GoalState.ACTIVE, GoalState.WAITING}
                or self._active_turn_msgids.get(goal_id) != msgid
            ):
                return None
            goal.turn_active = False
            self._active_turn_msgids.pop(goal_id, None)
            goal.state = GoalState.INTERRUPTED
            goal.state_reason = reason
            return await self._save(goal)

    async def settle_turn(
        self,
        goal_id: str,
        *,
        decision: GoalTurnDecision,
        next_focus: str | None = None,
        blocker: str | None = None,
        defer_budget_limit: bool = False,
        wake_from_steering: bool = False,
    ) -> GoalSnapshot:
        async with self._goal_lock(goal_id):
            return await self._settle_turn_unlocked(
                goal_id,
                decision=decision,
                next_focus=next_focus,
                blocker=blocker,
                defer_budget_limit=defer_budget_limit,
                wake_from_steering=wake_from_steering,
            )

    async def _settle_turn_unlocked(
        self,
        goal_id: str,
        *,
        decision: GoalTurnDecision,
        next_focus: str | None = None,
        blocker: str | None = None,
        defer_budget_limit: bool = False,
        wake_from_steering: bool = False,
    ) -> GoalSnapshot:
        """Persist one finished Main Agent turn and apply pending user control."""
        goal = await self._require_goal(goal_id)
        if goal.state != GoalState.ACTIVE:
            raise GoalConflictError("goal is not active")
        if goal.turn_active:
            goal.turn_active = False
        goal.turns_used += 1
        approval_ids = self._pending_review_approval_ids(goal)
        applied = self._apply_pending_control(goal)
        if applied == GoalControlAction.EDIT:
            self._active_turn_msgids.pop(goal_id, None)
            saved = await self._save(goal)
            await self._supersede_review_approvals(
                saved.goal_id,
                approval_ids,
            )
            return saved
        if applied is not None:
            self._active_turn_msgids.pop(goal_id, None)
            return await self._save(goal)
        self._apply_turn_decision(
            goal,
            decision=decision,
            next_focus=next_focus,
            blocker=blocker,
            wake_from_steering=wake_from_steering,
        )
        if (
            not defer_budget_limit
            and goal.state == GoalState.ACTIVE
            and goal.turns_used >= goal.turn_budget
        ):
            goal.state = GoalState.LIMITED
            goal.state_reason = "Main Agent turn budget exhausted"
        if goal.state != GoalState.WAITING:
            self._active_turn_msgids.pop(goal_id, None)
        return await self._save(goal)

    async def enforce_budget_limit(self, goal_id: str) -> GoalSnapshot:
        """Apply the fixed Main-Agent budget after a final completion review."""
        goal = await self._require_goal(goal_id)
        if (
            goal.state == GoalState.ACTIVE
            and goal.turns_used >= goal.turn_budget
        ):
            goal.state = GoalState.LIMITED
            budget_reason = "Main Agent turn budget exhausted"
            if goal.state_reason:
                goal.state_reason = f"{goal.state_reason}; {budget_reason}"
            else:
                goal.state_reason = budget_reason
            return await self._save(goal)
        return goal

    async def record_completion_review(
        self,
        goal_id: str,
        criterion_id: str,
        *,
        passed: bool,
        evidence_ref: str | None = None,
        expected_revision: int | None = None,
    ) -> GoalSnapshot:
        goal = await self._require_goal(goal_id)
        if goal.state != GoalState.ACTIVE:
            return goal
        if (
            expected_revision is not None
            and goal.revision != expected_revision
        ):
            return goal
        criterion = next(
            (
                item
                for item in goal.criteria
                if item.criterion_id == criterion_id
            ),
            None,
        )
        if criterion is None:
            raise ValueError("criterion not found")
        criterion.verification_request_id = None
        goal.pending_review_criteria = [
            item_id
            for item_id in goal.pending_review_criteria
            if item_id != criterion_id
        ]
        if passed:
            if evidence_ref:
                criterion.evidence_refs.append(evidence_ref)
            criterion.verified = True
            criterion.consecutive_failures = 0
        else:
            criterion.verified = False
            criterion.consecutive_failures += 1
            rejection_reason = evidence_ref or "completion review rejected"
            goal.state_reason = f"review rejected: {rejection_reason}"
            if criterion.consecutive_failures >= 3:
                goal.state = GoalState.BLOCKED
                goal.state_reason = f"criterion review rejected three times: {rejection_reason}"
        return await self._save(goal)

    async def complete_completion_review(
        self,
        goal_id: str,
        *,
        expected_revision: int,
    ) -> GoalSnapshot:
        """Complete only the still-active Revision reviewed by the Judge."""
        goal = await self._require_goal(goal_id)
        if (
            goal.state != GoalState.ACTIVE
            or goal.revision != expected_revision
            or not all(item.verified for item in goal.criteria)
        ):
            return goal
        goal.state = GoalState.COMPLETE
        goal.state_reason = None
        return await self._save(goal)

    async def wait_for_completion_review_approval(
        self,
        goal_id: str,
        criterion_id: str,
        *,
        request_id: str,
        reason: str,
        expected_revision: int | None = None,
        criterion_ids: set[str] | None = None,
    ) -> GoalSnapshot:
        """Persist a completion review approval wait without recording a failure."""
        goal = await self._require_goal(goal_id)
        if (
            expected_revision is not None
            and goal.revision != expected_revision
        ):
            return goal
        requested = criterion_ids or {criterion_id}
        available = {item.criterion_id for item in goal.criteria}
        if not requested.issubset(available):
            raise ValueError("criterion not found")
        for criterion in goal.criteria:
            if criterion.criterion_id in requested:
                criterion.verification_request_id = request_id
        goal.pending_review_criteria = sorted(requested)
        goal.state = GoalState.WAITING
        goal.state_reason = reason
        goal.next_focus = None
        return await self._save(goal)

    async def claim_pending_completion_review(
        self,
        goal_id: str,
    ) -> tuple[GoalSnapshot, str] | None:
        """Claim one pending review retry so it cannot be counted twice."""
        lock = self._review_claim_locks.setdefault(goal_id, asyncio.Lock())
        async with lock:
            goal = await self._require_goal(goal_id)
            if (
                goal.state != GoalState.ACTIVE
                or not goal.pending_review_criteria
                or goal.pending_review_claim_id
            ):
                return None
            claim_id = uuid4().hex
            goal.pending_review_claim_id = claim_id
            return await self._save(goal), claim_id

    async def release_pending_completion_review_claim(
        self,
        goal_id: str,
        claim_id: str,
    ) -> GoalSnapshot:
        """Release an unfinished retry claim after the reviewer returns."""
        lock = self._review_claim_locks.setdefault(goal_id, asyncio.Lock())
        async with lock:
            goal = await self._require_goal(goal_id)
            if goal.pending_review_claim_id != claim_id:
                return goal
            goal.pending_review_claim_id = None
            return await self._save(goal)

    def _apply_pending_control(
        self,
        goal: GoalSnapshot,
    ) -> GoalControlAction | None:
        pending = [
            command
            for command in goal.control_commands
            if command.status == "pending"
        ]
        if not pending:
            return None
        selected = max(
            pending,
            key=lambda command: _CONTROL_PRECEDENCE[command.action],
        )
        for command in pending:
            command.status = "applied" if command is selected else "superseded"
        if selected.action == GoalControlAction.CANCEL:
            goal.state = GoalState.CANCELLED
            goal.state_reason = "Cancelled by user"
        elif selected.action == GoalControlAction.PAUSE:
            goal.state = GoalState.PAUSED
            goal.state_reason = "Paused by user"
        elif selected.action == GoalControlAction.RESUME:
            if goal.state == GoalState.LIMITED:
                goal.budget_cycle += 1
                goal.turns_used = 0
            goal.state = GoalState.ACTIVE
            goal.state_reason = None
        elif selected.action == GoalControlAction.EDIT:
            if selected.contract is None:
                raise ValueError("edit command has no contract")
            self._activate_revision(goal, selected.contract)
        return selected.action

    @staticmethod
    def _apply_turn_decision(
        goal: GoalSnapshot,
        *,
        decision: GoalTurnDecision,
        next_focus: str | None,
        blocker: str | None,
        wake_from_steering: bool,
    ) -> None:
        if decision == "wait":
            if wake_from_steering:
                goal.state = GoalState.ACTIVE
                goal.state_reason = None
                goal.next_focus = (
                    next_focus or "Apply newly received user steering"
                )
            else:
                goal.state = GoalState.WAITING
                goal.state_reason = (
                    next_focus or "Waiting for a wake condition"
                )
                goal.next_focus = None
        elif decision == "blocked":
            goal.state = GoalState.BLOCKED
            goal.state_reason = blocker or "Main Agent reported a blocker"
            goal.next_focus = None
        else:
            goal.next_focus = next_focus

    @staticmethod
    def _activate_revision(goal: GoalSnapshot, contract: GoalContract) -> None:
        goal.revision += 1
        goal.contract = contract
        goal.criteria = [
            GoalCriterionStatus(
                criterion_id=f"criterion-{index}",
                criterion=criterion,
            )
            for index, criterion in enumerate(contract.completion_criteria, 1)
        ]
        goal.pending_review_criteria = []
        goal.pending_review_claim_id = None
        if goal.state == GoalState.WAITING:
            goal.state = GoalState.ACTIVE
        goal.next_focus = None
        if goal.state == GoalState.ACTIVE:
            goal.state_reason = None

    @staticmethod
    def _pending_review_approval_ids(goal: GoalSnapshot) -> tuple[str, ...]:
        return tuple(
            item.verification_request_id
            for item in goal.criteria
            if item.verification_request_id
        )

    @staticmethod
    async def _supersede_review_approvals(
        goal_id: str,
        request_ids: tuple[str, ...],
    ) -> None:
        if not request_ids:
            return
        from ..approvals import get_approval_service

        await get_approval_service().supersede_goal_review_approvals(
            goal_id,
            request_ids,
        )

    async def _require_goal(self, goal_id: str) -> GoalSnapshot:
        goal = await self._store.get(goal_id)
        if goal is None:
            raise GoalNotFoundError("goal not found")
        return goal

    async def _save(self, goal: GoalSnapshot) -> GoalSnapshot:
        goal.updated_at = utc_now()
        saved = await self._store.save(goal)
        logger.info(
            "goal_state goal_id=%s revision=%s state=%s turns=%s/%s active_turn=%s",
            saved.goal_id,
            saved.revision,
            saved.state.value,
            saved.turns_used,
            saved.turn_budget,
            saved.turn_active,
        )
        return saved
