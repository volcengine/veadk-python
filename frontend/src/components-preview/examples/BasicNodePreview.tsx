import { useId } from "react";
import { BasicNode } from "../../components/nodes/BasicNode";
import "./BasicNodePreview.css";

export function BasicNodePreview() {
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="component-preview-title">Basic node</h2>
      <div className="basic-node-preview-example"><BasicNode /></div>
    </section>
  );
}
