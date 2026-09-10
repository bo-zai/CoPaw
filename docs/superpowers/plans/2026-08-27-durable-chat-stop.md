# Durable Chat Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make explicit Console Stop preserve and query an admitted answer turn without breaking the existing `/console/chat` submission contract.

**Architecture:** A turn-aware TaskTracker becomes the atomic owner of stop admission and output freezing.  Runner/session code admits the user question before Agent execution and settles stopped metadata; Console router/API code validates turn ownership and exposes compatible responses.  The frontend stores server identities and applies a Chat-scoped composer lock.

**Tech Stack:** Python 3, FastAPI, asyncio, pytest, React, TypeScript, Vitest.

---

### Task 1: Make tracked runs turn-aware and freeze output after Stop acceptance

**Files:**
- Modify: `src/swe/app/runner/task_tracker.py`
- Modify: `tests/unit/app/test_task_tracker.py`

- [ ] **Step 1: Write failing tracker tests**

Add tests that start a run with `msgid="turn-1"`, assert a Stop for another
Message ID is a no-op, assert the matching Stop transitions the run to
`stopping` without immediate task cancellation, and assert output yielded after
the transition is not delivered to either the first subscriber or a reconnect.

- [ ] **Step 2: Run the tracker tests and verify the new assertions fail**

Run: `venv/bin/python -m pytest tests/unit/app/test_task_tracker.py -q`

Expected: the exact-turn and output-freeze assertions fail against the
chat-only tracker.

- [ ] **Step 3: Implement a minimal turn-aware stop state**

Add `msgid`, accepted-stop state, and settlement helpers to `_RunState`.  Make
`attach_or_start` receive the server-issued message ID.  Add a stop-claim API
that checks the exact ID when supplied, preserves the old Chat-only fallback,
marks `stopping`, and returns an immutable result containing acceptance and the
validated identifiers.  Gate `_broadcast_sse` on the state under the tracker
lock.  Add a five-second bounded cooperative stop helper which cancels only a
still-running producer after the wait.

- [ ] **Step 4: Run the focused tracker tests**

Run: `venv/bin/python -m pytest tests/unit/app/test_task_tracker.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the tracked-run boundary**

Run: `git add src/swe/app/runner/task_tracker.py tests/unit/app/test_task_tracker.py && git commit -m "feat(chat): track stop by answer turn"`

### Task 2: Admit user questions before execution and settle stopped turn state

**Files:**
- Modify: `src/swe/app/runner/session.py`
- Modify: `src/swe/app/runner/session_lifecycle.py`
- Modify: `src/swe/app/runner/query_cleanup.py`
- Modify: `src/swe/app/runner/runner.py`
- Modify: `tests/unit/app/test_runner_session.py`
- Modify: `tests/unit/app/test_query_session_execution.py`

- [ ] **Step 1: Write failing session and cleanup tests**

Test that a submitted user message is saved before a fake Agent starts, that a
save failure prevents the Agent callback, and that cancelling before session
load still leaves the saved user message plus `turn_states[msgid]` stopped
metadata.  Test that a partial assistant display message gains
`metadata.turn_status == "stopped"`.

- [ ] **Step 2: Run the focused session tests and verify RED**

Run: `venv/bin/python -m pytest tests/unit/app/test_runner_session.py tests/unit/app/test_query_session_execution.py -q`

Expected: new admission and stopped-settlement tests fail.

- [ ] **Step 3: Implement durable admission and stopped settlement**

Create a session helper that writes the user anchor before the execution path
can call the Agent.  Carry `msgid` through execution state.  Make cleanup save
admitted state even when normal session loading never completed.  At accepted
stop settlement, mark the last displayable assistant message or store the
root-level no-output marker; log failed stop persistence without retrying.

- [ ] **Step 4: Run the focused session tests**

Run: `venv/bin/python -m pytest tests/unit/app/test_runner_session.py tests/unit/app/test_query_session_execution.py -q`

Expected: PASS.

- [ ] **Step 5: Commit durable turn persistence**

Run: `git add src/swe/app/runner/session.py src/swe/app/runner/session_lifecycle.py src/swe/app/runner/query_cleanup.py src/swe/app/runner/runner.py tests/unit/app/test_runner_session.py tests/unit/app/test_query_session_execution.py && git commit -m "feat(chat): persist admitted stopped turns"`

### Task 3: Expose compatible Stop and answer-turn APIs with lifecycle gates

**Files:**
- Modify: `src/swe/app/routers/console.py`
- Modify: `src/swe/app/_app.py`
- Modify: `src/swe/app/runner/api.py`
- Modify: `src/swe/app/runner/manager.py`
- Modify: `tests/unit/routers/test_console_chat_reconnect.py`
- Modify: `tests/unit/app/test_chat_answer_turn_api.py`

- [ ] **Step 1: Write failing router and query tests**

Cover `X-Swe-Chatid` exposure, Stop with exact identity, accepted/re-accepted
and no-op response bodies, unauthorised no-op, early `session_id` resolution,
and `409` for a non-reconnect submission while stopping.  Cover
`/chats/answer-turn?chat_id=&msgid=` returning `status` and `turn_status`,
including a no-output stopped turn.

- [ ] **Step 2: Run router/API tests and verify RED**

Run: `venv/bin/python -m pytest tests/unit/routers/test_console_chat_reconnect.py tests/unit/app/test_chat_answer_turn_api.py -q`

Expected: new header, Stop body, query identity/status and admission-gate
assertions fail.

- [ ] **Step 3: Implement compatible API behavior**

Add `X-Swe-Chatid` to stream headers and CORS exposure.  Extend the Stop route
with optional `msgid` and `session_id`, validate Chat ownership before invoking
the tracker, return only verified identity on acceptance, and preserve
`stopped` for legacy clients.  Reject non-reconnect submissions during
stopping.  Make answer-turn lookup prefer `chat_id + msgid`, constrain legacy
session lookup to authorised Chats, and normalise transient/terminal status.
Make Chat deletion claim task ownership before removing session state.

- [ ] **Step 4: Run router/API tests**

Run: `venv/bin/python -m pytest tests/unit/routers/test_console_chat_reconnect.py tests/unit/app/test_chat_answer_turn_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit router, query and deletion behavior**

