import React from "react";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createContext } from "use-context-selector";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/types/IMessages";
import { ChatAnywhereSessionsContext } from "@/components/agentscope-chat";
import {
  ActivePlanClarificationCard,
  ActivePlanInteractionComposer,
  PlanClarificationCard,
  PlanReviewCard,
  PlanReviewMessageCard,
  PlanReviewSnapshot,
} from "./PlanInteractionCards";
import { ChatPlanReviewRenderProvider } from "../planReviewRenderContext";
import type { ChatPlanReviewRenderContextValue } from "../planReviewRenderContext";
import styles from "./PlanInteractionCards.module.less";

const stylesheet = readFileSync(
  path.join(
    process.cwd(),
    "src/pages/Chat/components/PlanInteractionCards.module.less",
  ),
  "utf8",
);

vi.mock("@/components/agentscope-chat", () => ({
  ChatAnywhereSessionsContext: createContext({
    currentSessionId: "chat-1",
  }),
  OperateCard: Object.assign(
    ({
      header,
      body,
    }: {
      header: { title: string };
      body: { children: React.ReactNode };
    }) => (
      <section data-testid="generic-operate-card">
        <h3>{header.title}</h3>
        {body.children}
      </section>
    ),
    {
      LineBody: ({ children }: { children: React.ReactNode }) => (
        <div>{children}</div>
      ),
    },
  ),
}));

function captureSubmitEvents() {
  const handler = vi.fn();
  document.addEventListener("handleSubmit", handler);
  return {
    handler,
    cleanup: () => document.removeEventListener("handleSubmit", handler),
  };
}

function createSessionContextValue(sessionId = "chat-1") {
  return {
    sessions: [],
    setSessions: vi.fn(),
    getSessions: () => [],
    currentSessionId: sessionId,
    setCurrentSessionId: vi.fn(),
    getCurrentSessionId: () => sessionId,
    isSessionLoading: false,
    setSessionLoading: vi.fn(),
    isSessionsListLoading: false,
    setSessionsListLoading: vi.fn(),
  };
}

function renderActiveClarification(
  messages: IAgentScopeRuntimeWebUIMessage<unknown>[],
) {
  return render(
    <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
      <ChatAnywhereMessagesContext.Provider
        value={{
          messages,
          setMessages: vi.fn(),
          getMessages: () => messages,
        }}
      >
        <ActivePlanClarificationCard />
      </ChatAnywhereMessagesContext.Provider>
    </ChatAnywhereSessionsContext.Provider>,
  );
}

function renderPlanReviewMessage(
  data: React.ComponentProps<typeof PlanReviewCard>["data"],
  callbacks: {
    onContinueModifying?: (
      value: React.ComponentProps<typeof PlanReviewCard>["data"],
    ) => void;
    onPlanModeDecision?: (enabled: boolean) => void;
  } = {},
) {
  return render(
    <ChatPlanReviewRenderProvider value={callbacks}>
      <PlanReviewMessageCard data={data} />
    </ChatPlanReviewRenderProvider>,
  );
}

function renderActiveComposer(
  messages: IAgentScopeRuntimeWebUIMessage<unknown>[],
  callbacks: ChatPlanReviewRenderContextValue = {},
) {
  return render(
    <ChatPlanReviewRenderProvider value={callbacks}>
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages,
            setMessages: vi.fn(),
            getMessages: () => messages,
          }}
        >
          <ActivePlanInteractionComposer
            defaultComposer={<div data-testid="default-composer">composer</div>}
          />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>
    </ChatPlanReviewRenderProvider>,
  );
}

function createClarificationMessage({
  messageId,
  originalId,
  traceId,
  prompt = "Pick scope",
}: {
  messageId: string;
  originalId: string;
  traceId: string;
  prompt?: string;
}): IAgentScopeRuntimeWebUIMessage<unknown> {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        code: "AgentScopeRuntimeResponseCard",
        data: {
          id: `response-${messageId}`,
          output: [
            {
              role: "assistant",
              id: messageId,
              metadata: {
                original_id: originalId,
                trace_id: traceId,
              },
            },
          ],
        },
      },
      {
        code: "PlanInteraction",
        data: {
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt,
          options: [{ id: "small", label: "Small" }],
        },
      },
    ],
  };
}

