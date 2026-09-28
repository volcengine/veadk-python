import { BasicNode } from "../../components/nodes/BasicNode";
import "./BasicNodePreview.css";

export function BasicNodePreview() {
  const id = "preview-basic-node";
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 data-preview-heading tabIndex={-1} id={`${id}-title`} className="component-preview-title">Default</h2>
      <div className="basic-node-preview-example"><BasicNode /></div>
    </section>
  );
}
