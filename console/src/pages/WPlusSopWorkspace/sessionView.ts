import type {
  WPlusSopResultColumn,
  WPlusSopSession,
  WPlusSopSessionEvent,
  WPlusSopStage,
  WPlusSopState,
} from "@/api/types/wplusSop";

export interface StageQueueValidation {
  valid: boolean;
  message: string | null;
}

export interface ResultTableView {
  columns: WPlusSopResultColumn[];
  rows: Record<string, string>[];
}

export type SessionEventDecision =
  | { action: "ignore"; session: WPlusSopSession }
  | { action: "reload"; session: WPlusSopSession }
  | { action: "apply"; session: WPlusSopSession };

export function createCommandRequestId(): string {
  if (
    typeof globalThis.crypto !== "undefined" &&
    typeof globalThis.crypto.randomUUID === "function"
  ) {
    return globalThis.crypto.randomUUID();
  }
  return `cmd_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function validateStageQueue(
  stages: WPlusSopStage[],
): StageQueueValidation {
  if (stages.length < 2) {
    return { valid: false, message: "至少需要 2 个环节。" };
  }

  const ids = new Set<string>();
  const names = new Set<string>();
  for (const stage of stages) {
    const stageId = stage.stage_id.trim();
    const title = stage.title.trim();
    if (!stageId || !title) {
      return { valid: false, message: "每个环节都需要非空名称和稳定 ID。" };
    }
    const normalizedTitle = title.toLocaleLowerCase();
    if (ids.has(stageId) || names.has(normalizedTitle)) {
      return { valid: false, message: "环节名称和 ID 不能重复。" };
    }
    ids.add(stageId);
    names.add(normalizedTitle);
  }
  return { valid: true, message: null };
}

function displayCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function buildResultTable(
  sourceRows: Record<string, unknown>[] = [],
  declaredColumns: WPlusSopResultColumn[] = [],
): ResultTableView {
  const columns =
    declaredColumns.length > 0
      ? declaredColumns
      : Array.from(new Set(sourceRows.flatMap((row) => Object.keys(row))))
          .sort((left, right) => left.localeCompare(right))
          .map((field) => ({ field, label: field }));

  const rows = sourceRows.map((row) =>
    Object.fromEntries(
      columns.map((column) => [column.field, displayCell(row[column.field])]),
    ),
  );

  return { columns, rows };
}

export function applySessionEvent(
  current: WPlusSopSession,
  event: WPlusSopSessionEvent,
): SessionEventDecision {
  if (
    event.session_id !== current.session_id ||
    event.state_version <= current.state_version
  ) {
    return { action: "ignore", session: current };
  }
  if (event.state_version !== current.state_version + 1 || !event.snapshot) {
    return { action: "reload", session: current };
  }
  if (
    event.snapshot.session_id !== current.session_id ||
    event.snapshot.state_version !== event.state_version
  ) {
    return { action: "reload", session: current };
  }
  return { action: "apply", session: event.snapshot };
}

export function getWPlusSopStateLabel(state: WPlusSopState): string {
  const labels: Record<WPlusSopState, string> = {
    GeneratingStageProposal: "正在生成环节",
    AwaitingQueueConfirmation: "等待确认环节",
    GeneratingQuestions: "正在生成问题",
    AwaitingAnswer: "等待回答",
    GeneratingTrial: "正在准备预跑",
    ExecutingTrial: "正在执行预跑",
    AwaitingTrialFeedback: "等待预跑反馈",
    AwaitingStageConfirmation: "等待确认环节",
    GeneratingStageReport: "正在生成环节报告",
    RefreshingCumulative: "正在刷新累计 SOP",
    FinalizingOutputs: "正在生成结果",
    OutputReview: "等待确认结果",
    MemoryReview: "待处理记忆候选",
    WritingMemory: "正在写入获批记忆",
    PendingExit: "正在安全退出",
    Paused: "已暂停",
    RecoverableFailure: "可恢复失败",
    Completed: "已完成",
    Terminated: "已彻底结束",
  };
  return labels[state];
}

export function getSessionStateLabel(session: WPlusSopSession): string {
  return getWPlusSopStateLabel(session.state);
}
