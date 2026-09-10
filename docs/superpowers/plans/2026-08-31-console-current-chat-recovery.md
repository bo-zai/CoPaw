# Console Current-Chat Recovery Implementation Plan

> **Execution requirement:** apply each production change only after its focused
> regression test demonstrates the prior failure; preserve the legacy Console
> chat request path and SSE wire format unless `reconnect_mode == "current"`.

## Goal

Make an active Console chat reconnectable without blocking `GET /api/chats/{id}`
or relying on a client-supplied turn id.  The existing Console POST remains the
public compatibility surface; current-chat recovery is an opt-in mode.

## Work items

1. Add focused backend regression tests for a history read while a session
   execution owns the write lock, and make the read use the last atomically
   persisted state rather than waiting on that execution lock.
2. Extend answer-turn lifecycle persistence with durable `completed`,
   `stopped`, and `failed` terminal states.  Add a settlement barrier so neither
   recovery nor a following submission observes a terminal in-memory turn before
   its durable outcome is written.  Make persistence failures retry behind that
   barrier and fail closed with `503`/`Retry-After`; reconcile an orphaned
   admitted turn after restart as failed.
3. Add `reconnect_mode: "current"` to the existing Console POST.  Resolve a
   current Chat by optional `chat_id`, then compatible session locators;
   authorise before attaching; retain the legacy branch for every other mode.
   Return active traffic in the existing SSE format and a terminal durable
   snapshot as `event: chat.snapshot`.
4. Update Console reconnect to request current mode, consume terminal snapshots,
   and treat a first 404 as a one-shot GET refresh for mixed-version rollout.
   Preserve the legacy error and parser behavior for ordinary requests.
5. Run focused Python and Console tests, static checks appropriate to changed
   files, GitNexus change detection, and independent code review.  Resolve review
   findings, repeat checks, and commit in reviewable increments.

## Acceptance checks

- The history GET completes immediately with a durable `running` snapshot while
  generation holds its write lock.
- A current-mode reconnect attaches to an active Chat with no caller-provided
  `msgid`; terminal recovery returns one `chat.snapshot` SSE event and closes.
- Optional invalid/unauthorised `chat_id` does not prevent session fallback;
  final resolution failure is indistinguishable as `404 Chat not found`.
- Old payloads and unknown recovery modes remain on the old POST behavior.
- Terminal status remains recoverable after coordinator cleanup; settlement
  persistence failure never permits a competing turn or model re-execution.
- The Console applies a terminal snapshot without adding an empty assistant
  message and performs at most one GET refresh on a current-mode 404.
