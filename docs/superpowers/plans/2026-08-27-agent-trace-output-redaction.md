# AgentTraceSDK Output Redaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export bounded, redacted model and tool result summaries through AgentTraceSDK `cmb.output.arguments` without changing the existing `swe.tracing` pipeline or tool execution contracts.

**Architecture:** Add one JSON-safe, bounded sanitization primitive to `swe.tracing.sanitizer`, then make a small Agent-specific output projection module consume it. Model tracing passes a `Msg` directly to its output factory. Tool tracing wraps the existing `dict | None` execution result with a private trace-only outcome that also reads the terminal ToolResultBlock from memory; the public method still returns the original value.

**Tech Stack:** Python 3.10+, AgentScope `Msg`, `trace_sdk`, pytest, test-only `trace_sdk` fake.

---

## File Map

| Path | Action | Responsibility |
| --- | --- | --- |
| `src/swe/tracing/sanitizer.py` | Modify | Shared recursive secret redaction and UTF-8-bounded JSON-compatible value projection. |
| `tests/unit/tracing/test_sanitizer.py` | Modify | Unit coverage for value-pattern redaction and structural bounds. |
| `src/swe/agents/agent_trace_output.py` | Create | Model/tool output contracts, high-risk tool classification, and private tool outcome type. |
| `tests/unit/agents/test_agent_trace_output.py` | Create | Pure output-contract tests, including high-risk output exclusion. |
| `src/swe/agents/react_agent.py` | Modify | Replace the empty chat output factory with the model projection. |
| `src/swe/agents/tool_guard_mixin.py` | Modify | Preserve the public tool return value while providing terminal memory output to the semantic tool Span. |
| `tests/fakes/trace_sdk/_impl.py` | Modify | Make the test fake execute output factories and record `cmb.output.arguments`. |
| `tests/unit/agents/test_agent_trace_sdk.py` | Modify | Verify decorator contracts and non-empty output factory values. |
| `trace_design.md` | Modify | Document Swe's output contract and high-risk exclusions. |
| `docs/superpowers/specs/2026-08-27-agent-trace-output-redaction-design.md` | Modify | Record final accepted limits and remove any superseded empty-factory wording. |

### Task 1: Add a bounded shared trace-value sanitizer

**Files:**
- Modify: `src/swe/tracing/sanitizer.py`
- Modify: `tests/unit/tracing/test_sanitizer.py`

- [ ] **Step 1: Write failing tests for nested redaction and byte-based bounds**

Add imports and tests that establish the new public return contract:

```python
from swe.tracing.sanitizer import sanitize_trace_value


def test_sanitize_trace_value_redacts_embedded_secrets_and_registered_values():
    register_sensitive_values(["tenant-secret"])

    result = sanitize_trace_value(
        {
            "authorization": "Bearer direct-secret",
            "message": "cookie: sid=abc; token=tenant-secret",
            "nested": {"private_key": "secret-key-material"},
        },
    )

    assert result.value["authorization"] == "[REDACTED]"
    assert "tenant-secret" not in result.value["message"]
    assert result.value["nested"]["private_key"] == "[REDACTED]"


def test_sanitize_trace_value_bounds_utf8_depth_and_collection_size():
    text_result = sanitize_trace_value("你" * 20, max_bytes=16)
    nested_result = sanitize_trace_value(
        {"items": ["你" * 20, "discarded"], "nested": {"a": {"b": 1}}},
        max_depth=2,
        max_items=1,
    )

    assert text_result.truncated is True
    assert text_result.value.endswith("...")
    assert len(text_result.value.encode("utf-8")) <= 19
    assert nested_result.value["items"] == ["你" * 20]
    assert nested_result.value["nested"]["a"] == "<max-depth-exceeded>"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/tracing/test_sanitizer.py -q
```

Expected: FAIL because `sanitize_trace_value` does not exist.

- [ ] **Step 3: Implement one reusable sanitizer result type and value function**

Add the following public shape in `src/swe/tracing/sanitizer.py`; keep `sanitize_dict` and `sanitize_string` behavior unchanged for existing callers:

