# Skill 安全扫描实现计划

> **给执行型 Agent 的要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，并按任务逐项执行。所有步骤使用 checkbox（`- [ ]`）语法跟踪进度。

**目标：** 为 CoPaw 构建分阶段的 Skill 安全扫描体系，覆盖 Skill 创建、上传、Market 上架、租户安装以及后续运行时治理。

**架构：** 保留 CoPaw 现有 `scan_skill_directory()` 作为同步准入入口，将 `SkillScanner` 演进为分层扫描编排器，统一产出标准化 `Finding` 证据。第一阶段抽出现有 ZIP 安全解包边界，并增加高置信包体检测与 AST 行为检测，不改变现有调用方契约；第二、三阶段继续把开源组件纳入实现，通过统一 adapter 接入 SkillSpector、Agent-Scan、MCP-Scan、pip-audit、npm audit、OSV 等能力，再补齐扫描 profile、依赖/SCA、语义/数据流引擎、Market/SWE 共享能力和运营复核。

**技术栈：** Python、FastAPI、Pydantic 配置模型、现有 `swe.security.skill_scanner`、pytest、MySQL 扫描历史、React/TypeScript Console API 类型；分阶段接入 pip-audit、npm audit、OSV、SkillSpector、Agent-Scan、MCP-Scan 等开源组件。

---

## 设计依据

- `docs/superpowers/specs/2026-08-06-skill-security-scan-details.html`
- `docs/superpowers/specs/2026-08-06-skill-security-scan-architecture.html`

详细设计将 Skill 安全扫描拆成七层：

| 层级 | 实现范围 |
| --- | --- |
| L1 入口接入层 | 优先复用现有 SWE/Market 扫描调用点，后续再增加扫描任务 API。 |
| L2 包体解析与上下文层 | MVP 先补安全解包边界和包体安全检测；包体清单、完整 `ScanContext` 和跨分析器上下文放到第二阶段。 |
| L3 基础静态检测层 | 保留 YAML 规则，并增加 AST 行为分析。 |
| L4 语义与行为分析层 | MVP 之后增加 source/sink 与语义分析器。 |
| L5 供应链与情报层 | 增加依赖解析和可选漏洞库后端。 |
| L6 风险决策与准入层 | 在 block/warn/off 基础上扩展 profile 和更丰富的决策。 |
| L7 运行时与运营闭环层 | 在扫描证据稳定后增加复核、版本差分、回扫和运行时关联。 |

---

## 最新代码校准（2026-08-11）

本计划已按当前代码基线重新校准：

- `src/swe/security/skill_scanner/` 当前已有同步入口 `scan_skill_directory()`、`SkillScanner` 编排器、`PatternAnalyzer`、YAML policy、扫描历史和 block/warn/off/whitelist/timeout 契约。
- `SkillScanner` 默认仍只注册 `PatternAnalyzer`；尚未落地 `PackageAnalyzer`、`AstBehaviorAnalyzer`、`DependencyAnalyzer`、profile 选择器或 `external_engines.py`。
- `SkillScannerConfig` 当前只有 `mode`、`timeout`、`whitelist`，尚无 `profile` 字段。
- `models.py` 当前只有 `SkillFile`、`Finding`、`ScanResult` 等稳定结果模型；第一阶段不强制修改它，新增安全解包 helper 和分析器直接复用现有同步扫描入口与 `BaseAnalyzer.analyze(skill_dir, files, *, skill_name=None)` 接口。
- Market 下仍有一套 `market/src/market/security/skill_scanner/` 镜像实现；第一阶段必须先取消 Market 拦截历史写本地 `skill_scanner_blocked.json`，改为直接写入数据库表 `swe_skill_scan_history`，并补齐 `source_id`、`user_id`、`bbk_id` 上下文字段，保证 Console 技能扫描器页面能展示 Market 上传/启用拦截记录的来源、用户和分行。`swe_skill_scan_history` 的建表和补列迁移由独立 SQL 脚本维护，SWE 和 Market 启动时只校验数据库可用并读写已有表，不执行 DDL。共享扫描器实现仍放到第二阶段，避免第一阶段同时重构两套分析器。
- Console 安全页和 API 类型已经存在于 `console/src/pages/Settings/Security/` 与 `console/src/api/modules/security.ts`，但复核、报告详情和 profile 控件仍是后续阶段。

因此，第一阶段收敛为“在现有同步扫描链路上补齐安全解包边界、高置信本地分析器和统一数据库告警历史”，不提前引入完整扫描上下文模型、异步任务、Market 分析器重构或开源 CLI 运行器。

---

## 开源组件落地策略

开源组件会纳入实现范围，但不直接替代 CoPaw 的主准入入口。CoPaw 已有租户目录、Market 上架、Console 安全页、block/warn/off、白名单和扫描历史等业务契约；外部工具应通过统一 adapter 进入 `Finding` 和 `Decision`，再由 CoPaw 风险决策中心统一裁决。

| 开源组件 | 实现定位 | 接入阶段 | 在 CoPaw 中的作用 |
| --- | --- | --- | --- |
| SkillSpector | Skill 包二级扫描引擎 | 第二阶段 POC，第三阶段 strict profile 正式接入 | 复核语义风险、权限一致性、AST 行为和污点链路，主要用于 Market 上架和高风险 ZIP。 |
| Agent-Scan | 本机 Agent/MCP/Skill 资产巡检 | 第三阶段 | 扫描运行环境中已安装的 Agent、MCP Server 和 Skill，发现工具投毒和有毒流组合。 |
| MCP-Scan | MCP 专项扫描 | 第三阶段 | 检查 MCP 工具描述投毒、Prompt Injection 和 MCP Toxic Flow，挂到 MCP 上传/绑定流程。 |
| pip-audit / npm audit / OSV | 依赖漏洞增强 | 第二阶段 | 为 `DependencyAnalyzer` 提供漏洞库后端，strict profile 可联网增强，standard profile 仅做本地解析。 |
| Cisco Skill Scanner / Cisco MCP Scanner | 候选增强引擎 | 第二阶段调研验证，第三阶段按可用性接入 | 若部署和授权条件满足，作为 Skill/MCP 深度扫描补充；否则保留 adapter 设计，不阻塞主链路。 |

**实现原则：**

- CoPaw 自研 scanner 是准入主链路，负责租户上下文、路径边界、历史记录和 block/warn/off。
- 开源组件只通过 `external_engines.py` 进入系统，禁止业务代码直接依赖某个 CLI 的原始输出字段。
- 外部引擎执行必须受 timeout、工作目录、环境变量、网络和输出大小约束。
- strict profile 才能调用耗时或联网增强引擎；quick/standard 保持本地、稳定、低延迟。
- 开源引擎接入先做离线 POC 与样本回归，再进入 Market 上架或租户安装路径。

---

## 文件结构

### 第一阶段：MVP 安全准入

- 新建：`src/swe/security/skill_scanner/safe_unpack.py`
  - 抽出 `src/swe/agents/skills_manager.py` 中已有的 ZIP 安全解包逻辑，为现有 ZIP 外来包提供隔离目录解包前校验，阻断 Zip Slip、Zip Bomb、符号链接成员、绝对路径成员、超大成员和过多文件；TAR 等其他包格式后续按同一边界扩展。
- 修改：`src/swe/agents/skills_manager.py`
  - 将 `_extract_and_validate_zip()` 的路径穿越、符号链接、单成员体积、总体积、文件数校验委托给 `safe_unpack.py`，保持 `_extract_zip_skills(data)` 对外行为不变，并确保失败时清理临时目录。
- 新建：`src/swe/security/skill_scanner/analyzers/package_analyzer.py`
  - 检测符号链接、二进制可执行文件、隐藏可执行脚本、嵌套压缩包、可疑压缩包成员、超大文件和高风险包体结构。
- 新建：`src/swe/security/skill_scanner/analyzers/ast_behavior_analyzer.py`
  - 用 Python AST 检测动态执行等高风险行为，降低纯正则扫描误报。
- 修改：`src/swe/security/skill_scanner/scanner.py`
  - 将 `PackageAnalyzer` 和 `AstBehaviorAnalyzer` 注册进默认分析器集合。
  - 保持当前 `PatternAnalyzer` 文件发现行为稳定。
- 修改：`src/swe/security/skill_scanner/__init__.py`
  - 如测试或下游导入需要，导出新增分析器。
