import { useId } from "react";
import { Label, LabelAddIcon } from "../../components/primitives/Label";
import "./LabelPreview.css";

export function LabelPreview() {
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="component-preview-title">Label</h2>
      <div className="label-preview-examples">
        <section aria-labelledby={`${id}-default-title`}>
          <h3 id={`${id}-default-title`}>Label</h3>
          <Label className="label-preview-default">no-code-frontend-builder</Label>
        </section>
        <section aria-labelledby={`${id}-icon-title`}>
          <h3 id={`${id}-icon-title`}>Label with icon</h3>
          <Label className="label-preview-with-icon" startIcon={<LabelAddIcon />}>Add</Label>
        </section>
        <section aria-labelledby={`${id}-status-title`}>
          <h3 id={`${id}-status-title`}>Status label</h3>
          <Label className="label-preview-status" variant="status">Control B</Label>
        </section>
      </div>
    </section>
  );
}
