import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Modal } from "@agentscope-ai/design";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SkillScannerSection } from "./SkillScannerSection";

const mocks = vi.hoisted(() => ({
  setHistoryPagination: vi.fn(),
  fetchBlockedHistory: vi.fn(),
  hookState: {} as Record<string, unknown>,
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@agentscope-ai/design", async () => {
  const antd = await vi.importActual<typeof import("antd")>("antd");
  return {
    Alert: antd.Alert,
    Button: antd.Button,
    Card: antd.Card,
    Empty: antd.Empty,
    InputNumber: antd.InputNumber,
    Modal: antd.Modal,
    Table: antd.Table,
    Tabs: antd.Tabs,
    Tag: antd.Tag,
    Tooltip: antd.Tooltip,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../useSkillScanner", () => ({
  useSkillScanner: () => mocks.hookState,
}));

vi.mock("../../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: mocks.message }),
}));

vi.mock("../../../../contexts/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../../../../api/modules/mySkills", () => ({
  mySkillsApi: { disableSkill: vi.fn() },
}));

const records = Array.from({ length: 10 }, (_, index) => ({
  id: `record-${index}`,
  skill_name: `skill-${index}`,
  blocked_at: "2026-08-03T08:00:00+00:00",
  max_severity: "HIGH",
  findings: [
    {
      severity: "HIGH",
      title: "unsafe",
      description: "unsafe behavior",
      file_path: "SKILL.md",
      line_number: 3,
      rule_id: "RULE",
      analyzer: "package",
    },
  ],
  content_hash: "",
  action: "blocked" as const,
  source_id: "source-a",
  user_id: "user-a",
  bbk_id: "bbk-a",
}));

function setHookState(overrides: Record<string, unknown> = {}) {
  mocks.hookState = {
    config: { mode: "block", timeout: 30, whitelist: [] },
    blockedHistory: records,
    whitelist: [],
    loading: false,
    historyLoading: false,
    historyMutating: false,
    historyError: null,
    historyPage: 2,
    historyPageSize: 10,
    historyTotal: 5000,
    updateConfig: vi.fn(),
    addToWhitelist: vi.fn(),
    removeFromWhitelist: vi.fn(),
    removeBlockedEntry: vi.fn(),
    clearBlockedHistory: vi.fn(),
    fetchBlockedHistory: mocks.fetchBlockedHistory,
    setHistoryPagination: mocks.setHistoryPagination,
    ...overrides,
  };
}

describe("SkillScannerSection history", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    setHookState();
  });

  it("renders only the active backend page and controls server pagination", () => {
    const { container } = render(<SkillScannerSection />);

    for (const record of records) {
      expect(screen.getByText(record.skill_name)).toBeInTheDocument();
    }
    expect(screen.getByText("5000")).toBeInTheDocument();

    const pageThree = container.querySelector(".ant-pagination-item-3");
    expect(pageThree).not.toBeNull();
    fireEvent.click(pageThree as Element);
    expect(mocks.setHistoryPagination).toHaveBeenCalledWith(3, 10);
  });

  it("shows a scoped retry without hiding scanner controls", () => {
    setHookState({
      blockedHistory: [],
      historyTotal: 0,
      historyError: "database down",
    });

    render(<SkillScannerSection />);

    expect(
      screen.getByText("security.skillScanner.scanAlerts.loadFailed"),
    ).toBeInTheDocument();
    expect(screen.getByText("security.skillScanner.mode")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "security.skillScanner.scanAlerts.retry",
      }),
    );
    expect(mocks.fetchBlockedHistory).toHaveBeenCalledTimes(1);
  });

  it("keeps pagination available for a non-zero empty page", () => {
    setHookState({
      blockedHistory: [],
      historyPage: 3,
      historyPageSize: 10,
      historyTotal: 11,
    });

    const { container } = render(<SkillScannerSection />);

    expect(container.querySelector(".ant-pagination")).not.toBeNull();
    expect(container.querySelector(".ant-pagination-item-2")).not.toBeNull();
  });

  it("reports clear and single-delete failures", async () => {
    const clearBlockedHistory = vi.fn().mockResolvedValue(false);
    const removeBlockedEntry = vi.fn().mockResolvedValue(false);
    vi.spyOn(Modal, "confirm").mockImplementation((options) => {
      void options.onOk?.();
      return { destroy: vi.fn(), update: vi.fn() } as never;
    });
    setHookState({ clearBlockedHistory, removeBlockedEntry });
    render(<SkillScannerSection />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "security.skillScanner.scanAlerts.clearAll",
      }),
    );
    fireEvent.click(
      screen.getAllByRole("button", {
        name: "security.skillScanner.scanAlerts.remove",
      })[0],
    );

    await waitFor(() => {
      expect(mocks.message.error).toHaveBeenCalledWith(
        "security.skillScanner.scanAlerts.clearFailed",
      );
      expect(mocks.message.error).toHaveBeenCalledWith(
        "security.skillScanner.scanAlerts.removeFailed",
      );
    });
  });

  it("disables history mutation controls while a mutation is pending", () => {
    setHookState({ historyMutating: true });
    render(<SkillScannerSection />);

    expect(
      screen.getByRole("button", {
        name: "security.skillScanner.scanAlerts.clearAll",
      }),
    ).toBeDisabled();
    expect(
      screen.getAllByRole("button", {
        name: "security.skillScanner.scanAlerts.remove",
      })[0],
    ).toBeDisabled();
  });

  it("shows user and branch columns and analyzer details for scan alerts", () => {
    render(<SkillScannerSection />);

    expect(screen.getAllByText("user-a").length).toBeGreaterThan(0);
    expect(screen.getAllByText("bbk-a").length).toBeGreaterThan(0);
    expect(screen.queryByText("source-a")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getAllByRole("button", {
        name: "security.skillScanner.scanAlerts.viewFindings",
      })[0],
    );

    expect(screen.getByText("package")).toBeInTheDocument();
  });
});
