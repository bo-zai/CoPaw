# -*- coding: utf-8 -*-
"""Console active-model distribution contract tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
CONSOLE_SRC = ROOT / "console" / "src"
TENANT_PICKER = CONSOLE_SRC / "components" / "TenantTargetPicker" / "index.tsx"
SKILL_BROADCAST_MODAL = (
    CONSOLE_SRC
    / "pages"
    / "Agent"
    / "SkillPool"
    / "components"
    / "BroadcastModal.tsx"
)
MODELS_SECTION = (
    CONSOLE_SRC
    / "pages"
    / "Settings"
    / "Models"
    / "components"
    / "sections"
    / "ModelsSection.tsx"
)
PROVIDER_API = CONSOLE_SRC / "api" / "modules" / "provider.ts"
PROVIDER_TYPES = CONSOLE_SRC / "api" / "types" / "provider.ts"
LOCALE_FILES = {
    file_path.stem: file_path
    for file_path in (CONSOLE_SRC / "locales").glob("*.json")
}


def test_shared_tenant_picker_supports_discovered_and_manual_selection() -> (
    None
):
    content = TENANT_PICKER.read_text(encoding="utf-8")

    assert "tenantIds: string[];" in content
    assert "selectedTenantIds: string[];" in content
    assert "manualTenantIdsText" in content
    assert "function parseManualTenantIds(input: string): string[]" in content
    assert ".split(/[\\s,]+/)" in content
    assert "function mergeTenantIds(" in content
    assert "function haveSameTenantIds(" in content
    assert "const mergedTenantIds = useMemo(" in content
    assert "haveSameTenantIds(selectedTenantIds, mergedTenantIds)" in content
    assert 't("skillPool.allWorkspaces")' in content
    assert 't("skillPool.manualTenantIds")' in content
    assert 'placeholder={t("skillPool.manualTenantPlaceholder")}' in content


def test_skill_broadcast_modal_reuses_shared_tenant_picker() -> None:
    content = SKILL_BROADCAST_MODAL.read_text(encoding="utf-8")

    assert 'from "../../../../components/TenantTargetPicker"' in content
    assert "<TenantTargetPicker" in content
    assert "tenantIds={tenantIds}" in content
    assert "selectedTenantIds={selectedTenantIds}" in content


def test_provider_api_exposes_active_model_distribution_endpoints() -> None:
    content = PROVIDER_API.read_text(encoding="utf-8")

    assert "listActiveModelDistributionTenants" in content
    assert '"/models/distribution/tenants"' in content
    assert "distributeActiveLlm" in content
    assert '"/models/distribution/active-llm"' in content


def test_provider_types_cover_active_model_distribution_contract() -> None:
    content = PROVIDER_TYPES.read_text(encoding="utf-8")

    assert "export interface ActiveModelDistributionRequest" in content
    assert "target_tenant_ids: string[];" in content
    assert "overwrite: boolean;" in content
    assert "export interface ActiveModelDistributionTenantResult" in content
    assert "provider_updated?: string;" in content
    assert "active_llm_updated?: ModelSlotConfig;" in content
    assert "export interface ActiveModelDistributionResponse" in content
    assert "source_active_llm: ModelSlotConfig;" in content


def test_models_section_wires_distribution_modal_warning_and_result_feedback() -> (
    None
):
    content = MODELS_SECTION.read_text(encoding="utf-8")

    assert "api.distributeActiveLlm({" in content
    assert "target_tenant_ids: selectedDistributionTenantIds," in content
    assert "overwrite: true," in content
    assert "<TenantSelector" in content
    assert "excludeTenantId={currentTenantId}" in content
    assert 't("models.distribute")' in content
    assert 't("models.distributeOverwriteWarning")' in content
    assert (
        "message.success(`模型分发任务已提交：${result.task_id}`)" in content
    )


def test_models_locales_cover_distribution_copy() -> None:
    expected_keys = {
        "distribute",
        "distributeHint",
        "distributeTitle",
        "distributeCurrentSource",
        "distributeOverwriteWarning",
        "distributeSuccess",
        "distributeFailed",
        "distributeBootstrapped",
        "distributeResultTitle",
        "distributeSuccessList",
        "distributeFailureInlineHint",
        "distributePartialFailureTitle",
    }

    for language, file_path in LOCALE_FILES.items():
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        models = payload.get("models") or {}
        missing = expected_keys - set(models)
        assert (
            not missing
        ), f"{language} missing models keys: {sorted(missing)}"