- 修改：`console/src/api/modules/security.ts`
  - 为 `BlockedSkillFinding` 补充可选 `analyzer` 字段；为 `BlockedSkillRecord` 补充 `source_id`、`user_id`、`bbk_id` 字段。
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.tsx`
  - 在现有 Findings 弹窗中增加 analyzer 展示列；在拦截历史表增加来源、用户和分行展示列，形成一阶段最小风险可见性。
- 修改：`console/src/api/modules/security.test.ts`
  - 覆盖扫描历史 API 类型承接 `source_id`、`user_id`、`bbk_id` 和 finding analyzer 字段。
- 修改：`console/src/locales/zh.json`, `console/src/locales/en.json`
  - 为来源、用户、分行和 analyzer 列补充本地化文案；空值统一展示 `-`。
- 修改：`src/swe/security/skill_scanner/history.py`
  - 将 `BlockedSkillRecord` 和读写 SQL 扩展为包含 `source_id`、`user_id`、`bbk_id`；启动初始化不再执行建表或补列 DDL。
- 新建：`deploy/migrations/2026_08_19_create_swe_skill_scan_history.sql`
  - 独立维护 `swe_skill_scan_history` 建表和已有表幂等补列/补索引迁移，由部署或管理员手工执行。
- 新建：`scripts/sql/skill_scan_history_tables.sql`
  - 提供同内容的手工执行入口。
- 修改：`src/swe/app/routers/config.py`
  - 技能扫描历史接口返回 `source_id`、`user_id`、`bbk_id`，后续可按这些字段做过滤；第一阶段先保证响应字段完整。
- 修改：`market/src/market/security/skill_scanner/__init__.py`
  - 取消 `skill_scanner_blocked.json` 本地文件历史写入；Market 上传、上架、启用技能被扫描拦截或告警时，直接写入数据库表 `swe_skill_scan_history`，并携带 `source_id`、`user_id`、`bbk_id`。
- 新建：`market/src/market/security/skill_scanner/history.py`
  - 提供 Market 侧数据库历史写入器，复用独立 SQL 维护的 `swe_skill_scan_history` 表结构和 `BlockedSkillRecord` 字段，包含 `source_id`、`user_id`、`bbk_id`；不包含 `CREATE TABLE` 或 `ALTER TABLE`，不引入新的本地文件、轮转文件或 JSONL；支持 `submit()` 和 `flush()`，让接口返回拦截错误前能等待写库完成。
- 修改：`market/src/market/app/_app.py`
  - Market 服务启动时把数据库 history writer 安装到 Market scanner；不在 Market 启动流程中建表或迁移表结构。
- 修改：`market/src/market/app/routers/skills_browse.py`
  - 用户侧上传/启用和管理操作读取 `X-Source-Id`、`X-User-Id`、`X-Bbk-Id` 并透传给扫描历史。
- 修改：`market/src/market/app/routers/skills_market.py`
  - 管理员上架接口新增 `X-Bbk-Id` 请求头，并透传给扫描历史；`bbk_ids` 仍只表示技能分发范围。
- 修改：`market/src/market/marketplace/service.py`
  - 首次启用 Skill 的扫描链路透传 `source_id`、`user_id`、`bbk_id`，并在返回 `security_scan_failed` 前等待历史写入完成。
- 测试：`console/src/pages/Settings/Security/components/SkillScannerSection.test.tsx`
- 测试：`console/src/api/modules/security.test.ts`
- 测试：`tests/unit/security/test_skill_scanner_package_analyzer.py`
- 测试：`tests/unit/security/test_skill_scanner_safe_unpack.py`
- 测试：`tests/unit/agents/test_tenant_skill_pool_scope.py`
- 测试：`tests/unit/security/test_skill_scanner_ast_behavior.py`
- 测试：`tests/unit/security/test_skill_scanner_default_analyzers.py`
- 测试：`market/tests/unit/security/test_skill_scan_history.py`
- 测试：`market/tests/unit/marketplace/test_skills_browse.py`
- 测试：`market/tests/unit/marketplace/test_skills_market.py`

### 第二阶段：Profile、依赖与 Market 对齐

- 修改：`src/swe/security/skill_scanner/models.py`
  - 如 profile、依赖和外部引擎需要跨分析器共享输入，再增加包体清单或可选 `ScanContext`；必须保留现有 `ScanResult.to_dict()` 兼容性。
- 修改：`src/swe/config/config.py`
  - 为 `SkillScannerConfig` 增加 `profile` 和面向未来的 analyzer 开关。
- 修改：`src/swe/security/skill_scanner/scan_policy.py`
  - 增加 profile 感知的策略 helper，同时不改变现有默认策略行为。
- 新建：`src/swe/security/skill_scanner/analyzers/dependency_analyzer.py`
  - 解析 `requirements.txt`、`pyproject.toml`、`package.json` 和 lock 文件。
- 修改：`market/src/market/security/skill_scanner/`
  - 用共享 adapter 替换重复逻辑，或保留一层兼容包装并复用 SWE scanner 模型。
- 修改：`console/src/api/modules/security.ts`
  - 增加扫描 profile 字段和后续 decision payload 类型。
- 测试：`tests/unit/security/test_skill_scanner_profiles.py`
- 测试：`tests/unit/security/test_skill_scanner_dependency_analyzer.py`
- 测试：`market/tests/unit/marketplace/test_skills_market.py`
- 测试：`console/src/api/modules/security.test.ts`

### 第三阶段：语义/数据流、复核与运营

- 新建：`src/swe/security/skill_scanner/analyzers/taint_flow_analyzer.py`
  - 实现 source/sink 启发式检测。
- 新建：`src/swe/security/skill_scanner/analyzers/semantic_analyzer.py`
  - 增加可选 LLM-as-a-judge adapter，仅在 strict profile 启用。
- 新建：`src/swe/security/skill_scanner/external_engines.py`
  - 将 SkillSpector、Agent-Scan、MCP-Scan、SCA CLI 等可选输出归一化为 CoPaw `Finding`。
- 修改：`src/swe/security/skill_scanner/history.py`
  - 扩展记录字段：scan profile、analyzer list、decision、review state。
- 修改：`src/swe/app/routers/config.py`
  - 增加复核与扫描详情接口。
- 修改：`console/src/pages/Settings/Security/index.tsx`
  - 增加复核状态入口和扫描报告展示位置。
- 修改：`console/src/pages/Settings/Security/useSkillScanner.ts`
  - 加载 profile、报告详情、复核决策和重新扫描状态。
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.tsx`
  - 增加 profile 控件、风险卡片、分析器明细行和复核操作。
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.test.tsx`
  - 覆盖 profile 渲染、报告加载和复核操作。
- 测试：为每个新增分析器和 API 契约补充聚焦单元测试。

---

## 迭代计划

### 迭代一：MVP 安全准入

**产出：** 现有 Skill 创建、导入、安装路径通过当前扫描入口获得安全解包边界、包体与 AST 检查能力；Console 复用现有安全页和历史列表完成最小风险可见性，不新增复核型 UI。

**退出标准：**

- `scan_skill_directory()` 在 off、白名单、超时场景仍返回 `None`。
- 现有 pattern analyzer 行为保持兼容。
- 现有 ZIP 外来包在进入运行目录前完成隔离区安全解包校验，Zip Slip、Zip Bomb、符号链接成员、绝对路径成员会被阻断或产出明确 Finding。
- 符号链接、可执行二进制、隐藏可执行文件、嵌套压缩包和 Python 危险执行调用能产出 Findings。
- 现有 SWE Skill manager 调用点无需修改函数签名。
- 现有 Console 安全页 Findings 弹窗能看到新增 analyzer 名称和风险摘要；拦截历史列表能看到来源、用户和分行。
- Market 服务上传、上架或首次启用 Skill 被安全扫描拦截后，记录直接写入 `swe_skill_scan_history` 表，并包含 `source_id`、`user_id`、`bbk_id`；不再创建、读取或追加 `skill_scanner_blocked.json`。

### 迭代二：Profile、依赖/供应链与开源引擎 POC

**产出：** 运维或管理员可以选择 quick/standard/strict 行为，依赖元数据能被一致扫描，并完成开源扫描引擎 adapter 契约与离线 POC。

**退出标准：**

- 配置支持 profile，且不破坏已有 config。
- 默认模式继续保持当前 warning 行为，除非显式修改。
- Dependency analyzer 能在无网络环境下解析 Python 和 Node 依赖声明。
- strict profile 在可用时可选择调用 OSV、pip-audit 或 npm audit。
- `external_engines.py` 能把至少一种开源工具的样例 JSON/文本输出归一化为 CoPaw `Finding`。

### 迭代三：语义、数据流、开源引擎与运营

**产出：** 高风险 Skill 包获得语义/数据流验证和运营复核支持。

**退出标准：**

- strict profile 支持通过标准 adapter 调用 SkillSpector/Cisco Skill Scanner 风格的二级扫描。
- MCP 专项扫描可挂到 Skill/MCP 上传流程。
- 扫描历史和复核 API 暴露 decision state。
- Console 能展示简洁风险卡片和分析器证据。

---

## 第一阶段详细任务

### 任务 1：抽出安全解包边界测试与 helper

**文件：**

- 新建：`src/swe/security/skill_scanner/safe_unpack.py`
- 新建：`tests/unit/security/test_skill_scanner_safe_unpack.py`
- 修改：`src/swe/agents/skills_manager.py`
- 测试：`tests/unit/agents/test_tenant_skill_pool_scope.py`

- [ ] **步骤 1：编写安全解包失败测试**

```python
# -*- coding: utf-8 -*-
"""测试 Skill ZIP 安全解包边界."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pytest

from swe.security.skill_scanner.safe_unpack import safe_unpack_skill_zip


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_safe_unpack_rejects_zip_slip(tmp_path: Path) -> None:
    data = _zip_bytes({"../escape.py": b"print('escape')\n"})

    with pytest.raises(ValueError, match="ZIP 成员路径不安全"):
        safe_unpack_skill_zip(data, tmp_path / "stage")


def test_safe_unpack_rejects_absolute_path(tmp_path: Path) -> None:
    data = _zip_bytes({"/tmp/escape.py": b"print('escape')\n"})

    with pytest.raises(ValueError, match="ZIP 成员路径不安全"):
        safe_unpack_skill_zip(data, tmp_path / "stage")


def test_safe_unpack_rejects_symlink_member(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("demo/link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "/etc/passwd")

    with pytest.raises(ValueError, match="ZIP 符号链接成员不允许"):
        safe_unpack_skill_zip(buffer.getvalue(), tmp_path / "stage")


def test_safe_unpack_rejects_too_many_members(tmp_path: Path) -> None:
    entries = {f"demo/file_{idx}.txt": b"x" for idx in range(4)}
    data = _zip_bytes(entries)

    with pytest.raises(ValueError, match="ZIP 成员数量超过限制"):
        safe_unpack_skill_zip(data, tmp_path / "stage", max_entries=3)


def test_safe_unpack_rejects_oversized_member(tmp_path: Path) -> None:
    data = _zip_bytes({"demo/large.bin": b"abcd"})

    with pytest.raises(ValueError, match="ZIP 单个成员体积超过限制"):
        safe_unpack_skill_zip(data, tmp_path / "stage", max_member_bytes=3)


def test_safe_unpack_extracts_valid_skill(tmp_path: Path) -> None:
    data = _zip_bytes({
        "demo/SKILL.md": b"---\nname: demo\ndescription: demo\n---\n",
    })

    unpacked = safe_unpack_skill_zip(data, tmp_path / "stage")

    assert (unpacked / "demo" / "SKILL.md").exists()
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_safe_unpack.py -v
```

预期：失败，并出现 `ModuleNotFoundError: No module named 'swe.security.skill_scanner.safe_unpack'`。

- [ ] **步骤 3：实现共享安全解包 helper**

```python
# -*- coding: utf-8 -*-
"""Skill 外来压缩包安全解包工具."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Callable

