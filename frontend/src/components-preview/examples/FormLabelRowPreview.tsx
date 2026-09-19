import { FormLabelRow } from "../../components/composites/FormLabelRow";

export function FormLabelRowPreview() {
  return <section aria-labelledby="form-label-row-title">
    <h2 data-preview-heading tabIndex={-1} id="form-label-row-title" className="component-preview-title">Default</h2>
    <FormLabelRow label="Knowledge base" />
  </section>;
}