```python
@dataclass(frozen=True)
class SanitizedTraceValue:
    value: Any
    original_bytes: int
    truncated: bool


def sanitize_trace_value(
    value: Any,
    *,
    max_bytes: int = 2048,
    max_depth: int = 5,
    max_items: int = 32,
) -> SanitizedTraceValue:
    """Return a JSON-compatible, redacted and bounded trace value."""
    # Convert Pydantic-like values with model_dump(mode="json") when present.
    # Redact dictionary keys before traversing their values.
    # Apply registered-value replacement plus embedded-text patterns to strings.
    # Truncate strings by UTF-8 bytes without splitting a code point.
    # Replace over-depth values with "<max-depth-exceeded>" and excess items
    # with an omitted-count marker. Never propagate serialization errors.
```

Use module-level compiled regular expressions for Authorization/Bearer, Cookie,
sensitive `key=value`, JWTs, PEM private keys, and URL credentials. Reuse
`_redact_registered_values` before applying the patterns. Keep the replacement
literal `[REDACTED]`; do not expose configurable redaction values through this
new application-side boundary.

- [ ] **Step 4: Add complete edge-case tests**

Add parameterized coverage for:

```python
(
    "Authorization: Bearer abcdefghijklmnop",
    "Cookie: sid=abcdef",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
    "postgres://alice:password@db.example/app",
    "-----BEGIN " + "PRIVATE KEY-----\nsecret\n-----END " + "PRIVATE KEY-----",
)
```

For every value, assert the original credential fragment is absent. Also test
that numbers, booleans, `None`, dictionaries, and lists remain JSON-compatible
and that malformed `model_dump` objects produce a string fallback rather than
raising.

- [ ] **Step 5: Run the sanitizer suite**

Run:

```bash
venv/bin/python -m pytest tests/unit/tracing/test_sanitizer.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the isolated sanitizer change**

```bash
git add src/swe/tracing/sanitizer.py tests/unit/tracing/test_sanitizer.py
git commit -m "feat: add bounded trace value sanitization"
```

### Task 2: Define AgentTraceSDK output projections

**Files:**
- Create: `src/swe/agents/agent_trace_output.py`
- Create: `tests/unit/agents/test_agent_trace_output.py`

- [ ] **Step 1: Write failing output-contract tests**

Create `tests/unit/agents/test_agent_trace_output.py` with direct tests:

```python
from agentscope.message import Msg

from swe.agents.agent_trace_output import (
    ToolTraceOutcome,
    build_chat_output_arguments,
    build_tool_output_arguments,
)


def test_build_chat_output_arguments_keeps_only_safe_message_fields():
    result = Msg(
        name="Friday",
        role="assistant",
        content=[
            {"type": "text", "text": "token=tenant-secret"},
            {"type": "tool_use", "name": "read_file", "input": {"path": "x"}},
        ],
        metadata={"provider_raw": "must-not-export"},
    )

    output = build_chat_output_arguments(result)

    assert output["role"] == "assistant"
    assert output["tool_call_names"] == ["read_file"]
    assert "tenant-secret" not in output["text"]
    assert "provider_raw" not in output


def test_build_tool_output_arguments_hides_shell_preview():
    output = build_tool_output_arguments(
        ToolTraceOutcome(
            business_result=None,
            terminal_output="password=secret",
            tool_name="execute_shell_command",
        ),
    )

    assert output["status"] == "ok"
    assert output["output_bytes"] > 0
    assert "output_preview" not in output
```

- [ ] **Step 2: Run the projection tests and verify they fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/agents/test_agent_trace_output.py -q
```

Expected: FAIL because the projection module is absent.

- [ ] **Step 3: Implement a narrow Agent-specific projection module**

Create `src/swe/agents/agent_trace_output.py` with these names and contracts:

```python
@dataclass(frozen=True)
class ToolTraceOutcome:
    business_result: dict[str, Any] | None
    terminal_output: Any
    tool_name: str
    mcp_server: str | None = None


def build_chat_output_arguments(result: Msg) -> dict[str, Any]:
    """Project a model message without exporting metadata or attachments."""


def build_tool_output_arguments(outcome: ToolTraceOutcome) -> dict[str, Any]:
    """Project terminal tool output into a bounded, redacted summary."""
```

`build_chat_output_arguments` collects only assistant text blocks and tool-use
names. It calls `sanitize_trace_value` with a 2 KiB text limit and returns
`role`, `text`, `text_truncated`, and `tool_call_names`.

