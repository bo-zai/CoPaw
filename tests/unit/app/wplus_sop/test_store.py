# -*- coding: utf-8 -*-
"""Persistence and concurrency tests for the W+ SOP local JSON store."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from swe.app.wplus_sop.models import (
    ChatProjectionOutboxItem,
    CommandReceipt,
    CumulativePreview,
    ConfirmedStageSnapshot,
    EntryDetectionMode,
    EntryProposalStatus,
    EventKind,
    MemoryCandidateStatus,
    OwnershipTuple,
    RunAttempt,
    RunStatus,
    SessionProjection,
    SessionRecord,
    SessionState,
    Stage,
    StageProposalPayload,
    StageQueueConfirmedPayload,
    StageReport,
    StageReportArtifact,
    StageReportGeneratedPayload,
    StageReportValidationEvidence,
    StructuredInteractionEnvelope,
    WPlusEntryProposal,
)
from swe.app.wplus_sop.store import (
    ActiveSessionExistsError,
    StaleStateVersionError,
    WPlusSopStoreError,
    WPlusSopStore,
)


def _ownership(chat_id: str = "chat_1") -> OwnershipTuple:
    return OwnershipTuple(
        tenant_id="tenant_1",
        source_id="console",
        user_id="user_1",
        agent_id="agent_1",
        chat_id=chat_id,
        logical_chat_session_id="logical_1",
    )


def _projection(
    sop_session_id: str = "sop_1",
    *,
    chat_id: str = "chat_1",
) -> SessionProjection:
    return SessionProjection(
        sop_session_id=sop_session_id,
        ownership=_ownership(chat_id),
        skill_snapshot_id="sha256:miner-v1",
        state=SessionState.GENERATING_STAGE_PROPOSAL,
        state_version=1,
        title="客户交付 SOP",
    )


def _entry_receipt(session_id: str = "sop_1") -> CommandReceipt:
    return CommandReceipt(
        command_request_id="cmd_entry_1",
        command="confirm_entry",
        sop_session_id=session_id,
        resulting_state_version=1,
        starts_run=True,
        run_id="run_1",
        attempt_id="attempt_1",
    )


def _stage_event() -> StructuredInteractionEnvelope:
    return StructuredInteractionEnvelope(
        event_id="evt_stage_1",
        sop_session_id="sop_1",
        chat_id="chat_1",
        revision=1,
        round=0,
        state_version=2,
        kind=EventKind.STAGE_PROPOSAL,
        payload=StageProposalPayload(
            stages=[
                Stage(stage_id="one", name="需求确认"),
                Stage(stage_id="two", name="交付校验"),
            ],
        ),
    )


def _entry_proposal() -> WPlusEntryProposal:
    return WPlusEntryProposal(
        proposal_id="proposal_1",
        ownership=_ownership(),
        logical_chat_session_id="logical_1",
        original_request={"content": [{"type": "text", "text": "请梳理 SOP"}]},
        original_request_digest="sha256:original-request",
        detection_mode=EntryDetectionMode.EXPLICIT,
    )


def test_entry_proposal_is_persisted_without_creating_a_session(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    created = store.create_entry_proposal(_entry_proposal())

    reloaded = WPlusSopStore(path)
    assert created.status is EntryProposalStatus.PENDING
    assert reloaded.get_entry_proposal("proposal_1") == created
    assert reloaded.list_sessions() == []


def test_reject_entry_proposal_is_idempotent_and_never_creates_session(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    store.create_entry_proposal(_entry_proposal())
    receipt = CommandReceipt(
        command_request_id="cmd_reject_1",
        command="reject_entry",
        sop_session_id=None,
        resulting_state_version=None,
    )

    first = store.resolve_entry_proposal(
        "proposal_1",
        status=EntryProposalStatus.REJECTED,
        receipt=receipt,
        suppression_token="suppress_once_1",
    )
    duplicate = store.resolve_entry_proposal(
        "proposal_1",
        status=EntryProposalStatus.REJECTED,
        receipt=receipt,
        suppression_token="suppress_once_1",
    )

    assert first.status is EntryProposalStatus.REJECTED
    assert duplicate == first
    assert duplicate.suppression_token == "suppress_once_1"
    assert store.list_sessions() == []


def test_confirm_entry_proposal_returns_same_session_for_duplicate_command(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    store.create_entry_proposal(_entry_proposal())
    receipt = _entry_receipt()

    first = store.confirm_entry_proposal(
        "proposal_1",
        projection=_projection(),
        receipt=receipt,
        run_attempt=RunAttempt(
            run_id="run_1",
            attempt_id="attempt_1",
            command_request_id="cmd_entry_1",
            command="confirm_entry",
            status=RunStatus.CLAIMED,
        ),
    )
    duplicate = store.confirm_entry_proposal(
        "proposal_1",
        projection=_projection("sop_should_not_exist"),
        receipt=_entry_receipt("sop_should_not_exist"),
    )

    assert first.record.projection.sop_session_id == "sop_1"
    assert duplicate.duplicate is True
    assert duplicate.record.projection.sop_session_id == "sop_1"
    assert store.get_entry_proposal("proposal_1").status is (
        EntryProposalStatus.CONFIRMED
    )
    assert store.get_session("sop_should_not_exist") is None


def test_create_reload_and_find_active_session_by_chat(tmp_path: Path) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    created = store.create_session(
        _projection(),
        command_receipt=_entry_receipt(),
        run_attempt=RunAttempt(
            run_id="run_1",
            attempt_id="attempt_1",
            command_request_id="cmd_entry_1",
            command="confirm_entry",
            status=RunStatus.CLAIMED,
        ),
    )

    reloaded = WPlusSopStore(path)
    by_id = reloaded.get_session("sop_1")
    by_chat = reloaded.get_active_by_chat(_ownership())

    assert created.projection.sop_session_id == "sop_1"
    assert by_id is not None
    assert by_id.projection == created.projection
    assert by_chat is not None
    assert by_chat.projection.sop_session_id == "sop_1"
    assert len(by_id.events) == 1


def test_duplicate_entry_command_returns_original_session_and_receipt(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    first = store.create_session(
        _projection(),
        command_receipt=_entry_receipt(),
    )
    duplicate = store.create_session(
        _projection("sop_should_not_exist"),
        command_receipt=_entry_receipt("sop_should_not_exist"),
    )

    assert duplicate.duplicate is True
    assert duplicate.record.projection.sop_session_id == "sop_1"
    assert duplicate.receipt == first.receipt
    assert store.get_session("sop_should_not_exist") is None


def test_global_command_id_cannot_return_a_foreign_owned_session(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    store.create_session(
        _projection("sop_foreign", chat_id="chat_foreign"),
        command_receipt=CommandReceipt(
            command_request_id="cmd_shared",
            command="confirm_entry",
            sop_session_id="sop_foreign",
            resulting_state_version=1,
        ),
    )
    target_ownership = _ownership("chat_target").model_copy(
        update={"user_id": "user_target"},
    )
    target = _projection("sop_target", chat_id="chat_target").model_copy(
        update={"ownership": target_ownership},
    )

    with pytest.raises(WPlusSopStoreError, match="scope"):
        store.create_session(
            target,
            command_receipt=CommandReceipt(
                command_request_id="cmd_shared",
                command="confirm_entry",
                sop_session_id="sop_target",
                resulting_state_version=1,
            ),
        )

    assert store.get_session("sop_target") is None


def test_global_command_id_cannot_resolve_a_different_proposal(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    first = _entry_proposal()
    second_ownership = _ownership("chat_2").model_copy(
        update={
            "user_id": "user_2",
            "logical_chat_session_id": "logical_2",
        },
    )
    second = first.model_copy(
        update={
            "proposal_id": "proposal_2",
            "ownership": second_ownership,
            "logical_chat_session_id": "logical_2",
        },
    )
    store.create_entry_proposal(first)
    store.create_entry_proposal(second)
    receipt = CommandReceipt(
        command_request_id="cmd_shared_reject",
        command="reject_entry",
        sop_session_id=None,
    )
    store.resolve_entry_proposal(
        first.proposal_id,
        status=EntryProposalStatus.REJECTED,
        receipt=receipt,
        suppression_token="suppress_1",
    )

    with pytest.raises(WPlusSopStoreError, match="scope"):
        store.resolve_entry_proposal(
            second.proposal_id,
            status=EntryProposalStatus.REJECTED,
            receipt=receipt,
            suppression_token="suppress_2",
        )

    assert store.get_entry_proposal(second.proposal_id).status is (
        EntryProposalStatus.PENDING
    )


def test_rejected_proposal_suppression_can_be_consumed_only_once(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    proposal = store.create_entry_proposal(_entry_proposal())
    rejected = store.resolve_entry_proposal(
        proposal.proposal_id,
        status=EntryProposalStatus.REJECTED,
        receipt=CommandReceipt(
            command_request_id="cmd_reject_once",
            command="reject_entry",
            sop_session_id=None,
        ),
        suppression_token="suppress_once",
    )

    wrong_owner = rejected.ownership.model_copy(update={"user_id": "other"})
    claim_id = store.claim_suppression(
        rejected.proposal_id,
        suppression_token="suppress_once",
        original_request_digest=rejected.original_request_digest,
        ownership=rejected.ownership,
    )
    assert claim_id is not None
    assert (
        store.claim_suppression(
            rejected.proposal_id,
            suppression_token="suppress_once",
            original_request_digest=rejected.original_request_digest,
            ownership=rejected.ownership,
        )
        == claim_id
    )
    assert (
        store.consume_suppression(
            rejected.proposal_id,
            claim_id=claim_id,
            suppression_token="suppress_once",
            original_request_digest=rejected.original_request_digest,
            ownership=wrong_owner,
        )
        is False
    )

    def consume() -> bool:
        return WPlusSopStore(path).consume_suppression(
            rejected.proposal_id,
            claim_id=claim_id,
            suppression_token="suppress_once",
            original_request_digest=rejected.original_request_digest,
            ownership=rejected.ownership,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(8)))

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 7
    assert (
        WPlusSopStore(path).consume_suppression(
            rejected.proposal_id,
            claim_id="replay_forged",
            suppression_token="suppress_once",
            original_request_digest=rejected.original_request_digest,
            ownership=rejected.ownership,
        )
        is False
    )
    persisted = WPlusSopStore(path).get_entry_proposal(rejected.proposal_id)
    assert persisted is not None
    assert persisted.suppression_consumed_at is not None


def test_finish_run_requires_exact_attempt_and_persists_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    store.create_session(
        _projection(),
        command_receipt=_entry_receipt(),
        run_attempt=RunAttempt(
            run_id="run_1",
            attempt_id="attempt_1",
            command_request_id="cmd_entry_1",
            command="confirm_entry",
            status=RunStatus.CLAIMED,
        ),
    )

    with pytest.raises(WPlusSopStoreError, match="attempt"):
        store.finish_run(
            "sop_1",
            run_id="run_1",
            attempt_id="attempt_wrong",
            status=RunStatus.COMPLETED,
        )

    completed = store.finish_run(
        "sop_1",
        run_id="run_1",
        attempt_id="attempt_1",
        status="completed",
    )
    duplicate = store.finish_run(
        "sop_1",
        run_id="run_1",
        attempt_id="attempt_1",
        status=RunStatus.COMPLETED,
    )

    assert completed.status is RunStatus.COMPLETED
    assert completed.completed_at is not None
    assert duplicate.completed_at == completed.completed_at
    persisted = WPlusSopStore(path).get_session("sop_1")
    assert persisted is not None
    assert persisted.runs[0].completed_at == completed.completed_at


def test_stale_state_version_does_not_append_event_or_outbox(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    store.create_session(_projection(), command_receipt=_entry_receipt())

    with pytest.raises(StaleStateVersionError):
        store.commit_event(
            "sop_1",
            expected_state_version=0,
            event=_stage_event(),
            next_state=SessionState.AWAITING_QUEUE_CONFIRMATION,
            projection_changes={"stages": _stage_event().payload.stages},
            outbox_item=ChatProjectionOutboxItem(
                projection_event_id="chatproj_evt_stage_1",
                sop_session_id="sop_1",
                chat_id="chat_1",
                event_id="evt_stage_1",
                kind="stage_proposal",
                payload={"stage_count": 2},
            ),
        )

    reloaded = store.get_session("sop_1")
    assert reloaded is not None
    assert reloaded.projection.state_version == 1
    assert len(reloaded.events) == 1
    assert reloaded.outbox == []


def test_event_and_chat_outbox_are_committed_atomically_and_ack_persists(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    store.create_session(_projection(), command_receipt=_entry_receipt())
    item = ChatProjectionOutboxItem(
        projection_event_id="chatproj_evt_stage_1",
        sop_session_id="sop_1",
        chat_id="chat_1",
        event_id="evt_stage_1",
        kind="stage_proposal",
        payload={"stage_count": 2},
    )

    result = store.commit_event(
        "sop_1",
        expected_state_version=1,
        event=_stage_event(),
        next_state=SessionState.AWAITING_QUEUE_CONFIRMATION,
        projection_changes={"stages": _stage_event().payload.stages},
        outbox_item=item,
    )

    assert result.record.projection.state_version == 2
    assert result.record.events[-1].event_id == "evt_stage_1"
    assert [pending.projection_event_id for pending in store.pending_outbox()] == [
        "chatproj_evt_stage_1",
    ]

    assert store.ack_outbox("chatproj_evt_stage_1") is True
    assert store.ack_outbox("chatproj_evt_stage_1") is False
    assert WPlusSopStore(path).pending_outbox() == []


def test_command_receipt_deduplicates_event_and_run_lineage_is_preserved(
    tmp_path: Path,
) -> None:
    store = WPlusSopStore(tmp_path / "wplus-sop.json")
    store.create_session(_projection(), command_receipt=_entry_receipt())
    event = _stage_event()
    receipt = CommandReceipt(
        command_request_id="cmd_stage_1",
        command="accept_stage_proposal",
        sop_session_id="sop_1",
        resulting_state_version=2,
        starts_run=False,
    )

    first = store.commit_event(
        "sop_1",
        expected_state_version=1,
        event=event,
        next_state=SessionState.AWAITING_QUEUE_CONFIRMATION,
        command_receipt=receipt,
    )
    duplicate = store.commit_event(
        "sop_1",
        expected_state_version=1,
        event=event,
        next_state=SessionState.AWAITING_QUEUE_CONFIRMATION,
        command_receipt=receipt,
    )

    assert duplicate.duplicate is True
    assert duplicate.receipt == first.receipt
    record = store.get_session("sop_1")
    assert record is not None
    assert [stored.event_id for stored in record.events].count("evt_stage_1") == 1

    retry_receipt = CommandReceipt(
        command_request_id="cmd_retry_1",
        command="retry_current_turn",
        sop_session_id="sop_1",
        resulting_state_version=3,
        starts_run=True,
        run_id="run_2",
        attempt_id="attempt_2",
    )
    retry = RunAttempt(
        run_id="run_2",
        attempt_id="attempt_2",
        command_request_id="cmd_retry_1",
        command="retry_current_turn",
        status=RunStatus.CLAIMED,
        retry_of_run_id="run_1",
    )
    claimed = store.claim_run(
        "sop_1",
        expected_state_version=2,
        receipt=retry_receipt,
        attempt=retry,
    )
    assert claimed.record.runs[-1].retry_of_run_id == "run_1"
    assert claimed.record.projection.state_version == 3


def test_concurrent_create_allows_only_one_active_or_paused_session(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"

    def create(index: int) -> str:
        store = WPlusSopStore(path)
        session_id = f"sop_{index}"
        store.create_session(
            _projection(session_id),
            command_receipt=CommandReceipt(
                command_request_id=f"cmd_{index}",
                command="confirm_entry",
                sop_session_id=session_id,
                resulting_state_version=1,
            ),
        )
        return session_id

    outcomes: list[str] = []
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(create, index) for index in range(8)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except Exception as exc:  # noqa: BLE001 - asserted below
                failures.append(exc)

    assert len(outcomes) == 1
    assert len(failures) == 7
    assert all(isinstance(exc, ActiveSessionExistsError) for exc in failures)
    active = WPlusSopStore(path).get_active_by_chat(_ownership())
    assert active is not None
    assert active.projection.sop_session_id == outcomes[0]


def test_load_preserves_minimal_legacy_memory_history_without_reopening_session(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    projection = _projection()
    projection.state = SessionState.COMPLETED
    store.create_session(projection, command_receipt=_entry_receipt())

    raw = json.loads(path.read_text(encoding="utf-8"))
    legacy_candidates = [
        {
            "candidate_id": "legacy-approved",
            "summary": "旧版本曾由用户批准",
            "value": "旧版自由文本记忆",
            "status": "approved",
        },
        {
            "candidate_id": "legacy-failed",
            "summary": "旧版本失败项",
            "value": {"pattern": "旧版失败记录"},
            "status": "failed",
        },
    ]
    session = raw["sessions"]["sop_1"]
    session["projection"]["memory_candidates"] = legacy_candidates
    session["events"].append(
        {
            "object": "structured_interaction",
            "protocol_version": 1,
            "interaction": "wplus_sop",
            "event_id": "evt-legacy-memory",
            "session_id": "sop_1",
            "chat_id": "chat_1",
            "revision": 1,
            "round": 0,
            "state_version": 2,
            "kind": "memory_candidates",
            "payload": {"candidates": legacy_candidates},
        },
    )
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    reloaded_store = WPlusSopStore(path)
    loaded = reloaded_store.get_session("sop_1")

    assert loaded is not None
    assert loaded.projection.state is SessionState.COMPLETED
    assert loaded.projection.state_version == projection.state_version
    approved, failed = loaded.projection.memory_candidates
    assert approved.status is MemoryCandidateStatus.APPROVED
    assert approved.write_receipt is None
    assert approved.legacy_read_only is True
    assert failed.status is MemoryCandidateStatus.FAILED
    assert failed.failure_reason is None
    assert failed.legacy_read_only is True
    historical = loaded.events[-1].payload
    assert historical.candidates[0].status is MemoryCandidateStatus.APPROVED
    assert historical.candidates[0].value == "旧版自由文本记忆"
    assert historical.candidates[1].status is MemoryCandidateStatus.FAILED
    assert historical.candidates[1].failure_reason is None

    before_events = [
        (
            event.kind.value,
            event.state_version,
            event.payload.model_dump(mode="json", by_alias=True),
        )
        for event in loaded.events
    ]
    before_receipts = {
        key: receipt.model_dump(mode="json")
        for key, receipt in loaded.command_receipts.items()
    }
    with reloaded_store._lock:
        reloaded_store._save_unlocked(reloaded_store._load_unlocked())
    saved_raw = json.loads(path.read_text(encoding="utf-8"))
    saved_session = saved_raw["sessions"]["sop_1"]
    assert saved_session["projection"]["state"] == "Completed"
    assert saved_session["projection"]["state_version"] == projection.state_version
    assert saved_session["command_receipts"] == session["command_receipts"]
    assert saved_session["events"][-1]["payload"]["candidates"][0]["status"] == (
        "approved"
    )
    assert saved_session["events"][-1]["payload"]["candidates"][0]["value"] == (
        "旧版自由文本记忆"
    )
    assert "legacy_read_only" not in json.dumps(saved_raw)

    saved_and_reloaded = reloaded_store.get_session("sop_1")
    assert saved_and_reloaded is not None
    assert saved_and_reloaded.projection.state is SessionState.COMPLETED
    assert saved_and_reloaded.projection.state_version == projection.state_version
    assert {
        key: receipt.model_dump(mode="json")
        for key, receipt in saved_and_reloaded.command_receipts.items()
    } == before_receipts
    assert [
        (
            event.kind.value,
            event.state_version,
            event.payload.model_dump(mode="json", by_alias=True),
        )
        for event in saved_and_reloaded.events
    ] == before_events


def _report_artifacts() -> list[StageReportArtifact]:
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


def _report() -> StageReport:
    return StageReport(
        stage_id="one",
        report_no=1,
        revision=0,
        artifacts=_report_artifacts(),
        validation=StageReportValidationEvidence(
            schema_validator="scripts/validate_stage_sop.py",
            schema_exit_code=0,
            renderers=("scripts/render_stage_md.py", "scripts/render_stage_sop.py"),
        ),
    )


def _snapshot() -> ConfirmedStageSnapshot:
    return ConfirmedStageSnapshot(
        stage_id="one",
        report_no=1,
        revision=0,
        artifact_sha256="d" * 64,
    )


def _cumulative() -> CumulativePreview:
    return CumulativePreview(
        preview_version=1,
        stage_order=["one"],
        snapshots=[_snapshot()],
        artifacts=_report_artifacts(),
        rendered_sha256={"stage_sop_json": "e" * 64},
    )


def test_legacy_store_file_without_incremental_fields_loads_with_defaults(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    record = SessionRecord(projection=_projection(), events=[_stage_event()])
    dumped = record.model_dump(mode="json")
    del dumped["projection"]["stage_reports"]
    del dumped["projection"]["confirmed_snapshots"]
    del dumped["projection"]["cumulative_preview"]
    legacy = {
        "schema_version": 1,
        "entry_proposals": {},
        "sessions": {record.projection.sop_session_id: dumped},
        "command_index": {},
    }
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    loaded = WPlusSopStore(path).get_session("sop_1")
    assert loaded is not None
    assert loaded.projection.stage_reports == []
    assert loaded.projection.confirmed_snapshots == []
    assert loaded.projection.cumulative_preview is None


def test_commit_event_persists_incremental_projection_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wplus-sop.json"
    store = WPlusSopStore(path)
    report = _report()
    snapshot = _snapshot()
    preview = _cumulative()
    projection = _projection().model_copy(
        update={
            "stages": [
                Stage(stage_id="one", name="需求确认"),
                Stage(stage_id="two", name="交付校验"),
            ],
        },
    )
    store.create_session(projection, command_receipt=_entry_receipt())
    store.commit_event(
        "sop_1",
        expected_state_version=1,
        event=StructuredInteractionEnvelope(
            event_id="evt_queue_1",
            sop_session_id="sop_1",
            chat_id="chat_1",
            revision=1,
            round=0,
            state_version=2,
            kind=EventKind.STAGE_QUEUE_CONFIRMED,
            payload=StageQueueConfirmedPayload(
                stages=[
                    Stage(stage_id="one", name="需求确认"),
                    Stage(stage_id="two", name="交付校验"),
                ],
            ),
        ),
        next_state=SessionState.AWAITING_QUEUE_CONFIRMATION,
        projection_changes={
            "stage_reports": [report],
            "confirmed_snapshots": [snapshot],
            "cumulative_preview": preview,
        },
    )

    reloaded = WPlusSopStore(path).get_session("sop_1")
    assert reloaded is not None
    assert reloaded.projection.stage_reports == [report]
    assert reloaded.projection.confirmed_snapshots == [snapshot]
    assert reloaded.projection.cumulative_preview == preview
    assert reloaded.projection.state_version == 2
