import { FormLabel } from "../../components/primitives/FormLabel";

export function FormLabelPreview() {
  return <section aria-labelledby="component-page-title">
    <section className="components-preview-variant" aria-labelledby="form-label-default-title">
      <h2 data-preview-heading tabIndex={-1} id="form-label-default-title">Default</h2>
      <FormLabel>Description</FormLabel>
    </section>
    <section className="components-preview-variant" aria-labelledby="form-label-required-title">
      <h2 data-preview-heading tabIndex={-1} id="form-label-required-title">Required</h2>
      <FormLabel required>Description</FormLabel>
    </section>
    <section className="components-preview-variant" aria-labelledby="form-label-field-title">
      <h2 data-preview-heading tabIndex={-1} id="form-label-field-title">Field</h2>
      <div className="components-preview-example-row"><FormLabel variant="field">Endpoint</FormLabel><FormLabel variant="field" required>Endpoint</FormLabel></div>
    </section>
    </section>;
}
