# -*- coding: utf-8 -*-
"""Selected community expert session dependency binding tests."""

from __future__ import annotations

from pathlib import Path

from swe.app.subagents.models import (
    AgentOwnedDefinitionMetadata,
    SubAgentDefinition,
)
from swe.app.subagents.session_dependencies import (
    initialize_community_expert_dependency_view,
)


def _received_definition(
    definition_id: str,
    *,
    declared_skills: list[str] | None = None,
    fingerprint: str = "fingerprint",
) -> SubAgentDefinition:
    return SubAgentDefinition(
        name="received-reviewer",
        description="Received",
        instruction="Do work",
        agent_owned=AgentOwnedDefinitionMetadata(
            definition_id=definition_id,
            declared_skills=declared_skills or [],
            community={
                "item_id": "expert-1",
                "version": "1.0.0",
                "content_fingerprint": fingerprint,
            },
        ),
    )


def test_selected_received_expert_initializes_its_chat_dependency_view(
    tmp_path: Path,
) -> None:
    from swe.app.runner import runner as runner_module

    initialize = getattr(
        runner_module,
        "_initialize_selected_expert_dependency_view",
        None,
    )
    assert callable(initialize)
    definition_id = "00000000-0000-0000-0000-000000000050"
    expert_dir = tmp_path / "agents"
    expert_dir.mkdir()
    (expert_dir / f"{definition_id}.toml").write_text(
        'name = "received-reviewer"\n'
        'description = "Received"\n'
        'instruction = "Do work"\n'
        "enabled = true\n\n"
        "[community]\n"
        'item_id = "expert-1"\n'
        'version = "1.0.0"\n'
        'content_fingerprint = "fingerprint"\n',
        encoding="utf-8",
    )
    (expert_dir / f"{definition_id}.dependencies").mkdir()
    chat_id = "00000000-0000-0000-0000-000000000051"

    view_root = initialize(
        workspace_dir=tmp_path,
        tenant_id="tenant-1",
        agent_id="agent-1",
        selected_expert_id=definition_id,
        chat_id=chat_id,
    )

    assert view_root == (
        tmp_path / ".expert_sessions" / chat_id / definition_id
    )
    assert view_root.is_dir()


def test_chat_dependency_view_remains_frozen_after_received_update(
    tmp_path: Path,
) -> None:
    definition_id = "00000000-0000-0000-0000-000000000052"
    chat_id = "00000000-0000-0000-0000-000000000053"
    source = (
        tmp_path
        / "agents"
        / f"{definition_id}.dependencies"
        / "skills"
        / "frozen"
    )
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("v1", encoding="utf-8")
    first = _received_definition(
        definition_id,
        declared_skills=["frozen"],
        fingerprint="one",
    )
    view = initialize_community_expert_dependency_view(
        workspace_dir=tmp_path,
        chat_id=chat_id,
        definition=first,
    )
    assert view is not None
    (source / "SKILL.md").write_text("v2", encoding="utf-8")
    second = first.model_copy(
        update={
            "agent_owned": AgentOwnedDefinitionMetadata(
                definition_id=definition_id,
                declared_skills=["frozen"],
                community={
                    "item_id": "expert-1",
                    "version": "2.0.0",
                    "content_fingerprint": "two",
                },
            ),
        },
    )
    assert (
        initialize_community_expert_dependency_view(
            workspace_dir=tmp_path,
            chat_id=chat_id,
            definition=second,
        )
        == view
    )
    assert (view / "skills" / "frozen" / "SKILL.md").read_text() == "v1"
