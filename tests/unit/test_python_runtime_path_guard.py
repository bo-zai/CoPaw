# -*- coding: utf-8 -*-
"""Tests for the injected Python runtime tenant path guard."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

import swe.constant as swe_constant
from swe.security.python_runtime_path_guard import (
    prepare_python_runtime_path_guard_env,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_guard_starts_python_without_sitecustomize_error(
    tmp_path: Path,
) -> None:
    """The generated sitecustomize module must load cleanly at Python startup."""
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir()
    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=tenant_root,
    )

    with guard_dir:
        result = subprocess.run(
            [sys.executable, "-c", "print('guard-ready')"],
            cwd=tenant_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard-ready"
    assert "Error in sitecustomize" not in result.stderr


def test_runtime_guard_allows_imports_from_existing_pythonpath_roots(
    tmp_path: Path,
) -> None:
    """Editable/local packages outside the tenant root must remain importable."""
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir()
    package_root = tmp_path / "package_src"
    package_root.mkdir()
    (package_root / "outside_package.py").write_text(
        "VALUE = 'imported from package root'\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(package_root)
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=tenant_root,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import outside_package; print(outside_package.VALUE)",
            ],
            cwd=tenant_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imported from package root"


def test_runtime_guard_allows_trusted_swe_entrypoint_to_read_trusted_file(
    tmp_path: Path,
) -> None:
    """Trusted SWE launchers may read explicit app metadata files."""
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir()
    config_path = tmp_path / ".swe" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(
        '{"last_api": {"host": "127.0.0.1", "port": 8088}}\n',
        encoding="utf-8",
    )
    trusted_bin = tmp_path / "venv" / "Scripts"
    trusted_bin.mkdir(parents=True)
    swe_entrypoint = trusted_bin / "swe"
    swe_entrypoint.write_text(
        (
            "from pathlib import Path\n"
            f"path = Path({str(config_path)!r})\n"
            "print(path.is_file())\n"
            "print(path.read_text(encoding='utf-8'))\n"
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=tenant_root,
        trusted_paths=[config_path],
        trusted_entrypoint_roots=[trusted_bin],
    )

    with guard_dir:
        result = subprocess.run(
            [sys.executable, str(swe_entrypoint)],
            cwd=tenant_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout
    assert '"last_api"' in result.stdout


def test_runtime_guard_allows_trusted_swe_entrypoint_to_bootstrap_envs_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """可信 SWE 启动器需要读取密钥目录中的 envs.json 完成初始化。"""
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir()
    working_dir = tmp_path / ".swe"
    secret_dir = tmp_path / ".swe.secret"
    secret_dir.mkdir()
    envs_path = secret_dir / "envs.json"
    envs_path.write_text(
        '{"SWE_GUARD_BOOTSTRAP_TEST": "loaded"}\n',
        encoding="utf-8",
    )
    trusted_bin = tmp_path / "venv" / "bin"
    trusted_bin.mkdir(parents=True)
    swe_entrypoint = trusted_bin / "swe"
    swe_entrypoint.write_text(
        (
            "import os\n"
            "import swe\n"
            "print(os.environ.get('SWE_GUARD_BOOTSTRAP_TEST'))\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(swe_constant, "WORKING_DIR", working_dir)
    monkeypatch.setattr(swe_constant, "SECRET_DIR", secret_dir)

    env = os.environ.copy()
    env["SWE_WORKING_DIR"] = str(working_dir)
    env["SWE_SECRET_DIR"] = str(secret_dir)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=tenant_root,
        trusted_entrypoint_roots=[trusted_bin],
    )

    with guard_dir:
        result = subprocess.run(
            [sys.executable, str(swe_entrypoint)],
            cwd=tenant_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "loaded"
    assert "failed to load persisted envs on init" not in result.stderr


def test_runtime_guard_denies_untrusted_python_access_to_trusted_file(
    tmp_path: Path,
) -> None:
    """Trusted metadata files are not a general escape hatch for python -c."""
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir()
    config_path = tmp_path / ".swe" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text('{"secretish": true}\n', encoding="utf-8")
    trusted_bin = tmp_path / "venv" / "Scripts"
    trusted_bin.mkdir(parents=True)

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=tenant_root,
        trusted_paths=[config_path],
        trusted_entrypoint_roots=[trusted_bin],
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"from pathlib import Path; print(Path({str(config_path)!r}).read_text())",
            ],
            cwd=tenant_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "outside the allowed workspace" in result.stderr


def test_runtime_guard_denies_direct_workspace_skill_write(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)

    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"uploaded": {"source": "marketplace:demo"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('skills/uploaded/SKILL.md').parent.mkdir(parents=True, exist_ok=True); "
                    "Path('skills/uploaded/SKILL.md').write_text('# Uploaded\\n')"
                ),
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "workspace skill directory" in result.stderr
    assert not (workspace_dir / "skills" / "uploaded" / "SKILL.md").exists()


def test_runtime_guard_allows_writes_to_created_workspace_skill(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "uploaded"
    skill_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"uploaded": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('skills/uploaded/SKILL.md').parent.mkdir(parents=True, exist_ok=True); "
                    "Path('skills/uploaded/SKILL.md').write_text('# Uploaded\\n')"
                ),
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert (skill_dir / "SKILL.md").exists()


def test_runtime_guard_allows_read_only_os_open_for_created_workspace_skill(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "uploaded"
    skill_dir.mkdir(parents=True)
    target = skill_dir / "SKILL.md"
    target.write_text("# Uploaded\n", encoding="utf-8")
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"uploaded": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os; "
                    "fd = os.open('skills/uploaded/SKILL.md', os.O_RDONLY); "
                    "os.close(fd)"
                ),
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert target.exists()


def test_runtime_guard_denies_skill_directory_removal(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "uploaded"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Uploaded\n", encoding="utf-8")
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"uploaded": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import shutil; shutil.rmtree('skills')",
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "workspace skill directory" in result.stderr
    assert (skill_dir / "SKILL.md").exists()


def test_runtime_guard_denies_skill_root_creation(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"uploaded": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('skills').mkdir(exist_ok=True)",
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "workspace skill directory" in result.stderr
    assert not (workspace_dir / "skills").exists()


def test_runtime_guard_allows_new_skill_root_creation(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('skills/new-skill').mkdir(parents=True, exist_ok=True)",
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert (workspace_dir / "skills" / "new-skill").exists()


def test_runtime_guard_allows_new_skill_root_removal(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "new-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("x", encoding="utf-8")
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
        active_skill="new-skill",
        active_skill_base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import shutil; shutil.rmtree('skills/new-skill')",
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert not skill_dir.exists()


def test_runtime_guard_denies_existing_skill_root_without_manifest(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "received"
    skill_dir.mkdir(parents=True)

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import shutil; shutil.rmtree('skills/received')",
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "workspace skill directory" in result.stderr
    assert skill_dir.exists()


def test_runtime_guard_denies_skill_directory_metadata_mutation(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    skill_dir = workspace_dir / "skills" / "uploaded"
    skill_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"uploaded": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; os.chmod('skills', 0o700)",
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "workspace skill directory" in result.stderr
    assert skill_dir.exists()


def test_runtime_guard_keeps_active_skill_protection_after_env_mutation(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"edited": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os; "
                    "from pathlib import Path; "
                    "Path('skills/edited/SKILL.md').parent.mkdir(parents=True, exist_ok=True); "
                    "Path('skills/edited/SKILL.md').write_text('# Edited\\n')"
                ),
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert (workspace_dir / "skills" / "edited" / "SKILL.md").exists()


def test_runtime_guard_preserves_active_skill_protection_in_child_python(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"edited": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import subprocess, sys; "
                    "subprocess.run([sys.executable, '-c', "
                    '"from pathlib import Path; "'
                    "\"Path('skills/edited/SKILL.md').parent.mkdir(parents=True, exist_ok=True); \""
                    "\"Path('skills/edited/SKILL.md').write_text('x')\"], check=True)"
                ),
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert (workspace_dir / "skills" / "edited" / "SKILL.md").exists()


def test_runtime_guard_denies_unlisted_workspace_skill_write(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"edited": {"source": "marketplace:demo"}}}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=workspace_dir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('skills/edited/SKILL.md').parent.mkdir(parents=True, exist_ok=True); "
                    "Path('skills/edited/SKILL.md').write_text('x')"
                ),
            ],
            cwd=workspace_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode != 0
    assert "workspace skill directory" in result.stderr


def test_runtime_guard_allows_created_workspace_skill_write_when_cwd_is_subdir(
    tmp_path: Path,
) -> None:
    tenant_root = tmp_path / "tenant"
    workspace_dir = tenant_root / "workspaces" / "agent_a"
    subdir = workspace_dir / "subdir"
    subdir.mkdir(parents=True)
    (workspace_dir / "skill.json").write_text(
        json.dumps({"skills": {"edited": {"source": "customized"}}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    guard_dir = prepare_python_runtime_path_guard_env(
        env,
        tenant_root=tenant_root,
        base_dir=subdir,
    )

    with guard_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('../skills/edited/SKILL.md').parent.mkdir(parents=True, exist_ok=True); "
                    "Path('../skills/edited/SKILL.md').write_text('# Edited\\n')"
                ),
            ],
            cwd=subdir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert (workspace_dir / "skills" / "edited" / "SKILL.md").exists()
