import { AppstoreOutlined } from "@ant-design/icons";
import { Spin } from "antd";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";
import type {
  EffectiveScenarioPresetCatalog,
  ScenarioPresetCapability,
  ScenarioPresetDomain,
  ScenarioPresetScenario,
} from "@/api/types/scenarioPreset";

interface SelectedScenarioPreset {
  capability: ScenarioPresetCapability;
  scenario: ScenarioPresetScenario;
}

export interface ScenarioPresetSelectorRenderProps {
  capability: ScenarioPresetCapability | undefined;
  onScenarioSelect: (scenario: ScenarioPresetScenario) => void;
  scenarios: ScenarioPresetScenario[];
  selectedScenarioId?: string;
}

interface ScenarioPresetSelectorProps {
  children?: (props: ScenarioPresetSelectorRenderProps) => ReactNode;
  disabled?: boolean;
  onBrowseChange?: () => void;
  onSelect: (selection: SelectedScenarioPreset) => void;
  selectedScenarioId?: string;
}

function firstCapability(domain: ScenarioPresetDomain | undefined) {
  return domain?.capabilities[0];
}

/** Browse a Source catalog as capability-domain cards, capability tabs, and scenes. */
export default function ScenarioPresetSelector({
  children,
  disabled = false,
  onBrowseChange,
  onSelect,
  selectedScenarioId,
}: ScenarioPresetSelectorProps) {
  const [catalog, setCatalog] = useState<EffectiveScenarioPresetCatalog>();
  const [selectedDomainId, setSelectedDomainId] = useState<string>();
  const [selectedCapabilityId, setSelectedCapabilityId] = useState<string>();

  useEffect(() => {
    let active = true;
    void scenarioPresetApi
      .getEffectiveCatalog()
      .then((result) => {
        if (!active) return;
        setCatalog(result);
        const initialDomain = result.domains[0];
        setSelectedDomainId(initialDomain?.id);
        setSelectedCapabilityId(firstCapability(initialDomain)?.id);
      })
      .catch(() => {
        if (active) setCatalog({ domains: [] });
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedDomain = useMemo(
    () => catalog?.domains.find((domain) => domain.id === selectedDomainId),
    [catalog, selectedDomainId],
  );
  const selectedCapability = useMemo(
    () =>
      selectedDomain?.capabilities.find(
        (capability) => capability.id === selectedCapabilityId,
      ),
    [selectedCapabilityId, selectedDomain],
  );

  const handleDomainSelect = (domain: ScenarioPresetDomain) => {
    if (domain.id === selectedDomainId) return;
    setSelectedDomainId(domain.id);
    setSelectedCapabilityId(firstCapability(domain)?.id);
    onBrowseChange?.();
  };

  const handleCapabilitySelect = (capability: ScenarioPresetCapability) => {
    if (capability.id === selectedCapabilityId) return;
    setSelectedCapabilityId(capability.id);
    onBrowseChange?.();
  };

  const handleScenarioSelect = (scenario: ScenarioPresetScenario) => {
    if (!selectedCapability) return;
    onSelect({ capability: selectedCapability, scenario });
  };

  const composer = children?.({
    capability: selectedCapability,
    onScenarioSelect: handleScenarioSelect,
    scenarios: selectedCapability?.scenarios ?? [],
    selectedScenarioId,
  });

  const selectionControls = catalog?.domains.length ? (
    <>
      <div
        className={`scenario-preset-domain-selector${
          catalog.domains.length === 1 ? " is-single" : ""
        }`}
        role="tablist"
        aria-label="能力域"
      >
        <div className="scenario-preset-domain-track">
          {catalog.domains.map((domain) => (
            <button
              key={domain.id}
              aria-selected={selectedDomain?.id === domain.id}
              className={`scenario-preset-domain-card${
                selectedDomain?.id === domain.id ? " is-active" : ""
              }`}
              disabled={disabled}
              onClick={() => handleDomainSelect(domain)}
              role="tab"
              type="button"
            >
              <AppstoreOutlined aria-hidden />
              <span>{domain.name}</span>
            </button>
          ))}
        </div>
      </div>

      <div
        className="scenario-preset-capability-row"
        role="tablist"
        aria-label="能力"
      >
        {selectedDomain?.capabilities.map((capability) => (
          <button
            key={capability.id}
            aria-selected={selectedCapability?.id === capability.id}
            className={`scenario-preset-capability-tab${
              selectedCapability?.id === capability.id ? " is-active" : ""
            }`}
            disabled={disabled}
            onClick={() => handleCapabilitySelect(capability)}
            role="tab"
            type="button"
          >
            {capability.name}
          </button>
        ))}
      </div>
    </>
  ) : null;

  if (children) {
    return (
      <div
        aria-label={catalog?.domains.length ? "能力与场景选择" : undefined}
        className={
          catalog?.domains.length
            ? "scenario-preset-selector"
            : "scenario-preset-selector-shell"
        }
      >
        {catalog ? (
          selectionControls
        ) : (
          <Spin size="small" aria-label="加载场景" />
        )}
        {composer}
      </div>
    );
  }

  if (!catalog) return <Spin size="small" aria-label="加载场景" />;
  if (!catalog.domains.length) return null;

  return (
    <div className="scenario-preset-selector" aria-label="能力与场景选择">
      {selectionControls}
    </div>
  );
}
