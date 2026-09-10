# Goal Contract Draft Composer Card Design

## Purpose

Refine the pre-confirmation Goal Contract Draft so it follows the visual
language of `goal_card.html` while remaining a compact, blocking interaction
inside the Chat Composer. It must leave the existing conversation visible and
retain the current Goal creation contract.

## Scope

The work is limited to the existing Goal proposal card in the Chat Console.
It does not change the Goal Contract API, the Goal data model, or the Goal
creation flow.

## Layout

The Draft temporarily replaces the Chat Composer, with a maximum height of
`min(440px, 50vh)`. The card has three stable areas:

- Header: `Goal Contract Draft`, pending status, and a read-only execution
  summary.
- Detail: an independently scrollable, default-expanded contract editor.
- Footer: return and confirmation actions that stay visible.

The summary includes a shortened objective, completion-criteria count,
whether each constraint list is set, and whether the autonomy boundary is
defined. It is derived from the local edit state and never persisted as a
Contract field.

The only disclosure control is an accessible `展开详情` / `收起详情` button
with `aria-expanded`. A new Draft starts expanded. A validation failure keeps
the detail open. When collapsed, the card is approximately 160px high.

Section styling borrows the reference design's white surface, fine borders,
blue primary action, icon-led headings, and code-editor treatment without
cloning its standalone page shell. `must_preserve` and `must_not_do` render as
a two-column pair on wide screens and stack on narrow screens. The forbidden
operation field uses a restrained warning color. Empty lists stay visible with
an empty-state prompt.

## Editing

All Contract fields remain directly editable:

- Objective and autonomy boundary are text areas with 4000-character limits.
- Completion criteria remain a JSON editor with line numbers, monospace type,
  a user-triggered format action, and parse-location feedback.
- Constraints remain one trimmed entry per line.

Formatting applies two-space indentation only when the JSON parses. Invalid
JSON is not rewritten or repaired.

Edits live only in the mounted card. The UI states that changes are retained
only on the current page and a Goal is created only after confirmation. No
browser-level unsaved-change prompt is installed for refresh, route navigation,
or tab closure.

The summary displays an unconfirmed-change marker when normalized local data
differs from the received proposal. Objective and boundary compare after trim;
valid criteria JSON compares as structured data; constraints compare by trimmed
line and order. Formatting-only changes do not mark the Draft changed.

## Validation And Exit

On confirmation, all fields are validated. Errors appear beside the affected
field and as an aggregate count above the footer. The detail opens and the
first invalid field receives focus. Editing remains available to correct errors.

`返回消息编辑` restores the ordinary Composer without creating a Goal. If there
are unconfirmed changes, it asks for explicit discard confirmation first.

## Confirmation Handoff

Submitting a valid Draft disables editing and displays `创建中…`. On a success,
the card shows a short local `Goal 已确认，正在开始执行` transition before the
existing Goal runtime flow takes over. On a failure, it preserves all edits,
surfaces the creation error, and allows retrying.

## Verification

Focused component tests will cover the default disclosure state, derived
summary, normalized change marker, JSON formatting and errors, full validation
and focus, discard confirmation, submission failure, and successful handoff.
Visual verification will cover the bounded card height, inner scrolling,
conversation visibility, desktop constraint pair, and narrow-screen stacking.
