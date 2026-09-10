export type WPlusSopState =
  | "GeneratingStageProposal"
  | "AwaitingQueueConfirmation"
  | "GeneratingQuestions"
  | "AwaitingAnswer"
  | "GeneratingTrial"
  | "ExecutingTrial"
  | "AwaitingTrialFeedback"
  | "AwaitingStageConfirmation"
  | "GeneratingStageReport"
  | "RefreshingCumulative"
  | "FinalizingOutputs"
  | "OutputReview"
  | "MemoryReview"
  | "WritingMemory"
  | "PendingExit"
  | "Paused"
  | "RecoverableFailure"
  | "Completed"
  | "Terminated";

export type WPlusSopStageStatus =
  | "confirmed"
  | "current"
  | "pending"
  | "invalidated";

export interface WPlusSopStage {
  stage_id: string;
  title: string;
  description?: string | null;
  status: WPlusSopStageStatus;
}

export interface WPlusSopQuestionOption {
  option_id: string;
  label: string;
  description?: string | null;
  requires_custom_input?: boolean;
}

export interface WPlusSopQuestion {
  question_id: string;
  kind: "single_select" | "multi_select" | "free_text";
  prompt: string;
  help_text?: string | null;
  required?: boolean;
  options?: WPlusSopQuestionOption[];
}

export interface WPlusSopQuestionBatch {
  batch_id: string;
  stage_id: string;
  questions: WPlusSopQuestion[];
}

export interface WPlusSopCustomAnswerValue {
  selected_option_ids: string[];
  text?: string;
}

export type WPlusSopAnswerValue = string | string[] | WPlusSopCustomAnswerValue;

export interface WPlusSopRunStep {
  step_id: string;
  title: string;
  capability?: string | null;
  status: "pending" | "running" | "completed" | "failed" | "blocked";
  summary?: string | null;
  elapsed_ms?: number | null;
}

export interface WPlusSopResultColumn {
  field: string;
  label: string;
  type?: string | null;
}

export interface WPlusSopSchemaNode {
  name?: string;
  type: string;
  description?: string | null;
  properties?: Record<string, WPlusSopSchemaNode>;
  items?: WPlusSopSchemaNode;
}

export interface WPlusSopCapabilityEvidence {
  capability_id: string;
  name: string;
  verification_status: "verified" | "partially_verified" | "unverified";
  output_contract_status?: "verified" | "partially_verified" | "unverified";
  output_schema?: WPlusSopSchemaNode | null;
}

export interface WPlusSopTrial {
  run_id: string;
  attempt_id?: string | null;
  rerun_of_run_id?: string | null;
  status:
    | "planning"
    | "running"
    | "completed"
    | "failed"
    | "approval_pending"
    | "approval_denied"
    | "approval_timeout"
    | "permission_limited";
  started_at?: string | null;
  completed_at?: string | null;
  elapsed_ms?: number | null;
  steps: WPlusSopRunStep[];
  summary?: string | null;
  warnings?: string[];
  result_columns?: WPlusSopResultColumn[];
  result_rows?: Record<string, unknown>[];
}

export interface WPlusSopArtifact {
  artifact_id: string;
  name: string;
  format: "json" | "markdown" | "html" | string;
  status: "validated" | "failed";
  download_url?: string | null;
  description?: string | null;
  sha256?: string | null;
  copied_by?: "copy_file_to_static" | null;
}

export interface WPlusSopStageReport {
  stage_id: string;
  report_no: number;
  revision: number;
  superseded_by?: number | null;
  created_at: string;
  artifacts: WPlusSopArtifact[];
}

export interface WPlusSopCumulativeSnapshot {
  stage_id: string;
  report_no: number;
  revision: number;
  artifact_sha256: string;
  confirmed_at: string;
}

export interface WPlusSopCumulativePreview {
  preview_version: number;
  stage_order: string[];
  snapshots: WPlusSopCumulativeSnapshot[];
  artifacts: WPlusSopArtifact[];
  rendered_sha256: Record<string, string>;
}

export interface WPlusSopStageArtifactIdentity {
  stageId: string;
  revision: number;
  reportNo: number;
  artifactId: string;
}

export interface WPlusSopCumulativeArtifactIdentity {
  previewVersion: number;
  artifactId: string;
}