`build_tool_output_arguments` determines `timeout` from structured failure
`error_type == "tool_timeout"`, `error` from any other structured failure,
`empty` for no terminal output, otherwise `ok`. It returns `status`,
`output_bytes`, and `truncated`. It returns `output_preview` only for tools
outside this deny-by-default set:

```python
_HIGH_RISK_OUTPUT_TOOLS = frozenset(
    {
        "execute_shell_command",
        "read_file",
        "write_file",
        "copy_file",
        "grep_search",
        "glob_search",
    },
)


def _is_high_risk_tool(tool_name: str, mcp_server: str | None) -> bool:
    return tool_name in _HIGH_RISK_OUTPUT_TOOLS or bool(mcp_server)
```

Do not export a digest for high-risk output: an unkeyed hash can reveal
low-entropy secrets by comparison. Length, status, and truncation are
sufficient for this phase.

- [ ] **Step 4: Add status and truncation coverage**

Add tests for ordinary output previews, `isError/tool_timeout`,
`isError/mcp_tool_error`, `None`, a 2 KiB-plus multi-byte value, `read_file`,
and an outcome whose `mcp_server` is non-empty. Assert no test secret appears in any serialized
output value.

- [ ] **Step 5: Run the projection tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/agents/test_agent_trace_output.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the output contract**

```bash
git add src/swe/agents/agent_trace_output.py tests/unit/agents/test_agent_trace_output.py
git commit -m "feat: define agent trace output contracts"
```

### Task 3: Make the SDK fake assert real output-factory behavior

**Files:**
- Modify: `tests/fakes/trace_sdk/_impl.py`
- Modify: `tests/unit/agents/test_agent_trace_sdk.py`

- [ ] **Step 1: Write a failing fake-SDK behavior test**

Add an async decorated sample to `tests/unit/agents/test_agent_trace_sdk.py`:

```python
@chat_traced(output_arguments_factory=lambda result: {"answer": result})
async def traced_sample() -> str:
    return "done"


@pytest.mark.asyncio
async def test_fake_sdk_records_output_factory_value():
    reset()

    await traced_sample()

    assert json.loads(spans[0]["attributes"]["cmb.output.arguments"]) == {
        "answer": "done",
    }
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONPATH=tests/fakes:src venv/bin/python -m pytest tests/unit/agents/test_agent_trace_sdk.py -q
```

Expected: FAIL because the fake does not invoke factories.

- [ ] **Step 3: Implement the documented fake behavior**

After the wrapped function successfully returns, execute the configured output
factory exactly once and record its compact JSON value:

```python
output_factory = config.get("output_arguments_factory")
if output_factory is not None:
    output = output_factory(result)
    span.set_attribute(
        "cmb.output.arguments",
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
    )
```

Do not call the output factory when the wrapped function raises. Preserve the
exception and do not add an output attribute in that case.

- [ ] **Step 4: Replace empty-factory assertions with projection assertions**

Update the existing decorator tests to assert:

```python
assert config["output_arguments_factory"](
    Msg(name="Friday", role="assistant", content="answer"),
)["text"] == "answer"
```

and assert the tool decorator is attached to the new private tracing wrapper,
not the public `dict | None` method. Retain the assertions that summarization
and `_run_approved_tool_call` do not create duplicate semantic Spans.

- [ ] **Step 5: Run fake-SDK and fallback tests**

Run:

```bash
PYTHONPATH=tests/fakes:src venv/bin/python -m pytest \
  tests/unit/agents/test_agent_trace_sdk.py \
  tests/unit/tracing/test_agent_trace_sdk_fallback.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the fake fidelity change**

```bash
git add tests/fakes/trace_sdk/_impl.py tests/unit/agents/test_agent_trace_sdk.py
git commit -m "test: record trace sdk output factory attributes"
```

### Task 4: Wire model and tool projections without changing tool callers

**Files:**
- Modify: `src/swe/agents/react_agent.py:1786-1812`
- Modify: `src/swe/agents/tool_guard_mixin.py:393-449`
- Modify: `tests/unit/agents/test_phase_aware_watchdog.py`
- Modify: `tests/unit/agents/test_agent_trace_sdk.py`

- [ ] **Step 1: Add a failing tool execution regression test**

Using the AgentScope-like fake in `test_phase_aware_watchdog.py`, add a normal
tool response whose public result is `None`, invoke the public method under a
fake trace parent, and assert one `execute_tool` Span has a non-empty output
attribute with an `ok` status. Add a timeout case that asserts `timeout` and
does not expose the timeout message as a shell-style preview.

- [ ] **Step 2: Run the narrow regression tests and verify failure**

Run:

```bash
PYTHONPATH=tests/fakes:src venv/bin/python -m pytest \
  tests/unit/agents/test_phase_aware_watchdog.py \
  tests/unit/agents/test_agent_trace_sdk.py -q
