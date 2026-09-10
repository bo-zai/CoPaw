# Memory Compaction Projected Token Accounting Plan

## Problem

`MemoryCompactionHook` passes both online messages and fixed prompt text to
`SweEstimateTokenCounter.count()`. That counter intentionally treats `text` as
a direct-count alternative and returns before counting messages. The staged
context budget can therefore classify an oversized persisted task session as
`normal` and skip compaction before the provider call.

The existing domain contract defines persisted context occupancy as the system
prompt, completed compressed summary, effective online history, and compacted
tool results. The implementation must account for the fixed text and online
messages without changing the public counter's established either-or semantics.

## Scope

- Correct initial projected-token measurement in the pre-reasoning compaction
  hook.
- Correct the post-checkpoint remeasurement through the same accounting path.
- Add real-counter regression coverage proving that non-empty prompt text does
  not hide large online messages.
- Preserve structured tool-call and tool-result payloads when estimating the
  online-message portion of projected context.
- Update affected mock-based checkpoint coverage for the additional counter
  calls.

## Non-goals

- Changing `SweEstimateTokenCounter.count()` semantics.
- Changing the 65/80/90 context-budget stages.
- Changing Cron `skip_history` or task-session persistence behavior.
- Deriving limits from provider model metadata.
- Expanding tool-schema accounting beyond the existing hook inputs.

## Implementation Units

### U1: Characterize combined projected context accounting

Files:

- `tests/unit/agents/test_memory_compaction_checkpoint.py`

Execution note: test first.

Test scenarios:

- A real `SweEstimateTokenCounter` receives large online messages and short
  prompt text; projected tokens equal the sum of independent message and text
  counts.
- Existing emergency remeasurement still retries the legacy compactor once,
  with mock results representing separate message and fixed-text measurements.

### U2: Sum independent message and fixed-text counts

Files:

- `src/swe/agents/hooks/memory_compaction.py`
- `src/swe/agents/utils/swe_token_counter.py`

Decision:

- Add one private helper that separately calls the existing counter for online
  messages and for system-prompt-plus-summary text, then sums the results.
- Reuse it for both initial projection and remeasurement so the two budget
  decisions cannot drift.
- Keep the counter's direct-text alternative intact while making its message
  branch account for serialized structured blocks, not only top-level `text`.

### U3: Verify the compaction surface

Verification:

- Run the focused checkpoint-compaction test file.
- Run memory-compaction archive and source-scoped tool-result compaction tests.
- Run formatting/static checks for touched files and `git diff --check`.
- Run GitNexus change detection before any commit decision.

## Acceptance Criteria

- Non-empty fixed text no longer causes online messages to disappear from the
  staged context budget.
- The public token-counter behavior remains unchanged.
- Initial measurement and remeasurement use identical accounting.
- Existing checkpoint lifecycle behavior remains green.
