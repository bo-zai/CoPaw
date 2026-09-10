import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ScenarioPresetSelector from "./index";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";

vi.mock("@/api/modules/scenarioPreset", () => ({
  scenarioPresetApi: { getEffectiveCatalog: vi.fn() },
}));

const getEffectiveCatalog = vi.mocked(scenarioPresetApi.getEffectiveCatalog);

describe("ScenarioPresetSelector", () => {
  afterEach(cleanup);

  it("stays absent for an empty effective catalog", async () => {
    getEffectiveCatalog.mockResolvedValueOnce({ domains: [] });
    const { container } = render(<ScenarioPresetSelector onSelect={vi.fn()} />);

    await waitFor(() => expect(getEffectiveCatalog).toHaveBeenCalledOnce());

    expect(container.querySelector(".scenario-preset-selector")).toBeNull();
  });

  it("uses a simplified domain selector when the catalog has only one domain", async () => {
    getEffectiveCatalog.mockResolvedValueOnce({
      domains: [
        {
          id: "domain-a",
          name: "文档处理",
          capabilities: [
            {
              id: "capability-a",
              name: "信息提取",
              scenarios: [],
            },
          ],
        },
      ],
    });

    render(<ScenarioPresetSelector onSelect={vi.fn()} />);

    const domainSelector = await screen.findByRole("tablist", {
      name: "能力域",
    });
    expect(domainSelector).toHaveClass("is-single");
    expect(screen.getByRole("tab", { name: "文档处理" })).toBeInTheDocument();
  });

  it("renders independent domain cards, capability tabs, and the selected capability scenarios", async () => {
    getEffectiveCatalog.mockResolvedValueOnce({
      domains: [
        {
          id: "domain-a",
          name: "文档处理",
          capabilities: [
            {
              id: "capability-a",
              name: "信息提取",
              scenarios: [
                { id: "scenario-a", name: "提取字段", prompt_draft: "提取" },
              ],
            },
            {
              id: "capability-b",
              name: "格式转换",
              scenarios: [
                { id: "scenario-b", name: "转成表格", prompt_draft: "转换" },
              ],
            },
          ],
        },
        {
          id: "domain-b",
          name: "数据分析",
          capabilities: [
            {
              id: "capability-c",
              name: "趋势分析",
              scenarios: [
                { id: "scenario-c", name: "分析趋势", prompt_draft: "分析" },
              ],
            },
          ],
        },
      ],
    });
    const onSelect = vi.fn();
    const onBrowseChange = vi.fn();
    render(
      <ScenarioPresetSelector
        onSelect={onSelect}
        onBrowseChange={onBrowseChange}
      >
        {({ onScenarioSelect, scenarios }) => (
          <div>
            {scenarios.map((scenario) => (
              <button
                key={scenario.id}
                onClick={() => onScenarioSelect(scenario)}
                type="button"
              >
                {scenario.name}
              </button>
            ))}
          </div>
        )}
      </ScenarioPresetSelector>,
    );

    expect(
      await screen.findByRole("tab", { name: "文档处理" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "数据分析" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "信息提取" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "提取字段" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "转成表格" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "格式转换" }));
    expect(
      screen.getByRole("button", { name: "转成表格" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "提取字段" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "数据分析" }));
    expect(onBrowseChange).toHaveBeenCalledTimes(2);
  });

  it("submits the selected leaf without resolving resources", async () => {
    getEffectiveCatalog.mockResolvedValueOnce({
      domains: [
        {
          id: "domain-a",
          name: "文档",
          capabilities: [
            {
              id: "capability-a",
              name: "信息提取",
              scenarios: [
                { id: "scenario-a", name: "提取字段", prompt_draft: "提取" },
              ],
            },
          ],
        },
      ],
    });
    const onSelect = vi.fn();
    render(
      <ScenarioPresetSelector onSelect={onSelect}>
        {({ onScenarioSelect, scenarios }) => (
          <div>
            {scenarios.map((scenario) => (
              <button
                key={scenario.id}
                onClick={() => onScenarioSelect(scenario)}
                type="button"
              >
                {scenario.name}
              </button>
            ))}
          </div>
        )}
      </ScenarioPresetSelector>,
    );

    const scenario = await screen.findByRole("button", { name: "提取字段" });
    fireEvent.click(scenario);

    expect(onSelect).toHaveBeenCalledWith({
      capability: expect.objectContaining({ id: "capability-a" }),
      scenario: expect.objectContaining({ id: "scenario-a" }),
    });
  });
});
