# Goal Contract Draft Composer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Goal proposal Composer replacement into a compact, reference-inspired, editable Goal Contract Draft with derived summary, disclosure, validation, and safe exit feedback.

**Architecture:** Keep the existing `GoalProposalCard` and its `onConfirmGoalProposal` data flow. Add local UI state and small pure helpers in the same component module, with Less module styles for bounded scrolling, section hierarchy, code editor, and responsive constraint pairing. No API, Goal model, or message-card schema changes.

**Tech Stack:** React 18, TypeScript, CSS Modules via Less, Vitest, Testing Library, existing `lucide-react` icons.

---

### Task 1: Establish impact baseline and test fixtures

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
- Inspect: `console/src/pages/Chat/components/PlanInteractionCards.tsx`

- [ ] **Step 1: Run GitNexus impact analysis for the edited component**

Run the repository's GitNexus impact query for `GoalProposalCard` upstream before editing. Record direct callers (`ActivePlanInteractionComposer`) and the Composer render flow; proceed only after confirming no HIGH or CRITICAL warning.

- [ ] **Step 2: Add a reusable proposal fixture helper in the test file**

Factor the existing inline Goal proposal data into a helper that returns the complete contract shape, preserving the current `createGoalProposalMessage()` behavior. Keep the fixture values small enough for summary assertions and include one preserve constraint, one forbidden constraint, and one completion criterion.

- [ ] **Step 3: Run the existing focused tests**

Run `cd console && pnpm test:run -- src/pages/Chat/components/PlanInteractionCards.test.tsx`.
Expected: all existing Plan interaction tests pass before UI changes.

### Task 2: Add local draft normalization and derived summary helpers

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:1048-1193`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing tests for summary and change equivalence**

Add tests that render a Goal proposal and assert:

```tsx
expect(screen.getByText("1 项完成条件")).toBeInTheDocument();
expect(screen.getByText("必须保留 1 条")).toBeInTheDocument();
expect(screen.getByText("禁止操作 1 条")).toBeInTheDocument();
expect(screen.getByText("未确认修改")).toBeInTheDocument();
```

Then edit the objective with surrounding whitespace and format the criteria JSON; assert the change marker is absent after the normalized values equal the original proposal.

- [ ] **Step 2: Implement pure normalization helpers**

Add module-local helpers with explicit types:

```ts
function normalizeDraftText(value: string): string;
function parseDraftCriteria(value: string): ChatGoalCompletionCriterion[] | null;
function draftHasChanges(current: DraftState, initial: DraftState): boolean;
function summarizeDraft(draft: DraftState): DraftSummary;
```

Normalize text with `trim()`, compare valid criteria JSON by parsed structure, and compare constraint lines after per-line trim while preserving order. Derive summary counts and “已设置/未设置” states directly from local state.

- [ ] **Step 3: Run the new tests**

Run `cd console && pnpm test:run -- src/pages/Chat/components/PlanInteractionCards.test.tsx -t "summary|change"`.
Expected: PASS.

### Task 3: Rebuild Goal proposal layout as compact summary plus expanded details

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:1048-1193`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less:1-620`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing tests for disclosure and bounded structure**

Assert new proposals render with `aria-expanded="true"`, a `合同详情` region, the local-edit disclosure text, and the two action buttons `返回消息编辑` and `确认并开始执行`. Click the detail toggle and assert `aria-expanded="false"`; assert the details region is hidden while summary remains visible.

- [ ] **Step 2: Implement the compact card structure**

Keep `GoalProposalCard` as the public component. Add:

```tsx
const [detailsOpen, setDetailsOpen] = useState(true);
const [submitted, setSubmitted] = useState(false);
const detailsId = `goal-contract-details-${cardInstanceKey}`;
```

Render a stable header, read-only derived summary, dedicated disclosure button with `aria-controls`/`aria-expanded`, and a details container. Preserve all existing controlled field values and labels so current tests and accessibility names remain valid.

- [ ] **Step 3: Apply bounded and responsive styles**

Set the card to `max-height: min(440px, 50vh)` with a flex column layout; make only the detail body scrollable; keep header/footer visible; style the summary as a soft bordered band; use `grid-template-columns: repeat(2, minmax(0, 1fr))` for preserve/forbidden sections and one column below 768px. Keep the existing card width and Composer placement.

- [ ] **Step 4: Run focused disclosure tests**

Run `cd console && pnpm test:run -- src/pages/Chat/components/PlanInteractionCards.test.tsx -t "Goal Contract Draft|detail|summary"`.
Expected: PASS.

### Task 4: Add JSON editor affordances and full validation feedback

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:1048-1193`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing tests for formatting and validation**

