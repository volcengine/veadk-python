import type { ComponentRendererProps } from "../../registry";
import { alignToCss, justifyToCss } from "../../layout";

export function Row({ node, ctx }: ComponentRendererProps) {
  const children = (node.children as string[]) ?? [];
  return (
    <div
      className="a2ui-row"
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
