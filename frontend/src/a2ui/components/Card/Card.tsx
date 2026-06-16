import type { ComponentRendererProps } from "../../registry";

export function Card({ node, ctx }: ComponentRendererProps) {
  return (
    <div
      className="a2ui-card"
      data-a2ui-id={node.id}
      data-a2ui-component={node.component}
    >
      {ctx.render(node.child as string)}
    </div>
  );
}
