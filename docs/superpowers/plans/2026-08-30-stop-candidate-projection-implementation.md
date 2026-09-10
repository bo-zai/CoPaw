# Stop Candidate Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make visible text in structured assistant responses eligible for Stop, invoke Stop exactly once for Goal final delivery, and make skipped Stop gates observable through `hook_telemetry.v1`.

**Architecture:** Introduce one candidate-selection/text-projection rule and apply it consistently to memory extraction, buffered delivery, and text replacement. Keep the Hook Runtime handler telemetry schema, adding Stop gate state to the existing event rather than creating a second event type. Goal internal turns remain outside Stop; only its final delivery uses the ordinary gate with a Finalization-local retry loop.

**Tech Stack:** Python, Pydantic hook models, pytest, existing Hook Runtime and Goal Runtime.

---

### Task 1: Candidate text projection

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/app/runner/turn_lifecycle.py`
- Test: `tests/unit/app/test_runner_hook_runtime.py`

- [ ] **Step 1: Write failing tests** for `thinking + text`, `text + image`, and `thinking + text + tool_use`; assert only the first two have a non-empty projection and only eligible messages are buffered.
- [ ] **Step 2: Run the targeted tests** and verify the `thinking + text` test fails because `_has_only_text_blocks` rejects the response.
- [ ] **Step 3: Implement the shared eligibility rule**: current-turn, non-live assistant message, no `tool_use`, at least one non-empty text block. Extract only ordered text blocks; retain reasoning and passive media in memory.
- [ ] **Step 4: Implement text-preserving replacement**: write the full replacement to the first text block, clear later text blocks, never alter non-text blocks.
- [ ] **Step 5: Run the targeted projection tests** and verify they pass.

### Task 2: Stop telemetry for skipped gates

**Files:**
- Modify: `src/swe/agents/hook_runtime/runtime.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/agents/hook_runtime/test_handlers_and_merge.py`
- Test: `tests/unit/app/test_runner_hook_runtime.py`

- [ ] **Step 1: Write failing tests** for a skipped Stop gate that assert `hook_telemetry.v1`, `execution_state="skipped"`, empty handlers, stable skip reason, and no candidate plaintext.
- [ ] **Step 2: Run the telemetry tests** and verify current behavior has no Stop telemetry for an empty candidate.
- [ ] **Step 3: Add a narrow Stop telemetry emitter** that reuses the current schema and records the safe candidate summary; preserve non-Stop behavior where no handler means no telemetry.
- [ ] **Step 4: Call it for each Runner Stop skip branch** and mark actual Stop execution as `execution_state="executed"` without changing decision merge semantics.
- [ ] **Step 5: Run the targeted telemetry tests** and verify they pass.

### Task 3: Goal Finalization Stop boundary

**Files:**
- Modify: `src/swe/app/runner/turn_lifecycle.py`
- Test: `tests/unit/app/test_runner_goal_lifecycle.py`

- [ ] **Step 1: Write failing lifecycle tests** proving a Goal final text calls the Stop gate once, a block retries only a tool-free Finalization turn within `max_stop_turns`, and Finalization Fallback does not call Stop.
- [ ] **Step 2: Run those tests** and verify finalization currently bypasses `_resolve_stop_gate`.
- [ ] **Step 3: Add a Finalization-local gate loop** that derives the text projection, calls the ordinary Stop emitter, and retries only finalization without mutating Goal state or its turn budget.
- [ ] **Step 4: Run the Goal lifecycle tests** and verify they pass.

### Task 4: Regression verification and handoff

**Files:**
- Modify: `CONTEXT.md`
- Modify: `docs/adr/0020-stop-is-the-unified-completion-hook.md`
- Modify: `docs/adr/0029-stop-output-transformations-use-strict-two-phase-finalization.md`
- Modify: `docs/superpowers/specs/2026-08-22-goal-runtime-design.md`

- [ ] **Step 1: Run the focused Hook Runtime, Runner Hook, and Goal lifecycle test files.**
- [ ] **Step 2: Run formatting, `git diff --check`, and GitNexus `detect_changes`.**
- [ ] **Step 3: Review that code and documentation match the approved terms, then commit only task-owned files.**
