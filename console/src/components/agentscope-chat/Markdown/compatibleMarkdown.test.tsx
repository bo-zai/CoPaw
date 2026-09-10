import XMarkdown from "@ant-design/x-markdown";
import { render } from "@testing-library/react";
import { marked } from "marked";
import { describe, expect, it, vi } from "vitest";

import {
  createTableScopedHtmlRenderer,
  renderCompatibleMarkdownHtml,
} from "./compatibleMarkdownHtml";

describe("compatible Markdown fallback", () => {
  it("renders GFM tables instead of raw pipe text", () => {
    const html = renderCompatibleMarkdownHtml(
      "| A | B |\n| --- | --- |\n| 1 | 2 |",
      false,
    );

    expect(html).toContain("<table>");
    expect(html).toContain("<td>1</td>");
    expect(html).not.toContain("| --- | --- |");
  });

  it("escapes HTML when allowHtml is false", () => {
    const html = renderCompatibleMarkdownHtml(
      "<script>alert(1)</script>",
      false,
    );

    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });

  it.each(["<br>", "<br/>", "<br />"])(
    "allows the safe line break tag %s inside GFM table cells",
    (lineBreak) => {
      const html = renderCompatibleMarkdownHtml(
        `| A | B |\n| --- | --- |\n| first${lineBreak}second | value |`,
        false,
      );

      expect(html).toContain("<td>first<br>second</td>");
      expect(html).not.toContain("&lt;br");
    },
  );

  it("keeps line break tags escaped outside GFM table cells", () => {
    const html = renderCompatibleMarkdownHtml(
      "某个<br>环节<br>可能需要<br>处理<br>。",
      false,
    );

    expect(html).toContain(
      "某个&lt;br&gt;环节&lt;br&gt;可能需要&lt;br&gt;处理&lt;br&gt;。",
    );
    expect(html).not.toContain("某个<br>环节");
  });

  it("keeps unsafe HTML escaped inside and outside table cells", () => {
    const html = renderCompatibleMarkdownHtml(
      "safe<br><img src=x onerror=alert(1)>\n\n| A |\n| --- |\n| first<br onclick=alert(1)>second |",
      false,
    );

    expect(html).toContain("safe&lt;br&gt;");
    expect(html).toContain("&lt;br onclick=alert(1)&gt;");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).not.toContain("<img");
  });

  it("preserves normal inline Markdown parsing inside table cells", () => {
    const html = renderCompatibleMarkdownHtml(
      "| Header<br>next | Value |\n| :---: | --- |\n| **bold**<br>`code` | [link](https://example.com) |",
      false,
    );

    expect(html).toContain('<th align="center">Header<br>next</th>');
    expect(html).toContain(
      '<td align="center"><strong>bold</strong><br><code>code</code></td>',
    );
    expect(html).toContain('<a href="https://example.com">link</a>');
  });

  it("does not interpret line break tags inside code as HTML", () => {
    const html = renderCompatibleMarkdownHtml(
      "| A |\n| --- |\n| `<br>` |",
      false,
    );

    expect(html).toContain("<td><code>&lt;br&gt;</code></td>");
  });

  it("keeps explicit allowHtml behavior unchanged", () => {
    const html = renderCompatibleMarkdownHtml("first<br>second", true);

    expect(html).toContain("first<br>second");
  });

  it("uses the caller escape policy outside table cells", () => {
    const escapeHtmlToken = vi.fn((value: string) => `[escaped:${value}]`);
    const renderer = new marked.Renderer();
    Object.assign(renderer, createTableScopedHtmlRenderer(escapeHtmlToken));

    const html = marked.parse(
      "outside<br>text\n\n| A |\n| --- |\n| inside<br>cell |",
      { renderer },
    ) as string;

    expect(html).toContain("outside[escaped:<br>]text");
    expect(html).toContain("<td>inside<br>cell</td>");
    expect(escapeHtmlToken).toHaveBeenCalledTimes(1);
  });

  it("matches the default Marked output for normal Markdown", () => {
    const content = [
      "# Heading",
      "",
      "Paragraph with **bold**, *emphasis*, `code`, and [link](https://example.com).",
      "",
      "> Quote",
      "",
      "- first",
      "- second",
      "",
      "| Name | Value |",
      "| :---: | ---: |",
      "| **alpha** | `1` |",
    ].join("\n");
    const renderer = new marked.Renderer();
    Object.assign(
      renderer,
      createTableScopedHtmlRenderer((value) =>
        value.replace(/</g, "&lt;").replace(/>/g, "&gt;"),
      ),
    );

    expect(marked.parse(content, { renderer })).toBe(marked.parse(content));
  });

  it("restores the non-table escape policy after cell rendering fails", () => {
    const escapeHtmlToken = vi.fn((value: string) => {
      if (value.startsWith("<img")) throw new Error("test escape failure");
      return `[escaped:${value}]`;
    });
    const renderer = new marked.Renderer();
    Object.assign(renderer, createTableScopedHtmlRenderer(escapeHtmlToken));

    expect(() =>
      marked.parse("| A |\n| --- |\n| <img src=x> |", { renderer }),
    ).toThrow("test escape failure");

    expect(marked.parse("outside<br>text", { renderer })).toContain(
      "outside[escaped:<br>]text",
    );
  });

  it("scopes line breaks when used through XMarkdown config", () => {
    const { container } = render(
      <XMarkdown
        content={"outside<br>text\n\n| A |\n| --- |\n| inside<br>cell |"}
        config={{
          renderer: createTableScopedHtmlRenderer((value) =>
            value.replace(/</g, "&lt;").replace(/>/g, "&gt;"),
          ),
        }}
      />,
    );

    const paragraph = container.querySelector("p");
    const tableCell = container.querySelector("td");
    expect(paragraph?.textContent).toBe("outside<br>text");
    expect(paragraph?.querySelector("br")).toBeNull();
    expect(tableCell?.textContent).toBe("insidecell");
    expect(tableCell?.querySelectorAll("br")).toHaveLength(1);
  });
});
