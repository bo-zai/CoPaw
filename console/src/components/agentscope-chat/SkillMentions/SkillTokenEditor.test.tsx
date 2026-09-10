import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillTokenEditor } from "./SkillTokenEditor";
import type { SkillMentionItem } from "./useSkillMentions";

const items: SkillMentionItem[] = [
  {
    id: "skill:browser",
    type: "skill",
    label: "browser",
    name: "browser",
    description: "Use a browser",
  },
  {
    id: 'mcp_tool:["docs","search"]',
    type: "mcp_tool",
    label: "docs / search",
    server: "docs",
    name: "search",
    description: "Search docs",
  },
  {
    id: "workspace_file:media/report.pdf",
    type: "workspace_file",
    label: "report.pdf",
    root: "media",
    relative_path: "report.pdf",
    description: "media/report.pdf",
  },
  {
    id: "workspace_file:media/report file.pdf",
    type: "workspace_file",
    label: "report file.pdf",
    root: "media",
    relative_path: "report file.pdf",
    description: "media/report file.pdf",
  },
];

function ControlledTokenEditor() {
  const [selected, setSelected] = useState<SkillMentionItem[]>([]);
  const [value, setValue] = useState("");
  return (
    <SkillTokenEditor
      aria-label="消息"
      value={value}
      skillMentions={{
        items,
        selected,
        onChange: setSelected,
        onOpen: () => undefined,
      }}
      onValueChange={setValue}
    />
  );
}

function SelectedTokenEditor() {
  const [selected, setSelected] = useState<SkillMentionItem[]>([items[1]]);
  const [value, setValue] = useState("@docs/search ");
  return (
    <SkillTokenEditor
      aria-label="消息"
      value={value}
      skillMentions={{
        items,
        selected,
        onChange: setSelected,
        onOpen: () => undefined,
      }}
      onValueChange={setValue}
    />
  );
}

