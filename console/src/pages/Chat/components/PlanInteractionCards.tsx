import { type ReactElement, useEffect, useRef, useState } from "react";
import {
  Ban,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CornerDownLeft,
  Crosshair,
  ShieldCheck,
} from "lucide-react";
import { type IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import { emit } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter";
import type {
  ChatRuntimeResponseCardData,
  ChatPlanClarificationCardData,
  PlanClarificationField,
  ChatPlanReviewCardData,
  ChatGoalProposalCardData,
  ChatGoalCompletionCriterion,
  PlanClarificationOption,
} from "../messageMeta";
import {
  resolveFeedbackResponseId,
  resolveFeedbackTraceId,
} from "../messageMeta";
import { useChatPlanReviewRenderContext } from "../planReviewRenderContext";
import styles from "./PlanInteractionCards.module.less";
import { useContextSelector } from "use-context-selector";

const PLAN_INTERACTION_CARD_CODE = "PlanInteraction";
const RUNTIME_RESPONSE_CARD_CODE = "AgentScopeRuntimeResponseCard";

function optionLabels(
  options: PlanClarificationOption[] | undefined,
  selectedIds: string[],
): string {
  const labelById = new Map(
    (options || []).map((item) => [item.id, item.label]),
  );
  return selectedIds
    .map((id) => labelById.get(id) || id)
    .filter(Boolean)
    .join(", ");
}

function hasFormValue(value: string | string[] | undefined): boolean {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return Boolean(value && value.trim());
}

function formatFormFieldValue(
  field: PlanClarificationField,
  value: string | string[] | undefined,
): string {
  if (!hasFormValue(value)) return "";
  const optionLabelById = new Map(
    (field.options || []).map((item) => [item.id, item.label]),
  );
  if (Array.isArray(value)) {
    return value
      .map((item) => optionLabelById.get(item) || item)
      .filter(Boolean)
      .join(", ");
  }
  return optionLabelById.get(value) || value;
}

function collectFormValues(
  fields: PlanClarificationField[],
  values: Record<string, string | string[]>,
): Record<string, string | string[]> {
  return Object.fromEntries(
    fields
      .map((field) => [field.id, values[field.id]] as const)
      .filter(([, value]) => hasFormValue(value)),
  );
}

function collectCustomFormValues(
  values: Record<string, string>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values)
      .map(([fieldId, value]) => [fieldId, value.trim()] as const)
      .filter(([, value]) => Boolean(value)),
  );
}

function isPlanClarificationCardData(
  data: unknown,
): data is ChatPlanClarificationCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    (data as { card_type?: unknown }).card_type === "plan_clarification"
  );
}

function isPlanReviewCardData(data: unknown): data is ChatPlanReviewCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    (data as { card_type?: unknown }).card_type === "plan_review"
  );
}

function isRuntimeResponseCardData(
  data: unknown,
): data is ChatRuntimeResponseCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    Array.isArray((data as { output?: unknown }).output)
  );
}

function createPlanClarificationFingerprint(
  data: ChatPlanClarificationCardData,
): string {
  return JSON.stringify({
    kind: data.kind,
    prompt: data.prompt,
    form_id: data.form_id,
    options: data.options || [],
    fields: data.fields || [],
    allow_custom_response: data.allow_custom_response !== false,
  });
}

function resolveClarificationSourceKey(
  cards: IAgentScopeRuntimeWebUIMessage["cards"],
  data: ChatPlanClarificationCardData,
): string | null {
  const responseCard = (cards || []).find(
    (card) =>
      card.code === RUNTIME_RESPONSE_CARD_CODE &&
      isRuntimeResponseCardData(card.data),
  );
  if (!responseCard || !isRuntimeResponseCardData(responseCard.data)) {
    return null;
  }

  const responseId = resolveFeedbackResponseId(responseCard.data);
  if (responseId) {
    return JSON.stringify({
      source: "response",
      response_id: responseId,
      clarification: createPlanClarificationFingerprint(data),
    });
  }

  const traceId = resolveFeedbackTraceId(responseCard.data);
  if (traceId) {
    return JSON.stringify({
      source: "trace",
      trace_id: traceId,
      clarification: createPlanClarificationFingerprint(data),
    });
  }

  return null;
}

function findLatestPlanClarificationCard(
  messages: IAgentScopeRuntimeWebUIMessage[],
): {
  data: ChatPlanClarificationCardData;
  instanceKey: string;
  sourceKey: string | null;
} | null {
  let hasLaterUserMessage = false;
  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = messages[messageIndex];
    if (message?.role === "user") {
      hasLaterUserMessage = true;
      continue;
    }
    const cards = message?.cards || [];
    for (let cardIndex = cards.length - 1; cardIndex >= 0; cardIndex -= 1) {
      const card = cards[cardIndex];
      if (
        !hasLaterUserMessage &&
        card.code === PLAN_INTERACTION_CARD_CODE &&
        isPlanClarificationCardData(card.data)
      ) {
        return {
          data: card.data,
          instanceKey: `${message.id}:${card.id || card.code}:${cardIndex}`,
          sourceKey: resolveClarificationSourceKey(cards, card.data),
        };
      }
    }
  }
  return null;
}

