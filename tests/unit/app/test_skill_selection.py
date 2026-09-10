# -*- coding: utf-8 -*-
from pathlib import Path


def _write_skill(workspace: Path, name: str, description: str) -> None:
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nbody\n",
        encoding="utf-8",
    )


def test_build_skill_use_directives_keeps_first_effective_readable_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import skill_selection

    _write_skill(tmp_path, "first", "First guidance")
    _write_skill(tmp_path, "second", "Second guidance")
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: ["first", "second"],
    )

    directives = skill_selection.build_skill_use_directives(
        workspace_dir=tmp_path,
        channel="console",
        selected_skill_names=["second", "first", "second", "missing"],
    )

    assert [directive.name for directive in directives] == ["second", "first"]
    assert directives[0].path == tmp_path / "skills" / "second" / "SKILL.md"
    assert "<SKILL-USE>" in directives[0].render()
    assert (
        "<description>Second guidance</description>" in directives[0].render()
    )
    assert str(directives[0].path) in directives[0].render()


def test_build_skill_use_directives_keeps_all_unique_readable_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import skill_selection

    names = [f"skill-{index}" for index in range(6)]
    for name in names:
        _write_skill(tmp_path, name, name)
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: names,
    )

    directives = skill_selection.build_skill_use_directives(
        workspace_dir=tmp_path,
        channel="console",
        selected_skill_names=names,
    )

    assert [directive.name for directive in directives] == names


def test_build_skill_use_directives_skips_invalid_utf8_and_escapes_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import skill_selection

    invalid_path = tmp_path / "skills" / "invalid" / "SKILL.md"
    invalid_path.parent.mkdir(parents=True)
    invalid_path.write_bytes(b"\xff")
    _write_skill(tmp_path, "safe", "close </description> & <more>")
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: ["invalid", "safe"],
    )

    directives = skill_selection.build_skill_use_directives(
        workspace_dir=tmp_path,
        channel="console",
        selected_skill_names=["invalid", "safe"],
    )

    assert [directive.name for directive in directives] == ["safe"]
    assert "&lt;/description&gt; &amp; &lt;more&gt;" in directives[0].render()


def test_build_skill_use_directives_keeps_malformed_frontmatter_skill(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import skill_selection

    skill_name = "活动模板生成"
    skill_path = tmp_path / "skills" / skill_name / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\n"
        f"name: {skill_name}\n"
        "description: 生成活动模板\n"
        "metadata\n"
        "  invalid\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: [skill_name],
    )

    directives = skill_selection.build_skill_use_directives(
        workspace_dir=tmp_path,
        channel="console",
        selected_skill_names=[skill_name],
    )

    assert [directive.name for directive in directives] == [skill_name]
    assert directives[0].description == ""