Cover these cases:

```tsx
fireEvent.change(criteria, { target: { value: '{"requirement":"x"}' } });
fireEvent.click(screen.getByRole("button", { name: "格式化 JSON" }));
expect(criteria).toHaveValue(expect.stringContaining("\n  \"requirement\""));

fireEvent.click(confirmButton);
expect(screen.getByRole("alert")).toHaveTextContent(/完成条件/);
expect(screen.getByRole("button", { name: "收起详情" })).toBeInTheDocument();
```

Also assert malformed JSON remains unchanged after formatting and the criteria field receives focus after confirmation.

- [ ] **Step 2: Implement JSON formatting and parse feedback**

Add a `格式化 JSON` button next to the criteria section heading. On valid JSON, call `JSON.stringify(parsed, null, 2)`; on invalid JSON, preserve the original text and set a parse error with the parser message. Keep the editor as a controlled textarea with line-number decoration derived from `criteriaText.split("\n").length`.

- [ ] **Step 3: Implement full validation state**

Validate objective and autonomy boundary after trim and max length 4000; parse criteria as a non-empty array and validate required non-blank strings; validate each constraint line length and count against existing backend limits. Store field errors in a typed object, render field-local messages, render an aggregate error count above the footer, set `detailsOpen(true)`, and focus the first invalid input through refs.

- [ ] **Step 4: Run validation tests**

Run `cd console && pnpm test:run -- src/pages/Chat/components/PlanInteractionCards.test.tsx -t "JSON|validation|focus"`.
Expected: PASS.

### Task 5: Implement explicit exit, submission handoff, and failure states

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:1048-1193`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing tests for exit and handoff**

Add tests that click `返回消息编辑` with no changes and assert the default Composer returns immediately. With a changed objective, mock `window.confirm` to return false and assert the card remains; return true and assert the default Composer returns without calling `onConfirmGoalProposal`. For submission, assert controls become disabled during the promise, success text appears briefly, and rejection preserves the edited objective and displays the error.

- [ ] **Step 2: Implement explicit exit semantics**

Use `draftHasChanges` to decide whether to call `window.confirm("修改尚未确认，返回后将丢失，是否继续？")`. Call `onComplete` only after no-change exit or confirmed discard. Do not emit a submit event or invoke the Goal callback.

- [ ] **Step 3: Implement confirmation handoff state**

Set `submitted` before invoking `onConfirmGoalProposal`, disable all fields/buttons, show `创建中…`, then on success show `Goal 已确认，正在开始执行` and trigger the existing `emit`/`onComplete` flow after the short local transition. On failure clear `submitted`, keep local values, and set the field-independent error message.

- [ ] **Step 4: Run handoff tests**

Run `cd console && pnpm test:run -- src/pages/Chat/components/PlanInteractionCards.test.tsx -t "return|handoff|failure|confirmation"`.
Expected: PASS.

### Task 6: Verify complete Console behavior and responsive presentation

**Files:**
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
- Inspect: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Inspect: `console/src/pages/Chat/components/PlanInteractionCards.module.less`

- [ ] **Step 1: Run the complete focused test file**

Run `cd console && pnpm test:run -- src/pages/Chat/components/PlanInteractionCards.test.tsx`.
Expected: PASS.

- [ ] **Step 2: Run typecheck and lint**

Run `cd console && pnpm typecheck && pnpm lint`.
Expected: both commands exit 0.

- [ ] **Step 3: Run a production build**

Run `cd console && pnpm build`.
Expected: build completes without TypeScript or Vite errors.

- [ ] **Step 4: Perform visual verification**

Start the Console dev server with `cd console && pnpm dev --host 127.0.0.1 --port 4175`, open the existing Goal proposal flow, and inspect desktop and mobile widths. Confirm the card stays within the 440px/50vh bound, conversation remains visible, details scroll internally, and constraints switch from two columns to one without overflow.

- [ ] **Step 5: Run GitNexus change detection before committing**

Run the repository's GitNexus `detect_changes()` check for the working tree and confirm only `GoalProposalCard` render paths, its styles, and focused tests are affected. Investigate any unexpected execution flow before commit.

- [ ] **Step 6: Commit the implementation**

```bash
git add console/src/pages/Chat/components/PlanInteractionCards.tsx console/src/pages/Chat/components/PlanInteractionCards.module.less console/src/pages/Chat/components/PlanInteractionCards.test.tsx
git commit -m "feat(console): polish goal contract draft card"
```