type ActivePlanInteraction =
  | {
      type: "clarification";
      data: ChatPlanClarificationCardData;
      instanceKey: string;
      sourceKey: string | null;
    }
  | {
      type: "goal_proposal";
      data: ChatGoalProposalCardData;
      instanceKey: string;
      sourceKey: string | null;
    };

function findLatestActivePlanInteractionCard(
  messages: IAgentScopeRuntimeWebUIMessage[],
): ActivePlanInteraction | null {
  let hasLaterUserMessage = false;
  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = messages[messageIndex];
    if (message?.role === "user") {
      hasLaterUserMessage = true;
      continue;
    }

    const cards = message?.cards || [];
    for (let cardIndex = cards.length - 1; cardIndex >= 0; cardIndex -= 1) {
      const card = cards[cardIndex];
      if (card.code !== PLAN_INTERACTION_CARD_CODE || hasLaterUserMessage) {
        continue;
      }

      const instanceKey = `${message.id}:${card.id || card.code}:${cardIndex}`;
      if (isPlanReviewCardData(card.data)) {
        return null;
      }

      if (isGoalProposalCardData(card.data)) {
        return {
          type: "goal_proposal",
          data: card.data,
          instanceKey,
          sourceKey: null,
        };
      }

      if (isPlanClarificationCardData(card.data)) {
        return {
          type: "clarification",
          data: card.data,
          instanceKey,
          sourceKey: resolveClarificationSourceKey(cards, card.data),
        };
      }

      return null;
    }
  }
  return null;
}

function isGoalProposalCardData(
  data: unknown,
): data is ChatGoalProposalCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    (data as { card_type?: unknown }).card_type === "goal_proposal"
  );
}

function boundedIndex(index: number, count: number): number {
  if (count <= 0) return 0;
  return Math.min(Math.max(index, 0), count - 1);
}

function isTextTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
  );
}

