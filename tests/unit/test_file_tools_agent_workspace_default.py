# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from swe.agents.tools.file_io import (
    append_file,
    edit_file,
    read_file,
    write_file,
)
from swe.config.context import tenant_context


@pytest.mark.asyncio
async def test_read_file_defaults_to_workspace_dir(tmp_path: Path):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "note.txt").write_text("workspace content")
    (tenant_dir / "note.txt").write_text("tenant-root content")

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await read_file("note.txt")

    assert "workspace content" in result.content[0].get("text", "")


@pytest.mark.asyncio
async def test_write_and_append_file_default_to_workspace_dir(tmp_path: Path):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            await write_file("note.txt", "hello")
            await append_file("note.txt", " world")

    # file_io uses UTF-8 BOM for .txt for Windows compatibility.
    assert (workspace_dir / "note.txt").read_text().lstrip(
        "\ufeff",
    ) == "hello world"


@pytest.mark.asyncio
async def test_write_file_creates_missing_parent_dirs_within_workspace(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await write_file("nested/child/note.txt", "hello")

    assert "Wrote 5 bytes" in result.content[0].get("text", "")
    assert (
        workspace_dir / "nested" / "child" / "note.txt"
    ).read_text().lstrip(
        "\ufeff",
    ) == "hello"


@pytest.mark.asyncio
async def test_write_file_allows_default_source_workspace_absolute_path(
    tmp_path: Path,
):
    workspace_dir = tmp_path / "default_RMASSIST" / "workspaces" / "default"
    workspace_dir.mkdir(parents=True)
    target = workspace_dir / "report.md"

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(
            tenant_id="default",
            source_id="RMASSIST",
            workspace_dir=workspace_dir,
        ):
            result = await write_file(str(target), "hello")

    assert "Wrote 5 bytes" in result.content[0].get("text", "")
    assert target.read_text() == "hello"


@pytest.mark.asyncio
async def test_write_file_rejects_legacy_skill_pool_absolute_path(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    target = tmp_path / "skill_pool" / "custom-skill" / "SKILL.md"

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            with pytest.raises(Exception) as exc_info:
                await write_file(str(target), "# Updated skill\n")

    assert getattr(exc_info.value, "error_type", "") == "permission_denied"
    assert not target.exists()


@pytest.mark.asyncio
async def test_write_file_allows_created_workspace_skill_from_manifest(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "custom-skill"
    (workspace_dir / "skill.json").write_text(
        json.dumps(
            {
                "skills": {
                    "custom-skill": {
                        "enabled": True,
                        "source": "customized",
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await write_file(
                "skills/custom-skill/SKILL.md",
                "# safe\n",
            )

    assert "Wrote 7 bytes" in result.content[0].get("text", "")
    assert (skill_dir / "SKILL.md").read_text() == "# safe\n"


@pytest.mark.asyncio
async def test_write_file_allows_new_workspace_skill_directory(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await write_file("skills/new-skill/SKILL.md", "# new\n")

    assert "Wrote 6 bytes" in result.content[0].get("text", "")
    assert (
        workspace_dir / "skills" / "new-skill" / "SKILL.md"
    ).read_text() == "# new\n"


@pytest.mark.asyncio
async def test_edit_file_allows_created_workspace_skill_from_manifest(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    skill_dir = workspace_dir / "skills" / "custom-skill"
    skill_dir.mkdir(parents=True)
    target = skill_dir / "SKILL.md"
    target.write_text("# old\n", encoding="utf-8")
    (workspace_dir / "skill.json").write_text(
        json.dumps(
            {
                "skills": {
                    "custom-skill": {
                        "enabled": True,
                        "source": "customized",
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await edit_file(
                "skills/custom-skill/SKILL.md",
                "old",
                "new",
            )

    assert "Successfully replaced text" in result.content[0].get("text", "")
    assert target.read_text(encoding="utf-8") == "# new\n"


@pytest.mark.asyncio
async def test_write_file_rejects_received_workspace_skill_from_manifest(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    skill_dir = workspace_dir / "skills" / "received-skill"
    skill_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps(
            {
                "skills": {
                    "received-skill": {
                        "enabled": True,
                        "source": "marketplace:skill-123",
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            with pytest.raises(Exception) as exc_info:
                await write_file(
                    "skills/received-skill/SKILL.md",
                    "# unsafe\n",
                )

    assert getattr(exc_info.value, "error_type", "") == "permission_denied"
    assert not (skill_dir / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_write_file_rejects_existing_workspace_skill_without_manifest(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    skill_dir = workspace_dir / "skills" / "received-skill"
    skill_dir.mkdir(parents=True)

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            with pytest.raises(Exception) as exc_info:
                await write_file(
                    "skills/received-skill/SKILL.md",
                    "# unsafe\n",
                )

    assert getattr(exc_info.value, "error_type", "") == "permission_denied"
    assert not (skill_dir / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_append_file_creates_missing_parent_dirs_within_workspace(
    tmp_path: Path,
):
    tenant_dir = tmp_path / "tenant_a"
    workspace_dir = tenant_dir / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    with patch("swe.security.tenant_path_boundary.WORKING_DIR", tmp_path):
        with tenant_context(tenant_id="tenant_a", workspace_dir=workspace_dir):
            result = await append_file("nested/child/note.txt", "hello")

    assert "Appended 5 bytes" in result.content[0].get("text", "")
    assert (
        workspace_dir / "nested" / "child" / "note.txt"
    ).read_text().lstrip(
        "\ufeff",
    ) == "hello"