Run: `git add src/swe/app/routers/console.py src/swe/app/_app.py src/swe/app/runner/api.py src/swe/app/runner/manager.py tests/unit/routers/test_console_chat_reconnect.py tests/unit/app/test_chat_answer_turn_api.py && git commit -m "feat(chat): expose turn-bound stop API"`

### Task 4: Coordinate approvals, workers and Goal interruption

**Files:**
- Modify: `src/swe/app/approvals/service.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/app/goals/service.py`
- Modify: `tests/unit/app/test_approval_service.py`
- Modify: `tests/unit/app/goals/test_service.py`
- Modify: `tests/unit/app/test_runner_goal_lifecycle.py`

- [ ] **Step 1: Write failing lifecycle tests**

Create a turn-scoped pending approval and assert Stop marks it `superseded`.
Create an active Goal turn and assert Stop calls `abandon_turn`; assert a
durably applied Goal cancel remains `CANCELLED`.  Assert selected and
background worker completion cannot feed an already stopped turn.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run: `venv/bin/python -m pytest tests/unit/app/test_approval_service.py tests/unit/app/goals/test_service.py tests/unit/app/test_runner_goal_lifecycle.py -q`

Expected: new turn ownership and interruption assertions fail.

- [ ] **Step 3: Implement coordinated stop effects**

Record enough turn identity on pending approvals and worker links to supersede
or cancel only the stopped turn.  Make agent interruption cancel selected and
active background work best-effort and guard all return paths from merging into
the stopped turn.  Add Goal service logic that does not overwrite a first-won
`CANCELLED` state and otherwise abandons the active turn into `INTERRUPTED`.

- [ ] **Step 4: Run lifecycle tests**

Run: `venv/bin/python -m pytest tests/unit/app/test_approval_service.py tests/unit/app/goals/test_service.py tests/unit/app/test_runner_goal_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit coordinated lifecycle behavior**

Run: `git add src/swe/app/approvals/service.py src/swe/agents/react_agent.py src/swe/app/runner/runner.py src/swe/app/goals/service.py tests/unit/app/test_approval_service.py tests/unit/app/goals/test_service.py tests/unit/app/test_runner_goal_lifecycle.py && git commit -m "feat(chat): settle stop-owned lifecycle work"`

### Task 5: Capture turn identity and apply Chat-scoped Console stop behavior

**Files:**
- Modify: `console/src/api/modules/chat.ts`
- Modify: `console/src/pages/Chat/index.tsx`
- Modify: `console/src/pages/Chat/index.test.tsx`

- [ ] **Step 1: Write failing Console tests**

Mock a streaming response with `X-Swe-Chatid`, `X-Swe-Msgid`, and
`X-Swe-Sessionid`; assert the Stop call uses exact `chat_id + msgid`.  Assert
only explicit UI cancellation invokes Stop, the stopping Chat composer is
disabled until the original stream closes, another Chat stays enabled, and
`409 chat is stopping` preserves the draft without a notification.

- [ ] **Step 2: Run the Console test and verify RED**

Run: `pnpm --dir console test:run src/pages/Chat/index.test.tsx --run`

Expected: the exact Stop parameters and Composer-lock assertions fail.

- [ ] **Step 3: Implement client turn state and stop interaction**

Parse and persist the three stream headers in the per-session Chat state.
Extend `chatApi.stopChat` with optional `msgid` and `sessionId`.  Use the exact
identity whenever available; use early fallback only before headers arrive.
Maintain a per-Chat stopping flag around the original stream lifecycle, wire it
into Composer disabled state, and intercept only the recognised `409` race.
Remove any implicit Stop call from generic transport cancellation.

- [ ] **Step 4: Run the Console test**

Run: `pnpm --dir console test:run src/pages/Chat/index.test.tsx --run`

Expected: PASS.

- [ ] **Step 5: Commit the Console behavior**

Run: `git add console/src/api/modules/chat.ts console/src/pages/Chat/index.tsx console/src/pages/Chat/index.test.tsx && git commit -m "feat(console): bind stop to answer turn"`

### Task 6: Run focused regression suites and inspect the final scope

**Files:**
- Verify: all files above

- [ ] **Step 1: Run backend regression suites**

Run: `venv/bin/python -m pytest tests/unit/app/test_task_tracker.py tests/unit/app/test_runner_session.py tests/unit/app/test_query_session_execution.py tests/unit/routers/test_console_chat_reconnect.py tests/unit/app/test_chat_answer_turn_api.py tests/unit/app/test_approval_service.py tests/unit/app/goals/test_service.py tests/unit/app/test_runner_goal_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 2: Run Console test and build checks**

Run: `pnpm --dir console test:run src/pages/Chat/index.test.tsx --run && pnpm --dir console build`

Expected: PASS.

- [ ] **Step 3: Verify the committed change scope**

Run: `git diff --check HEAD~5..HEAD && node .gitnexus/run.cjs analyze && node .gitnexus/run.cjs detect-changes --repo CoPaw --base-ref HEAD~5`

Expected: no whitespace errors; GitNexus reports only Console Chat Stop,
runner/session, lifecycle and Goal/approval flows.
