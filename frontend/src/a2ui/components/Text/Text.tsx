import type { ComponentRendererProps } from "../../registry";
import type { DynamicValue } from "../../types";

const HEADINGS = new Set(["h1", "h2", "h3", "h4", "h5"]);

export function Text({ node, ctx }: ComponentRendererProps) {
  const variant = (node.variant as string) ?? "body";
  const text = ctx.resolveString(node.text as DynamicValue);
  const Tag = (HEADINGS.has(variant) ? variant : "p") as keyof JSX.IntrinsicElements;
  return (
    <Tag
      className={`a2ui-text a2ui-text--${variant}`}
      data-a2ui-id={node.id}
      data-a2ui-component={node.component}
    >
      {text}
    </Tag>
  );
}
