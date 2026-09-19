import { Divider } from "../../components/primitives/Divider";

export function DividerPreview() {
  return <section aria-labelledby="divider-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="divider-preview-title" className="component-preview-title">Default</h2>
    <Divider />
    </section>;
}
