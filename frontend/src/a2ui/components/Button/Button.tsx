import type { ComponentRendererProps } from "../../registry";
import type { A2uiAction } from "../../types";

export function Button({ node, ctx }: ComponentRendererProps) {
  const variant = (node.variant as string) ?? "default";
  return (
    <button
      type="button"
      className={`a2ui-button a2ui-button--${variant}`}
      onClick={() => ctx.dispatchAction(node.action as A2uiAction | undefined, node)}
    >
      {ctx.render(node.child as string)}
    </button>
  );
}
