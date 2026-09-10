import { useId, useState, type HTMLAttributes } from "react";
import copyIcon from "./assets/copy.svg";
import "./CodeBlock.css";

export interface CodeBlockToken { text: string; color?: string }
export interface CodeBlockProps extends Omit<HTMLAttributes<HTMLElement>, "title" | "children"> {
  title?: string;
  lines: readonly (string | readonly CodeBlockToken[])[];
}

export function CodeBlock({ title = "Request example", lines, className = "", ...props }: CodeBlockProps) {
  const titleId = useId();
  const [status, setStatus] = useState("");
  async function copy() {
    const text = lines.map(line => typeof line === "string" ? line : line.map(token => token.text).join("")).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setStatus("Copied");
    } catch {
      setStatus("Unable to copy, select the code to copy manually");
    }
  }
  return <section {...props} aria-labelledby={titleId} className={`studio-code-block ${className}`.trim()}>
    <header className="studio-code-block__header">
      <h3 id={titleId}>{title}</h3>
      <button type="button" aria-label="Copy code" title={status || "Copy code"} onClick={copy}><img src={copyIcon} alt="" /></button>
    </header>
    <div className="studio-code-block__viewport" tabIndex={0} role="region" aria-label={title}>
      <pre><code>{lines.map((line, index) => <span className="studio-code-block__line" key={index}>
        <span className="studio-code-block__number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
        <span className="studio-code-block__text">{typeof line === "string" ? line : line.map((token, tokenIndex) => <span key={tokenIndex} style={{ color: token.color }}>{token.text}</span>)}{"\n"}</span>
      </span>)}</code></pre>
    </div>
    <span className="studio-code-block__status" role="status">{status}</span>
  </section>;
}
