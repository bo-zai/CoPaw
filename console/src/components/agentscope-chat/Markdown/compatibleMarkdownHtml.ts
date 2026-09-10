/**
 * 旧浏览器兜底渲染只处理 Markdown 到安全 HTML 的转换，不绑定 React 上下文。
 */
import DOMPurify from "dompurify";
import { marked, type RendererObject } from "marked";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function createTableScopedHtmlRenderer(
  escapeHtmlToken: (value: string) => string,
): RendererObject {
  let tableCellDepth = 0;

  return {
    html(token) {
      const value = token.text || token.raw || "";
      return tableCellDepth > 0 && /^<br\s*\/?>$/i.test(value)
        ? "<br>"
        : escapeHtmlToken(value);
    },
    tablecell(token) {
      tableCellDepth += 1;
      try {
        const content = this.parser.parseInline(token.tokens);
        const type = token.header ? "th" : "td";
        const tag = token.align
          ? `<${type} align="${token.align}">`
          : `<${type}>`;
        return `${tag}${content}</${type}>\n`;
      } finally {
        tableCellDepth -= 1;
      }
    },
  };
}

export function renderCompatibleMarkdownHtml(
  content: string,
  allowHtml: boolean,
): string {
  const renderer = new marked.Renderer();

  if (!allowHtml) {
    Object.assign(renderer, createTableScopedHtmlRenderer(escapeHtml));
  }

  const html = marked.parse(content, {
    async: false,
    breaks: false,
    gfm: true,
    renderer,
  }) as string;

  return DOMPurify.sanitize(html, {
    ADD_TAGS: ["custom-cursor", "citation"],
  });
}
