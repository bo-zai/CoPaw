# Durable Chat Stop Design

**Status:** Approved

## Goal

An explicit Console Stop preserves the admitted user question and all displayable
content produced before stopping.  It targets one answer turn precisely, closes
the active stream after bounded settlement, and never converts a transport
disconnect into a stop request.

## Identity and compatibility

The Server issues a Chat ID and User Question Message ID for every new Console
turn.  The response exposes them as `X-Swe-Chatid` and `X-Swe-Msgid`, with the
logical session in `X-Swe-Sessionid`.  The Console stores that tuple immediately
and sends `chat_id + msgid` to Stop.

`POST /console/chat/stop` remains compatible with existing Chat-ID-only clients.
Target resolution is ordered: exact `chat_id + msgid`, legacy `chat_id`, then an
early `session_id` startup locator only when no Chat ID is known.  A Message ID
without a Chat ID, an ambiguous locator, a stale turn, or an unauthorised target
is a successful no-op.  Accepted responses return
`stopped: true, accepted: true, status: "stopping", chat_id, msgid`; no-ops
return `stopped: false, accepted: false, status: "idle"` and do not echo an
unvalidated identity.

## Runtime lifecycle

The runtime admits a turn only after its user question is durably written.  A
write failure prevents Agent execution.  Task tracking is turn-aware and owns a
`running` or `stopping` state.  Stop atomically claims the matching turn, freezes
normal display output, supersedes turn approvals, and begins a five-second
cooperative settlement window.  It cancels the task only after that window if
the run has not settled.  Repeated Stop while the turn is stopping is a
re-acknowledgement, not another cancellation.

The task tracker retains output admitted before the claim and rejects normal
output received after it.  A reconnect may attach during `stopping` to replay
that buffer and await stream closure; it never revives Agent execution.

On stopping, the runtime writes `metadata.turn_status = "stopped"` to a final
displayable assistant message.  If no assistant message exists, it stores the
same terminal information in session-root `turn_states[msgid]`.  Persisting
new stop state may fail without retry, frontend local storage, or a public
failure status; the pre-admitted user question remains available.

## Coordinated lifecycle effects

New non-reconnect submissions and `/clear` or `/new` commands for a stopping
Chat are rejected without consuming the input.  Chat deletion wins ownership:
it prevents a stopping task from recreating state before deleting session and
archive resources.

Every pending approval belonging to the stopped turn is marked `superseded` and
remains auditable.  Selected Experts and Goal-owned background subagents are
best-effort cancelled and cannot merge results, wake a Goal, or continue the
stopped turn.  When the turn belongs to a Goal, Chat Stop calls
`abandon_turn` and reaches `INTERRUPTED`; a Goal Monitor cancellation that
durably wins first remains `CANCELLED`.  Tool side effects are not rolled back.

## Query and Console behavior

`/chats/answer-turn` uses `chat_id + msgid` as its canonical identity and
performs legacy `sessionid + msgid` lookup only across authorised candidate
Chats.  It returns the existing message representation plus optional
`turn_status: "stopped"`.  During settlement it returns `status: "stopping"`;
after the run closes it returns `status: "idle"`.

The Console disables submission only for the stopping Chat until its original
stream closes.  It preserves unsubmitted input, does not show a stop-specific
notice, does not refresh history automatically, and treats a concurrent
`409 chat is stopping` as a silent, resubmittable rejection.  Other Chats
remain usable.  Only an explicit Stop action calls the Stop endpoint.

## Verification

- Task tracker tests cover exact identity, re-acknowledgement, output freeze,
  graceful timeout and reconnect during stopping.
- Runner/session tests cover durable user admission, all interruption phases,
  stopped metadata/root state and persistence-failure preservation.
- Router/API tests cover headers, response compatibility, ownership no-op,
  query status, submission gate and delete arbitration.
- Goal, approval and worker tests cover `INTERRUPTED` versus `CANCELLED`,
  approval supersession and prevented post-stop callbacks.
- Console tests cover header capture, precise Stop parameters, Chat-scoped
  composer lock, silent `409`, and disconnect-without-stop behavior.