```

Expected: FAIL because both production decorators still return `{}`.

- [ ] **Step 3: Wire the model output factory**

In `react_agent.py`, import `build_chat_output_arguments` and replace only the
empty model lambda:

```python
@chat_traced(
    request_model_factory=lambda self, *args, **kwargs: (
        self._resolved_model_slot.get("model")
    ),
    provider_name_factory=lambda self, *args, **kwargs: (
        self._resolved_model_slot.get("provider_id")
    ),
    output_arguments_factory=build_chat_output_arguments,
)
```

Do not add tracing to `_summarizing` or alter `_reasoning` retry behavior.

- [ ] **Step 4: Split the tool tracing wrapper from the public execution method**

Keep `_run_tool_call_with_hard_timeout` returning `dict | None` as the existing
caller-facing method. Move its current body to a private
`_run_tool_call_with_hard_timeout_impl` returning `dict | None`, then add this
private wrapper:

```python
@execute_tool_traced(
    tool_name_factory=lambda self, _call, tool_name, _input: tool_name,
    input_arguments_factory=lambda self, _call, _tool_name, tool_input: tool_input,
    output_arguments_factory=build_tool_output_arguments,
)
async def _run_tool_call_with_hard_timeout_traced(
    self,
    tool_call: dict[str, Any],
    tool_name: str,
    tool_input: dict[str, Any],
) -> ToolTraceOutcome:
    result = await self._run_tool_call_with_hard_timeout_impl(
        tool_call,
        tool_name,
        tool_input,
    )
    terminal_output = result
    if terminal_output is None:
        terminal_output = self._extract_current_tool_response(
            str(tool_call.get("id") or ""),
            include_structured_failure=True,
        )
    return ToolTraceOutcome(
        result,
        terminal_output,
        tool_name,
        self._resolve_mcp_server(tool_name),
    )


