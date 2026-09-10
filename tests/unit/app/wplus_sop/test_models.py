# -*- coding: utf-8 -*-
"""Contract tests for the W+ SOP structured interaction models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from swe.app.wplus_sop.models import (
    CumulativePreview,
    ConfirmedStageSnapshot,
    EventKind,
    FinalSopResult,
    MemoryCandidate,
    MemoryWriteBatchResultPayload,
    MemoryWriteReceipt,
    OwnershipTuple,
    Question,
    QuestionBatch,
    QuestionOption,
    QuestionType,
    ResultObjectList,
    SessionProjection,
    SessionState,
    Stage,
    StageProposalPayload,
    StageQueue,
    StageQueueConfirmedPayload,
    StageReport,
    StageReportArtifact,
    StageReportGeneratedPayload,
    StageReportValidationEvidence,
    StructuredInteractionEnvelope,
    TrialExecutionCompletedPayload,
    assert_legal_transition,
)


def _stages() -> list[Stage]:
    return [
        Stage(stage_id="stage_discovery", name="需求确认"),
        Stage(stage_id="stage_delivery", name="交付校验"),
    ]


def test_stage_proposal_requires_two_to_four_stable_unique_stages() -> None:
    proposal = StageProposalPayload(stages=_stages())
    envelope = StructuredInteractionEnvelope(
        event_id="evt_1",
        sop_session_id="sop_1",
        chat_id="chat_1",
        revision=1,
        round=0,
        state_version=2,
        kind=EventKind.STAGE_PROPOSAL,
        payload=proposal,
    )

    assert envelope.session_id == "sop_1"
    assert [stage.stage_id for stage in proposal.stages] == [
        "stage_discovery",
        "stage_delivery",
    ]

    with pytest.raises(ValidationError):
        StageQueue(stages=[Stage(stage_id="only", name="只有一个")])

    with pytest.raises(ValidationError):
        StageQueue(
            stages=[
                Stage(stage_id="same", name="环节一"),
                Stage(stage_id="same", name="环节二"),
            ],
        )

    with pytest.raises(ValidationError):
        StageQueue(
            stages=[
                Stage(stage_id="one", name="重复"),
                Stage(stage_id="two", name="重复"),
            ],
        )


def test_confirmed_stage_queue_accepts_five_stages() -> None:
    stages = [
        Stage(stage_id=f"stage-{index}", name=f"环节 {index}")
        for index in range(1, 6)
    ]

    persisted = StageQueue(stages=stages)
    confirmed = StageQueueConfirmedPayload(stages=stages)

    assert len(persisted.stages) == 5
    assert len(confirmed.stages) == 5
    assert "maxItems" not in StageQueue.model_json_schema()["properties"][
        "stages"
    ]


def test_confirmed_stage_queue_preserves_a_large_manual_queue() -> None:
    confirmed = StageQueueConfirmedPayload(
        stages=[
            Stage(stage_id=f"stage-{index}", name=f"环节 {index}")
            for index in range(1, 51)
        ],
    )

    assert [stage.stage_id for stage in confirmed.stages] == [
        f"stage-{index}" for index in range(1, 51)
    ]


def test_agent_stage_proposal_rejects_five_candidates() -> None:
    stages = [
        Stage(stage_id=f"stage-{index}", name=f"候选环节 {index}")
        for index in range(1, 6)
    ]

    with pytest.raises(ValidationError):
        StageProposalPayload(stages=stages)

    stages_schema = StageProposalPayload.model_json_schema()["properties"][
        "stages"
    ]
    assert stages_schema["minItems"] == 2
    assert stages_schema["maxItems"] == 4


def test_question_option_serializes_custom_input_requirement() -> None:
    ordinary = QuestionOption(option_id="fixed", label="固定选项")
    custom = QuestionOption(
        option_id="other",
        label="其他",
        requires_custom_input=True,
    )

    assert ordinary.model_dump(mode="json")["requires_custom_input"] is False
    assert custom.model_dump(mode="json")["requires_custom_input"] is True
    description = QuestionOption.model_json_schema()["properties"][
        "requires_custom_input"
    ]["description"]
    assert "custom" in description.casefold()


def test_question_batch_is_atomic_and_uses_stable_option_ids() -> None:
    batch = QuestionBatch(
        batch_id="batch_1",
        stage_id="stage_discovery",
        questions=[
            Question(
                question_id="q_channel",
                prompt="主要入口是什么？",
                type=QuestionType.SINGLE_SELECT,
                options=[
                    QuestionOption(option_id="chat", label="Chat"),
                    QuestionOption(option_id="api", label="API"),
                ],
            ),
            Question(
                question_id="q_note",
                prompt="还有哪些约束？",
                type=QuestionType.FREE_TEXT,
            ),
        ],
    )

    assert len(batch.questions) == 2

    with pytest.raises(ValidationError):
        Question(
            question_id="q_bad",
            prompt="请选择",
            type=QuestionType.MULTI_SELECT,
            options=[],
        )

    with pytest.raises(ValidationError):
        Question(
            question_id="q_bad_free",
            prompt="请说明",
            type=QuestionType.FREE_TEXT,
            options=[QuestionOption(option_id="unexpected", label="不应存在")],
        )


def test_object_list_results_preserve_nested_objects() -> None:
    result = ResultObjectList(
        list_id="trial_rows",
        label="预跑结果",
        rows=[
            {
                "name": "父项",
                "children": [
                    {"name": "子项", "metrics": {"count": 3, "ok": True}},
                ],
            },
        ],
    )

    dumped = result.model_dump(mode="json")
    assert dumped["rows"][0]["children"][0]["metrics"] == {
        "count": 3,
        "ok": True,
    }


def test_trial_summary_rejects_known_raw_customer_payload_keys() -> None:
    with pytest.raises(ValidationError, match="raw_response"):
        TrialExecutionCompletedPayload(
            run_id="run_1",
            summary="完成",
            result_lists=[
                ResultObjectList(
                    list_id="rows",
                    label="结果",
                    rows=[{"raw_response": {"customer_id": "secret"}}],
                ),
            ],
        )


def test_trial_completion_accepts_sanitized_fact_snapshot() -> None:
    payload = TrialExecutionCompletedPayload(
        run_id="run_1",
        summary="预跑完成",
        confirmed_facts=["统计范围为未来 30 天"],
        unknowns=["是否排除已冻结账户"],
    )

    assert payload.confirmed_facts == ["统计范围为未来 30 天"]
    assert payload.unknowns == ["是否排除已冻结账户"]


def test_trial_completion_rejects_contact_values_in_context_snapshot() -> None:
    with pytest.raises(ValidationError, match="contact values"):
        TrialExecutionCompletedPayload(
            run_id="run_1",
            summary="预跑完成",
            confirmed_facts=["联系人为 13812345678"],
        )


def test_memory_candidate_exposes_fixed_target_and_write_receipt() -> None:
    candidate = MemoryCandidate(
        candidate_id="candidate-1",
        summary="保留复核口径",
        memory_type="common_wplus_knowledge",
        value={"rule": "优先复核高风险分组"},
        evidence="用户在最终确认时明确认可该口径。",
        target_scope="common",
        target_file="memory/common-wplus-knowledge.jsonl",
        status="approved",
        write_receipt=MemoryWriteReceipt(
            memory_id="wplus-sop/sop-1/candidate-1",
            target_scope="common",
            target_file="memory/common-wplus-knowledge.jsonl",
            written_at="2026-08-04T10:00:00Z",
            reused_existing=False,
            store_result="appended",
        ),
    )

    assert candidate.memory_type == "common_wplus_knowledge"
    assert candidate.target_scope == "common"
    assert candidate.target_file == "memory/common-wplus-knowledge.jsonl"
    assert candidate.write_receipt.memory_id.endswith("candidate-1")


def test_final_sop_result_requires_four_static_tool_artifacts() -> None:
    result = FinalSopResult(
        sop_spec={"name": "SOP"},
        readable_sop="# SOP",
        html="<h1>SOP</h1>",
        example_result_html="<section>示例</section>",
        artifacts=[
            {
                "artifact_id": "sop_spec",
                "name": "sop_spec.json",
                "static_file_name": "sop_spec.json",
                "static_url": "http://localhost/static/tenant/agent/sop_spec.json",
                "sha256": "a" * 64,
                "copied_by": "copy_file_to_static",
            },
            {
                "artifact_id": "sop_render_md",
                "name": "sop_render.md",
                "static_file_name": "sop_render.md",
                "static_url": "http://localhost/static/tenant/agent/sop_render.md",
                "sha256": "b" * 64,
                "copied_by": "copy_file_to_static",
            },
            {
                "artifact_id": "sop_render_html",
                "name": "sop_render.html",
                "static_file_name": "sop_render.html",
                "static_url": "http://localhost/static/tenant/agent/sop_render.html",
                "sha256": "c" * 64,
                "copied_by": "copy_file_to_static",
            },
            {
                "artifact_id": "example_result_html",
                "name": "example_result.html",
                "static_file_name": "example_result.html",
                "static_url": (
                    "http://localhost/static/tenant/agent/example_result.html"
                ),
                "sha256": "d" * 64,
                "copied_by": "copy_file_to_static",
            },
        ],
        validation={
            "schema_validator": "scripts/validate_sop.py",
            "schema_exit_code": 0,
            "renderers": ["scripts/render_md.py", "scripts/render_sop.py"],
        },
    )

    assert len(result.artifacts) == 4
    assert result.validation.schema_exit_code == 0

    with pytest.raises(ValidationError, match="four required artifacts"):
        FinalSopResult(
            sop_spec={"name": "SOP"},
            readable_sop="# SOP",
            html="<h1>SOP</h1>",
            example_result_html="<section>示例</section>",
            artifacts=result.artifacts[:3],
            validation=result.validation,
        )


def test_memory_candidate_rejects_approval_without_store_receipt() -> None:
    with pytest.raises(ValidationError, match="approved memory candidates require"):
        MemoryCandidate(
            candidate_id="candidate-1",
            summary="Approved reusable rule",
            memory_type="common_wplus_knowledge",
            value={"rule": "Keep the confirmed review rule"},
            evidence="The user explicitly approved this reusable rule.",
            target_scope="common",
            target_file="memory/common-wplus-knowledge.jsonl",
            status="approved",
        )


def test_memory_candidate_rejects_failed_status_without_reason() -> None:
    with pytest.raises(
        ValidationError,
        match="failed memory candidates require a failure reason",
    ):
        MemoryCandidate(
            candidate_id="candidate-1",
            summary="Reusable rule could not be persisted",
            value={"rule": "Keep the confirmed review rule"},
            status="failed",
        )


def test_memory_candidate_content_validation_precedes_target_and_status() -> None:
    with pytest.raises(ValidationError, match="contact values"):
        MemoryCandidate(
            candidate_id="candidate-1",
            summary="Save this contact: 13812345678",
            value={"rule": "Keep the confirmed review rule"},
            target_scope="common",
            status="failed",
        )


def test_memory_candidate_target_validation_precedes_failure_status() -> None:
    with pytest.raises(
        ValidationError,
        match="memory candidate target fields must coexist",
    ):
        MemoryCandidate(
            candidate_id="candidate-1",
            summary="Reusable rule could not be persisted",
            value={"rule": "Keep the confirmed review rule"},
            target_scope="common",
            status="failed",
        )


def test_memory_receipt_rejects_legacy_target_and_result_values() -> None:
    with pytest.raises(ValidationError):
        MemoryWriteReceipt(
            memory_id="legacy-memory",
            target_scope="agent",
            target_file="MEMORY.md",
            store_result="legacy",
        )


def test_memory_candidate_rejects_sensitive_unsanitized_content() -> None:
    with pytest.raises(ValidationError, match="contact values"):
        MemoryCandidate(
            candidate_id="candidate-1",
            summary="保存联系人",
            value={"note": "联系 13812345678"},
        )


def test_memory_batch_result_requires_unique_complete_outcome_fields() -> None:
    with pytest.raises(ValidationError, match="unique candidates"):
        MemoryWriteBatchResultPayload.model_validate(
            {
                "results": [
                    {
                        "candidate_id": "candidate-1",
                        "status": "failed",
                        "error_code": "store_failed",
                        "summary": "disk unavailable",
                        "script": "scripts/memory_store.py",
                    },
                    {
                        "candidate_id": "candidate-1",
                        "status": "failed",
                        "error_code": "store_failed",
                        "summary": "disk unavailable",
                        "script": "scripts/memory_store.py",
                    },
                ],
            },
        )

    with pytest.raises(ValidationError, match="successful memory result"):
        MemoryWriteBatchResultPayload.model_validate(
            {
                "results": [
                    {
                        "candidate_id": "candidate-1",
                        "status": "succeeded",
                        "target_scope": "common",
                        "target_file": "memory/common-wplus-knowledge.jsonl",
                        "script": "scripts/memory_store.py",
                    },
                ],
            },
        )


@pytest.mark.parametrize(
    "field",
    [
        "CustomerEmail",
        "phone-number",
        "customer_identifier",
        "customers",
        "acctNo",
        "orderId",
        "contact",
        "shippingAddress",
        "objectId",
        "accessToken",
    ],
)
def test_trial_summary_rejects_normalized_sensitive_aliases_recursively(
    field: str,
) -> None:
    with pytest.raises(ValidationError, match=field):
        ResultObjectList(
            list_id="rows",
            label="结果",
            rows=[{"groups": [{"details": [{field: "secret"}]}]}],
        )


def test_trial_summary_allows_ordinary_aggregate_fields() -> None:
    result = ResultObjectList(
        list_id="summary",
        label="汇总",
        rows=[
            {
                "customer_count": 18,
                "order_total": 42,
                "account_status_distribution": {
                    "active": 12,
                    "paused": 6,
                },
                "email_delivery_rate": 0.97,
            },
        ],
    )

    assert result.rows[0]["customer_count"] == 18
    assert result.rows[0]["order_total"] == 42


def test_trial_summary_rejects_sensitive_column_aliases() -> None:
    with pytest.raises(ValidationError, match="CustomerEmail"):
        ResultObjectList(
            list_id="summary",
            label="汇总",
            columns=[
                {
                    "field": "CustomerEmail",
                    "label": "邮箱",
                    "type": "string",
                },
            ],
            rows=[],
        )


@pytest.mark.parametrize(
    "value",
    [
        "person@example.com",
        "13812345678",
        "+1 202 555 0147",
        "(415) 555-2671",
        "010-12345678",
    ],
)
def test_trial_summary_rejects_sensitive_contact_values_recursively(
    value: str,
) -> None:
    with pytest.raises(ValidationError, match="sensitive contact value"):
        ResultObjectList(
            list_id="summary",
            label="汇总",
            rows=[{"groups": [{"display_value": value}]}],
        )


def test_trial_summary_does_not_treat_dates_or_plain_numbers_as_phone_data() -> None:
    result = ResultObjectList(
        list_id="summary",
        label="汇总",
        rows=[
            {
                "period": "2026-07-29",
                "period_note": "Report date 2026-07-29",
                "reference": "12345678",
                "amount": 12345678,
            },
        ],
    )

    assert result.rows[0]["period"] == "2026-07-29"


def test_paused_session_holds_slot_without_locking_ordinary_chat_input() -> None:
    ownership = OwnershipTuple(
        tenant_id="tenant_1",
        source_id="console",
        user_id="user_1",
        agent_id="agent_1",
        chat_id="chat_1",
        logical_chat_session_id="logical_1",
    )
    active = SessionProjection(
        sop_session_id="sop_active",
        ownership=ownership,
        skill_snapshot_id="sha256:miner-v1",
        state=SessionState.AWAITING_ANSWER,
        state_version=1,
        title="Active",
    )
    paused = SessionProjection(
        sop_session_id="sop_paused",
        ownership=ownership,
        skill_snapshot_id="sha256:miner-v1",
        state=SessionState.PAUSED,
        state_version=1,
        title="Paused",
        resume_state=SessionState.AWAITING_ANSWER,
    )

    assert active.holds_chat_slot is True
    assert active.locks_chat_input is True
    assert paused.holds_chat_slot is True
    assert paused.locks_chat_input is False


def test_event_kind_must_match_typed_payload() -> None:
    with pytest.raises(ValidationError, match="payload"):
        StructuredInteractionEnvelope(
            event_id="evt_1",
            sop_session_id="sop_1",
            chat_id="chat_1",
            revision=1,
            round=0,
            state_version=2,
            kind=EventKind.QUESTION_BATCH,
            payload=StageProposalPayload(stages=_stages()),
        )


def test_state_machine_accepts_main_path_and_rejects_skips() -> None:
    assert_legal_transition(
        SessionState.GENERATING_STAGE_PROPOSAL,
        SessionState.AWAITING_QUEUE_CONFIRMATION,
    )
    assert_legal_transition(
        SessionState.AWAITING_STAGE_CONFIRMATION,
        SessionState.FINALIZING_OUTPUTS,
    )
    assert_legal_transition(
        SessionState.AWAITING_STAGE_CONFIRMATION,
        SessionState.GENERATING_TRIAL,
    )
    assert_legal_transition(
        SessionState.FINALIZING_OUTPUTS,
        SessionState.OUTPUT_REVIEW,
    )
    assert_legal_transition(
        SessionState.OUTPUT_REVIEW,
        SessionState.MEMORY_REVIEW,
    )
    assert_legal_transition(
        SessionState.OUTPUT_REVIEW,
        SessionState.COMPLETED,
    )

    with pytest.raises(ValueError, match="Illegal W\\+ SOP state transition"):
        assert_legal_transition(
            SessionState.GENERATING_STAGE_PROPOSAL,
            SessionState.AWAITING_ANSWER,
        )

    with pytest.raises(ValueError, match="Illegal W\\+ SOP state transition"):
        assert_legal_transition(
            SessionState.COMPLETED,
            SessionState.GENERATING_TRIAL,
        )


@pytest.mark.parametrize(
    "state",
    [
        SessionState.GENERATING_STAGE_PROPOSAL,
        SessionState.GENERATING_QUESTIONS,
        SessionState.GENERATING_TRIAL,
        SessionState.EXECUTING_TRIAL,
        SessionState.FINALIZING_OUTPUTS,
    ],
)
def test_generating_states_allow_progress_events_without_state_change(
    state: SessionState,
) -> None:
    assert_legal_transition(state, state)


def test_pending_exit_may_complete_at_the_natural_run_boundary() -> None:
    assert_legal_transition(
        SessionState.PENDING_EXIT,
        SessionState.COMPLETED,
    )


def _stage_report_artifacts() -> list[StageReportArtifact]:
    return [
        StageReportArtifact(
            artifact_id="stage_sop_json",
            name="stage_sop.json",
            static_file_name="json.file",
            static_url="https://static.example/stage_sop.json",
            sha256="a" * 64,
            copied_by="copy_file_to_static",
        ),
        StageReportArtifact(
            artifact_id="stage_sop_md",
            name="stage_sop.md",
            static_file_name="md.file",
            static_url="https://static.example/stage_sop.md",
            sha256="b" * 64,
            copied_by="copy_file_to_static",
        ),
        StageReportArtifact(
            artifact_id="stage_sop_html",
            name="stage_sop.html",
            static_file_name="html.file",
            static_url="https://static.example/stage_sop.html",
            sha256="c" * 64,
            copied_by="copy_file_to_static",
        ),
    ]


def _validation_evidence() -> StageReportValidationEvidence:
    return StageReportValidationEvidence(
        schema_validator="scripts/validate_stage_sop.py",
        schema_exit_code=0,
        renderers=("scripts/render_stage_md.py", "scripts/render_stage_sop.py"),
    )


def _stage_report(
    stage_id: str,
    report_no: int,
    *,
    revision: int = 0,
) -> StageReport:
    return StageReport(
        stage_id=stage_id,
        report_no=report_no,
        revision=revision,
        artifacts=_stage_report_artifacts(),
        validation=_validation_evidence(),
    )


def _snapshot(
    stage_id: str,
    report_no: int,
    *,
    revision: int = 0,
) -> ConfirmedStageSnapshot:
    return ConfirmedStageSnapshot(
        stage_id=stage_id,
        report_no=report_no,
        revision=revision,
        artifact_sha256="d" * 64,
    )


def _incremental_projection(
    stages: list[Stage],
    *,
    reports: list[StageReport] | None = None,
    snapshots: list[ConfirmedStageSnapshot] | None = None,
    preview: CumulativePreview | None = None,
) -> SessionProjection:
    return SessionProjection(
        sop_session_id="sop_1",
        ownership=OwnershipTuple(
            tenant_id="tenant_1",
            source_id="console",
            user_id="user_1",
            agent_id="agent_1",
            chat_id="chat_1",
            logical_chat_session_id="logical_1",
        ),
        skill_snapshot_id="sha256:miner-v1",
        state=SessionState.AWAITING_STAGE_CONFIRMATION,
        state_version=1,
        title="t",
        stages=stages,
        stage_reports=reports or [],
        confirmed_snapshots=snapshots or [],
        cumulative_preview=preview,
    )


def test_stage_report_requires_three_artifacts() -> None:
    with pytest.raises(ValidationError):
        StageReport(
            stage_id="stage_1",
            report_no=1,
            artifacts=_stage_report_artifacts()[:2],
            validation=_validation_evidence(),
        )


def test_stage_report_rejects_non_newer_superseded_by() -> None:
    with pytest.raises(ValidationError):
        StageReport(
            stage_id="stage_1",
            report_no=2,
            superseded_by=2,
            artifacts=_stage_report_artifacts(),
            validation=_validation_evidence(),
        )


def test_confirmed_snapshots_must_follow_stage_queue_prefix() -> None:
    stages = [
        Stage(stage_id="stage_1", name="一"),
        Stage(stage_id="stage_2", name="二"),
    ]
    with pytest.raises(ValidationError):
        _incremental_projection(
            stages,
            reports=[_stage_report("stage_2", 1)],
            snapshots=[_snapshot("stage_2", 1)],
        )


def test_confirmed_snapshot_must_reference_an_existing_report() -> None:
    stages = [
        Stage(stage_id="stage_1", name="一"),
        Stage(stage_id="stage_2", name="二"),
    ]
    with pytest.raises(ValidationError):
        _incremental_projection(
            stages,
            reports=[_stage_report("stage_1", 1)],
            snapshots=[_snapshot("stage_1", 2)],
        )


def test_cumulative_preview_requires_matching_confirmed_snapshots() -> None:
    stages = [
        Stage(stage_id="stage_1", name="一"),
        Stage(stage_id="stage_2", name="二"),
    ]
    preview = CumulativePreview(
        preview_version=1,
        stage_order=["stage_1"],
        snapshots=[_snapshot("stage_1", 1)],
        artifacts=_stage_report_artifacts(),
    )
    with pytest.raises(ValidationError):
        _incremental_projection(
            stages,
            reports=[_stage_report("stage_1", 1)],
            snapshots=[],
            preview=preview,
        )


def test_consistent_incremental_projection_roundtrips() -> None:
    stages = [
        Stage(stage_id="stage_1", name="一"),
        Stage(stage_id="stage_2", name="二"),
    ]
    snapshots = [_snapshot("stage_1", 1)]
    preview = CumulativePreview(
        preview_version=1,
        stage_order=["stage_1"],
        snapshots=snapshots,
        artifacts=_stage_report_artifacts(),
        rendered_sha256={"stage_sop_json": "a" * 64},
    )
    projection = _incremental_projection(
        stages,
        reports=[_stage_report("stage_1", 1)],
        snapshots=snapshots,
        preview=preview,
    )
    restored = SessionProjection.model_validate(
        projection.model_dump(mode="json"),
    )
    assert restored.stage_reports == projection.stage_reports
    assert restored.confirmed_snapshots == snapshots
    assert restored.cumulative_preview == preview


def test_legacy_projection_defaults_incremental_fields() -> None:
    raw = {
        "sop_session_id": "sop_1",
        "ownership": {
            "tenant_id": "tenant_1",
            "source_id": "console",
            "user_id": "user_1",
            "agent_id": "agent_1",
            "chat_id": "chat_1",
            "logical_chat_session_id": "logical_1",
        },
        "skill_snapshot_id": "sha256:miner-v1",
        "state": "AwaitingStageConfirmation",
        "state_version": 1,
        "title": "t",
        "stages": [
            {"stage_id": "stage_1", "name": "一"},
            {"stage_id": "stage_2", "name": "二"},
        ],
    }
    projection = SessionProjection.model_validate(raw)
    assert projection.stage_reports == []
    assert projection.confirmed_snapshots == []
    assert projection.cumulative_preview is None


def test_stage_report_generated_envelope_parses_typed_payload() -> None:
    envelope = StructuredInteractionEnvelope(
        event_id="evt_report_1",
        sop_session_id="sop_1",
        chat_id="chat_1",
        revision=1,
        round=1,
        state_version=3,
        kind=EventKind.STAGE_REPORT_GENERATED,
        payload=StageReportGeneratedPayload(report=_stage_report("stage_1", 1)),
    )
    parsed = StructuredInteractionEnvelope.model_validate(
        envelope.model_dump(mode="json", by_alias=True),
    )
    assert parsed.kind is EventKind.STAGE_REPORT_GENERATED
    assert parsed.payload.report.report_no == 1
    assert len(parsed.payload.report.artifacts) == 3


def test_stage_report_transitions_are_legal() -> None:
    assert_legal_transition(
        SessionState.EXECUTING_TRIAL,
        SessionState.GENERATING_STAGE_REPORT,
    )
    assert_legal_transition(
        SessionState.GENERATING_STAGE_REPORT,
        SessionState.AWAITING_STAGE_CONFIRMATION,
    )
    assert_legal_transition(
        SessionState.AWAITING_STAGE_CONFIRMATION,
        SessionState.REFRESHING_CUMULATIVE,
    )
    assert_legal_transition(
        SessionState.REFRESHING_CUMULATIVE,
        SessionState.GENERATING_QUESTIONS,
    )
    assert_legal_transition(
        SessionState.REFRESHING_CUMULATIVE,
        SessionState.FINALIZING_OUTPUTS,
    )
    with pytest.raises(ValueError):
        assert_legal_transition(
            SessionState.REFRESHING_CUMULATIVE,
            SessionState.AWAITING_ANSWER,
        )