export interface WPlusSopMemoryCandidate {
  candidate_id: string;
  title: string;
  description?: string | null;
  memory_type?:
    | "common_wplus_knowledge"
    | "user_wplus_usage"
    | "sop_case"
    | null;
  content: unknown;
  evidence?: string | null;
  target_scope?: "common" | "user" | "cases" | null;
  target_file?: string | null;
  status: "pending" | "writing" | "approved" | "rejected" | "failed";
  failure_reason?: string | null;
  write_receipt?: WPlusSopMemoryWriteReceipt | null;
  legacy_read_only?: boolean;
}

export interface WPlusSopMemoryWriteReceipt {
  memory_id: string;
  target_scope: "common" | "user" | "cases";
  target_file: string;
  written_at: string;
  reused_existing: boolean;
  store_result: "appended" | "duplicate";
}

export interface WPlusSopResultPreview {
  markdown: string;
  html: string;
  markdown_url?: string | null;
  html_url?: string | null;
  markdown_sha256?: string | null;
  html_sha256?: string | null;
}

export interface WPlusSopFailure {
  code: string;
  message: string;
  retryable: boolean;
  failed_run_id?: string | null;
}

export interface WPlusSopPendingExit {
  requested_action: "pause" | "terminate";
  requested_at: string;
  timed_out?: boolean;
}

export interface WPlusSopRuntimeStatus {
  status: "ready" | "finalizing" | "running" | "stopping";
  runtime_ready: boolean;
  blocking_run_id: string | null;
}

export interface WPlusSopSession {
  session_id: string;
  chat_id: string;
  logical_chat_session_id?: string | null;
  title: string;
  state: WPlusSopState;
  state_version: number;
  revision: number;
  round: number;
  stages: WPlusSopStage[];
  current_stage_id: string | null;
  question_batch?: WPlusSopQuestionBatch | null;
  trial?: WPlusSopTrial | null;
  facts?: string[];
  unknowns?: string[];
  capabilities?: WPlusSopCapabilityEvidence[];
  artifacts?: WPlusSopArtifact[];
  stage_reports?: WPlusSopStageReport[];
  cumulative_preview?: WPlusSopCumulativePreview | null;
  result_preview?: WPlusSopResultPreview | null;
  memory_candidates?: WPlusSopMemoryCandidate[];
  failure?: WPlusSopFailure | null;
  pending_exit?: WPlusSopPendingExit | null;
  resume_state?: WPlusSopState | null;
  runtime_status?: WPlusSopRuntimeStatus;
  updated_at: string;
}

export type WPlusSopCommandType =
  | "confirm_stage_queue"
  | "submit_answers"
  | "submit_trial_feedback"
  | "accept_trial"
  | "confirm_stage"
  | "confirm_outputs"
  | "save_and_exit"
  | "resume"
  | "retry_current_turn"
  | "terminate"
  | "cancel_run_and_pause"
  | "continue_waiting"
  | "revise_answer"
  | "resolve_memory"
  | "skip_memory";

export interface WPlusSopCommandRequest {
  command: WPlusSopCommandType;
  command_request_id: string;
  expected_state_version: number;
  payload?: Record<string, unknown>;
}

export interface WPlusSopCommandReceipt {
  command_request_id: string;
  accepted: boolean;
  session: WPlusSopSession;
  run_id?: string | null;
  attempt_id?: string | null;
}

export interface WPlusSopEntryProposal {
  object: "wplus_sop_entry_proposal";
  status: "completed";
  proposal_id: string;
  mode: "explicit" | "implicit";
  confidence?: number | null;
  chat_id: string;
  session_id: string;
  title: string;
  message: string;
}

export interface WPlusSopEntryRejectReceipt {
  proposal_id: string;
  status: "rejected";
  suppression_token: string;
  original_request: {
    text?: string;
  };
}

export type WPlusSopSafeStreamTraceEntry =
  | {
      entry_id: string;
      kind: "assistant_text";
      text: string;
      status: "running" | "completed" | "failed";
    }
  | {
      entry_id: string;
      kind: "tool";
      tool_name: string;
      server_label?: string;
      status: "running" | "completed" | "failed";
    };

export interface WPlusSopSafeStreamTrace {
  sequence: number;
  summary_text: string;
  truncated: boolean;
  entries?: WPlusSopSafeStreamTraceEntry[];
}

export interface WPlusSopSessionEvent {
  event_id: string;
  session_id: string;
  state_version: number;
  kind: string;
  run_id?: string | null;
  snapshot?: WPlusSopSession | null;
  safe_stream_trace?: WPlusSopSafeStreamTrace | null;
  runtime_status?: WPlusSopRuntimeStatus | null;
}

export interface WPlusSopApiError extends Error {
  status?: number;
  data?: unknown;
}
