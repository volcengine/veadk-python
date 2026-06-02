import type { ComponentRendererProps } from "../../registry";

export function Card({ node, ctx }: ComponentRendererProps) {
  return <div className="a2ui-card">{ctx.render(node.child as string)}</div>;
}
