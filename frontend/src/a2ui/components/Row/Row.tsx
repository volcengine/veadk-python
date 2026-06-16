import type { ComponentRendererProps } from "../../registry";
import { alignToCss, justifyToCss } from "../../layout";

export function Row({ node, ctx }: ComponentRendererProps) {
  const children = (node.children as string[]) ?? [];
  return (
    <div
      className="a2ui-row"
      data-a2ui-id={node.id}
      data-a2ui-component={node.component}
      style={{
        display: "flex",
        flexDirection: "row",
        justifyContent: justifyToCss(node.justify),
        alignItems: alignToCss(node.align ?? "center"),
      }}
    >
      {children.map((id) => ctx.render(id))}
    </div>
  );
}