_DEFAULT_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
_DEFAULT_MAX_MEMBER_BYTES = 20 * 1024 * 1024
_DEFAULT_MAX_ENTRIES = 2000
MemberNameDecoder = Callable[[zipfile.ZipInfo], str]


def safe_unpack_skill_zip(
    data: bytes,
    target_dir: Path,
    *,
    max_uncompressed_bytes: int = _DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_member_bytes: int = _DEFAULT_MAX_MEMBER_BYTES,
    max_entries: int = _DEFAULT_MAX_ENTRIES,
    decode_member_name: MemberNameDecoder | None = None,
) -> Path:
    """将 Skill ZIP 安全解包到隔离目录."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("上传文件不是有效的 ZIP 压缩包")

    target_dir.mkdir(parents=True, exist_ok=True)
    root_path = target_dir.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > max_entries:
            raise ValueError("ZIP 成员数量超过限制")

        total_size = sum(info.file_size for info in members)
        if total_size > max_uncompressed_bytes:
            raise ValueError("ZIP 解压后体积超过限制")
        if any(info.file_size > max_member_bytes for info in members):
            raise ValueError("ZIP 单个成员体积超过限制")

        for info in members:
            member_name = _normalized_member_name(info, decode_member_name)
            target = (target_dir / member_name).resolve()
            if not target.is_relative_to(root_path):
                raise ValueError(f"ZIP 成员路径不安全: {member_name}")
            if _is_symlink(info):
                raise ValueError(f"ZIP 符号链接成员不允许: {member_name}")

        for info in members:
            member_name = _normalized_member_name(info, decode_member_name)
            target = (target_dir / member_name).resolve()
            _extract_member(archive, info, target)
    return target_dir


def _normalized_member_name(
    info: zipfile.ZipInfo,
    decode_member_name: MemberNameDecoder | None,
) -> str:
    raw_name = decode_member_name(info) if decode_member_name else info.filename
    member_name = (raw_name or "").replace("\\", "/").strip()
    if not member_name or member_name.startswith("/"):
        raise ValueError(f"ZIP 成员路径不安全: {member_name}")
    return member_name


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return info.external_attr >> 16 & 0o120000 == 0o120000


def _extract_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    target: Path,
) -> None:
    if info.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as source, open(target, "wb") as dest:
        shutil.copyfileobj(source, dest, length=1024 * 1024)
```

- [ ] **步骤 4：让 Skill ZIP 导入入口复用 helper**

在 `src/swe/agents/skills_manager.py` 中保留 `_decode_zip_member_name()` 兼容中文成员名；将 `_extract_and_validate_zip(data, tmp_dir)` 改为委托 `safe_unpack_skill_zip()`，并通过 `decode_member_name` 参数保持 GBK 成员名兼容。

```python
from ..security.skill_scanner.safe_unpack import safe_unpack_skill_zip


def _extract_and_validate_zip(data: bytes, tmp_dir: Path) -> None:
    """复用统一安全解包边界，保持原 ZIP 导入入口行为稳定."""
    try:
        safe_unpack_skill_zip(
            data,
            tmp_dir,
            max_uncompressed_bytes=_MAX_ZIP_BYTES,
            decode_member_name=_decode_zip_member_name,
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
```

同时在 `tests/unit/agents/test_tenant_skill_pool_scope.py` 或邻近 ZIP 导入测试中增加失败清理断言，使用路径穿越 ZIP 触发异常，并确认临时导入目录不会残留有效 Skill 内容：

```python
def test_import_from_zip_cleans_stage_on_unsafe_zip(tmp_path: Path) -> None:
    service = _build_skill_service(tmp_path)
    data = _zip_bytes({"../escape.py": b"print('escape')\n"})

    with pytest.raises(ValueError):
        service.import_from_zip(data=data)

    assert not any(tmp_path.rglob("escape.py"))
```

- [ ] **步骤 5：运行安全解包与现有 ZIP 导入回归**

运行：

```bash
venv/bin/python -m pytest \
  tests/unit/security/test_skill_scanner_safe_unpack.py \
  tests/unit/agents/test_tenant_skill_pool_scope.py::test_import_from_zip_is_tenant_scoped \
  tests/unit/agents/test_tenant_skill_pool_scope.py::test_import_from_zip_overwrite_false_rejected \
  tests/unit/agents/test_utf8_skill_cleanup.py::test_extract_zip_skills_recovers_gbk_chinese_member_names \
  -v
```

预期：通过。

- [ ] **步骤 6：提交安全解包边界**

```bash
git add \
  src/swe/security/skill_scanner/safe_unpack.py \
  src/swe/agents/skills_manager.py \
  tests/unit/security/test_skill_scanner_safe_unpack.py
git commit -m "feat(security): share safe skill zip unpacking"
```

### 任务 2：增加 Package Analyzer 测试样例

**文件：**

- 新建：`tests/unit/security/test_skill_scanner_package_analyzer.py`
- 参考：`src/swe/security/skill_scanner/models.py`
- 参考：`src/swe/security/skill_scanner/analyzers/__init__.py`

- [ ] **步骤 1：编写包体层风险的失败测试**

```python
# -*- coding: utf-8 -*-
"""测试 Skill 包体安全分析器."""

from __future__ import annotations

import os
import stat
import zipfile
from pathlib import Path

from swe.security.skill_scanner.analyzers.package_analyzer import (
    PackageAnalyzer,
)
from swe.security.skill_scanner.models import Severity, ThreatCategory


def _write_skill(skill_root: Path) -> None:
    skill_root.mkdir(parents=True, exist_ok=True)
    (skill_root / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill package\n---\n",
        encoding="utf-8",
    )


def test_package_analyzer_flags_symlink_escape(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    os.symlink("/etc/passwd", skill_root / "passwd_link")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_SYMLINK_ESCAPE" for f in findings)
    finding = next(f for f in findings if f.rule_id == "PACKAGE_SYMLINK_ESCAPE")
    assert finding.severity == Severity.CRITICAL
    assert finding.category == ThreatCategory.SUPPLY_CHAIN_ATTACK


def test_package_analyzer_flags_binary_extension(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    binary_path = skill_root / "bin" / "helper"
    binary_path.parent.mkdir()
    binary_path.write_bytes(b"\x7fELF\x02\x01\x01\x00payload")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_EXECUTABLE_BINARY" for f in findings)


def test_package_analyzer_flags_hidden_executable_script(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    hidden_script = skill_root / ".hidden.py"
    hidden_script.write_text("print('hidden')\n", encoding="utf-8")
    hidden_script.chmod(hidden_script.stat().st_mode | stat.S_IXUSR)

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_HIDDEN_EXECUTABLE" for f in findings)


def test_package_analyzer_flags_zip_slip_archive_entry(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    archive_path = skill_root / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("../../escape.py", "print('escape')\n")

    findings = PackageAnalyzer().analyze(skill_root, [], skill_name="demo")

    assert any(f.rule_id == "PACKAGE_ARCHIVE_PATH_TRAVERSAL" for f in findings)


def test_package_analyzer_flags_oversized_file(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    _write_skill(skill_root)
    large_path = skill_root / "large.dat"
    large_path.write_bytes(b"abcd")

    findings = PackageAnalyzer(max_file_bytes=3).analyze(
        skill_root,
        [],
        skill_name="demo",
    )

    assert any(f.rule_id == "PACKAGE_OVERSIZED_FILE" for f in findings)
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_package_analyzer.py -v
```

预期：失败，并出现 `ModuleNotFoundError: No module named 'swe.security.skill_scanner.analyzers.package_analyzer'`。

- [ ] **步骤 3：提交测试脚手架**

```bash
git add tests/unit/security/test_skill_scanner_package_analyzer.py
git commit -m "test(security): cover skill package analyzer risks"
```

### 任务 3：实现 PackageAnalyzer

**文件：**

- 新建：`src/swe/security/skill_scanner/analyzers/package_analyzer.py`
- 测试：`tests/unit/security/test_skill_scanner_package_analyzer.py`

- [ ] **步骤 1：实现分析器**

```python
# -*- coding: utf-8 -*-
"""Skill 包体安全分析器."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

from ..models import Finding, Severity, SkillFile, ThreatCategory
from . import BaseAnalyzer

_BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".o",
    ".a",
}
_ARCHIVE_EXTENSIONS = {".zip"}
_EXECUTABLE_MAGIC = (b"\x7fELF", b"MZ")
_DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024


