# Console Chat B3 Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the complete B3 parent context supplied to `POST /console/chat` and use it to parent Agent Trace SDK spans.

**Architecture:** Parse and validate the B3 multi-header context at the Console HTTP boundary, carry the canonical values through the background turn payload, then activate that remote context before the existing `agent.run` span is created. The custom trace manager retains the upstream trace identifier for query correlation; it is not responsible for B3 parentage.

**Tech Stack:** FastAPI, Python `contextvars`, Agent Trace SDK, pytest.

---

### Task 1: Carry a validated B3 context through the Console payload

**Files:**
- Modify: `src/swe/app/b3_headers.py`
- Modify: `src/swe/app/routers/console.py:958-971,1300-1320`
- Modify: `src/swe/app/channels/console/channel.py:296-333`
- Test: `tests/unit/routers/test_console_chat_stream.py`

- [ ] **Step 1: Write failing router tests**

```python
def test_console_chat_copies_complete_b3_context_to_native_meta(...):
    # POST all three valid B3 headers.
    assert tracker.payload["meta"]["b3_context"] == {
        "X-B3-Traceid": TRACE_ID,
        "X-B3-Spanid": PARENT_SPAN_ID,
        "X-B3-Sampled": "1",
    }

def test_console_chat_rejects_partial_b3_context(...):
    response = client.post(..., headers={"X-B3-Traceid": TRACE_ID})
    assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -k b3 -q`

Expected: FAIL because the route only copies `b3_trace_id` and accepts partial B3 headers.

- [ ] **Step 3: Implement the minimal canonical B3 extraction helper and payload propagation**

```python
def extract_required_b3_headers(headers: Any) -> dict[str, str] | None:
    values = extract_b3_headers(headers)
    if not values:
        return None
    # Require Traceid, Spanid and Sampled, then validate their documented formats.
    return {name: values[name] for name in REQUIRED_B3_HEADERS}
```

Store the result in `native_payload["meta"]["b3_context"]`, retain `b3_trace_id` only for existing custom trace-manager correlation, and copy `b3_context` onto the generated `AgentRequest`.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_header_passthrough.py tests/unit/routers/test_console_chat_stream.py -k b3 -q`

Expected: PASS.

### Task 2: Bind the remote B3 parent before `agent.run`

**Files:**
- Modify: `src/swe/tracing/agent_trace_sdk.py`
- Modify: `src/swe/app/runner/runner.py:5520-5575`
- Test: `tests/unit/app/test_agent_trace_sdk.py`

- [ ] **Step 1: Write a failing agent trace test**

```python
async def test_query_handler_parents_agent_run_to_request_b3_context(...):
    request.b3_context = {"X-B3-Traceid": TRACE_ID, ...}
    ...
    assert root["trace_id"] == TRACE_ID
    assert root["parent_span_id"] == PARENT_SPAN_ID
    assert root["sampled"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_agent_trace_sdk.py -k b3 -q`

Expected: FAIL because the current `agent.run` span is an unparented root.

- [ ] **Step 3: Implement the SDK compatibility boundary and binding**

```python
with use_remote_b3_context(getattr(request, "b3_context", None)):
    async with global_tracer.start_as_current_span("agent.run", kind=SpanKind.INTERNAL, ...):
        ...
```

Expose the real SDK extraction/binding API through `agent_trace_sdk.py`, with a no-op-compatible fallback for local development. Do not change trace-manager lifecycle ownership.

- [ ] **Step 4: Run the agent SDK tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_agent_trace_sdk.py -q`

Expected: PASS.

### Task 3: Verify the complete regression boundary

**Files:**
- Test: `tests/unit/app/test_header_passthrough.py`
- Test: `tests/unit/routers/test_console_chat_stream.py`
- Test: `tests/unit/app/test_runner_query_retry.py`
- Test: `tests/unit/app/test_agent_trace_sdk.py`

- [ ] **Step 1: Run the focused B3 and tracing suite**

Run: `../../venv/bin/python -m pytest tests/unit/app/test_header_passthrough.py tests/unit/routers/test_console_chat_stream.py tests/unit/app/test_runner_query_retry.py tests/unit/app/test_agent_trace_sdk.py -q`

Expected: PASS.

- [ ] **Step 2: Inspect the diff impact before commit**

Run: `detect_changes({scope: "worktree"})`

Expected: only the Console route, Console channel, tracing adapter/runner, and their targeted tests are affected.

- [ ] **Step 3: Commit the focused change**

```bash
git add src/swe/app/b3_headers.py src/swe/app/routers/console.py src/swe/app/channels/console/channel.py src/swe/tracing/agent_trace_sdk.py src/swe/app/runner/runner.py tests/unit/routers/test_console_chat_stream.py tests/unit/app/test_agent_trace_sdk.py
git commit -m "fix(tracing): preserve console chat B3 context"
```
