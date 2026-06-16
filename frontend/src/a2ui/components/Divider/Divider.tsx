import type { ComponentRendererProps } from "../../registry";

export function Divider({ node }: ComponentRendererProps) {
  const vertical = (node.axis as string) === "vertical";
  return (
    <div
      className={`a2ui-divider ${vertical ? "a2ui-divider--v" : "a2ui-divider--h"}`}
      data-a2ui-id={node.id}
      data-a2ui-component={node.component}
    />
  );
}