function createReviewData(
  overrides: Partial<React.ComponentProps<typeof PlanReviewCard>["data"]> = {},
): React.ComponentProps<typeof PlanReviewCard>["data"] {
  return {
    card_type: "plan_review",
    plan_id: "plan-123",
    title: "Fix bug",
    summary: "Investigate and patch",
    steps: ["Read code", "Patch code"],
    risks: ["Regression"],
    verification: ["Focused tests"],
    ...overrides,
  };
}

function createReviewMessage({
  messageId,
  cardId,
  title,
  status,
  submittedDecision,
}: {
  messageId: string;
  cardId: string;
  title: string;
  status?: "pending" | "submitted";
  submittedDecision?: "revise" | "execute" | "exit_plan";
}): IAgentScopeRuntimeWebUIMessage<unknown> {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        id: cardId,
        code: "PlanInteraction",
        data: createReviewData({
          plan_id: cardId,
          title,
          status,
          submitted_decision: submittedDecision,
        }),
      },
    ],
  };
}

function createGoalProposalMessage(): IAgentScopeRuntimeWebUIMessage<unknown> {
  return {
    id: "goal-proposal-message",
    role: "assistant",
    cards: [
      {
        code: "PlanInteraction",
        data: {
          card_type: "goal_proposal",
          objective: "Ship Goal Runtime",
          completion_criteria: [
            {
              requirement: "Runtime works",
              observable_assertion: "Goal completes",
              verification_method: "command: pytest tests/unit/app/goals -q",
              expected_outcome: "exit 0",
            },
          ],
          constraints: { must_preserve: ["Chat"], must_not_do: [] },
          autonomy_boundary: "No deploy",
        },
      },
    ],
  };
}