class PackageAnalyzer(BaseAnalyzer):
    """检查 Skill 包体结构中的高风险文件."""

    def __init__(self, *, max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES) -> None:
        super().__init__(name="package")
        self._max_file_bytes = max_file_bytes

    def analyze(
        self,
        skill_dir: Path,
        files: list[SkillFile],
        *,
        skill_name: str | None = None,
    ) -> list[Finding]:
        """扫描包体层风险并返回发现项."""
        del files, skill_name
        findings: list[Finding] = []
        for path in sorted(skill_dir.rglob("*")):
            rel_path = _relative_path(path, skill_dir)
            if path.is_symlink():
                findings.append(_finding(
                    "PACKAGE_SYMLINK_ESCAPE",
                    Severity.CRITICAL,
                    "Skill 包中包含符号链接",
                    rel_path,
                    "移除 Skill 包中的符号链接，改用可审计的普通文件。",
                ))
                continue
            if not path.is_file():
                continue
            if path.stat().st_size > self._max_file_bytes:
                findings.append(_finding(
                    "PACKAGE_OVERSIZED_FILE",
                    Severity.HIGH,
                    "Skill 包中包含超大文件",
                    rel_path,
                    "移除不必要的大文件，或拆分为外部受控资源。",
                ))
            if _is_executable_binary(path):
                findings.append(_finding(
                    "PACKAGE_EXECUTABLE_BINARY",
                    Severity.CRITICAL,
                    "Skill 包中包含可执行二进制内容",
                    rel_path,
                    "移除二进制可执行文件，改用可审计脚本或受控工具。",
                ))
            if _is_hidden_executable(path, skill_dir):
                findings.append(_finding(
                    "PACKAGE_HIDDEN_EXECUTABLE",
                    Severity.HIGH,
                    "Skill 包中包含隐藏可执行代码",
                    rel_path,
                    "将可执行代码放在显式路径中，并补充用途说明。",
                ))
            if path.suffix.lower() in _ARCHIVE_EXTENSIONS:
                findings.extend(_scan_zip(path, rel_path))
        return findings


def _relative_path(path: Path, skill_dir: Path) -> str:
    try:
        return str(path.relative_to(skill_dir))
    except ValueError:
        return str(path)


def _is_executable_binary(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_EXTENSIONS:
        return True
    try:
        head = path.read_bytes()[:4]
    except OSError:
        return False
    return any(head.startswith(magic) for magic in _EXECUTABLE_MAGIC)


def _is_hidden_executable(path: Path, skill_dir: Path) -> bool:
    rel_parts = path.relative_to(skill_dir).parts
    if not any(part.startswith(".") for part in rel_parts):
        return False
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & stat.S_IXUSR)


def _scan_zip(path: Path, rel_path: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    findings.append(_finding(
                        "PACKAGE_ARCHIVE_PATH_TRAVERSAL",
                        Severity.CRITICAL,
                        "嵌套压缩包包含路径穿越成员",
                        rel_path,
                        "移除嵌套压缩包中的路径穿越成员。",
                        snippet=name,
                    ))
    except zipfile.BadZipFile:
        findings.append(_finding(
            "PACKAGE_ARCHIVE_UNREADABLE",
            Severity.MEDIUM,
            "嵌套压缩包无法被检查",
            rel_path,
            "将不可读压缩包替换为可审计的普通文件。",
        ))
    return findings


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    file_path: str,
    remediation: str,
    *,
    snippet: str | None = None,
) -> Finding:
    return Finding(
        id=f"{rule_id}:{file_path}",
        rule_id=rule_id,
        category=ThreatCategory.SUPPLY_CHAIN_ATTACK,
        severity=severity,
        title=title,
        description=title,
        file_path=file_path,
        snippet=snippet,
        remediation=remediation,
        analyzer="package",
    )
```

- [ ] **步骤 2：运行 package analyzer 测试**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_package_analyzer.py -v
```

预期：通过。

- [ ] **步骤 3：提交实现**

```bash
git add src/swe/security/skill_scanner/analyzers/package_analyzer.py tests/unit/security/test_skill_scanner_package_analyzer.py
git commit -m "feat(security): add skill package analyzer"
```

### 任务 4：增加 AST 行为分析器测试

**文件：**

- 新建：`tests/unit/security/test_skill_scanner_ast_behavior.py`
- 参考：`src/swe/security/skill_scanner/analyzers/__init__.py`

- [ ] **步骤 1：编写 Python 危险行为的失败测试**

```python
# -*- coding: utf-8 -*-
"""测试 Python AST 行为分析器."""

from __future__ import annotations

from pathlib import Path

from swe.security.skill_scanner.analyzers.ast_behavior_analyzer import (
    AstBehaviorAnalyzer,
)
from swe.security.skill_scanner.models import SkillFile


def _skill_file(path: Path, skill_root: Path) -> SkillFile:
    return SkillFile.from_path(path, skill_root)


def test_ast_behavior_flags_eval(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    code_path = skill_root / "main.py"
    code_path.write_text("def run(user_code):\n    return eval(user_code)\n")

    findings = AstBehaviorAnalyzer().analyze(
        skill_root,
        [_skill_file(code_path, skill_root)],
        skill_name="demo",
    )

    assert any(f.rule_id == "AST_DANGEROUS_EVAL" for f in findings)


def test_ast_behavior_flags_subprocess_shell_true(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    code_path = skill_root / "main.py"
    code_path.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    return subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )

    findings = AstBehaviorAnalyzer().analyze(
        skill_root,
        [_skill_file(code_path, skill_root)],
        skill_name="demo",
    )

    assert any(f.rule_id == "AST_SUBPROCESS_SHELL_TRUE" for f in findings)


def test_ast_behavior_ignores_documentation_markdown(tmp_path: Path) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    doc_path = skill_root / "README.md"
    doc_path.write_text("Example: eval(user_code)\n", encoding="utf-8")

    findings = AstBehaviorAnalyzer().analyze(
        skill_root,
        [_skill_file(doc_path, skill_root)],
        skill_name="demo",
    )

    assert findings == []
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_ast_behavior.py -v
```

预期：失败，并出现 `ModuleNotFoundError: No module named 'swe.security.skill_scanner.analyzers.ast_behavior_analyzer'`。

- [ ] **步骤 3：提交测试脚手架**

```bash
git add tests/unit/security/test_skill_scanner_ast_behavior.py
git commit -m "test(security): cover skill AST behavior analyzer"
```

### 任务 5：实现 AstBehaviorAnalyzer

**文件：**

- 新建：`src/swe/security/skill_scanner/analyzers/ast_behavior_analyzer.py`
- 测试：`tests/unit/security/test_skill_scanner_ast_behavior.py`

- [ ] **步骤 1：实现分析器**

```python
# -*- coding: utf-8 -*-
"""Python AST 行为安全分析器."""

from __future__ import annotations

import ast
from pathlib import Path

from ..models import Finding, Severity, SkillFile, ThreatCategory
from . import BaseAnalyzer

_DANGEROUS_BUILTINS = {
    "eval": "AST_DANGEROUS_EVAL",
    "exec": "AST_DANGEROUS_EXEC",
    "compile": "AST_DANGEROUS_COMPILE",
}


class AstBehaviorAnalyzer(BaseAnalyzer):
    """通过 AST 识别 Python 技能中的危险行为."""

    def __init__(self) -> None:
        super().__init__(name="ast_behavior")

    def analyze(
        self,
        skill_dir: Path,
        files: list[SkillFile],
        *,
        skill_name: str | None = None,
    ) -> list[Finding]:
        """扫描 Python 文件并返回 AST 行为发现项."""
        del skill_dir, skill_name
        findings: list[Finding] = []
        for sf in files:
            if sf.file_type != "python":
                continue
            content = sf.read_content()
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            visitor = _DangerousCallVisitor(sf.relative_path)
            visitor.visit(tree)
            findings.extend(visitor.findings)
        return findings


class _DangerousCallVisitor(ast.NodeVisitor):
    """收集危险函数调用."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        rule_id = self._rule_for_call(node)
        if rule_id is not None:
            self.findings.append(_finding(
                rule_id,
                self.relative_path,
                node.lineno,
            ))
        self.generic_visit(node)

    def _rule_for_call(self, node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return _DANGEROUS_BUILTINS.get(node.func.id)
        if _is_subprocess_shell_true(node):
            return "AST_SUBPROCESS_SHELL_TRUE"
        if _is_os_system(node):
            return "AST_OS_SYSTEM"
        return None


def _is_subprocess_shell_true(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"run", "call", "Popen"}:
        return False
    if not isinstance(node.func.value, ast.Name):
        return False
    if node.func.value.id != "subprocess":
        return False
    return any(
        kw.arg == "shell"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is True
        for kw in node.keywords
    )


def _is_os_system(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "system":
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "os"


def _finding(rule_id: str, file_path: str, line_number: int) -> Finding:
    title = {
        "AST_DANGEROUS_EVAL": "检测到 Python eval() 动态执行",
        "AST_DANGEROUS_EXEC": "检测到 Python exec() 动态执行",
        "AST_DANGEROUS_COMPILE": "检测到 Python compile() 动态编译",
        "AST_SUBPROCESS_SHELL_TRUE": "检测到 shell=True 的 subprocess 调用",
        "AST_OS_SYSTEM": "检测到 os.system() 命令执行",
    }[rule_id]
    severity = (
        Severity.CRITICAL
        if rule_id in {"AST_DANGEROUS_EVAL", "AST_DANGEROUS_EXEC"}
        else Severity.HIGH
    )
    return Finding(
        id=f"{rule_id}:{file_path}:{line_number}",
        rule_id=rule_id,
        category=ThreatCategory.COMMAND_INJECTION,
        severity=severity,
        title=title,
        description=title,
        file_path=file_path,
        line_number=line_number,
        remediation=(
            "移除动态代码执行，或替换为参数受限且经过校验的 API。"
        ),
        analyzer="ast_behavior",
    )
```

- [ ] **步骤 2：运行 AST analyzer 测试**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_ast_behavior.py -v
```

预期：通过。

- [ ] **步骤 3：提交实现**

```bash
git add src/swe/security/skill_scanner/analyzers/ast_behavior_analyzer.py tests/unit/security/test_skill_scanner_ast_behavior.py
git commit -m "feat(security): add skill AST behavior analyzer"
```

### 任务 6：默认注册 MVP 分析器

**文件：**

- 修改：`src/swe/security/skill_scanner/scanner.py`
- 修改：`src/swe/security/skill_scanner/__init__.py`
- 新建：`tests/unit/security/test_skill_scanner_default_analyzers.py`

- [ ] **步骤 1：编写默认分析器注册的失败测试**

```python
# -*- coding: utf-8 -*-
"""测试默认 Skill 扫描器加载 MVP 分析器."""