function ContainerAnchoredTokenEditor({
  placement = "top",
}: {
  placement?: "top" | "bottom";
}) {
  const [menuContainer, setMenuContainer] = useState<HTMLDivElement | null>(
    null,
  );
  return (
    <div data-testid="menu-container" ref={setMenuContainer}>
      <SkillTokenEditor
        aria-label="消息"
        mentionMenuContainer={menuContainer}
        mentionMenuPlacement={placement}
        value="@"
        skillMentions={{
          items,
          selected: [],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />
    </div>
  );
}

describe("SkillTokenEditor", () => {
  afterEach(cleanup);
  it("renders typed references as atomic tokens", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="请看 @report.pdf "
        skillMentions={{
          items,
          selected: [items[2]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const token = screen.getByText("@report.pdf");
    expect(token).toHaveAttribute("contenteditable", "false");
    expect(token).toHaveAttribute("data-reference-type", "workspace_file");
  });

  it("renders a scenario capability marker as an atomic prefix and reports its removal", () => {
    const onFixedTokenRemove = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        fixedToken={{ text: "@信息提取", onRemove: onFixedTokenRemove }}
        value="请总结附件"
        skillMentions={{
          items,
          selected: [],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "消息" });
    const marker = screen.getByText("@信息提取");
    expect(marker).toHaveAttribute("contenteditable", "false");
    expect(marker).toHaveAttribute("data-scenario-token", "true");
    expect(marker).toHaveStyle({
      background: "#EEF4FF",
      color: "#2957DC",
    });

    marker.remove();
    fireEvent.input(editor);

    expect(onFixedTokenRemove).toHaveBeenCalledOnce();
  });
  it("removes the scenario capability marker with Backspace", () => {
    const onFixedTokenRemove = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        fixedToken={{ text: "@信息提取", onRemove: onFixedTokenRemove }}
        value="草稿"
        skillMentions={{
          items,
          selected: [],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "消息" });
    const range = document.createRange();
    range.setStart(editor.childNodes[1], 0);
    range.collapse(true);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    fireEvent.keyDown(editor, { key: "Backspace" });

    expect(onFixedTokenRemove).toHaveBeenCalledOnce();
  });
  it("renders one distinguishable atomic token for every reference type", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser @docs/search @report.pdf "
        skillMentions={{
          items,
          selected: [items[0], items[1], items[2]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const tokens = document.querySelectorAll("[data-skill-token=true]");
    expect(tokens).toHaveLength(3);
    expect(tokens[0]).toHaveAttribute("data-reference-type", "skill");
    expect(tokens[1]).toHaveAttribute("data-reference-type", "mcp_tool");
    expect(tokens[2]).toHaveAttribute("data-reference-type", "workspace_file");
    expect(
      tokens[0].querySelector("svg[data-icon=thunderbolt]"),
    ).not.toBeNull();
    expect(tokens[1].querySelector("svg[data-icon=api]")).not.toBeNull();
    expect(tokens[2].querySelector("svg[data-icon=file]")).not.toBeNull();
  });
  it("uses a named icon instead of a dot before an MCP token", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@docs/search "
        skillMentions={{
          items,
          selected: [items[1]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("img", { name: "MCP 工具" })).toBeInTheDocument();
  });
  it("keeps a token icon out of editor text while ordinary text is entered", () => {
    render(<SelectedTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    expect(editor.textContent).toBe("@docs/search ");

    editor.append(document.createTextNode("后续文本"));
    fireEvent.input(editor);

    expect(editor).toHaveTextContent("@docs/search 后续文本");
    expect(document.querySelectorAll("[data-skill-token=true]")).toHaveLength(
      1,
    );
  });
  it("keeps a file name containing spaces as one atomic token", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="请看 @report file.pdf "
        skillMentions={{
          items,
          selected: [items[3]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    expect(screen.getByText("@report file.pdf")).toHaveAttribute(
      "contenteditable",
      "false",
    );
  });
  it("renders tokens in text order when a later selection was inserted before an earlier one", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@report.pdf @browser "
        skillMentions={{
          items,
          selected: [items[0], items[2]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    expect(document.querySelectorAll("[data-skill-token=true]")).toHaveLength(
      2,
    );
  });
  it("removes a typed token with Backspace", () => {
    const onChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser "
        skillMentions={{
          items,
          selected: [items[0]],
          onChange,
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "消息" });
    const range = document.createRange();
    range.setStart(editor.lastChild!, 0);
    range.collapse(true);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.keyDown(editor, { key: "Backspace" });
    expect(onChange).toHaveBeenCalledWith([]);
  });
  it("keeps keyboard selection and focus after Enter", () => {
    render(<ControlledTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.focus();
    editor.textContent = "@";
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.input(editor);
    expect(editor).toHaveAttribute("aria-controls", "context-reference-menu");
    expect(editor).toHaveAttribute("aria-haspopup", "listbox");
    expect(editor).toHaveAttribute(
      "aria-activedescendant",
      "context-reference-option-skill%3Abrowser",
    );
    fireEvent.keyDown(editor, { key: "Enter" });
    expect(document.activeElement).toBe(editor);
    expect(screen.getByText("@browser")).toBeInTheDocument();
  });
  it("positions the context-reference menu 8px above the editor", () => {
    render(<ControlledTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.textContent = "@";
    fireEvent.input(editor);

    expect(document.getElementById("context-reference-menu")).toHaveStyle({
      bottom: "calc(100% + 8px)",
    });
  });
  it("positions the context-reference menu 8px below the editor when requested", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        mentionMenuPlacement="bottom"
        value="@"
        skillMentions={{
          items,
          selected: [],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );

    fireEvent.input(screen.getByRole("textbox", { name: "消息" }));

    expect(document.getElementById("context-reference-menu")).toHaveStyle({
      top: "calc(100% + 8px)",
    });
    expect(document.getElementById("context-reference-menu")).not.toHaveStyle({
      bottom: "calc(100% + 8px)",
    });
  });
  it("anchors the menu to the supplied full input card", () => {
    render(<ContainerAnchoredTokenEditor placement="bottom" />);

    fireEvent.input(screen.getByRole("textbox", { name: "消息" }));

    const container = screen.getByTestId("menu-container");
    const menu = document.getElementById("context-reference-menu");

    expect(menu?.parentElement).toBe(container);
    expect(menu).toHaveStyle({ top: "calc(100% + 8px)" });
  });
  it("restores editor focus after a clicked option took focus", () => {
    render(<ControlledTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.focus();
    editor.textContent = "@";
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.input(editor);
    const option = screen.getByRole("option", { name: /^browser/ });
    option.focus();
    fireEvent.click(option);

    expect(document.activeElement).toBe(editor);
  });
});
