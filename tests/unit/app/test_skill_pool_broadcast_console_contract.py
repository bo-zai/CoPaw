# -*- coding: utf-8 -*-
"""Console skill-pool broadcast contract tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
CONSOLE_SRC = ROOT / "console" / "src"
BROADCAST_MODAL = (
    CONSOLE_SRC
    / "pages"
    / "Agent"
    / "SkillPool"
    / "components"
    / "BroadcastModal.tsx"
)
SKILL_POOL_PAGE = CONSOLE_SRC / "pages" / "Agent" / "SkillPool" / "index.tsx"
SKILL_API = CONSOLE_SRC / "api" / "modules" / "skill.ts"
LOCALE_FILES = {
    file_path.stem: file_path
    for file_path in (CONSOLE_SRC / "locales").glob("*.json")
}


def test_broadcast_modal_supports_discovered_and_manual_tenant_selection() -> (
    None
):
    content = BROADCAST_MODAL.read_text(encoding="utf-8")

    assert "tenantIds: string[];" in content
    assert 'from "../../../../components/TenantTargetPicker"' in content
    assert "<TenantTargetPicker" in content
    assert "selectedTenantIds={selectedTenantIds}" in content
    assert "onChange={setSelectedTenantIds}" in content
    assert (
        "onOk={() => onConfirm(selectedSkillNames, targetTenantIds)}"
        in content
    )


def test_skill_pool_page_wires_tenant_broadcast_api_and_result_dialogs() -> (
    None
):
    content = SKILL_POOL_PAGE.read_text(encoding="utf-8")

    assert "api.listBroadcastTenants()" in content
    assert "setBroadcastTenantIds(tenantResponse.tenant_ids || []);" in content
    assert "api.broadcastPoolSkillsToDefaultAgents({" in content
    assert "target_tenant_ids: targetTenantIds," in content
    assert 'title: t("skillPool.broadcastResultTitle")' in content
    assert 'title: t("skillPool.broadcastPartialFailureTitle")' in content
    assert 't("skillPool.broadcastSuccessList")' in content
    assert 't("skillPool.broadcastFailureInlineHint")' in content
    assert "tenantIds={broadcastTenantIds}" in content
    assert "onConfirm={handleBroadcast}" in content


def test_skill_api_exposes_cross_tenant_broadcast_endpoints() -> None:
    content = SKILL_API.read_text(encoding="utf-8")

    assert 'const cacheKey = "/skills/pool/broadcast/tenants";' in content
    assert '"/skills/pool/broadcast/tenants"' in content
    assert '"/skills/pool/broadcast/default-agents"' in content
    assert "target_tenant_ids: string[];" in content
    assert "overwrite: boolean;" in content


def test_broadcast_locales_cover_manual_tenants_and_result_feedback() -> None:
    expected_keys = {
        "broadcast",
        "broadcastHint",
        "selectWorkspaces",
        "allWorkspaces",
        "manualTenantIds",
        "manualTenantHint",
        "manualTenantPlaceholder",
        "broadcastSuccess",
        "broadcastBootstrapped",
        "broadcastResultTitle",
        "broadcastSuccessList",
        "broadcastFailureInlineHint",
        "broadcastPartialFailureTitle",
    }

    for language, file_path in LOCALE_FILES.items():
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        skill_pool = payload.get("skillPool") or {}
        missing = expected_keys - set(skill_pool)
        assert (
            not missing
        ), f"{language} missing skillPool keys: {sorted(missing)}"
