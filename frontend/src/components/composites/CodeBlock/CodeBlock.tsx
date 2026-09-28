import { useId, useMemo, useState, type HTMLAttributes, type ReactNode } from "react";
import { highlightCode } from "./highlightCode";
import { Button } from "../../primitives/Button";
import { ScrollArea, type ScrollAreaProps } from "../../primitives/ScrollArea";
import "./CodeBlock.css";

export interface CodeBlockToken { text: string; color?: string }
export interface CodeBlockProps extends Omit<HTMLAttributes<HTMLElement>, "title" | "children"> {
  title?: string;
  lines: readonly (string | readonly CodeBlockToken[])[];
  /** 纯文本行的语法语言，默认 auto 自动识别；log 高亮日志，plaintext 关闭高亮，手动颜色 token 保留 */
  language?: string;
  /** 长行按容器宽度折行，续行沿用同一行号 */
  wordWrap?: boolean;
  /** 是否显示行号，默认 true；false 保留代码字体及原始缩进 */
  showLineNumbers?: boolean;
  /** 复制按钮右侧的操作区域 */
  actions?: ReactNode;
  /** 自定义代码区域，例如复用代码编辑器 */
  children?: ReactNode;
  /** 仅代码正文复用 ScrollArea，标题及操作栏保持固定 */
  scrollAreaProps?: Omit<ScrollAreaProps, "children">;
}

function CopyIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M10.3333 6.5C10.3333 6.03976 9.96025 5.66667 9.5 5.66667H3.83333C3.3731 5.66667 3 6.03976 3 6.5V12.1667C3 12.6269 3.37309 13 3.83333 13H9.5C9.96026 13 10.3333 12.6269 10.3333 12.1667V6.5ZM11.3333 10.3398H12.1667C12.6269 10.3398 13 9.96677 13 9.50651V3.83333C13 3.37309 12.6269 3 12.1667 3H6.5C6.03976 3 5.66667 3.3731 5.66667 3.83333V4.66667H9.5C10.5125 4.66667 11.3333 5.48748 11.3333 6.5V10.3398ZM14 9.50651C14 10.5191 13.1792 11.3398 12.1667 11.3398H11.3333V12.1667C11.3333 13.1792 10.5125 14 9.5 14H3.83333C2.82082 14 2 13.1792 2 12.1667V6.5C2 5.48748 2.82081 4.66667 3.83333 4.66667H4.66667V3.83333C4.66667 2.82081 5.48748 2 6.5 2H12.1667C13.1792 2 14 2.82082 14 3.83333V9.50651Z" fill="currentColor" />
  </svg>;
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

export function CodeBlock({ title = "Request example", lines, language = "auto", wordWrap = false, showLineNumbers = true, actions, children, scrollAreaProps, className = "", ...props }: CodeBlockProps) {
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
      {showLineNumbers && <span className="studio-code-block__number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>}
      <span className="studio-code-block__text">{typeof line === "string"
        ? highlighted[index]?.map((token, tokenIndex) => <span key={tokenIndex} className={token.color ? `studio-code-block__token--${token.color}` : undefined}>{token.text}</span>)
        : line.map((token, tokenIndex) => <span key={tokenIndex} style={{ color: token.color }}>{token.text}</span>)}{"\n"}</span>
    </span>)}</code></pre>
  </div>;
  return <section {...props} aria-labelledby={titleId} data-word-wrap={wordWrap || undefined} data-line-numbers={showLineNumbers} className={`studio-code-block ${className}`.trim()}>
    <header className="studio-code-block__header">
      <h3 id={titleId}>{title}</h3>
      <div className="studio-code-block__actions">
        <Button variant="ghost" iconOnly aria-label="Copy code" title={status || "Copy code"} onClick={copy} startIcon={<CopyIcon />} />
        {actions}
      </div>
    </header>
    {scrollAreaProps ? <ScrollArea {...scrollAreaProps}>{body}</ScrollArea> : body}
    <span className="studio-code-block__status" role="status">{status}</span>
  </section>;
}
