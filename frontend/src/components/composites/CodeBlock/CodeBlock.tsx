import { useId, useMemo, useState, type HTMLAttributes, type ReactNode } from "react";
import { highlightCode } from "./highlightCode";
import { ScrollArea, type ScrollAreaProps } from "../../primitives/ScrollArea";
import copyIcon from "./assets/copy.svg";
import "./CodeBlock.css";

export interface CodeBlockToken { text: string; color?: string }
export interface CodeBlockProps extends Omit<HTMLAttributes<HTMLElement>, "title" | "children"> {
  title?: string;
  lines: readonly (string | readonly CodeBlockToken[])[];
  /** 纯文本行的语法语言，默认 auto 自动识别；plaintext 关闭高亮，手动颜色 token 保留 */
  language?: string;
  /** 长行按容器宽度折行，续行沿用同一行号 */
  wordWrap?: boolean;
  /** 复制按钮右侧的操作区域 */
  actions?: ReactNode;
  /** 自定义代码区域，例如复用代码编辑器 */
  children?: ReactNode;
  /** 仅代码正文复用 ScrollArea，标题及操作栏保持固定 */
  scrollAreaProps?: Omit<ScrollAreaProps, "children">;
}

function physicalLines(lines: CodeBlockProps["lines"]): CodeBlockProps["lines"] {
  const result: (string | CodeBlockToken[])[] = [];
  for (const line of lines) {
    if (typeof line === "string") {
      for (const part of line.split("\n")) result.push(part);
      continue;
    }
    const parts: CodeBlockToken[][] = [[]];
    for (const token of line) {
      token.text.split("\n").forEach((text, index) => {
        if (index > 0) parts.push([]);
        if (text) parts[parts.length - 1].push({ ...token, text });
      });
    }
    for (const part of parts) {
      const last = part[part.length - 1];
      if (last?.text.endsWith("\r")) last.text = last.text.slice(0, -1);
      result.push(part);
    }
  }
  return result;
}

export function CodeBlock({ title = "Request example", lines, language = "auto", wordWrap = false, actions, children, scrollAreaProps, className = "", ...props }: CodeBlockProps) {
  const titleId = useId();
  const [status, setStatus] = useState("");
  const text = useMemo(() => lines.map(line => typeof line === "string" ? line : line.map(token => token.text).join("")).join("\n"), [lines]);
  const displayLines = useMemo(() => physicalLines(lines), [lines]);
  const hasPlainLines = !children && lines.some(line => typeof line === "string");
  const highlighted = useMemo(() => hasPlainLines ? highlightCode(text, language) : [], [text, language, hasPlainLines]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("Copied");
    } catch {
      setStatus("Unable to copy, select the code to copy manually");
    }
  }
  const body = children ?? <div className="studio-code-block__viewport" tabIndex={0} role="region" aria-label={title}>
    <pre><code>{displayLines.map((line, index) => <span className="studio-code-block__line" key={index}>
      <span className="studio-code-block__number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
      <span className="studio-code-block__text">{typeof line === "string"
        ? highlighted[index]?.map((token, tokenIndex) => <span key={tokenIndex} className={token.color ? `studio-code-block__token--${token.color}` : undefined}>{token.text}</span>)
        : line.map((token, tokenIndex) => <span key={tokenIndex} style={{ color: token.color }}>{token.text}</span>)}{"\n"}</span>
    </span>)}</code></pre>
  </div>;
  return <section {...props} aria-labelledby={titleId} data-word-wrap={wordWrap || undefined} className={`studio-code-block ${className}`.trim()}>
    <header className="studio-code-block__header">
      <h3 id={titleId}>{title}</h3>
      <div className="studio-code-block__actions">
        <button type="button" aria-label="Copy code" title={status || "Copy code"} onClick={copy}><img src={copyIcon} alt="" /></button>
        {actions}
      </div>
    </header>
    {scrollAreaProps ? <ScrollArea {...scrollAreaProps}>{body}</ScrollArea> : body}
    <span className="studio-code-block__status" role="status">{status}</span>
  </section>;
}