describe("Plan interaction cards", () => {
  afterEach(() => {
    cleanup();
    (window as Window & { currentSessionId?: string }).currentSessionId =
      undefined;
  });

  it("renders Goal Contract Draft in the composer and creates it only after confirmation", async () => {
    const onConfirmGoalProposal = vi
      .fn()
      .mockResolvedValue({ goal_id: "goal-1" });
    const events = captureSubmitEvents();
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal,
    });

    expect(screen.getByLabelText("Goal Contract Draft")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("整体目标"), {
      target: { value: "Edited Goal" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认并开始执行" }));

    await waitFor(() =>
      expect(onConfirmGoalProposal).toHaveBeenCalledWith(
        expect.objectContaining({ objective: "Edited Goal" }),
      ),
    );
    await waitFor(() => expect(events.handler).toHaveBeenCalled());
    events.cleanup();
  });

  it("shows local success feedback before starting the confirmed Goal", async () => {
    vi.useFakeTimers();
    const onConfirmGoalProposal = vi
      .fn()
      .mockResolvedValue({ goal_id: "goal-1" });
    const events = captureSubmitEvents();
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal,
    });

    fireEvent.click(screen.getByRole("button", { name: "确认并开始执行" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("Goal 已确认，正在开始执行")).toBeInTheDocument();
    expect(events.handler).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(700);
    });
    expect(events.handler).toHaveBeenCalled();
    events.cleanup();
    vi.useRealTimers();
  });

  it("shows a derived summary and starts with contract details expanded", () => {
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal: vi.fn(),
    });

    expect(screen.getByText("1 项完成条件")).toBeInTheDocument();
    expect(screen.getByText("必须保留 1 条")).toBeInTheDocument();
    expect(screen.getByText("禁止操作 未设置")).toBeInTheDocument();
    expect(screen.queryByText("未确认修改")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起详情" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("region", { name: "合同详情" })).toBeVisible();
  });

  it("formats valid criteria JSON without marking a formatting-only edit", () => {
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal: vi.fn(),
    });

    const criteria = screen.getByLabelText(
      "完成条件（JSON）",
    ) as HTMLTextAreaElement;
    fireEvent.change(criteria, {
      target: { value: JSON.stringify(JSON.parse(criteria.value)) },
    });
    fireEvent.click(screen.getByRole("button", { name: "格式化 JSON" }));

    expect(criteria.value).toContain('\n    "requirement"');
    expect(screen.queryByText("未确认修改")).not.toBeInTheDocument();
  });

  it("collapses details while keeping the summary and reopens them for validation", () => {
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal: vi.fn(),
    });
    const toggle = screen.getByRole("button", { name: "收起详情" });
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "展开详情" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByText("执行摘要")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "合同详情" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开详情" }));
    fireEvent.change(screen.getByLabelText("完成条件（JSON）"), {
      target: { value: "{" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认并开始执行" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请修正");
    expect(screen.getByLabelText("完成条件（JSON）")).toHaveFocus();
  });

  it("focuses the first invalid constraint field", () => {
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal: vi.fn(),
    });
    const preserve = screen.getByLabelText("必须保留");
    fireEvent.change(preserve, {
      target: {
        value: Array.from({ length: 33 }, (_, index) => `rule ${index}`).join(
          "\n",
        ),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认并开始执行" }));

    expect(screen.getByRole("alert")).toHaveTextContent("请修正");
    expect(preserve).toHaveFocus();
  });

  it("returns to the composer and confirms discarding local edits", () => {
    const confirm = vi.spyOn(window, "confirm");
    renderActiveComposer([createGoalProposalMessage()], {
      onConfirmGoalProposal: vi.fn(),
    });
    fireEvent.change(screen.getByLabelText("整体目标"), {
      target: { value: "Changed" },
    });
    confirm.mockReturnValueOnce(false);
    fireEvent.click(screen.getByRole("button", { name: "返回消息编辑" }));
    expect(screen.getByLabelText("Goal Contract Draft")).toBeInTheDocument();
    confirm.mockReturnValueOnce(true);
    fireEvent.click(screen.getByRole("button", { name: "返回消息编辑" }));
    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("hides a dismissed clarification only for the current render", () => {
    const data = {
      card_type: "plan_clarification" as const,
      kind: "single_choice" as const,
      prompt: "Pick scope",
      options: [{ id: "small", label: "Small" }],
    };
    const { container, unmount } = render(
      <PlanClarificationCard data={data} />,
    );

    expect(
      container.querySelector('[data-plan-clarification-active="true"]'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(
      container.querySelector('[data-plan-clarification-active="true"]'),
    ).not.toBeInTheDocument();

    unmount();
    render(<PlanClarificationCard data={data} />);
    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("keeps the composer when a plan review follows a clarification", () => {
    renderActiveComposer([
      createClarificationMessage({
        messageId: "assistant-clarification",
        originalId: "original-1",
        traceId: "trace-1",
        prompt: "Pick scope",
      }),
      createReviewMessage({
        messageId: "assistant-review",
        cardId: "plan-2",
        title: "Review latest plan",
      }),
    ]);

    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Pick scope" }),
    ).not.toBeInTheDocument();
  });

  it("falls back to the default composer when no active plan interaction exists", () => {
    renderActiveComposer([
      createReviewMessage({
        messageId: "assistant-review",
        cardId: "plan-2",
        title: "Submitted plan",
        status: "submitted",
        submittedDecision: "execute",
      }),
    ]);

    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Submitted plan" }),
    ).not.toBeInTheDocument();
  });

  it("does not resurrect older cards when the latest plan interaction is submitted", () => {
    renderActiveComposer([
      createClarificationMessage({
        messageId: "assistant-clarification",
        originalId: "original-1",
        traceId: "trace-1",
        prompt: "Older clarification",
      }),
      createReviewMessage({
        messageId: "assistant-review",
        cardId: "plan-2",
        title: "Submitted plan",
        status: "submitted",
        submittedDecision: "execute",
      }),
    ]);

    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Older clarification" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the default composer when a plan review is pending", () => {
    renderActiveComposer([
      createReviewMessage({
        messageId: "assistant-review",
        cardId: "plan-2",
        title: "Review latest plan",
      }),
    ]);

    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Review latest plan" }),
    ).not.toBeInTheDocument();
  });

  it("uses focus-only initial state and submits the focused single choice with Enter", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [
            { id: "small", label: "Small" },
            { id: "large", label: "Large" },
          ],
        }}
      />,
    );

    const small = screen.getByRole("button", { name: /Small/ });
    expect(small).toHaveAttribute("aria-current", "true");
    expect(small).toHaveAttribute("aria-pressed", "false");
    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Small",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: ["small"],
        },
      },
    });

    submit.cleanup();
  });

  it("focuses a choice clarification card on render for immediate keyboard use", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [
            { id: "small", label: "Small" },
            { id: "large", label: "Large" },
          ],
        }}
      />,
    );

    expect(screen.getByRole("region", { name: "Pick scope" })).toHaveFocus();
  });

  it("shows keyboard operation guidance in the card footer", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [
            { id: "lint", label: "Lint" },
            { id: "test", label: "Test" },
          ],
        }}
      />,
    );

    expect(screen.getByText("方向键切换选项，Space 选择")).toBeInTheDocument();
  });

  it("separates multi-choice focus from selection and submits selected rows", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [
            { id: "lint", label: "Lint" },
            { id: "test", label: "Test" },
          ],
        }}
      />,
    );
    const card = screen.getByRole("region", { name: "Pick checks" });

    fireEvent.keyDown(card, { key: " " });
    fireEvent.keyDown(card, { key: "ArrowDown" });
    fireEvent.keyDown(card, { key: " " });
    expect(screen.getByRole("button", { name: /Lint/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Test/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.keyDown(card, { key: "Enter" });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Lint, Test",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: ["lint", "test"],
        },
      },
    });
    submit.cleanup();
  });

  it("does not move choice focus or scroll on mouse hover", () => {
    const originalScrollIntoView = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "scrollIntoView",
    );
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    try {
      render(
        <PlanClarificationCard
          data={{
            card_type: "plan_clarification",
            kind: "single_choice",
            prompt: "Pick scope",
            options: [
              { id: "small", label: "Small" },
              { id: "large", label: "Large" },
            ],
          }}
        />,
      );
      scrollIntoView.mockClear();

      const largeOption = screen.getByRole("button", { name: /Large/ });
      fireEvent.mouseEnter(largeOption);

      expect(largeOption).not.toHaveAttribute("aria-current", "true");
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      if (originalScrollIntoView) {
        Object.defineProperty(
          HTMLElement.prototype,
          "scrollIntoView",
          originalScrollIntoView,
        );
      } else {
        delete (HTMLElement.prototype as { scrollIntoView?: unknown })
          .scrollIntoView;
      }
    }
  });

  it("shows a custom text box by default for top-level single choice cards", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    expect(
      screen.getByRole("textbox", { name: "Pick scope" }),
    ).toBeInTheDocument();
  });

  it("single choice custom text clears the selected option and submits only text", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Pick scope" }), {
      target: { value: "Use a narrower module" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "single_choice",
      selected_option_ids: [],
      text: "Use a narrower module",
    });
    submit.cleanup();
  });

  it("single choice selecting an option clears custom text", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    const textbox = screen.getByRole("textbox", {
      name: "Pick scope",
    }) as HTMLTextAreaElement;
    fireEvent.change(textbox, { target: { value: "Custom scope" } });
    fireEvent.click(screen.getByRole("button", { name: /Small/ }));

    expect(textbox.value).toBe("");
  });

  it("single choice Enter on the card submits custom text without the focused option", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Pick scope" }), {
      target: { value: "Custom scope" },
    });
    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "single_choice",
      selected_option_ids: [],
      text: "Custom scope",
    });
    submit.cleanup();
  });

  it("multi choice submits selected options together with custom text", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [
            { id: "unit", label: "Unit tests" },
            { id: "lint", label: "Lint" },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Unit tests/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
      target: { value: "Also run smoke test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "multi_choice",
      selected_option_ids: ["unit"],
      text: "Also run smoke test",
    });
    submit.cleanup();
  });

  it("multi choice allows submitting only custom text", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [{ id: "unit", label: "Unit tests" }],
        }}
      />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
      target: { value: "Manual QA only" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "multi_choice",
      selected_option_ids: [],
      text: "Manual QA only",
    });
    submit.cleanup();
  });

  it("multi choice preserves existing custom text when selecting options", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [{ id: "unit", label: "Unit tests" }],
        }}
      />,
    );

    const textbox = screen.getByRole("textbox", { name: "Pick checks" });
    fireEvent.change(textbox, { target: { value: "Manual QA" } });
    fireEvent.click(screen.getByRole("button", { name: /Unit tests/ }));
    expect(textbox).toHaveValue("Manual QA");
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "multi_choice",
      selected_option_ids: ["unit"],
      text: "Manual QA",
    });
    submit.cleanup();
  });

  it("keeps top-level multi-choice custom text additive even when custom response is allowed", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          allow_custom_response: true,
          options: [
            { id: "lint", label: "Lint" },
            { id: "test", label: "Test" },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Lint/ }));
    expect(
      screen.queryByRole("button", { name: /自定义回复/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Lint/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
      target: { value: "Run security checks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Lint\nRun security checks",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: ["lint"],
          text: "Run security checks",
        },
      },
    });
    submit.cleanup();
  });

  it("uses Enter to submit text and preserves Shift+Enter for new lines", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "text",
          prompt: "Add detail",
        }}
      />,
    );
    const input = screen.getByPlaceholderText("Add detail");

    fireEvent.change(input, { target: { value: "Line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(submit.handler).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Line one",
    });
    submit.cleanup();
  });

  it("ignores Enter while IME composition is active in text clarifications", () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "text",
          prompt: "Add detail",
        }}
      />,
    );
    const input = screen.getByPlaceholderText("Add detail");

    fireEvent.change(input, { target: { value: "正在输入" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(submit.handler).not.toHaveBeenCalled();
    expect(input).toHaveValue("正在输入");
    submit.cleanup();
  });

  it("uses Enter to advance form pages and Escape to return", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan-context",
          prompt: "Collect context",
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              required: true,
              options: [{ id: "small", label: "Small" }],
            },
            {
              id: "detail",
              label: "Detail",
              type: "text",
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    fireEvent.keyDown(screen.getByRole("region", { name: "Collect context" }), {
      key: "Enter",
    });
    expect(screen.getByPlaceholderText("Detail")).toBeInTheDocument();

    fireEvent.keyDown(screen.getByPlaceholderText("Detail"), {
      key: "Escape",
    });
    expect(screen.getByRole("button", { name: /Small/ })).toBeInTheDocument();
  });

  it("keeps a form text field visible when Space is pressed on the card", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan-detail",
          prompt: "Collect detail",
          fields: [
            {
              id: "detail",
              label: "Detail",
              type: "text",
            },
          ],
        }}
      />,
    );

    fireEvent.keyDown(screen.getByRole("region", { name: "Collect detail" }), {
      key: " ",
    });

    expect(screen.getByPlaceholderText("Detail")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("请输入自定义回复"),
    ).not.toBeInTheDocument();
  });

  it("submits paged form values without a global supplemental step", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "customer_plan_clarification",
          prompt: "Collect planning context",
          fields: [
            {
              id: "industry",
              label: "所在行业",
              type: "single_choice",
              required: true,
              options: [{ id: "retail", label: "零售/电商" }],
            },
            {
              id: "challenges",
              label: "当前主要挑战",
              type: "text",
              placeholder: "请补充",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /零售\/电商/ }));
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    fireEvent.change(screen.getByPlaceholderText("请补充"), {
      target: { value: "复购率低" },
    });
    fireEvent.keyDown(screen.getByPlaceholderText("请补充"), { key: "Enter" });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "所在行业: 零售/电商\n当前主要挑战: 复购率低",
      biz_params: {
        plan_interaction_response: {
          kind: "form",
          form_id: "customer_plan_clarification",
          field_values: {
            industry: "retail",
            challenges: "复购率低",
          },
        },
      },
    });
    submit.cleanup();
  });

  it("submits structured multi-choice form values as selected option ids", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan_checks",
          prompt: "Choose verification checks",
          fields: [
            {
              id: "checks",
              label: "验证项",
              type: "multi_choice",
              required: true,
              options: [
                { id: "frontend", label: "前端测试" },
                { id: "backend", label: "后端测试" },
              ],
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /前端测试/ }));
    fireEvent.click(screen.getByRole("button", { name: /后端测试/ }));
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "验证项: 前端测试, 后端测试",
      biz_params: {
        plan_interaction_response: {
          field_values: {
            checks: ["frontend", "backend"],
          },
        },
      },
    });
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).not.toHaveProperty("custom_field_values");
    submit.cleanup();
  });

  it("shows a persistent custom input for a required single-choice form field", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              required: true,
              options: [{ id: "backend", label: "Backend" }],
            },
          ],
        }}
      />,
    );

    expect(screen.getByRole("textbox", { name: "Scope" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "自定义填写" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox", { name: "Scope" }), {
      target: { value: "CLI only" },
    });
    expect(screen.getByRole("button", { name: "提交" })).toBeEnabled();
  });

  it("renders persistent custom input as a single horizontally scrollable line", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              options: [{ id: "backend", label: "Backend" }],
            },
          ],
        }}
      />,
    );

    const customInput = screen.getByRole("textbox", { name: "Scope" });
    expect(customInput.tagName).toBe("INPUT");
    expect(stylesheet).toContain("overflow-x: auto;");
    expect(stylesheet).toContain("white-space: nowrap;");
    expect(stylesheet).toContain(".choiceOptionsViewport + .customFieldInput");
    expect(stylesheet).toContain("margin-top: 10px;");
  });

  it("replaces a single-choice selection when persistent custom text is entered", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              required: true,
              options: [{ id: "backend", label: "Backend" }],
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Backend" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Scope" }), {
      target: { value: "CLI only" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Scope: CLI only",
      biz_params: {
        plan_interaction_response: {
          field_values: {},
          custom_field_values: { scope: "CLI only" },
        },
      },
    });
    submit.cleanup();
  });

  it("submits multi-choice ids and field-level custom text independently", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "checks-context",
          prompt: "Collect checks",
          fields: [
            {
              id: "checks",
              label: "Checks",
              type: "multi_choice",
              options: [{ id: "lint", label: "Lint" }],
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Lint" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Checks" }), {
      target: { value: "Security scan" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Checks: Lint, Security scan",
      biz_params: {
        plan_interaction_response: {
          field_values: { checks: ["lint"] },
          custom_field_values: { checks: "Security scan" },
        },
      },
    });
    submit.cleanup();
  });

  it("does not append a global custom-response step to forms", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          allow_custom_response: true,
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              options: [{ id: "backend", label: "Backend" }],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("1 of 1")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("请输入自定义回复"),
    ).not.toBeInTheDocument();
  });

  it("hides the persistent custom input when explicitly disabled", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          allow_custom_response: false,
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              options: [{ id: "backend", label: "Backend" }],
            },
          ],
        }}
      />,
    );

    expect(
      screen.queryByRole("textbox", { name: "Scope" }),
    ).not.toBeInTheDocument();
  });

  it("preserves custom field context when revisiting a form field", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          allow_custom_response: true,
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "multi_choice",
              required: true,
              options: [{ id: "small", label: "Small" }],
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("请输入自定义填写"), {
      target: { value: "Keep this context" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Small" }));

    expect(screen.getByPlaceholderText("请输入自定义填写")).toHaveValue(
      "Keep this context",
    );
  });

  it("keeps long option sets inside the card viewport", () => {
    const { container } = render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: Array.from({ length: 6 }, (_, index) => ({
            id: String(index),
            label: `Option ${index + 1}`,
          })),
        }}
      />,
    );

    expect(
      container.querySelector(`.${styles.choiceOptionsViewport}`),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Option/ })).toHaveLength(6);
  });

  it("wraps long option labels and retains their complete label", () => {
    const longLabel =
      "This is a deliberately long option label that must wrap inside the clarification card without being truncated";
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "long", label: longLabel }],
        }}
      />,
    );

    expect(screen.getByRole("button", { name: longLabel })).toHaveAttribute(
      "aria-label",
      longLabel,
    );
    expect(screen.getByTitle(longLabel)).toBeInTheDocument();
    expect(stylesheet).toContain("max-height: 244px;");
    expect(stylesheet).toContain("overflow-y: auto;");
    expect(stylesheet).toContain("white-space: normal;");
    expect(stylesheet).toContain("overflow-wrap: anywhere;");
  });

  it("hides a submitted clarification in the current render", async () => {
    const submit = captureSubmitEvents();
    const data = {
      card_type: "plan_clarification" as const,
      kind: "single_choice" as const,
      prompt: "Pick scope",
      options: [{ id: "small", label: "Small" }],
    };
    render(<PlanClarificationCard data={data} />);

    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });
    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));

    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();
    submit.cleanup();
  });

  it("resets stale clarification state when a newer card instance replaces it", () => {
    const firstMessages = [
      {
        id: "message-1",
        role: "assistant" as const,
        cards: [
          {
            id: "clarification-1",
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];
    const { rerender } = renderActiveClarification(firstMessages);

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    expect(screen.getByRole("button", { name: "提交" })).toBeEnabled();

    const secondMessages = [
      ...firstMessages,
      {
        id: "message-2",
        role: "assistant" as const,
        cards: [
          {
            id: "clarification-2",
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick size",
              options: [{ id: "large", label: "Large" }],
            },
          },
        ],
      },
    ];

    rerender(
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages: secondMessages,
            setMessages: vi.fn(),
            getMessages: () => secondMessages,
          }}
        >
          <ActivePlanClarificationCard />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>,
    );

    expect(screen.getByRole("button", { name: /Large/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
  });

  it("shows a dismissed clarification after reload when it is not superseded", () => {
    const firstMessages = [
      {
        id: "msg_runtime_1",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_1",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_1",
                  metadata: {
                    original_id: "assistant-stable-1",
                    trace_id: "trace-stable-1",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];
    const { rerender } = renderActiveClarification(firstMessages);

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();

    const reloadedMessages = [
      {
        id: "msg_runtime_2",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_2",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_2",
                  metadata: {
                    original_id: "assistant-stable-1",
                    trace_id: "trace-stable-1",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];

    rerender(
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages: reloadedMessages,
            setMessages: vi.fn(),
            getMessages: () => reloadedMessages,
          }}
        >
          <ActivePlanClarificationCard />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>,
    );

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("shows a repeated clarification again when it is a new card instance", () => {
    const firstMessages = [
      {
        id: "message-1",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_1",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_1",
                  metadata: {
                    original_id: "assistant-stable-1",
                    trace_id: "trace-stable-1",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];
    const { rerender } = renderActiveClarification(firstMessages);

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();

    const secondMessages = [
      ...firstMessages,
      {
        id: "message-2",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_2",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_2",
                  metadata: {
                    original_id: "assistant-stable-2",
                    trace_id: "trace-stable-2",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];

    rerender(
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages: secondMessages,
            setMessages: vi.fn(),
            getMessages: () => secondMessages,
          }}
        >
          <ActivePlanClarificationCard />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>,
    );

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("hides a clarification superseded by a later user message", async () => {
    const messages = [
      createClarificationMessage({
        messageId: "message-1",
        originalId: "assistant-stable-1",
        traceId: "trace-stable-1",
      }),
    ];
    const { unmount } = renderActiveClarification(messages);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );
    unmount();
    renderActiveClarification(messages);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );

    cleanup();
    renderActiveClarification([
      ...messages,
      {
        id: "user-1",
        role: "user" as const,
        cards: [
          {
            code: "AgentScopeRuntimeRequestCard",
            data: {
              input: [
                {
                  role: "user",
                  type: "message",
                  content: [
                    {
                      type: "text",
                      text: "Continue without answering",
                    },
                  ],
                },
              ],
            },
          },
        ],
      },
    ]);

    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();
  });

  it("renders a repeated clarification from a later assistant message", async () => {
    const firstMessage = createClarificationMessage({
      messageId: "message-1",
      originalId: "assistant-stable-1",
      traceId: "trace-stable-1",
    });
    const { unmount } = renderActiveClarification([firstMessage]);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );
    unmount();

    renderActiveClarification([
      firstMessage,
      createClarificationMessage({
        messageId: "message-2",
        originalId: "assistant-stable-2",
        traceId: "trace-stable-2",
      }),
    ]);

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("does not suppress a later repeated clarification after submitting the first instance", async () => {
    const submit = captureSubmitEvents();
    const firstMessage = createClarificationMessage({
      messageId: "message-1",
      originalId: "assistant-stable-1",
      traceId: "trace-stable-1",
    });
    const { unmount } = renderActiveClarification([firstMessage]);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );
    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });
    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    unmount();

    renderActiveClarification([
      firstMessage,
      createClarificationMessage({
        messageId: "message-2",
        originalId: "assistant-stable-2",
        traceId: "trace-stable-2",
      }),
    ]);

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
    submit.cleanup();
  });

  it("renders an interactive plan review in the message flow", () => {
    const onContinueModifying = vi.fn();
    renderPlanReviewMessage(createReviewData(), { onContinueModifying });

    expect(screen.getByRole("region", { name: "Fix bug" })).toHaveAttribute(
      "data-active-plan-review-card",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "继续修改" }));

    expect(onContinueModifying).toHaveBeenCalledWith(
      expect.objectContaining({ plan_id: "plan-123" }),
    );
  });

  it("renders a read-only plan review snapshot with submitted execute status", () => {
    render(
      <PlanReviewSnapshot
        data={createReviewData({
          status: "submitted",
          submitted_decision: "execute",
        })}
      />,
    );

    expect(screen.getByRole("region", { name: "Fix bug" })).toHaveAttribute(
      "data-plan-review-snapshot",
      "true",
    );
    expect(screen.getByText("已接受并开始执行")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "继续修改" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "开始执行" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "退出计划模式" }),
    ).not.toBeInTheDocument();
  });

  it("keeps action buttons in active plan review mode", () => {
    const { container } = render(
      <PlanReviewCard active data={createReviewData()} />,
    );

    expect(
      container.querySelector(`.${styles.planReviewActiveCard}`),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "继续修改" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "开始执行" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "退出计划模式" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "反馈意见" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Feedback")).not.toBeInTheDocument();
  });

  it("renders long plan review summary in the body summary area", () => {
    const longSummary =
      "This summary is intentionally long so it should wrap inside the review body instead of being placed in a single-line header paragraph.";
    const { container } = render(
      <PlanReviewCard
        active
        data={createReviewData({ summary: longSummary })}
      />,
    );

    expect(
      container.querySelector(`.${styles.reviewSummary}`),
    ).toHaveTextContent(longSummary);
  });

  it("uses Chinese review actions with one primary execute action", () => {
    render(<PlanReviewCard active data={createReviewData()} />);

    expect(
      screen.getByRole("button", { name: "继续修改" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "退出计划模式" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始执行" })).toHaveClass(
      styles.reviewPrimaryButton,
    );
  });

  it("calls continue modifying without submitting a plan review response", () => {
    const submit = captureSubmitEvents();
    const onContinueModifying = vi.fn();

    render(
      <PlanReviewCard
        active
        onContinueModifying={onContinueModifying}
        data={{
          card_type: "plan_review",
          plan_id: "plan-123",
          title: "Fix bug",
          summary: "Investigate and patch",
          steps: ["Read code", "Patch code"],
          risks: ["Regression"],
          verification: ["Focused tests"],
        }}
      />,
    );
    expect(
      screen.queryByTestId("generic-operate-card"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Fix bug" })).toHaveAttribute(
      "data-plan-review-card",
      "true",
    );
    expect(screen.getByText("执行步骤")).toBeInTheDocument();
    expect(screen.getByText("风险提示")).toBeInTheDocument();
    expect(screen.getByText("验证方式")).toBeInTheDocument();
    expect(screen.queryByText("Open questions")).not.toBeInTheDocument();
    expect(screen.queryByText(/Confidence:/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "继续修改" }));

    expect(onContinueModifying).toHaveBeenCalledWith(
      expect.objectContaining({ plan_id: "plan-123" }),
    );
    expect(submit.handler).not.toHaveBeenCalled();

    submit.cleanup();
  });

  it("executes review cards in normal mode and disables duplicates", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanReviewCard
        active
        data={{
          card_type: "plan_review",
          plan_id: "plan-456",
          title: "Ship plan",
          summary: "Ready",
          steps: [],
          risks: [],
          verification: [],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "开始执行" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      biz_params: {
        mode: "normal",
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: "plan-456",
          decision: "execute",
        },
      },
    });
    expect(screen.getByRole("button", { name: "开始执行" })).toBeDisabled();

    submit.cleanup();
  });

  it("exits plan mode locally without submitting a chat message", async () => {
    const submit = captureSubmitEvents();
    const onPlanModeDecision = vi.fn();

    render(
      <PlanReviewCard
        active
        onPlanModeDecision={onPlanModeDecision}
        data={createReviewData({
          plan_id: "plan-exit",
          title: "Exit without message",
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "退出计划模式" }));

    expect(onPlanModeDecision).toHaveBeenCalledWith(false);
    await Promise.resolve();
    expect(submit.handler).not.toHaveBeenCalled();

    submit.cleanup();
  });

  it("uses the approved task-panel visual state tokens", () => {
    expect(stylesheet).toContain("--clarification-card-bg: #ffffff");
    expect(stylesheet).toContain("--clarification-border: #e5e7eb");
    expect(stylesheet).toContain("--clarification-accent: #3769fc");
    expect(stylesheet).toContain("--clarification-selected-bg: #eef4ff");
    expect(stylesheet).toContain(
      "border-left: 3px solid var(--clarification-accent)",
    );
    expect(stylesheet).toContain("min-height: 44px");
    expect(stylesheet).toContain("height: 36px");
    expect(stylesheet).toContain(".optionRowFocused");
    expect(stylesheet).toContain(".optionRowSelected");
    expect(stylesheet).not.toContain("optionFocusIcon");
    expect(stylesheet).not.toContain("height: 48vh");
    expect(stylesheet).toContain(":global(.dark-mode)");
    expect(stylesheet).toContain("@media (prefers-reduced-motion: reduce)");
    expect(stylesheet).toContain("animation: none");
    expect(stylesheet).toContain("transition: none");
    expect(stylesheet).not.toContain("#4f6f63");
  });

  it("uses compact vertical spacing for clarification cards", () => {
    expect(stylesheet).toContain("padding: 16px;");
    expect(stylesheet).toContain("min-height: 44px;");
    expect(stylesheet).not.toContain("flex: 0 0 44px;");
    expect(stylesheet).toContain("gap: 6px;");
    expect(stylesheet).toContain("min-height: 64px;");
    expect(stylesheet).toContain("margin-top: 12px;");
    expect(stylesheet).toContain("padding-top: 12px;");
  });
});