async def _run_tool_call_with_hard_timeout(
    self,
    tool_call: dict[str, Any],
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict | None:
    outcome = await self._run_tool_call_with_hard_timeout_traced(
        tool_call,
        tool_name,
        tool_input,
    )
    return outcome.business_result
```

The helper must cover ordinary, preapproved, plan-interaction, specific-timeout,
and generic-timeout paths exactly once. Do not invoke `_extract_current_tool_response`
before the original implementation has completed its memory write.

- [ ] **Step 5: Run tool and decorator regressions**

Run:

```bash
PYTHONPATH=tests/fakes:src venv/bin/python -m pytest \
  tests/unit/agents/test_agent_trace_sdk.py \
  tests/unit/agents/test_phase_aware_watchdog.py \
  tests/unit/agents/test_tool_guard_hook_runtime.py \
  tests/unit/agents/test_tool_output_budget_mixin.py -q
```

Expected: PASS, with unchanged public return values and one semantic tool Span
per actual execution.

- [ ] **Step 6: Commit the production integration**

```bash
git add src/swe/agents/react_agent.py src/swe/agents/tool_guard_mixin.py \
  tests/unit/agents/test_agent_trace_sdk.py \
  tests/unit/agents/test_phase_aware_watchdog.py
git commit -m "feat: capture redacted agent trace outputs"
```

### Task 5: Align documentation and verify the exported contract

**Files:**
- Modify: `trace_design.md:843-966`
- Modify: `trace_design.md:1174-1199`
- Modify: `docs/superpowers/specs/2026-08-27-agent-trace-output-redaction-design.md`

- [ ] **Step 1: Update the Swe-specific capture contract**

Document these exact rules next to the generic SDK rules:

```text
- Swe model Spans export only assistant text, truncation state, and tool names.
- Swe shell, file, and MCP tool Spans never export an output preview.
- Swe performs application-side redaction and bounds before SDK exporter redaction.
- Tool output is read after the matching tool-result message is persisted.
```

Remove any statement that Swe intentionally returns `{}` for model and tool
output factories. Keep the generic SDK statement that factory failures skip
only the output attribute.

- [ ] **Step 2: Add an executable real-SDK smoke command to the design doc**

Record this command, which must run only in an environment with the private
package installed and must use an isolated non-production exporter target:

```bash
AGENT_TRACE_ENABLED=true \
AGENT_TRACE_EXPORTER=console \
AGENT_TRACE_SERVICE_NAME=swe-agent \
AGENT_TRACE_ATTRIBUTE_REDACTION_ENABLED=true \
AGENT_TRACE_ATTRIBUTE_VALUE_REDACTION_ENABLED=true \
venv/bin/python -m pytest tests/integrated/test_agent_trace_sdk_console.py -q
```

Create `tests/integrated/test_agent_trace_sdk_console.py` only if the private
SDK has a stable console-capture API. Otherwise keep this as a deployment smoke
check and do not introduce an environment-dependent CI test.

- [ ] **Step 3: Validate documentation and focused tests**

Run:

```bash
git diff --check
venv/bin/python -m pytest tests/unit/tracing/test_sanitizer.py -q
PYTHONPATH=tests/fakes:src venv/bin/python -m pytest tests/unit/agents/test_agent_trace_output.py tests/unit/agents/test_agent_trace_sdk.py -q
```

Expected: PASS with no whitespace errors.

- [ ] **Step 4: Commit documentation**

```bash
git add trace_design.md docs/superpowers/specs/2026-08-27-agent-trace-output-redaction-design.md
git commit -m "docs: describe redacted agent trace outputs"
```

### Task 6: Run the complete regression set and inspect change scope

**Files:**
- No source changes expected.

- [ ] **Step 1: Run the complete focused regression suite**

Run:

```bash
PYTHONPATH=tests/fakes:src venv/bin/python -m pytest \
  tests/unit/tracing/test_sanitizer.py \
  tests/unit/tracing/test_agent_trace_sdk_fallback.py \
  tests/unit/agents/test_agent_trace_output.py \
  tests/unit/agents/test_agent_trace_sdk.py \
  tests/unit/agents/test_phase_aware_watchdog.py \
  tests/unit/agents/test_tool_guard_hook_runtime.py \
  tests/unit/agents/test_tool_output_budget_mixin.py -q
```

Expected: PASS.

- [ ] **Step 2: Re-run graph analysis and per-symbol impact checks**

Run:

```bash
node .gitnexus/run.cjs analyze
```

Then run impact analysis for `sanitize_trace_value`,
`_run_reasoning_with_internal_context`, and
`_run_tool_call_with_hard_timeout` in the refreshed index. Stop and review if
any report is HIGH or CRITICAL.

- [ ] **Step 3: Inspect only expected changed files and processes**

Run GitNexus `detect_changes({ scope: "all", repo: "CoPaw" })`, then:

```bash
git diff --check
git status --short
```

Expected: only the File Map paths are changed; Graph output does not show an
unexpected caller or execution flow.

- [ ] **Step 4: Commit only an actual verification correction**

If verification exposes a defect, return to the task that owns the affected
file, add its precise regression test, run that task's focused command, and
commit the implementation and test together. Do not create a no-op
verification commit.

## Plan Self-Review

- Spec coverage: Tasks 1 and 2 implement field and content redaction, byte and
  structural limits, model/tool payload contracts, and high-risk exclusions.
  Task 4 handles the `None` tool return/memory boundary. Tasks 3 and 6 verify
  the fake and real integration layers. Task 5 aligns the SDK guide.
- No placeholders: every task names files, functions, test cases, commands,
  and expected outcomes. The conditional real-SDK test is intentionally gated
  on a stable private SDK console-capture API to avoid inventing one.
- Type consistency: `ToolTraceOutcome` is created in the Agent output module,
  returned only by the private decorated helper, consumed only by its factory,
  and unwrapped into the original `dict | None` public return contract.
