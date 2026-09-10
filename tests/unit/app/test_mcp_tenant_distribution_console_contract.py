# -*- coding: utf-8 -*-
"""Console MCP tenant distribution contract tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
CONSOLE_SRC = ROOT / "console" / "src"
MCP_PAGE = CONSOLE_SRC / "pages" / "Agent" / "MCP" / "index.tsx"
MCP_CARD = (
    CONSOLE_SRC
    / "pages"
    / "Agent"
    / "MCP"
    / "components"
    / "MCPClientCard.tsx"
)
MCP_API = CONSOLE_SRC / "api" / "modules" / "mcp.ts"
MCP_TYPES = CONSOLE_SRC / "api" / "types" / "mcp.ts"
LOCALE_FILES = {
    file_path.stem: file_path
    for file_path in (CONSOLE_SRC / "locales").glob("*.json")
}


def test_mcp_page_supports_batch_selection_and_shared_tenant_picker() -> None:
    content = MCP_PAGE.read_text(encoding="utf-8")

    assert (
        "const [selectedClientKeys, setSelectedClientKeys] = useState<string[]>("
        in content
    )
    assert "api.listMCPDistributionTenants()" in content
    assert 'from "../../../utils/identity"' in content
    assert "const currentTenantId = getUserId();" in content
    assert 'from "../../../components/TenantTargetPicker"' in content
    assert "<TenantTargetPicker" in content
    assert "selectedTenantIds={selectedTenantIds}" in content
    assert "selected={selectedClientKeys.includes(client.key)}" in content
    assert "onSelectToggle={handleToggleSelectedClient}" in content


def test_mcp_page_wires_distribution_payload_and_result_feedback() -> None:
    content = MCP_PAGE.read_text(encoding="utf-8")

    assert "api.distributeMCPClientsToDefaultAgents({" in content
    assert "client_keys: selectedClientKeys," in content
    assert "target_tenant_ids: sanitizedSelectedTenantIds," in content
    assert "overwrite: true," in content
    assert ".filter((tenantId) => tenantId !== currentTenantId)" in content
    assert 'title: t("mcp.distributeResultTitle")' in content
    assert 'title: t("mcp.distributePartialFailureTitle")' in content
    assert 't("mcp.distributeSuccessList")' in content
    assert 't("mcp.distributeFailureInlineHint")' in content
    assert 't("mcp.distributeDefaultAgentWarning")' in content
    assert 't("mcp.distributeOverwriteWarning")' in content


def test_mcp_client_card_exposes_select_toggle() -> None:
    content = MCP_CARD.read_text(encoding="utf-8")

    assert "selected: boolean;" in content
    assert "onSelectToggle: (clientKey: string) => void;" in content
    assert 'selected ? t("mcp.selected") : t("mcp.select")' in content
    assert "onSelectToggle(client.key);" in content


def test_mcp_api_exposes_distribution_endpoint() -> None:
    content = MCP_API.read_text(encoding="utf-8")

    assert "distributeMCPClientsToDefaultAgents" in content
    assert '"/mcp/distribute/default-agents"' in content
    assert "listMCPDistributionTenants" in content
    assert '"/mcp/distribution/tenants"' in content


def test_mcp_types_cover_distribution_contract() -> None:
    content = MCP_TYPES.read_text(encoding="utf-8")

    assert "export interface MCPDistributionRequest" in content
    assert "client_keys: string[];" in content
    assert "target_tenant_ids: string[];" in content
    assert "overwrite: boolean;" in content
    assert "export interface MCPDistributionTenantResult" in content
    assert "default_agent_updated?: string[];" in content
    assert "export interface MCPDistributionResponse" in content
    assert "source_agent_id: string;" in content
    assert "export interface MCPDistributionTenantListResponse" in content
    assert "tenant_ids: string[];" in content


def test_mcp_locales_cover_distribution_copy() -> None:
    expected_keys = {
        "select",
        "selected",
        "selectedCount",
        "distribute",
        "distributeHint",
        "distributeTitle",
        "distributeCurrentSource",
        "distributeDefaultAgentWarning",
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
        mcp = payload.get("mcp") or {}
        missing = expected_keys - set(mcp)
        assert not missing, f"{language} missing mcp keys: {sorted(missing)}"
