import { ComponentApi } from "../api/ComponentApi";
import { FormLabel } from "../../components/primitives/FormLabel";

import { FormLabelRow } from "../../components/composites/FormLabelRow";

export function FormLabelPreview() {
  return <section aria-labelledby="form-label-preview-title">
    <h2 id="form-label-preview-title" className="component-preview-title">Form label</h2>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 32 }}>
      <FormLabel>Description</FormLabel>
      <FormLabel required>Description</FormLabel>
      <FormLabel variant="field">Endpoint</FormLabel>
      <FormLabel variant="field" required>Endpoint</FormLabel>
    </div>
    <div style={{ marginTop: 32 }}>
      <FormLabelRow label="Knowledge base" />
    </div>
  <ComponentApi names={["FormLabel", "FormLabelRow"]} />
    </section>;
}
