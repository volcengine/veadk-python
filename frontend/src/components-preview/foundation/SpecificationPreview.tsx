import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "../../components/primitives/Button";
import specification from "./Specification.md?raw";
import "./SpecificationPreview.css";

const headingIds: Record<string, string> = {
  适用范围: "spec-scope",
  文案分隔: "spec-text-separators",
  复用组件: "spec-components",
  复用布局: "spec-layouts",
  保留组件完整行为: "spec-behavior",
  字体: "spec-typography",
  动效: "spec-motion",
  产品文案: "spec-product-copy",
  视觉与光学对齐: "spec-alignment",
  执行与检查: "spec-checks",
};

export function SpecificationPreview() {
  const [copyStatus, setCopyStatus] = useState("");

  async function copySpecification() {
    try {
      await navigator.clipboard.writeText(specification);
      setCopyStatus("已复制，可直接提供给 AI");
    } catch {
      setCopyStatus("复制失败，请重试或手动选择下方文字");
    }
  }

  return <article className="specification-preview" aria-labelledby="component-page-title">
    <div className="specification-preview__actions">
      <Button variant="secondary" onClick={copySpecification}>复制规范</Button>
      <span role="status" aria-live="polite">{copyStatus}</span>
    </div>
    <ReactMarkdown components={{
      h1: () => null,
      h2: ({ children }) => <h2 id={headingIds[String(children)]} data-preview-heading tabIndex={-1}>{children}</h2>,
    }}>{specification}</ReactMarkdown>
  </article>;
}