from __future__ import annotations

from pathlib import Path

from swe.security.skill_scanner.scanner import SkillScanner


def test_default_scanner_uses_package_pattern_and_ast_analyzers(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    (skill_root / "main.py").write_text("def run(x):\n    return eval(x)\n")

    result = SkillScanner().scan_skill(skill_root, skill_name="demo")

    assert {"package", "pattern", "ast_behavior"}.issubset(
        set(result.analyzers_used),
    )
    assert any(f.rule_id == "AST_DANGEROUS_EVAL" for f in result.findings)
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_default_analyzers.py -v
```

预期：失败，因为 `analyzers_used` 中没有 `ast_behavior`。

- [ ] **步骤 3：修改 `scanner.py` 的 import 和默认分析器列表**

增加 import：

```python
from .analyzers.ast_behavior_analyzer import AstBehaviorAnalyzer
from .analyzers.package_analyzer import PackageAnalyzer
```

替换 `_default_analyzers()`：

```python
    @staticmethod
    def _default_analyzers(
        policy: ScanPolicy | None = None,
    ) -> list[BaseAnalyzer]:
        """实例化默认分析器集合."""
        analyzers: list[BaseAnalyzer] = []

        for factory in (
            lambda: PackageAnalyzer(),
            lambda: PatternAnalyzer(policy=policy),
            lambda: AstBehaviorAnalyzer(),
        ):
            try:
                analyzers.append(factory())
            except Exception as exc:
                logger.error("加载 Skill 安全分析器失败: %s", exc)

        return analyzers
```

- [ ] **步骤 4：在 `__init__.py` 导出分析器**

增加 import：

```python
from .analyzers.ast_behavior_analyzer import AstBehaviorAnalyzer
from .analyzers.package_analyzer import PackageAnalyzer
```

加入 `__all__`：

```python
    "AstBehaviorAnalyzer",
    "PackageAnalyzer",
```

- [ ] **步骤 5：运行聚焦测试**

运行：

```bash
venv/bin/python -m pytest \
  tests/unit/security/test_skill_scanner_default_analyzers.py \
  tests/unit/security/test_skill_scanner_package_analyzer.py \
  tests/unit/security/test_skill_scanner_ast_behavior.py \
  tests/unit/security/test_skill_scanner_executor.py \
  tests/unit/security/test_skill_scanner_hook_files.py \
  -v
```

预期：通过。

- [ ] **步骤 6：提交分析器注册**

```bash
git add \
  src/swe/security/skill_scanner/scanner.py \
  src/swe/security/skill_scanner/__init__.py \
  tests/unit/security/test_skill_scanner_default_analyzers.py
git commit -m "feat(security): enable MVP skill scan analyzers"
```

### 任务 7：Console 展示 analyzer 最小可见性

**文件：**

- 修改：`console/src/api/modules/security.ts`
- 修改：`console/src/api/modules/security.test.ts`
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.tsx`
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.test.tsx`
- 修改：`console/src/locales/zh.json`
- 修改：`console/src/locales/en.json`

- [ ] **步骤 1：补充前端类型与失败测试**

在 `console/src/api/modules/security.ts` 的 `BlockedSkillFinding` 中加入可选字段，并新增 `BlockedSkillRecord` 类型：

```ts
export interface BlockedSkillFinding {
  severity: string;
  title: string;
  description: string;
  file_path: string;
  line_number: number | null;
  rule_id: string;
  analyzer?: string | null;
}

export interface BlockedSkillRecord {
  id: string;
  source_id: string;
  user_id: string;
  bbk_id: string;
  skill_name: string;
  blocked_at: string;
  max_severity: string;
  findings: BlockedSkillFinding[];
  content_hash: string;
  action: "blocked" | "warned";
}
```

在 `SkillScannerSection.test.tsx` 中增加一条历史记录样例，确保 findings 中包含 `analyzer: "ast_behavior"` 时弹窗可以看到该值，并且表格能看到 `source_id`、`user_id`、`bbk_id`：

```tsx
expect(screen.getByText("ast_behavior")).toBeInTheDocument();
expect(screen.getByText("portal")).toBeInTheDocument();
expect(screen.getByText("alice")).toBeInTheDocument();
expect(screen.getByText("1001")).toBeInTheDocument();
```

- [ ] **步骤 2：补充 API 与本地化测试**

在 `console/src/api/modules/security.test.ts` 中补充扫描历史响应样例，确保 `BlockedSkillRecord` 保留 `source_id`、`user_id`、`bbk_id`，`BlockedSkillFinding` 保留 `analyzer`。

在 `console/src/locales/zh.json` 和 `console/src/locales/en.json` 的 `security.skillScanner.scanAlerts` 下补充列名：

```json
{
  "source": "来源",
  "user": "用户",
  "bbk": "分行",
  "analyzer": "分析器"
}
```

英文文案使用：

```json
{
  "source": "Source",
  "user": "User",
  "bbk": "BBK",
  "analyzer": "Analyzer"
}
```

- [ ] **步骤 3：在历史表和 Findings 弹窗增加列**

在 `SkillScannerSection.tsx` 的历史表格 columns 中加入：

```tsx
{
  title: t("security.skillScanner.scanAlerts.source"),
  dataIndex: "source_id",
  key: "source_id",
  width: 120,
  render: (value: string | null | undefined) => value || "-",
},
{
  title: t("security.skillScanner.scanAlerts.user"),
  dataIndex: "user_id",
  key: "user_id",
  width: 120,
  render: (value: string | null | undefined) => value || "-",
},
{
  title: t("security.skillScanner.scanAlerts.bbk"),
  dataIndex: "bbk_id",
  key: "bbk_id",
  width: 120,
  render: (value: string | null | undefined) => value || "-",
},
```

在 Findings 弹窗的 columns 中加入：

```tsx
{
  title: t("security.skillScanner.scanAlerts.analyzer"),
  dataIndex: "analyzer",
  key: "analyzer",
  width: 120,
  render: (value: string | null | undefined) => value || "-",
},
```

- [ ] **步骤 4：运行 Console 聚焦测试**

运行：

```bash
cd console && npm run test:run -- src/pages/Settings/Security/components/SkillScannerSection.test.tsx src/api/modules/security.test.ts
```

预期：通过；如果仓库当前没有可用 npm test 脚本，执行现有前端测试命令并在交付说明记录。

- [ ] **步骤 5：提交 Console 最小可见性**

```bash
git add \
  console/src/api/modules/security.ts \
  console/src/api/modules/security.test.ts \
  console/src/pages/Settings/Security/components/SkillScannerSection.tsx \
  console/src/pages/Settings/Security/components/SkillScannerSection.test.tsx \
  console/src/locales/zh.json \
  console/src/locales/en.json
git commit -m "feat(security): show skill scan analyzer in console"
```

### 任务 8：记录第一阶段运行行为

**文件：**

- 修改：`analysis/security-and-governance.md`
- 修改：`analysis/agent-and-orchestration.md`

- [ ] **步骤 1：更新安全分析文档**

在 `analysis/security-and-governance.md` 的“其他安全边界”表格中加入：

```markdown
| `src/swe/security/skill_scanner/analyzers/package_analyzer.py` | Skill 包体安全检测，覆盖符号链接、二进制、隐藏可执行文件、嵌套压缩包路径穿越等入口风险 |
| `src/swe/security/skill_scanner/analyzers/ast_behavior_analyzer.py` | Python AST 行为检测，覆盖动态执行、shell 执行等高风险代码行为 |
```

在“治理范围”中加入：

```markdown
- Skill 扫描采用分层策略：包体与上下文先建立可信输入，静态规则和 AST 分析只产出证据，block/warn/off 与后续准入策略负责最终决策
```

- [ ] **步骤 2：更新 Agent 编排文档**

在 `analysis/agent-and-orchestration.md` 中扩展 `skills_manager.py` 描述：

```markdown
| `src/swe/agents/skills_manager.py`, `src/swe/agents/skills_hub.py` | 技能扫描、加载、分发；创建、导入和启用前通过 `scan_skill_directory()` 进入安全扫描闸口 |
```

- [ ] **步骤 3：运行文档 grep 检查**

运行：

```bash
rg -n "package_analyzer|ast_behavior_analyzer|scan_skill_directory\(\)" analysis/security-and-governance.md analysis/agent-and-orchestration.md
```

预期：输出包含全部三个关键词。

- [ ] **步骤 4：提交文档**

```bash
git add analysis/security-and-governance.md analysis/agent-and-orchestration.md
git commit -m "docs(security): document skill scan MVP layers"
```

### 任务 9：Market 拦截历史直接写数据库

**文件：**

- 修改：`src/swe/security/skill_scanner/history.py`
- 测试：`tests/unit/security/test_skill_scan_history.py`
- 新建：`market/src/market/security/skill_scanner/history.py`
- 修改：`market/src/market/security/skill_scanner/__init__.py`
- 修改：`market/src/market/app/_app.py`
- 修改：`market/src/market/app/routers/skills_browse.py`
- 修改：`market/src/market/app/routers/skills_market.py`
- 修改：`market/src/market/marketplace/service.py`
- 测试：`market/tests/unit/security/test_skill_scan_history.py`
- 测试：`market/tests/unit/marketplace/test_skills_browse.py`
- 测试：`market/tests/unit/marketplace/test_skills_market.py`

- [ ] **步骤 1：编写 Market 数据库历史写入测试**

在 `market/tests/unit/security/test_skill_scan_history.py` 中新增测试，确认写入目标是 `swe_skill_scan_history` 表，写入内容包含 `source_id`、`user_id`、`bbk_id`，且不会触碰 `skill_scanner_blocked.json`：

```python
# -*- coding: utf-8 -*-
"""测试 Market Skill 扫描历史直接写数据库."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from market.security.skill_scanner.history import (
    BlockedSkillRecord,
    SkillScanHistoryStore,
)


class _Db:
    is_connected = True

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []

    async def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | None = None,
    ) -> int:
        self.executed.append((sql, params))
        return 1


@pytest.mark.asyncio
async def test_market_skill_scan_history_inserts_database_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_SWE_ROOT", str(tmp_path))
    db = _Db()
    store = SkillScanHistoryStore(db)

    await store.insert(
        BlockedSkillRecord(
            source_id="portal",
            user_id="alice",
            bbk_id="1001",
            skill_name="danger",
            blocked_at="2026-08-18T08:00:00+00:00",
            max_severity="CRITICAL",
            findings=[
                {
                    "severity": "CRITICAL",
                    "title": "danger",
                    "description": "eval",
                    "file_path": "main.py",
                    "line_number": 1,
                    "rule_id": "AST_DANGEROUS_EVAL",
                    "analyzer": "ast_behavior",
                },
            ],
            content_hash="abc",
            action="blocked",
        ),
    )

    assert any("swe_skill_scan_history" in sql for sql, _ in db.executed)
    insert_sql, params = db.executed[-1]
    assert "INSERT INTO swe_skill_scan_history" in insert_sql
    assert params is not None
    assert params[1:4] == ("portal", "alice", "1001")
    assert params[4] == "danger"
    assert json.loads(params[7])[0]["analyzer"] == "ast_behavior"
    assert not (tmp_path / "skill_scanner_blocked.json").exists()
```

同文件再补一条 `flush()` 测试，确保接口可以在返回拦截错误前等待已接受的写库任务完成：

```python
@pytest.mark.asyncio
async def test_market_skill_scan_history_flush_waits_for_insert() -> None:
    db = _Db()
    store = SkillScanHistoryStore(db)
    accepted = store.submit(
        BlockedSkillRecord(
            source_id="portal",
            user_id="alice",
            bbk_id="1001",
            skill_name="danger",
            blocked_at="2026-08-18T08:00:00+00:00",
            max_severity="HIGH",
        ),
    )

    assert accepted is True
    await store.flush()
    assert any("INSERT INTO swe_skill_scan_history" in sql for sql, _ in db.executed)
```

这两个 Market 测试不能调用 `store.initialize()`，也不能断言任何 `CREATE TABLE`、`ALTER TABLE` 行为。Market 不是表结构 owner，只能在数据库已可用时写入 SWE 已维护的共享表。

- [ ] **步骤 2：补充 SWE 历史表上下文字段测试**

在 `tests/unit/security/test_skill_scan_history.py` 中补充测试，确认 SWE 侧 store 初始化不执行 DDL，插入和读取 API 模型都保留 `source_id`、`user_id`、`bbk_id`：

```python
@pytest.mark.asyncio
async def test_skill_scan_history_preserves_actor_context() -> None:
    db = _MockDb()
    store = SkillScanHistoryStore(db)

    await store.initialize()
    await store.insert(
        BlockedSkillRecord(
            source_id="portal",
            user_id="alice",
            bbk_id="1001",
            skill_name="danger",
            blocked_at="2026-08-18T08:00:00+00:00",
            max_severity="CRITICAL",
            findings=[],
            content_hash="abc",
            action="blocked",
        ),
    )

    insert_sql, params = db.executed[-1]
    assert "INSERT INTO swe_skill_scan_history" in insert_sql
    assert params is not None
    assert params[1:4] == ("portal", "alice", "1001")

    record = BlockedSkillRecord(
        source_id="portal",
        user_id="alice",
        bbk_id="1001",
        skill_name="danger",
        blocked_at="2026-08-18T08:00:00+00:00",
        max_severity="CRITICAL",
    )
    payload = record.to_dict()
    assert payload["source_id"] == "portal"
    assert payload["user_id"] == "alice"
    assert payload["bbk_id"] == "1001"
```

在 `deploy/migrations/2026_08_19_create_swe_skill_scan_history.sql` 和 `scripts/sql/skill_scan_history_tables.sql` 中提供独立迁移脚本，确认三列是逐列补齐，不能合并成一条 `ALTER TABLE`：

```python
@pytest.mark.asyncio
async def test_skill_scan_history_migrates_context_columns_individually() -> None:
    db = _MockDb()
    store = SkillScanHistoryStore(db)

    await store.initialize()

    alter_statements = [
        sql for sql, _ in db.executed
        if sql.strip().upper().startswith("ALTER TABLE swe_skill_scan_history".upper())
    ]
    assert any("ADD COLUMN source_id" in sql for sql in alter_statements)
    assert any("ADD COLUMN user_id" in sql for sql in alter_statements)
    assert any("ADD COLUMN bbk_id" in sql for sql in alter_statements)
    assert len(alter_statements) >= 3
```

- [ ] **步骤 3：运行测试并确认失败**

运行：

```bash
venv/bin/python -m pytest \
  tests/unit/security/test_skill_scan_history.py \
  market/tests/unit/security/test_skill_scan_history.py \
  -v
```

预期：失败；Market 测试会出现 `ModuleNotFoundError: No module named 'market.security.skill_scanner.history'`，SWE 测试会因 `BlockedSkillRecord` 尚未包含 `source_id`、`user_id`、`bbk_id` 失败。

- [ ] **步骤 4：扩展 SWE 数据库历史表结构**

修改 `src/swe/security/skill_scanner/history.py`，为 `BlockedSkillRecord`、`to_dict()`、`insert()`、`_row_to_record()`、`_INSERT_RECORD`、`_LIST_RECORDS`、`_GET_LATEST_WARNING` 补齐 `source_id`、`user_id`、`bbk_id`。`initialize()` 只校验数据库可用，不执行 `CREATE TABLE` 或 `ALTER TABLE`。

新增列必须允许空字符串默认值，避免破坏已有调用方：

```sql
source_id VARCHAR(128) NOT NULL DEFAULT '',
user_id VARCHAR(255) NOT NULL DEFAULT '',
bbk_id VARCHAR(128) NOT NULL DEFAULT '',
```

建表和已有表补列由独立 SQL 脚本执行。因为 `CREATE TABLE IF NOT EXISTS` 不会给已有表补字段，必须显式处理旧表；三列不能放进同一条 `ALTER TABLE`，否则线上若只缺其中一两列，会因已存在列报错导致剩余缺失列无法补上：

```python
_CONTEXT_COLUMN_MIGRATIONS = (
    "ALTER TABLE swe_skill_scan_history "
    "ADD COLUMN source_id VARCHAR(128) NOT NULL DEFAULT '' AFTER id",
    "ALTER TABLE swe_skill_scan_history "
    "ADD COLUMN user_id VARCHAR(255) NOT NULL DEFAULT '' AFTER source_id",
    "ALTER TABLE swe_skill_scan_history "
    "ADD COLUMN bbk_id VARCHAR(128) NOT NULL DEFAULT '' AFTER user_id",
)
```

执行迁移脚本时通过 `information_schema` 判断缺失列和索引，只补缺失对象。若项目已有通用 schema migration helper，优先复用项目既有 helper，不新增迁移框架。

`_CREATE_TABLE`、`_INSERT_RECORD`、`_LIST_RECORDS` 和 `_GET_LATEST_WARNING` 的字段顺序要保持一致：`id, source_id, user_id, bbk_id, skill_name, blocked_at, max_severity, findings_json, content_hash, action`。这样 SWE API 返回给 Console 的历史记录和 Market 插入的历史记录使用同一套列语义。

- [ ] **步骤 5：实现 Market 数据库历史写入器**

在 `market/src/market/security/skill_scanner/history.py` 中实现与 SWE Console 兼容的表写入器。它只负责写表，不提供本地文件 fallback，也不维护建表或迁移逻辑；表名、列名和写入顺序必须与 SWE 侧一致。写入器要提供 `submit()` 和 `flush()`，接口在返回拦截错误前调用 `flush()` 等待已接受记录完成：

```python
# -*- coding: utf-8 -*-
"""Market Skill scan history persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_INSERT_RECORD = """
    INSERT INTO swe_skill_scan_history (
        id, source_id, user_id, bbk_id,
        skill_name, blocked_at, max_severity,
        findings_json, content_hash, action
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass(frozen=True)
class BlockedSkillRecord:
    skill_name: str
    blocked_at: str
    max_severity: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    content_hash: str = ""
    action: str = "blocked"
    source_id: str = ""
    user_id: str = ""
    bbk_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class SkillScanHistoryStore:
    def __init__(self, db: Any | None = None) -> None:
        self.db = db
        self._pending: set[asyncio.Task[None]] = set()

    @property
    def is_available(self) -> bool:
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    async def insert(self, record: BlockedSkillRecord) -> None:
        if not self.is_available:
            return
        await self.db.execute(
            _INSERT_RECORD,
            (
                record.id,
                record.source_id,
                record.user_id,
                record.bbk_id,
                record.skill_name,
                _to_database_datetime(record.blocked_at),
                record.max_severity,
                json.dumps(record.findings, ensure_ascii=False),
                record.content_hash,
                record.action,
            ),
        )

    def submit(self, record: BlockedSkillRecord) -> bool:
        if not self.is_available:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        task = loop.create_task(self.insert(record))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return True

    async def flush(self) -> None:
        while self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)


def _to_database_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
```

- [ ] **步骤 6：让 Market scanner 使用数据库写入器**

修改 `market/src/market/security/skill_scanner/__init__.py`：

```python
from .history import BlockedSkillRecord, SkillScanHistoryStore

_history_store: SkillScanHistoryStore | None = None


def install_skill_scan_history_store(
    store: SkillScanHistoryStore | None,
) -> None:
    global _history_store
    _history_store = store


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    return {
        "severity": f.severity.value,
        "title": f.title,
        "description": f.description,
        "file_path": f.file_path,
        "line_number": f.line_number,
        "rule_id": f.rule_id,
        "analyzer": f.analyzer,
    }
```

将 Market 侧 `scan_skill_directory()` 增加仅 Market 内部使用的可选上下文参数：

```python
def scan_skill_directory(
    skill_dir: str | Path,
    *,
    skill_name: str | None = None,
    block: bool | None = None,
    timeout: float | None = None,
    source_id: str = "",
    user_id: str = "",
    bbk_id: str = "",
) -> ScanResult | None:
```

将 `_record_blocked_skill()` 改为只提交数据库写入，构造 `BlockedSkillRecord(source_id=source_id or "", user_id=user_id or "", bbk_id=bbk_id or "", ...)` 后调用 `store.submit(record)`。删除 `_BLOCKED_HISTORY_FILE`、`_history_lock`、`_get_blocked_history_path()`、`get_blocked_history()`、`clear_blocked_history()` 和 `remove_blocked_entry()` 的本地文件实现。没有运行循环或数据库不可用时记录 warning 并跳过，不写本地文件兜底。

同时修改 Market 上传、管理员上架和启用调用点，让扫描入口携带上下文。用户侧上传/启用使用 `X-Source-Id`、`X-User-Id`、`X-Bbk-Id`；管理员上架接口也必须新增并使用 `X-Bbk-Id` 请求头作为操作者分行归属。`bbk_ids` 查询参数只表示技能上架后的可见/分发分行范围，不能写入扫描历史的 `bbk_id`。`scan_skill_directory()` 的新上下文参数要从这些请求头向下透传到 `_record_blocked_skill()`：

管理员上架接口签名中显式增加请求头参数：

```python
x_bbk_id: Annotated[str | None, Header(alias="X-Bbk-Id")] = None
```

如果该文件仍使用 `Optional[str]` 风格，则保持现有风格并写成：

```python
x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id")
```

```python
scan_skill_directory(
    skill_dir,
    skill_name=skill_name,
    block=True,
    source_id=source_id or "",
    user_id=user_id or "",
    bbk_id=bbk_id or "",
)
```

新增可等待 helper，供路由或 service 在返回拦截错误前等待写库完成：

```python
async def flush_skill_scan_history() -> None:
    store = _history_store
    if store is not None:
        await store.flush()
```

在 `market/src/market/app/routers/skills_browse.py`、`market/src/market/app/routers/skills_market.py` 和 `market/src/market/marketplace/service.py` 中捕获 `SkillScanError` 后，返回 `HTTPException` 或 `{"reason": "security_scan_failed"}` 前先 `await flush_skill_scan_history()`。这一步是接口可观测性的关键：扫描拦截响应返回时，Console 查询历史表应该已经能看到该条记录。

- [ ] **步骤 7：Market 应用启动时安装数据库历史 writer**

修改 `market/src/market/app/_app.py`，在创建 `MarketplaceService` 后安装 store。Market 和 SWE 必须使用同一张表，但建表和补列迁移只由独立 SQL 脚本负责；Market 只做可用性检查并安装 writer：

```python
from ..security.skill_scanner import install_skill_scan_history_store
from ..security.skill_scanner.history import SkillScanHistoryStore

history_store = SkillScanHistoryStore(db)
if history_store.is_available:
    install_skill_scan_history_store(history_store)
else:
    install_skill_scan_history_store(None)
```

- [ ] **步骤 8：补充 Market 上传/上架拦截回归**

在 `market/tests/unit/marketplace/test_skills_browse.py` 和 `market/tests/unit/marketplace/test_skills_market.py` 中，为已有“上传危险 Skill 被拦截”的测试补充断言：

- 拦截后数据库收到 `INSERT INTO swe_skill_scan_history`。
- 用户侧上传/启用记录参数包含请求头中的 `X-Source-Id`、`X-User-Id`、`X-Bbk-Id`。
- 管理员上架接口必须新增 `X-Bbk-Id` 请求头，记录参数包含 `X-Source-Id`、`X-User-Id`、`X-Bbk-Id`。
- `bbk_ids` 查询参数不得写入扫描历史的 `bbk_id`。
- 返回 `security_scan_failed` 或抛出 `HTTPException` 前已经调用 `flush_skill_scan_history()`。
- 临时 `MARKET_SWE_ROOT/skill_scanner_blocked.json` 不存在。

Console 的字段展示由任务 7 的 `SkillScannerSection` 和 API 测试覆盖，不放在 Market 后端测试中。

- [ ] **步骤 9：运行 Market 聚焦测试**

运行：

```bash
venv/bin/python -m pytest \
  tests/unit/security/test_skill_scan_history.py \
  market/tests/unit/security/test_skill_scan_history.py \
  market/tests/unit/marketplace/test_skills_browse.py \
  market/tests/unit/marketplace/test_skills_market.py \
  -v
```

预期：通过。

- [ ] **步骤 10：提交 Market 数据库历史落库**

```bash
git add \
  src/swe/security/skill_scanner/history.py \
  tests/unit/security/test_skill_scan_history.py \
  market/src/market/security/skill_scanner/history.py \
  market/src/market/security/skill_scanner/__init__.py \
  market/src/market/app/_app.py \
  market/src/market/app/routers/skills_browse.py \
  market/src/market/app/routers/skills_market.py \
  market/src/market/marketplace/service.py \
  market/tests/unit/security/test_skill_scan_history.py \
  market/tests/unit/marketplace/test_skills_browse.py \
  market/tests/unit/marketplace/test_skills_market.py
git commit -m "feat(market): persist skill scan alerts to database"
```

### 任务 10：第一阶段回归验证

**文件：**

- 仅验证。

- [ ] **步骤 1：运行聚焦的 security scanner 测试**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/ -k "skill_scanner" -v
```

预期：通过。

- [ ] **步骤 2：运行 Skill manager 租户范围测试**

运行：

```bash
venv/bin/python -m pytest \
  tests/unit/security/test_skill_scanner_safe_unpack.py \
  tests/unit/agents/test_workspace_skill_layout_migration.py \
  tests/unit/agents/test_tenant_skill_pool_scope.py \
  tests/unit/agents/test_utf8_skill_cleanup.py \
  tests/unit/routers/test_skills_tenant_scope.py \
  tests/unit/app/test_skill_scan_history_lifecycle.py \
  -v
```

预期：通过。

- [ ] **步骤 3：运行格式化/预提交检查**

运行：

```bash
pre-commit run --all-files
```

预期：通过；若 `pre-commit` 不可用，在交付说明中明确记录。

- [ ] **步骤 4：提交格式化修复**

```bash
git add src/swe/security/skill_scanner tests/unit/security analysis
git commit -m "chore(security): verify skill scan MVP"
```

---

## 第二阶段任务池

### 任务 11：增加 Profile 配置测试

**文件：**

- 修改：`src/swe/config/config.py`
- 新建：`tests/unit/security/test_skill_scanner_profiles.py`

- [ ] **步骤 1：编写失败的 profile 配置测试**

```python
# -*- coding: utf-8 -*-
"""测试 Skill 扫描 profile 配置."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from swe.config.config import SkillScannerConfig


def test_skill_scanner_config_defaults_to_standard_profile() -> None:
    cfg = SkillScannerConfig()

    assert cfg.profile == "standard"


def test_skill_scanner_config_accepts_quick_and_strict_profiles() -> None:
    assert SkillScannerConfig(profile="quick").profile == "quick"
    assert SkillScannerConfig(profile="strict").profile == "strict"


def test_skill_scanner_config_rejects_unknown_profile() -> None:
    with pytest.raises(ValidationError):
        SkillScannerConfig(profile="unsafe")
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_profiles.py -v
```

预期：失败，因为缺少 `profile` 属性。

- [ ] **步骤 3：为 `SkillScannerConfig` 增加 `profile` 字段**

在 `src/swe/config/config.py` 的 `SkillScannerConfig` 中加入：

```python
    profile: Literal["quick", "standard", "strict"] = Field(
        default="standard",
        description=(
            "Scanner profile: quick runs low-latency local checks, standard "
            "runs all built-in local analyzers, strict may run optional "
            "semantic, dependency, or external engines."
        ),
    )
```

- [ ] **步骤 4：运行配置测试**

运行：

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_profiles.py -v
```

预期：通过。

- [ ] **步骤 5：提交 profile 配置**

```bash
git add src/swe/config/config.py tests/unit/security/test_skill_scanner_profiles.py
git commit -m "feat(security): add skill scanner profiles"
```

### 任务 12：开源引擎适配器契约

**文件：**

- 新建：`src/swe/security/skill_scanner/external_engines.py`
- 新建：`tests/unit/security/test_skill_scanner_external_engines.py`

**目标：**

先实现统一外部引擎 adapter 契约，不要求第一步就把所有 CLI 跑通。adapter 负责把 SkillSpector、Agent-Scan、MCP-Scan、pip-audit、npm audit、OSV 等工具的输出归一化为 CoPaw `Finding`，并集中控制 timeout、工作目录、环境变量、网络和输出大小。

**接口设计：**

```python
@dataclass(frozen=True)
class ExternalEngineSpec:
    """外部扫描引擎执行规格."""

    name: str
    command: tuple[str, ...]
    timeout_seconds: float = 30.0
    network_allowed: bool = False


@dataclass(frozen=True)
class ExternalEngineResult:
    """外部扫描引擎归一化结果."""

    engine: str
    findings: list[Finding]
    raw_summary: str
    succeeded: bool
    error: str = ""
```

**首批 adapter：**

- `normalize_skillspector_output(raw: str) -> list[Finding]`
- `normalize_agent_scan_output(raw: str) -> list[Finding]`
- `normalize_mcp_scan_output(raw: str) -> list[Finding]`
- `normalize_dependency_audit_output(raw: str, engine: str) -> list[Finding]`

**测试用例：**

- SkillSpector 样例 JSON 中的 high severity finding 能转成 `ThreatCategory.PROMPT_INJECTION` 或 `ThreatCategory.COMMAND_INJECTION`。
- Agent-Scan 样例输出中的 toxic flow 能转成 `ThreatCategory.TOOL_CHAINING_ABUSE`。
- MCP-Scan 样例输出中的 tool poisoning 能转成 `ThreatCategory.PROMPT_INJECTION`。
- pip-audit/OSV 样例输出中的 CVE 能转成 `ThreatCategory.SUPPLY_CHAIN_ATTACK`。
- 无法解析的输出不能抛出未捕获异常，应返回空 findings 并记录 `error`。

**验证命令：**

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_external_engines.py -v
```

**提交：**

```bash
git add src/swe/security/skill_scanner/external_engines.py tests/unit/security/test_skill_scanner_external_engines.py
git commit -m "feat(security): add external skill scan engine adapters"
```

### 任务 13：Dependency Analyzer

**文件：**

- 新建：`src/swe/security/skill_scanner/analyzers/dependency_analyzer.py`
- 新建：`tests/unit/security/test_skill_scanner_dependency_analyzer.py`

**测试用例：**

- 带有 `requests==2.31.0` 的 `requirements.txt` 能被解析为 metadata。
- 带有直接 URL dependency 的 `package.json` 产出 `DEPENDENCY_UNTRUSTED_SOURCE`。
- lock 文件会记录到 finding metadata，且不要求网络访问。

**实现轮廓：**

```python
class DependencyAnalyzer(BaseAnalyzer):
    """解析 Skill 依赖声明并识别供应链风险."""

    def __init__(self) -> None:
        super().__init__(name="dependency")

    def analyze(
        self,
        skill_dir: Path,
        files: list[SkillFile],
        *,
        skill_name: str | None = None,
    ) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(_scan_requirements(skill_dir / "requirements.txt"))
        findings.extend(_scan_package_json(skill_dir / "package.json"))
        return findings
```

**验证命令：**

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_dependency_analyzer.py -v
```

### 任务 14：按 Profile 选择分析器

**文件：**

- 修改：`src/swe/security/skill_scanner/__init__.py`
- 修改：`src/swe/security/skill_scanner/scanner.py`
- 测试：`tests/unit/security/test_skill_scanner_profiles.py`

**Profile 行为：**

| Profile | 分析器 |
| --- | --- |
| quick | package + pattern |
| standard | package + pattern + ast_behavior + dependency local parsing |
| strict | standard + optional semantic/external engines when configured |

**验证命令：**

```bash
venv/bin/python -m pytest tests/unit/security/test_skill_scanner_profiles.py -v
```

### 任务 15：Market Scanner 对齐

**文件：**

- 修改：`market/src/market/security/skill_scanner/__init__.py`
- 修改：`market/src/market/security/skill_scanner/scanner.py`
- 修改：`market/src/market/marketplace/service.py`
- 测试：`market/tests/unit/marketplace/test_skills_market.py`

**方案：**

- 第一选择：如果 Market 包导入边界允许，直接 import 共享 SWE scanner。
- 兜底选择：保留 Market scanner 作为 adapter，仅复制新增 analyzer，并保持测试一致。
- 在规划 Console/API 变更前，不改变 Market service 的公开结果形态。

**验证命令：**

```bash
venv/bin/python -m pytest market/tests/unit/marketplace/test_skills_market.py -v
```

---

## 第三阶段任务池

### 任务 16：Taint Flow Analyzer

**文件：**

- 新建：`src/swe/security/skill_scanner/analyzers/taint_flow_analyzer.py`
- 新建：`tests/unit/security/test_skill_scanner_taint_flow_analyzer.py`

**初始 source/sink 映射：**

| Source | Sink | 规则 |
| --- | --- | --- |
| `os.environ[...]` | `requests.post(...)` | `TAINT_ENV_TO_NETWORK` |
| `open("~/.ssh/...")` | `requests.post(...)` | `TAINT_SECRET_FILE_TO_NETWORK` |
| file read variable | `subprocess.run(..., shell=True)` | `TAINT_FILE_TO_SHELL` |

### 任务 17：Semantic Analyzer Adapter

**文件：**

- 新建：`src/swe/security/skill_scanner/analyzers/semantic_analyzer.py`
- 新建：`tests/unit/security/test_skill_scanner_semantic_analyzer.py`

**边界：**

- 默认关闭。
- 仅在 strict profile 启用。
- 将 Skill 内容视为对抗性输入。
- 在 Finding metadata 中返回 confidence。

### 任务 18：外部引擎运行器与 strict profile 集成

**文件：**

- 修改：`src/swe/security/skill_scanner/external_engines.py`
- 修改：`src/swe/security/skill_scanner/scanner.py`
- 修改：`src/swe/security/skill_scanner/__init__.py`
- 测试：`tests/unit/security/test_skill_scanner_external_engines.py`
- 测试：`tests/unit/security/test_skill_scanner_profiles.py`

**目标：**

在第二阶段 adapter 契约稳定后，增加受控运行器，把可用的开源组件接入 strict profile。运行器负责命令拼装、超时、环境变量裁剪、工作目录隔离、输出大小限制和失败降级。

**引擎接入顺序：**

1. pip-audit / OSV：优先用于依赖漏洞增强，风险较低，输出结构相对明确。
2. SkillSpector：用于 strict 高风险 Skill 包验证，先接离线样本，再接 Market 上架二级扫描。
3. MCP-Scan：用于 MCP 工具描述和 Toxic Flow 检查，挂到 MCP 上传/绑定流程。
4. Agent-Scan：用于本机 Agent/MCP/Skill 资产巡检，不进入同步 Skill 安装主链路。

**验证命令：**

```bash
venv/bin/python -m pytest \
  tests/unit/security/test_skill_scanner_external_engines.py \
  tests/unit/security/test_skill_scanner_profiles.py \
  -v
```

### 任务 19：复核与运营 API

**文件：**

- 修改：`src/swe/security/skill_scanner/history.py`
- 修改：`src/swe/app/routers/config.py`
- 修改：`console/src/api/modules/security.ts`
- 修改：`console/src/pages/Settings/Security/useSkillScanner.ts`
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.tsx`
- 修改：`console/src/pages/Settings/Security/components/SkillScannerSection.test.tsx`

**新增 API：**

```http
GET /config/security/skill-scanner/reports/{record_id}
POST /config/security/skill-scanner/reviews/{record_id}/decision
POST /config/security/skill-scanner/rescan
```

**Decision 状态：**

```text
blocked
needs_review
needs_fix
approved_with_warning
approved
```

---

## 风险管理

- **MVP 分析器误报：** 包体和 AST 规则保持高置信，不在现有 YAML policy 之外新增宽泛的网络 import 检测。
- **阻断现有内置 Skill：** 在默认模式改成 block 前，运行聚焦回归套件并扫描内置 Skill。
- **Market/SWE 扫描器重复导致漂移：** 先用共享测试对齐，再在导入边界清楚后抽出共享代码。
- **Strict profile 延迟过高：** 后续阶段中 strict 引擎保持可选和异步。
- **外部引擎输出不稳定：** 统一归一化为 CoPaw `Finding`，不要把原始 CLI 字段暴露成 API 契约。

---

## 验证矩阵

| 范围 | 命令 | 预期 |
| --- | --- | --- |
| Safe unpack | `venv/bin/python -m pytest tests/unit/security/test_skill_scanner_safe_unpack.py tests/unit/agents/test_utf8_skill_cleanup.py -v` | 通过 |
| Package analyzer | `venv/bin/python -m pytest tests/unit/security/test_skill_scanner_package_analyzer.py -v` | 通过 |
| AST analyzer | `venv/bin/python -m pytest tests/unit/security/test_skill_scanner_ast_behavior.py -v` | 通过 |
| Default scanner | `venv/bin/python -m pytest tests/unit/security/test_skill_scanner_default_analyzers.py -v` | 通过 |
| Console analyzer 可见性 | `cd console && npm test -- SkillScannerSection.test.tsx` | 通过或记录当前前端测试命令 |
| 现有 scanner 生命周期 | `venv/bin/python -m pytest tests/unit/security/test_skill_scanner_executor.py tests/unit/security/test_skill_scanner_hook_files.py -v` | 通过 |
| Security scanner 分组 | `venv/bin/python -m pytest tests/unit/security/ -k "skill_scanner" -v` | 通过 |
| Skill API 范围 | `venv/bin/python -m pytest tests/unit/routers/test_skills_tenant_scope.py -v` | 通过 |
| Pre-commit | `pre-commit run --all-files` | 通过或记录不可用 |

---

## 自检

- **设计覆盖：** 第一阶段覆盖 L1-L3、安全解包边界以及现有 L6 block/warn/off 准入路径；第二阶段覆盖 profile、依赖/SCA 和 Market 对齐；第三阶段覆盖 L4、L5 增强、开源引擎和 L7 复核/运营。
- **占位符扫描：** 本计划不包含未解决占位内容。后续阶段任务即使处于任务池，也给出明确文件、边界和验证命令。
- **类型一致性：** 新增 analyzer 遵循现有 `BaseAnalyzer.analyze(skill_dir, files, *, skill_name=None) -> list[Finding]` 接口。新增 Finding 使用现有 `Severity`、`ThreatCategory`、`Finding` 和 `ScanResult` 类型。
- **最新代码校准：** 第一阶段不再修改 `models.py` 或引入 `ScanContext`；这些内容延后到 profile、依赖和外部引擎需要共享上下文时再做。
