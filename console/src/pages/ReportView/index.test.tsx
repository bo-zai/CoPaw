import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import ReportView from ".";

vi.mock("@/components/agentscope-chat/FilePreviewPresentationContext", () => ({
  FilePreviewPresentationProvider: (props: {
    children: ReactNode;
    value: string;
  }) => <div data-preview-presentation={props.value}>{props.children}</div>,
}));

describe("ReportView", () => {
  it("keeps report previews on the legacy modal presentation", () => {
    render(<ReportView />);

    expect(
      screen.getByText("ReportView").closest("[data-preview-presentation]"),
    ).toHaveAttribute("data-preview-presentation", "modal");
  });
});
