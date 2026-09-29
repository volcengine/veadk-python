import { ButtonPreview } from "./ButtonPreview";
import { GlassIconButtonPreview } from "./GlassIconButtonPreview";

export function ButtonsPreview() {
  return <div style={{ display: "grid", gap: 40, minWidth: 0 }}>
    <ButtonPreview />
    <GlassIconButtonPreview />
  </div>;
}