function ChoiceRows({
  options,
  selectedIds,
  focusedIndex,
  onFocusIndexChange,
  onSelect,
}: {
  options: PlanClarificationOption[];
  selectedIds: string[];
  focusedIndex: number;
  onFocusIndexChange: (index: number) => void;
  onSelect: (optionId: string) => void;
}) {
  const rowRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    const focusedRow = rowRefs.current[focusedIndex];
    if (typeof focusedRow?.scrollIntoView === "function") {
      focusedRow.scrollIntoView({ block: "nearest" });
    }
  }, [focusedIndex]);

  return (
    <div className={styles.choiceOptionsViewport}>
      {options.map((option, index) => {
        const selected = selectedIds.includes(option.id);
        const focused = focusedIndex === index;
        return (
          <button
            ref={(node) => {
              rowRefs.current[index] = node;
            }}
            key={option.id}
            type="button"
            className={[
              styles.optionRow,
              focused ? styles.optionRowFocused : "",
              selected ? styles.optionRowSelected : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-current={focused ? "true" : undefined}
            aria-pressed={selected}
            aria-label={option.label}
            onFocus={() => onFocusIndexChange(index)}
            onClick={() => onSelect(option.id)}
          >
            <span className={styles.optionNumber}>{index + 1}.</span>
            <span className={styles.optionLabel} title={option.label}>
              {option.label}
            </span>
            {selected ? (
              <span className={styles.optionCheck} aria-hidden="true">
                <Check size={15} strokeWidth={3} />
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function PlanClarificationCard({
  data,
  cardInstanceKey,
  onComplete,
}: {
  data: ChatPlanClarificationCardData;
  cardInstanceKey?: string;
  onComplete?: () => void;
}) {
  const [singleChoice, setSingleChoice] = useState<string>("");
  const [multiChoice, setMultiChoice] = useState<string[]>([]);
  const [textInput, setTextInput] = useState("");
  const [customActive, setCustomActive] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [activeStep, setActiveStep] = useState(0);
  const [formValues, setFormValues] = useState<
    Record<string, string | string[]>
  >({});
  const [customFieldValues, setCustomFieldValues] = useState<
    Record<string, string>
  >({});
  const cardRef = useRef<HTMLElement | null>(null);
  const interactionResetKey =
    cardInstanceKey || createPlanClarificationFingerprint(data);
  const [submitted, setSubmitted] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const options = data.options || [];
  const fields = data.fields || [];
  const isTopLevelChoice =
    data.kind === "single_choice" || data.kind === "multi_choice";
  const totalSteps = data.kind === "form" ? fields.length : 1;
  const boundedStep = boundedIndex(activeStep, totalSteps);
  const activeField =
    data.kind === "form" && boundedStep < fields.length
      ? fields[boundedStep]
      : undefined;
  const activeOptions =
    activeField?.type === "single_choice" ||
    activeField?.type === "multi_choice"
      ? activeField.options || []
      : options;
  const activeSelectedIds = activeField
    ? Array.isArray(formValues[activeField.id])
      ? (formValues[activeField.id] as string[])
      : typeof formValues[activeField.id] === "string"
      ? [formValues[activeField.id] as string]
      : []
    : data.kind === "single_choice"
    ? singleChoice
      ? [singleChoice]
      : []
    : data.kind === "multi_choice"
    ? multiChoice
    : [];
  const selectedIds =
    data.kind === "single_choice"
      ? singleChoice
        ? [singleChoice]
        : []
      : data.kind === "multi_choice"
      ? multiChoice
      : [];
  const trimmedText = textInput.trim();
  const effectiveChoiceText = isTopLevelChoice
    ? trimmedText
    : customActive
    ? trimmedText
    : "";
  const fieldHasCustomValue = (field: PlanClarificationField): boolean =>
    Boolean(customFieldValues[field.id]?.trim());
  const fieldHasResponse = (field: PlanClarificationField): boolean =>
    hasFormValue(formValues[field.id]) || fieldHasCustomValue(field);
  const requiredFormFieldsSatisfied = fields.every(
    (field) => !field.required || fieldHasResponse(field),
  );
  const formQueryLines = fields
    .map((field) => {
      const values = [
        formatFormFieldValue(field, formValues[field.id]),
        customFieldValues[field.id]?.trim(),
      ].filter(Boolean);
      return values.length > 0 ? `${field.label}: ${values.join(", ")}` : "";
    })
    .filter(Boolean);
  const disabled =
    data.kind === "text"
      ? !trimmedText
      : data.kind === "form"
      ? !requiredFormFieldsSatisfied || formQueryLines.length === 0
      : selectedIds.length === 0 && !effectiveChoiceText;
  const currentFieldComplete = activeField
    ? !activeField.required || fieldHasResponse(activeField)
    : true;
  const isFinalStep = boundedStep >= totalSteps - 1;
  const canGoNext = !isFinalStep && currentFieldComplete;
  const pageTitle =
    data.kind === "form" ? activeField?.label || data.prompt : data.prompt;
  const showChoiceRows =
    isTopLevelChoice ||
    activeField?.type === "single_choice" ||
    activeField?.type === "multi_choice";
  const showTopLevelChoiceCustomInput = isTopLevelChoice;
  const showCustomInput =
    data.kind === "text" || showTopLevelChoiceCustomInput || customActive;

  useEffect(() => {
    setSubmitted(false);
    setDismissed(false);
    setSingleChoice("");
    setMultiChoice([]);
    setTextInput("");
    setCustomActive(false);
    setFormValues({});
    setCustomFieldValues({});
    setFocusedIndex(0);
    setActiveStep(0);
  }, [interactionResetKey]);

  const handleCustomTextChange = (value: string) => {
    setTextInput(value);
    if (data.kind === "single_choice" && value.trim()) {
      setSingleChoice("");
    }
  };

  const handleCustomFieldTextChange = (fieldId: string, value: string) => {
    setCustomFieldValues((current) => ({ ...current, [fieldId]: value }));
    if (activeField?.id === fieldId && activeField.type === "single_choice") {
      setFormValues((current) => ({ ...current, [fieldId]: "" }));
    }
  };

  useEffect(() => {
    if (submitted || dismissed || !showChoiceRows) return;
    cardRef.current?.focus({ preventScroll: true });
  }, [boundedStep, dismissed, interactionResetKey, showChoiceRows, submitted]);

  useEffect(() => {
    setFocusedIndex(0);
  }, [boundedStep]);

  const handleDismiss = () => {
    setDismissed(true);
    onComplete?.();
  };

  const handleSubmit = (selectedOverride?: string[]) => {
    const effectiveSelectedIds = selectedOverride || selectedIds;
    const effectiveSelectedLabels = optionLabels(options, effectiveSelectedIds);
    const effectiveText =
      data.kind === "text" ? trimmedText : effectiveChoiceText;
    const effectiveQuery =
      data.kind === "text"
        ? effectiveText
        : data.kind === "form"
        ? formQueryLines.join("\n")
        : [effectiveSelectedLabels, effectiveText].filter(Boolean).join("\n");
    const effectiveDisabled =
      data.kind === "text"
        ? !effectiveQuery
        : data.kind === "form"
        ? !requiredFormFieldsSatisfied || !effectiveQuery
        : effectiveSelectedIds.length === 0 && !effectiveText;
    if (effectiveDisabled || submitted) return;
    const payload =
      data.kind === "form"
        ? (() => {
            const customValues = collectCustomFormValues(customFieldValues);
            return {
              card_type: "plan_clarification" as const,
              kind: "form" as const,
              form_id: data.form_id,
              field_values: collectFormValues(fields, formValues),
              ...(Object.keys(customValues).length > 0
                ? { custom_field_values: customValues }
                : {}),
            };
          })()
        : {
            card_type: "plan_clarification" as const,
            kind: data.kind,
            selected_option_ids: effectiveSelectedIds,
            text: effectiveText || undefined,
          };
    setSubmitted(true);
    onComplete?.();
    emit({
      type: "handleSubmit",
      data: {
        query: effectiveQuery,
        fileList: [],
        biz_params: {
          plan_interaction_response: payload,
        },
      },
    });
  };

  const goBack = () => {
    if (customActive && data.kind !== "form") {
      setCustomActive(false);
      return;
    }
    if (boundedStep > 0) {
      setActiveStep((current) => boundedIndex(current - 1, totalSteps));
      return;
    }
    handleDismiss();
  };

  const goForward = () => {
    if (!isFinalStep) {
      if (canGoNext) {
        setActiveStep((current) => boundedIndex(current + 1, totalSteps));
      }
      return;
    }
    handleSubmit();
  };

  const selectActiveOption = (optionId: string) => {
    if (!activeField && data.kind === "single_choice") {
      setCustomActive(false);
      setTextInput("");
    }
    if (activeField) {
      if (activeField.type === "single_choice") {
        setCustomFieldValues((current) => ({
          ...current,
          [activeField.id]: "",
        }));
      }
      setFormValues((current) => {
        const currentValue = current[activeField.id];
        if (activeField.type === "multi_choice") {
          const currentIds = Array.isArray(currentValue) ? currentValue : [];
          return {
            ...current,
            [activeField.id]: currentIds.includes(optionId)
              ? currentIds.filter((id) => id !== optionId)
              : [...currentIds, optionId],
          };
        }
        return { ...current, [activeField.id]: optionId };
      });
      return;
    }
    if (data.kind === "multi_choice") {
      setMultiChoice((current) =>
        current.includes(optionId)
          ? current.filter((id) => id !== optionId)
          : [...current, optionId],
      );
      return;
    }
    setSingleChoice(optionId);
  };

  const handleCardKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      goBack();
      return;
    }
    if (isTextTarget(event.target)) {
      if (event.key === "Enter" && !event.shiftKey) {
        if (event.nativeEvent.isComposing) {
          return;
        }
        event.preventDefault();
        goForward();
      }
      return;
    }
    const rowCount = activeOptions.length;
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      setFocusedIndex((current) =>
        boundedIndex(current + (event.key === "ArrowUp" ? -1 : 1), rowCount),
      );
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (boundedStep > 0) {
        setActiveStep((current) => boundedIndex(current - 1, totalSteps));
      }
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      goForward();
      return;
    }
    if (/^[1-9]$/.test(event.key)) {
      const index = Number(event.key) - 1;
      if (index < rowCount) {
        event.preventDefault();
        setFocusedIndex(index);
        selectActiveOption(activeOptions[index].id);
      }
      return;
    }
    if (event.key === " ") {
      event.preventDefault();
      if (activeOptions[focusedIndex]) {
        selectActiveOption(activeOptions[focusedIndex].id);
      }
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (
        data.kind === "single_choice" &&
        !singleChoice &&
        !trimmedText &&
        activeOptions[focusedIndex]
      ) {
        const focusedOptionId = activeOptions[focusedIndex].id;
        setSingleChoice(focusedOptionId);
        handleSubmit([focusedOptionId]);
        return;
      }
      goForward();
    }
  };

  if (submitted || dismissed) return null;

  return (
    <section
      ref={cardRef}
      className={styles.planClarificationCard}
      data-plan-clarification-active="true"
      role="region"
      aria-label={data.prompt}
      tabIndex={0}
      onKeyDown={handleCardKeyDown}
    >
      <header className={styles.cardHeader}>
        <div className={styles.cardHeading}>
          <strong>{pageTitle}</strong>
          {activeField?.required ? <span>必填</span> : null}
        </div>
        <div className={styles.cardPager}>
          <button
            type="button"
            aria-label="上一项"
            disabled={boundedStep === 0}
            onClick={() =>
              setActiveStep((current) => boundedIndex(current - 1, totalSteps))
            }
          >
            <ChevronLeft aria-hidden="true" size={15} />
          </button>
          <span>
            {boundedStep + 1} of {totalSteps}
          </span>
          <button
            type="button"
            aria-label="下一项"
            disabled={!canGoNext}
            onClick={goForward}
          >
            <ChevronRight aria-hidden="true" size={15} />
          </button>
        </div>
      </header>

      {activeField?.description ? (
        <p className={styles.fieldDescription}>{activeField.description}</p>
      ) : null}

      <div className={styles.cardStage}>
        {showChoiceRows ? (
          <ChoiceRows
            options={activeOptions}
            selectedIds={activeSelectedIds}
            focusedIndex={focusedIndex}
            onFocusIndexChange={setFocusedIndex}
            onSelect={selectActiveOption}
          />
        ) : null}
        {activeField?.type === "text" ? (
          <input
            autoFocus
            className={styles.textField}
            aria-label={activeField.label}
            placeholder={activeField.placeholder || activeField.label}
            value={
              typeof formValues[activeField.id] === "string"
                ? (formValues[activeField.id] as string)
                : ""
            }
            onChange={(event) =>
              setFormValues((current) => ({
                ...current,
                [activeField.id]: event.target.value,
              }))
            }
          />
        ) : null}
        {showCustomInput ? (
          <textarea
            autoFocus
            className={styles.textArea}
            aria-label={pageTitle}
            placeholder={
              data.kind === "text"
                ? data.prompt
                : isTopLevelChoice
                ? "输入自定义回复"
                : "请输入自定义回复"
            }
            value={textInput}
            onChange={(event) => handleCustomTextChange(event.target.value)}
          />
        ) : null}
        {activeField &&
        (activeField.type === "single_choice" ||
          activeField.type === "multi_choice") &&
        data.allow_custom_response !== false ? (
          <input
            autoFocus
            className={`${styles.textField} ${styles.customFieldInput}`}
            aria-label={activeField.label}
            placeholder="请输入自定义填写"
            value={customFieldValues[activeField.id] || ""}
            onChange={(event) =>
              handleCustomFieldTextChange(activeField.id, event.target.value)
            }
          />
        ) : null}
      </div>

      <footer className={styles.cardFooter}>
        <p className={styles.keyboardHint}>方向键切换选项，Space 选择</p>
        <div className={styles.cardActions}>
          <button
            type="button"
            className={styles.dismissButton}
            aria-label="退出"
            onClick={handleDismiss}
          >
            <span>退出</span>
            <kbd>ESC</kbd>
          </button>
          <button
            type="button"
            className={styles.continueButton}
            aria-label={isFinalStep ? "提交" : "继续"}
            disabled={isFinalStep ? disabled : !canGoNext}
            onClick={goForward}
          >
            <span>{isFinalStep ? "提交" : "继续"}</span>
            <CornerDownLeft aria-hidden="true" size={14} />
          </button>
        </div>
      </footer>
    </section>
  );
}

export function ActivePlanClarificationCard() {
  const clarification = useContextSelector(
    ChatAnywhereMessagesContext,
    (value) => findLatestPlanClarificationCard(value.messages || []),
  );

  if (!clarification) {
    return null;
  }
  return (
    <PlanClarificationCard
      data={clarification.data}
      cardInstanceKey={clarification.instanceKey}
    />
  );
}

function PlanList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className={styles.reviewSection}>
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function planReviewStatusText(data: ChatPlanReviewCardData): string {
  switch (data.submitted_decision) {
    case "execute":
      return "已接受并开始执行";
    case "revise":
      return "已要求修改";
    case "exit_plan":
      return "已退出计划模式";
    default:
      return "计划待确认";
  }
}

export function PlanReviewSnapshot({ data }: { data: ChatPlanReviewCardData }) {
  return (
    <section
      className={styles.planReviewCard}
      data-plan-review-snapshot="true"
      role="region"
      aria-label={data.title}
    >
      <header className={styles.reviewHeader}>
        <div className={styles.reviewHeading}>
          <div>
            <strong>{data.title}</strong>
            <p className={styles.reviewStatus}>{planReviewStatusText(data)}</p>
          </div>
        </div>
      </header>

      <div className={styles.reviewContent}>
        <p className={styles.reviewSummary}>{data.summary}</p>
        <PlanList title="执行步骤" items={data.steps} />
        <PlanList title="风险提示" items={data.risks} />
        <PlanList title="验证方式" items={data.verification} />
        {data.feedback ? (
          <section className={styles.reviewSection}>
            <h4>修改意见</h4>
            <p className={styles.reviewFeedbackSummary}>{data.feedback}</p>
          </section>
        ) : null}
      </div>
    </section>
  );
}

function PlanReviewActiveCard({
  data,
  cardInstanceKey,
  onContinueModifying,
  onPlanModeDecision,
  onComplete,
}: {
  data: ChatPlanReviewCardData;
  cardInstanceKey?: string;
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
  onComplete?: () => void;
}) {
  const resolvedByBackend = data.status === "submitted";
  const [submitted, setSubmitted] = useState(false);
  const interactionResetKey = cardInstanceKey || data.plan_id;

  useEffect(() => {
    setSubmitted(resolvedByBackend);
  }, [interactionResetKey, resolvedByBackend]);

  const handleDecision = (decision: "revise" | "execute" | "exit_plan") => {
    if (submitted) return;

    if (decision === "revise") {
      onContinueModifying?.(data);
      setSubmitted(true);
      onComplete?.();
      return;
    }

    if (decision === "exit_plan") {
      onPlanModeDecision?.(false);
      setSubmitted(true);
      onComplete?.();
      return;
    }

    const mode = "normal";
    const query = `Execute plan ${data.plan_id}`;

    onPlanModeDecision?.(false);
    setSubmitted(true);
    onComplete?.();
    emit({
      type: "handleSubmit",
      data: {
        query,
        fileList: [],
        biz_params: {
          mode,
          plan_interaction_response: {
            card_type: "plan_review",
            plan_id: data.plan_id,
            decision,
          },
        },
      },
    });
  };

  return (
    <section
      className={`${styles.planReviewCard} ${styles.planReviewActiveCard}`}
      data-plan-review-card="true"
      data-active-plan-review-card="true"
      role="region"
      aria-label={data.title}
    >
      <header className={styles.reviewHeader}>
        <div className={styles.reviewHeading}>
          <div>
            <strong>{data.title}</strong>
            <p className={styles.reviewStatus}>计划待确认</p>
          </div>
        </div>
      </header>

      <div className={styles.reviewContent}>
        <p className={styles.reviewSummary}>{data.summary}</p>
        <PlanList title="执行步骤" items={data.steps} />
        <PlanList title="风险提示" items={data.risks} />
        <PlanList title="验证方式" items={data.verification} />
      </div>

      <footer className={styles.reviewActions}>
        <button
          type="button"
          className={styles.reviewSecondaryButton}
          disabled={submitted}
          onClick={() => handleDecision("revise")}
        >
          继续修改
        </button>
        <button
          type="button"
          className={styles.reviewSecondaryButton}
          disabled={submitted}
          onClick={() => handleDecision("exit_plan")}
        >
          退出计划模式
        </button>
        <button
          type="button"
          className={styles.reviewPrimaryButton}
          disabled={submitted}
          onClick={() => handleDecision("execute")}
        >
          开始执行
        </button>
      </footer>
    </section>
  );
}

export function PlanReviewCard({
  data,
  active = false,
  cardInstanceKey,
  onContinueModifying,
  onPlanModeDecision,
  onComplete,
}: {
  data: ChatPlanReviewCardData;
  active?: boolean;
  cardInstanceKey?: string;
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
  onComplete?: () => void;
}) {
  if (!active) {
    return <PlanReviewSnapshot data={data} />;
  }
  return (
    <PlanReviewActiveCard
      data={data}
      cardInstanceKey={cardInstanceKey}
      onContinueModifying={onContinueModifying}
      onPlanModeDecision={onPlanModeDecision}
      onComplete={onComplete}
    />
  );
}

export function PlanReviewMessageCard({
  data,
}: {
  data: ChatPlanReviewCardData;
}) {
  const { onContinueModifying, onPlanModeDecision } =
    useChatPlanReviewRenderContext();

  return (
    <PlanReviewCard
      active={data.status !== "submitted"}
      data={data}
      cardInstanceKey={data.plan_id}
      onContinueModifying={onContinueModifying}
      onPlanModeDecision={onPlanModeDecision}
    />
  );
}

function GoalProposalCard({
  data,
  cardInstanceKey,
  onComplete,
}: {
  data: ChatGoalProposalCardData;
  cardInstanceKey: string;
  onComplete?: () => void;
}) {
  const { onConfirmGoalProposal } = useChatPlanReviewRenderContext();
  type DraftState = {
    objective: string;
    criteriaText: string;
    mustPreserve: string;
    mustNotDo: string;
    autonomyBoundary: string;
  };
  type DraftErrors = Partial<Record<keyof DraftState | "form", string>>;
  const initialDraft: DraftState = {
    objective: data.objective,
    criteriaText: JSON.stringify(data.completion_criteria, null, 2),
    mustPreserve: data.constraints.must_preserve.join("\n"),
    mustNotDo: data.constraints.must_not_do.join("\n"),
    autonomyBoundary: data.autonomy_boundary,
  };
  const [objective, setObjective] = useState(data.objective);
  const [criteriaText, setCriteriaText] = useState(
    JSON.stringify(data.completion_criteria, null, 2),
  );
  const [mustPreserve, setMustPreserve] = useState(
    data.constraints.must_preserve.join("\n"),
  );
  const [mustNotDo, setMustNotDo] = useState(
    data.constraints.must_not_do.join("\n"),
  );
  const [autonomyBoundary, setAutonomyBoundary] = useState(
    data.autonomy_boundary,
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [errors, setErrors] = useState<DraftErrors>({});
  const criteriaRef = useRef<HTMLTextAreaElement>(null);
  const objectiveRef = useRef<HTMLTextAreaElement>(null);
  const preserveRef = useRef<HTMLTextAreaElement>(null);
  const notDoRef = useRef<HTMLTextAreaElement>(null);
  const autonomyRef = useRef<HTMLTextAreaElement>(null);
  const detailsId = `goal-contract-details-${cardInstanceKey}`;

  useEffect(() => {
    setObjective(data.objective);
    setCriteriaText(JSON.stringify(data.completion_criteria, null, 2));
    setMustPreserve(data.constraints.must_preserve.join("\n"));
    setMustNotDo(data.constraints.must_not_do.join("\n"));
    setAutonomyBoundary(data.autonomy_boundary);
    setErrors({});
    setSubmitted(false);
    setDetailsOpen(true);
  }, [cardInstanceKey, data]);

  const normalizedCriteria = (value: string) => {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? JSON.stringify(parsed) : null;
    } catch {
      return null;
    }
  };
  const hasChanges =
    objective.trim() !== initialDraft.objective.trim() ||
    autonomyBoundary.trim() !== initialDraft.autonomyBoundary.trim() ||
    normalizedCriteria(criteriaText) !==
      normalizedCriteria(initialDraft.criteriaText) ||
    mustPreserve
      .split("\n")
      .map((item) => item.trim())
      .join("\n") !==
      initialDraft.mustPreserve
        .split("\n")
        .map((item) => item.trim())
        .join("\n") ||
    mustNotDo
      .split("\n")
      .map((item) => item.trim())
      .join("\n") !==
      initialDraft.mustNotDo
        .split("\n")
        .map((item) => item.trim())
        .join("\n");

  const summaryObjective = objective.trim() || "尚未填写目标";
  const preserveCount = mustPreserve
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean).length;
  const notDoCount = mustNotDo
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean).length;
  const criteriaCount = (() => {
    try {
      const parsed = JSON.parse(criteriaText);
      return Array.isArray(parsed) ? parsed.length : 0;
    } catch {
      return 0;
    }
  })();

  const validate = (): DraftErrors => {
    const next: DraftErrors = {};
    if (!objective.trim()) next.objective = "整体目标不能为空";
    else if (objective.trim().length > 4000)
      next.objective = "整体目标不能超过 4000 字符";
    let parsedCriteria: unknown;
    try {
      parsedCriteria = JSON.parse(criteriaText);
      if (!Array.isArray(parsedCriteria) || parsedCriteria.length === 0) {
        next.criteriaText = "完成条件必须是非空 JSON 数组";
      } else if (
        parsedCriteria.length > 16 ||
        parsedCriteria.some(
          (item) =>
            !item ||
            typeof item !== "object" ||
            [
              "requirement",
              "observable_assertion",
              "verification_method",
              "expected_outcome",
            ].some(
              (key) =>
                typeof (item as Record<string, unknown>)[key] !== "string" ||
                !(item as Record<string, string>)[key].trim(),
            ),
        )
      ) {
        next.criteriaText = "每项完成条件必须包含四个非空字段，且最多 16 项";
      }
    } catch (cause) {
      next.criteriaText =
        cause instanceof Error
          ? `JSON 格式错误：${cause.message}`
          : "完成条件 JSON 无效";
    }
    if (objective.length > 4000 && !next.objective)
      next.objective = "整体目标不能超过 4000 字符";
    if (!autonomyBoundary.trim()) next.autonomyBoundary = "自主边界不能为空";
    else if (autonomyBoundary.trim().length > 4000)
      next.autonomyBoundary = "自主边界不能超过 4000 字符";
    for (const [field, value] of [
      ["mustPreserve", mustPreserve],
      ["mustNotDo", mustNotDo],
    ] as const) {
      const items = value
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);
      if (items.length > 32 || items.some((item) => item.length > 1000))
        next[field] = "每类约束最多 32 项，单项不超过 1000 字符";
    }
    return next;
  };

  const focusFirstError = (next: DraftErrors) => {
    const target = next.objective
      ? objectiveRef
      : next.criteriaText
      ? criteriaRef
      : next.mustPreserve
      ? preserveRef
      : next.mustNotDo
      ? notDoRef
      : next.autonomyBoundary
      ? autonomyRef
      : null;
    target?.current?.focus();
  };

  const formatCriteria = () => {
    try {
      setCriteriaText(JSON.stringify(JSON.parse(criteriaText), null, 2));
      setErrors((current) => ({ ...current, criteriaText: undefined }));
    } catch (cause) {
      setErrors((current) => ({
        ...current,
        criteriaText:
          cause instanceof Error
            ? `JSON 格式错误：${cause.message}`
            : "完成条件 JSON 无效",
      }));
    }
  };

  const closeCard = () => {
    if (hasChanges && !window.confirm("修改尚未确认，返回后将丢失，是否继续？"))
      return;
    onComplete?.();
  };

  const submit = async () => {
    if (!onConfirmGoalProposal) {
      setErrors({ form: "Goal 创建入口不可用" });
      return;
    }
    const nextErrors = validate();
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      setDetailsOpen(true);
      focusFirstError(nextErrors);
      return;
    }
    const criteria = JSON.parse(criteriaText) as ChatGoalCompletionCriterion[];
    setSubmitting(true);
    setSubmitted(false);
    setErrors({});
    try {
      const created = await onConfirmGoalProposal({
        card_type: "goal_proposal",
        objective: objective.trim(),
        completion_criteria: criteria,
        constraints: {
          must_preserve: mustPreserve
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          must_not_do: mustNotDo
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
        },
        autonomy_boundary: autonomyBoundary.trim(),
      });
      setSubmitted(true);
      window.setTimeout(() => {
        emit({
          type: "handleSubmit",
          data: {
            query: "开始执行已确认的 Goal",
            fileList: [],
            biz_params: {
              mode: "normal",
              goal_id: created.goal_id,
            },
          },
        });
        onComplete?.();
      }, 700);
    } catch (cause) {
      setErrors({
        form: cause instanceof Error ? cause.message : "Goal 创建失败",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      className={`${styles.planReviewCard} ${styles.goalProposalCard}`}
      aria-label="Goal Contract Draft"
    >
      <header className={styles.reviewHeader}>
        <div className={styles.reviewHeading}>
          <Crosshair aria-hidden="true" size={20} className={styles.goalIcon} />
          <div>
            <strong>Goal Contract Draft</strong>
            <p className={styles.reviewStatus}>
              {submitted
                ? "Goal 已确认，正在开始执行"
                : hasChanges
                ? "未确认修改"
                : "确认后开始执行"}
            </p>
          </div>
        </div>
        <span className={styles.goalDraftBadge}>{criteriaCount} 项条件</span>
      </header>
      <div className={styles.goalSummary}>
        <div className={styles.goalSummaryTitle}>执行摘要</div>
        <p>
          {summaryObjective.length > 150
            ? `${summaryObjective.slice(0, 150)}…`
            : summaryObjective}
        </p>
        <div className={styles.goalSummaryStats}>
          <span>{criteriaCount} 项完成条件</span>
          <span>
            必须保留 {preserveCount ? `${preserveCount} 条` : "未设置"}
          </span>
          <span>禁止操作 {notDoCount ? `${notDoCount} 条` : "未设置"}</span>
          <span>自主边界 {autonomyBoundary.trim() ? "已定义" : "未设置"}</span>
        </div>
      </div>
      <button
        type="button"
        className={styles.goalDetailToggle}
        aria-expanded={detailsOpen}
        aria-controls={detailsId}
        onClick={() => setDetailsOpen((open) => !open)}
        disabled={submitting || submitted}
      >
        {detailsOpen ? "收起详情" : "展开详情"}
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      {detailsOpen ? (
        <div
          id={detailsId}
          role="region"
          aria-label="合同详情"
          className={styles.goalDetails}
        >
          <p className={styles.goalDraftNotice}>
            修改仅在当前页面保留，确认后才会创建 Goal。
          </p>
          <div className={styles.goalField}>
            <label htmlFor="goal-proposal-objective">
              整体目标 <span>（{objective.length} / 4000）</span>
            </label>
            <textarea
              aria-label="整体目标"
              ref={objectiveRef}
              id="goal-proposal-objective"
              value={objective}
              maxLength={4000}
              onChange={(event) => setObjective(event.target.value)}
              rows={2}
              disabled={submitting || submitted}
            />
            {errors.objective ? (
              <p className={styles.goalFieldError}>{errors.objective}</p>
            ) : null}
          </div>
          <div className={styles.goalField}>
            <div className={styles.goalFieldLabel}>
              <label htmlFor="goal-proposal-criteria">完成条件（JSON）</label>
              <button
                type="button"
                className={styles.goalFormatButton}
                onClick={formatCriteria}
                disabled={submitting || submitted}
              >
                格式化 JSON
              </button>
            </div>
            <textarea
              aria-label="完成条件（JSON）"
              ref={criteriaRef}
              id="goal-proposal-criteria"
              value={criteriaText}
              onChange={(event) => setCriteriaText(event.target.value)}
              rows={7}
              disabled={submitting || submitted}
            />
            {errors.criteriaText ? (
              <p className={styles.goalFieldError}>{errors.criteriaText}</p>
            ) : null}
          </div>
          <div className={styles.goalConstraintPair}>
            <div className={styles.goalField}>
              <label htmlFor="goal-proposal-preserve">
                <ShieldCheck size={15} />
                必须保留
              </label>
              <textarea
                ref={preserveRef}
                id="goal-proposal-preserve"
                value={mustPreserve}
                placeholder="暂无约束，每行一项"
                onChange={(event) => setMustPreserve(event.target.value)}
                rows={2}
                disabled={submitting || submitted}
              />
              {errors.mustPreserve ? (
                <p className={styles.goalFieldError}>{errors.mustPreserve}</p>
              ) : null}
            </div>
            <div className={styles.goalField}>
              <label htmlFor="goal-proposal-not-do">
                <Ban size={15} />
                禁止操作
              </label>
              <textarea
                ref={notDoRef}
                id="goal-proposal-not-do"
                value={mustNotDo}
                placeholder="暂无约束，每行一项"
                onChange={(event) => setMustNotDo(event.target.value)}
                rows={2}
                disabled={submitting || submitted}
              />
              {errors.mustNotDo ? (
                <p className={styles.goalFieldError}>{errors.mustNotDo}</p>
              ) : null}
            </div>
          </div>
          <div className={styles.goalField}>
            <label htmlFor="goal-proposal-autonomy">自主边界</label>
            <textarea
              ref={autonomyRef}
              id="goal-proposal-autonomy"
              value={autonomyBoundary}
              maxLength={4000}
              onChange={(event) => setAutonomyBoundary(event.target.value)}
              rows={2}
              disabled={submitting || submitted}
            />
            {errors.autonomyBoundary ? (
              <p className={styles.goalFieldError}>{errors.autonomyBoundary}</p>
            ) : null}
          </div>
        </div>
      ) : null}
      {Object.keys(errors).length > 0 ? (
        <p role="alert" className={styles.goalAggregateError}>
          {Object.keys(errors).filter((key) => key !== "form").length > 0
            ? `请修正 ${
                Object.keys(errors).filter((key) => key !== "form").length
              } 处问题后再确认`
            : errors.form}
        </p>
      ) : null}
      <footer className={styles.reviewActions}>
        <button
          type="button"
          className={styles.reviewSecondaryButton}
          disabled={submitting || submitted}
          onClick={closeCard}
        >
          返回消息编辑
        </button>
        <button
          type="button"
          className={styles.reviewPrimaryButton}
          disabled={submitting || submitted}
          onClick={() => void submit()}
        >
          {submitted ? "已确认" : submitting ? "创建中…" : "确认并开始执行"}
        </button>
      </footer>
    </section>
  );
}

export function ActivePlanInteractionComposer({
  defaultComposer,
}: {
  defaultComposer: ReactElement;
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
}) {
  const interaction = useContextSelector(ChatAnywhereMessagesContext, (value) =>
    findLatestActivePlanInteractionCard(value.messages || []),
  );
  const [completedInstanceKey, setCompletedInstanceKey] = useState<
    string | null
  >(null);

  if (!interaction) {
    return defaultComposer;
  }

  if (completedInstanceKey === interaction.instanceKey) {
    return defaultComposer;
  }

  if (interaction.type === "goal_proposal") {
    return (
      <GoalProposalCard
        data={interaction.data}
        cardInstanceKey={interaction.instanceKey}
        onComplete={() => setCompletedInstanceKey(interaction.instanceKey)}
      />
    );
  }

  return (
    <PlanClarificationCard
      data={interaction.data}
      cardInstanceKey={interaction.instanceKey}
      onComplete={() => setCompletedInstanceKey(interaction.instanceKey)}
    />
  );
}
