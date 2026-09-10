# Stop Is the Unified Completion Hook

`Stop` is the single lifecycle event that evaluates a candidate Assistant Response before request completion. It replaces both the former `BeforeStop` completion gate and the observation-only `Stop` event.

A candidate is a newly recorded `assistant` message for the current turn with non-empty visible text and no `tool_use` block. The Stop payload is its ordered text projection: reasoning and passive media may accompany the message but neither participate in the payload nor disqualify it. This makes `thinking + text` a candidate while keeping `thinking + text + tool_use` an intermediate tool request.

Each matching Stop handler executes once per candidate completion attempt and may record or notify through its own external side effects. The runtime merges handler decisions: `allow` approves completion, while any explicit `block` vetoes it and may start a bounded automatic follow-up Agent turn. The next candidate response runs the same Stop handlers again, preserving attempt-level audit history.

Stop accepts only `allow` and `block`. A Stop handler failure under `failPolicy: block` ends the request incomplete and never retries the Agent; `failPolicy: allow` makes the failure diagnostic only. Tool-hook terminal-stop paths continue to bypass Stop.

Goal Runtime follows the same contract only at formal delivery: its Goal Finalization Turn emits one candidate and invokes Stop once before the Goal Chat Stream closes. An explicit block may start a tool-free Finalization retry, counted against the existing `max_stop_turns` through a Finalization-local counter; it never reopens Goal execution or verification and does not consume the Goal Turn Budget. The fixed Finalization Fallback is not a candidate and does not invoke Stop.

This is intentionally non-compatible. `BeforeStop` is removed and any residual configuration is invalid. Keeping it as an alias or retaining an observation-only Stop would preserve two competing definitions of completion and make handler behavior ambiguous.
